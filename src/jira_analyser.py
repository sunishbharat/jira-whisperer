import time
import logging
import requests
import json
from datetime import datetime
from src.colors import C
from src import config
from src.jql_reference import JQL_REFERENCE

logger = logging.getLogger(__name__)

# ===========================================================
# Rate Limiters
# ===========================================================

class RateLimiter:
    """Ensures a minimum interval between calls."""
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last_call = 0.0

    def throttle(self):
        elapsed = time.monotonic() - self._last_call
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

jira_limiter = RateLimiter(min_interval=config.JIRA_MIN_INTERVAL)
llm_limiter  = RateLimiter(min_interval=config.LLM_MIN_INTERVAL)


# ===========================================================
# LLM Abstraction
# Dispatches to Anthropic or HuggingFace based on config.
# ===========================================================

# Per-run token accumulator — reset at the start of each ask()
_token_usage: list[dict] = []


def call_llm(prompt: str, max_tokens: int, call_label: str = "llm") -> str:
    llm_limiter.throttle()
    if config.LLM_PROVIDER == "huggingface":
        res = requests.post(
            config.HF_API_URL,
            headers=config.HF_HEADERS,
            json={
                "model"     : config.HF_MODEL,
                "messages"  : [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
        ).json()
        if "choices" not in res:
            error = res.get("error", res)
            logger.error("HuggingFace API error: %s", error)
            raise RuntimeError(f"HuggingFace API error: {error}")
        usage = res.get("usage", {})
        _token_usage.append({
            "call"  : call_label,
            "input" : usage.get("prompt_tokens", 0),
            "output": usage.get("completion_tokens", 0),
        })
        return res["choices"][0]["message"]["content"]
    else:
        res = requests.post(
            config.ANTHROPIC_API_URL,
            headers=config.ANTHROPIC_HEADERS,
            json={
                "model"     : config.ANTHROPIC_MODEL,
                "max_tokens": max_tokens,
                "messages"  : [{"role": "user", "content": prompt}],
            },
        ).json()
        if "content" not in res:
            error = res.get("error", res)
            logger.error("Anthropic API error: %s", error)
            raise RuntimeError(f"Anthropic API error: {error}")
        usage = res.get("usage", {})
        _token_usage.append({
            "call"  : call_label,
            "input" : usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
        })
        return res["content"][0]["text"]


def get_token_summary() -> dict:
    """Return aggregated token counts for the current run."""
    total_in  = sum(u["input"]  for u in _token_usage)
    total_out = sum(u["output"] for u in _token_usage)
    return {
        "calls"      : list(_token_usage),
        "total_input": total_in,
        "total_output": total_out,
        "total"      : total_in + total_out,
    }

# ===========================================================
# Step 1: NLP -> API Plan
# LLM reads the question and decides what API call to make.
# ===========================================================

def generate_api_plan(user_question, projects: dict, fields: dict, _unused: dict = {}):
    today = datetime.now().strftime("%Y-%m-%d")

    projects_list = "\n".join(f"  {k}: {v}" for k, v in projects.items())
    fields_list   = "\n".join(f"  {k}: {v}" for k, v in fields.items())

    default_project_line = (
        f"Default project: {config.JIRA_DEFAULT_PROJECT} — use this in JQL when the user does not mention a specific project."
        if config.JIRA_DEFAULT_PROJECT else ""
    )

    prompt = f"""
You are a Jira API expert on Jira Server v9 (REST API v2).
Today's date is {today}.
{default_project_line}

Convert this user question into a Jira API call plan.
Return ONLY valid JSON, no explanation, no markdown.

User question: "{user_question}"

Available Jira project (key: name):
{projects_list}

Available fields to choose from (id: name) — select only what the question needs:
{fields_list}

Return this structure:
{{
  "endpoint"   : "/rest/api/2/search",
  "method"     : "GET",
  "params"     : {{
      "jql"       : "project = PROJ AND ...",
      "fields"    : "summary,status,created,resolutiondate,issuetype",
      "maxResults": 50,
      "expand"    : "changelog"
  }},
  "needs_changelog": true,
  "post_processing": "what to compute after fetching — e.g. cycle days, state breakdown",
  "explanation": "what this query does in plain english"
}}

CRITICAL JQL quoting rule — always follow:
- Any value containing a space MUST be wrapped in double quotes in the JQL string
- CORRECT:   status in (Open, "In Progress", "In Review", "Patch Available")
- INCORRECT: status in (Open, In Progress, In Review, Patch Available)
- CORRECT:   issuetype in (Bug, Story, Task, Epic, Improvement, "New Feature", Sub-task)
- INCORRECT: issuetype in (Bug, Story, Task, Epic, Improvement, New Feature, Sub-task)
- Do NOT filter by issuetype unless the user explicitly asks for a specific type (e.g. "show bugs", "list stories")

CRITICAL — GROUP BY and LIMIT do not exist in JQL — never generate them:
- "N issues per group" pattern → fetch a large set ordered by the group field, slice in post_processing
  CORRECT example for "2 issues per priority":
    JQL: project = KAFKA AND priority in (Blocker, Critical, Major, Minor, Trivial) ORDER BY priority ASC
    maxResults: 50
    post_processing: group issues by priority, take first 2 from each group
- "top N overall" pattern → fetch 50-100, sort and slice in post_processing
  CORRECT example for "top 5 oldest issues":
    JQL: project = KAFKA ORDER BY created ASC
    maxResults: 50
    post_processing: take first 5
- "sort by computed duration" (e.g. longest to resolve, most days in status) → ORDER BY cannot use expressions
  CORRECT example for "10 issues that took longest to resolve":
    JQL: project = KAFKA AND resolutiondate is not EMPTY ORDER BY created ASC
    maxResults: 100
    post_processing: compute (resolutiondate - created) days per issue, sort DESC, take top 10
  NEVER do: ORDER BY resolutiondate - created DESC  ← invalid, expressions not allowed in ORDER BY

Field selection rules — strictly follow these:
- Always include at minimum: summary, status, priority, assignee, created
- Add extra fields only when the question needs them (e.g. resolutiondate for cycle-time, issuetype for type breakdowns)
- Use field IDs (e.g. "customfield_10016") not display names for custom fields
- Do NOT include all fields — be selective
- Use only project keys from the available projects list above

{JQL_REFERENCE}
"""
    raw   = call_llm(prompt, max_tokens=1000, call_label="generate_api_plan")
    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)

# ===========================================================
# Jira Metadata Helpers
# ===========================================================

def get_all_projects():

    jira_limiter.throttle()
    # Get all projects
    res = requests.get(
        f"{config.JIRA_BASE_URL}/rest/api/2/project",
        auth=config.JIRA_AUTH, headers=config.JIRA_HEADERS
    ).json()

    
    project_dict ={}
    logger.info(f"Total projects: {len(res)}\n")
    for p in res:
        project_dict[p['key']] = p['name'] 
        logger.debug(f"  {p['key']:<15} {p['name']}")
    
    return project_dict


def get_all_fields():

    jira_limiter.throttle()
    # Get all projects
    fields = requests.get(
        f"{config.JIRA_BASE_URL}/rest/api/2/field",
        auth=config.JIRA_AUTH, headers=config.JIRA_HEADERS
    ).json()

    sys_fields = [field for field in fields if not field.get("custom") ]
    custom_fields = [field for field in fields if field.get("custom") ]

    logger.info(f"Total Column fields: {len(fields)}\n")
    logger.info(f"System fields : {len(sys_fields)}")
    sys_fields_dict={}
    custom_fields_dict={}
    for f in sys_fields :
        sys_fields_dict[f['id']] = f['name']
        logger.debug(f"  {f['id']:<25} {f['name']}")

    logger.info(f"Custom fields : {len(custom_fields)}")
    for f in custom_fields :
        custom_fields_dict[f['id']] = f['name']
        logger.debug(f"  {f['id']:<25} {f['name']}")
        
    return sys_fields_dict, custom_fields_dict



# ===========================================================
# JQL Sanitizer
# Fixes common model mistakes before sending to Jira.
# ===========================================================

def _sanitize_jql(jql: str) -> str:
    """
    Auto-quote any unquoted multi-word tokens inside JQL in (...) clauses.

    e.g.  issuetype in (Bug, New Feature, Sub-task)
      →   issuetype in (Bug, "New Feature", "Sub-task")
    """
    import re

    def quote_list_values(match):
        prefix  = match.group(1)   # e.g. "in ("
        content = match.group(2)   # comma-separated values
        suffix  = match.group(3)   # closing ")"

        def quote_token(token):
            token = token.strip()
            # Already quoted — leave as-is
            if token.startswith('"') or token.startswith("'"):
                return token
            # Contains a space — needs quoting
            if " " in token:
                return f'"{token}"'
            return token

        quoted = ", ".join(quote_token(t) for t in content.split(","))
        return f"{prefix}{quoted}{suffix}"

    sanitized = re.sub(
        r'(\bin\s*\()([^)]+)(\))',
        quote_list_values,
        jql,
        flags=re.IGNORECASE,
    )

    if sanitized != jql:
        logger.info("JQL sanitized: %s → %s", jql, sanitized)

    return sanitized


# ===========================================================
# Step 2: Execute the Jira API Call
# ===========================================================

def execute_jira_api(plan):
    endpoint = plan["endpoint"]
    params   = plan.get("params", {})

    # Sanitize JQL — auto-quote unquoted multi-word values in IN clauses
    if "jql" in params:
        params["jql"] = _sanitize_jql(params["jql"])

    # Always ensure minimum required fields are requested
    _MIN_FIELDS = {"summary", "status"}
    requested = set(params.get("fields", "").split(",")) if params.get("fields") else set()
    params["fields"] = ",".join(sorted(_MIN_FIELDS | requested - {""}))

    # Handle changelog expansion
    if plan.get("needs_changelog"):
        params["expand"] = "changelog"

    url     = f"{config.JIRA_BASE_URL}{endpoint}"
    issues  = []
    start   = 0
    retries = 0

    # Paginate through all results
    while True:
        params["startAt"] = start
        jira_limiter.throttle()
        response = requests.get(url, auth=config.JIRA_AUTH, headers=config.JIRA_HEADERS, params=params)
        logger.info("Jira request URL: %s", response.request.url)

        logger.info("Jira HTTP %s, content-type: %s", response.status_code, response.headers.get("content-type"))
        logger.debug("Jira raw response: %s", response.text[:1000])

        if not response.ok:
            logger.error("Jira HTTP %s: %s", response.status_code, response.text[:500])
            break

        res = response.json()
        if "issues" not in res:
            for r in res:
                logger.info(f"{C.YELLOW}response: {r}: {res[r]}")

        # Single-issue endpoint (/rest/api/2/issue/{key}) returns the issue directly
        if "key" in res:
            issues.append(res)
            break

        if "issues" not in res or not res["issues"]:
            logger.error("Jira error: %s", res.get("errorMessages", res))
            break

        batch = res["issues"]
        if not batch:
            retries += 1
            if retries >= 5:
                logger.warning("Pagination returned empty batch 5 times — stopping.")
                break
            continue

        retries = 0
        issues += batch
        start  += len(batch)
        if start >= res["total"]:
            break
        if params.get("maxResults") and len(issues) >= params["maxResults"]:
            break

    logger.info("Fetched %d issues from Jira", len(issues))
    return issues


# ===========================================================
# Custom Field Resolution
# Maps semantic names → actual field IDs by matching display
# names returned by this Jira instance's /field endpoint.
# Avoids hardcoding IDs that differ across instances.
# ===========================================================

# Each key is a semantic name; values are known display-name
# variants (lowercase) used across Jira Cloud / Server flavours.
_SEMANTIC_FIELD_VARIANTS: dict[str, set[str]] = {
    "sprint"      : {"sprint", "sprint name"},
    "story_points": {"story points", "story point estimate",
                     "story point", "sp", "story_points"},
    "epic_link"   : {"epic link"},
    "epic_name"   : {"epic name"},
    "team"        : {"team", "squad"},
}


def resolve_custom_field_ids(custom_fields: dict) -> dict[str, str]:
    """
    Return a mapping of semantic name → field ID for this Jira instance.

    Example output:
        {"sprint": "customfield_10020", "story_points": "customfield_10016"}

    Unrecognised fields are silently omitted so callers always get a safe dict.
    """
    resolved: dict[str, str] = {}
    for semantic, variants in _SEMANTIC_FIELD_VARIANTS.items():
        for field_id, display_name in custom_fields.items():
            if display_name.lower() in variants:
                resolved[semantic] = field_id
                logger.debug("Resolved custom field %r → %s (%s)",
                             semantic, field_id, display_name)
                break
    return resolved


def _get_field(fields: dict, resolved: dict, semantic: str, *fallback_ids: str):
    """
    Fetch a field value by semantic name, falling back to hardcoded IDs.

    Usage:
        value = _get_field(fields, resolved, "sprint", "customfield_10020")
    """
    field_id = resolved.get(semantic)
    if field_id:
        value = fields.get(field_id)
        if value is not None:
            return value
    for fid in fallback_ids:
        value = fields.get(fid)
        if value is not None:
            return value
    return None


# ===========================================================
# Step 3: Interpret Results -> Human-Readable Answer
# ===========================================================

def interpret_results(user_question, plan, issues, resolved_fields: dict | None = None):
    resolved_fields = resolved_fields or {}

    # Trim data sent to LLM — avoid token overflow
    # Send only key fields, not full changelog
    trimmed = []
    for issue in issues[:30]:   # cap at 30 issues
        fields    = issue.get("fields", {})
        histories = issue.get("changelog", {}).get("histories", [])

        # Extract status transitions only
        transitions = []
        for h in sorted(histories, key=lambda x: x["created"]):
            for item in h["items"]:
                if item["field"] == "status":
                    transitions.append({
                        "from"      : item.get("fromString"),
                        "to"        : item.get("toString"),
                        "changed_at": h["created"],
                        "changed_by": (h.get("author") or {}).get("displayName")
                    })

        # Sprint — resolved dynamically; fallback to common known IDs
        raw_sprints = _get_field(fields, resolved_fields, "sprint",
                                 "customfield_10020", "customfield_10010") or []
        if isinstance(raw_sprints, dict):
            raw_sprints = [raw_sprints]
        sprint_names = [s.get("name") for s in raw_sprints
                        if isinstance(s, dict) and s.get("name")]

        # Story points — resolved dynamically; fallback to common known IDs
        story_points = _get_field(fields, resolved_fields, "story_points",
                                  "customfield_10016", "customfield_10028",
                                  "customfield_10004", "story_points")

        trimmed.append({
            "key"             : issue["key"],
            "summary"         : fields.get("summary", ""),
            "issuetype"       : (fields.get("issuetype") or {}).get("name"),
            "status"          : (fields.get("status") or {}).get("name"),
            "priority"        : (fields.get("priority") or {}).get("name"),
            "assignee"        : (fields.get("assignee") or {}).get("displayName"),
            "reporter"        : (fields.get("reporter") or {}).get("displayName"),
            "created"         : fields.get("created"),
            "resolutiondate"  : fields.get("resolutiondate"),
            "sprint"          : sprint_names[-1] if sprint_names else None,
            "story_points"    : story_points,
            "transitions"     : transitions,
        })

    prompt = f"""
User asked: "{user_question}"

Here is the Jira data returned ({len(issues)} issues total):
{json.dumps(trimmed, indent=2)}

Post processing needed: {plan.get("post_processing", "none")}

Instructions:
- Answer ONLY using the Jira data provided above — never invent, guess, or fabricate issues, keys, names, or dates
- If the data is empty (0 issues), say so clearly and stop — do not make up example data
- Compute cycle days (first transition → Done) for each issue if relevant
- Compute time spent in each state if relevant
- Highlight bottlenecks or issues that took unusually long
- If the question asks about >10 days, filter and show only those

Output format rules — always follow these:
- Present results as a markdown table by default
- Include at minimum these 5 columns: Issue Key, Summary, Status, Priority, Assignee
- Add extra columns relevant to the question (e.g. Created, Resolution Date, Days Taken, Days in Status)
- After the table, add a short Summary section (3–5 bullet points) with key observations
- Only fall back to a plain list if there are 0 or 1 results
"""
    return call_llm(prompt, max_tokens=2000, call_label="interpret_results")


# ===========================================================
# Main Entry Point
# ===========================================================

def ask(question):
    _token_usage.clear()
    logger.info("Question: %s", question)

    # Step 1 — gather context: projects and available fields
    logger.debug("Fetching projects and fields...")
    all_projects = get_all_projects()
    sys_fields, custom_fields = get_all_fields()

    # Narrow to default project only
    if config.JIRA_DEFAULT_PROJECT and config.JIRA_DEFAULT_PROJECT in all_projects:
        projects = {config.JIRA_DEFAULT_PROJECT: all_projects[config.JIRA_DEFAULT_PROJECT]}
    else:
        projects = all_projects

    # Resolve semantic custom field IDs for this Jira instance
    resolved_fields = resolve_custom_field_ids(custom_fields)
    logger.info("Resolved custom fields: %s", resolved_fields)

    # Keep only the 15 most commonly needed fields total
    _CORE_SYS = {
        "summary", "status", "assignee", "reporter", "created",
        "updated", "resolutiondate", "issuetype", "priority",
        "description", "fixVersions", "components", "labels",
    }
    # Include any custom fields we resolved (sprint, story points, etc.)
    _useful_custom_ids = set(resolved_fields.values())
    filtered_sys    = {k: v for k, v in sys_fields.items() if k in _CORE_SYS}
    filtered_custom = {k: v for k, v in custom_fields.items()
                       if k in _useful_custom_ids}
    # Cap total at 15
    combined = {**filtered_sys, **filtered_custom}
    if len(combined) > 15:
        combined = dict(list(combined.items())[:15])
    logger.info("Fields passed to LLM: %d", len(combined))

    # Step 2 — NLP → API plan (with field context)
    logger.debug("Generating API plan...")
    plan = generate_api_plan(question, projects, combined, {})
    logger.info("JQL:    %s", plan["params"].get("jql"))
    logger.info("Fields: %s", plan["params"].get("fields"))
    logger.info("Plan:   %s", plan["explanation"])

    # Step 3 — Execute Jira API
    logger.debug("Calling Jira API...")
    issues = execute_jira_api(plan)

    # Step 4 — Interpret & answer
    logger.debug("Interpreting results...")
    answer = interpret_results(question, plan, issues, resolved_fields)

    logger.info("Answer ready (%d chars)", len(answer))
    return answer, get_token_summary()



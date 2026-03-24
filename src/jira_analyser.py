import time
import logging
import requests
import json
from datetime import datetime
from src.colors import C
from src import config

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

Field selection rules — strictly follow these:
- Only include fields in "fields" that are directly needed to answer the user's question
- Use field IDs (e.g. "customfield_10016") not display names for custom fields
- Always include "summary" and "status" as a minimum
- Do NOT include all fields — be selective

JQL date syntax — strictly follow these:
- For date ranges use: created >= "YYYY-MM-DD" AND created <= "YYYY-MM-DD"
- DURING does NOT exist in Jira Server JQL — never use it
- startOfQuarter() / endOfQuarter() are valid alternatives
- status CHANGED TO "Done" is valid
- issuetype in (Feature, Story, Bug, Epic) is valid

JQL constraints — strictly follow these:
- ORDER BY supports only: created, updated, priority, status, assignee, reporter, summary, key — ASC or DESC only
- RANDOM() does NOT exist in JQL — never use it
- When the user asks for "random" issues, use ORDER BY updated DESC or ORDER BY created DESC with a small maxResults
- Use only project keys from the available projects list above
"""
    llm_limiter.throttle()
    res = requests.post(
        config.ANTHROPIC_API_URL,
        headers=config.ANTHROPIC_HEADERS,
        json={
            "model"    : config.ANTHROPIC_MODEL,
            "max_tokens": 1000,
            "messages" : [{"role": "user", "content": prompt}]
        }
    ).json()

    raw  = res["content"][0]["text"]
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
# Step 2: Execute the Jira API Call
# ===========================================================

def execute_jira_api(plan):
    endpoint = plan["endpoint"]
    params   = plan.get("params", {})

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
# Step 3: Interpret Results -> Human-Readable Answer
# ===========================================================

def interpret_results(user_question, plan, issues):

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
                        "changed_by": h["author"].get("displayName")
                    })

        # Sprint: Jira Cloud uses customfield_10020 (list of sprint objects)
        sprints = fields.get("customfield_10020") or fields.get("sprint") or []
        if isinstance(sprints, dict):
            sprints = [sprints]
        sprint_names = [s.get("name") for s in sprints if isinstance(s, dict) and s.get("name")]

        # Story points: customfield_10016 (Jira Cloud) or customfield_10028 or story_points
        story_points = (
            fields.get("story_points")
            or fields.get("customfield_10016")
            or fields.get("customfield_10028")
        )

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
- Answer the user's question directly and clearly
- Compute cycle days (first transition → Done) for each issue if relevant
- Compute time spent in each state if relevant
- Highlight bottlenecks or issues that took unusually long
- Format as a clean readable report with a summary at the top
- If the question asks about >10 days, filter and show only those
"""
    llm_limiter.throttle()
    res = requests.post(
        config.ANTHROPIC_API_URL,
        headers=config.ANTHROPIC_HEADERS,
        json={
            "model"    : "claude-opus-4-6",
            "max_tokens": 2000,
            "messages" : [{"role": "user", "content": prompt}]
        }
    ).json()

    return res["content"][0]["text"]


# ===========================================================
# Main Entry Point
# ===========================================================

def ask(question):
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

    # Keep only the 15 most commonly needed fields total
    _CORE_SYS = {
        "summary", "status", "assignee", "reporter", "created",
        "updated", "resolutiondate", "issuetype", "priority",
        "description", "fixVersions", "components", "labels",
    }
    _USEFUL_CUSTOM_NAMES = {"story points", "sprint", "story point estimate"}
    filtered_sys    = {k: v for k, v in sys_fields.items() if k in _CORE_SYS}
    filtered_custom = {k: v for k, v in custom_fields.items()
                       if v.lower() in _USEFUL_CUSTOM_NAMES}
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
    answer = interpret_results(question, plan, issues)

    logger.info("Answer ready (%d chars)", len(answer))
    return answer



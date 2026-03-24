import os
import logging
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Jira Config ───────────────────────────────────────────
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
_jira_user  = os.environ.get("JIRA_USER", "")
_jira_token = os.environ.get("JIRA_API_TOKEN", "")
AUTH        = (_jira_user, _jira_token) if _jira_user and _jira_token else None
JIRA_HEADERS  = {"Accept": "application/json"}
API           = f"{JIRA_BASE_URL}/rest/api/2"

# ── Anthropic Config ──────────────────────────────────────
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
LLM_HEADERS   = {
    "x-api-key"        : ANTHROPIC_KEY,
    "anthropic-version": "2023-06-01",
    "content-type"     : "application/json"
}

# ─────────────────────────────────────────────────────────
# STEP 1 — NLP → API Plan
# LLM reads the question and decides what API call to make
# ─────────────────────────────────────────────────────────
def generate_api_plan(user_question):
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""
You are a Jira API expert on Jira Server v9 (REST API v2).
Today's date is {today}.

Convert this user question into a Jira API call plan.
Return ONLY valid JSON, no explanation, no markdown.

User question: "{user_question}"

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

JQL date functions you can use:
- DURING ("YYYY-MM-DD", "YYYY-MM-DD")  for Q1 2025 use ("2025-01-01","2025-03-31")
- startOfQuarter() / endOfQuarter()
- status CHANGED TO "Done"
- issuetype in (Feature, Story, Bug, Epic)
"""
    res = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=LLM_HEADERS,
        json={
            #"model"    : "claude-opus-4-6",
            "model"    : os.environ["MODEL_NAME"],
            "max_tokens": 1000,
            "messages" : [{"role": "user", "content": prompt}]
        }
    ).json()

    raw  = res["content"][0]["text"]
    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)


# ─────────────────────────────────────────────────────────
# STEP 2 — Execute the API Call
# ─────────────────────────────────────────────────────────
def execute_jira_api(plan):
    endpoint = plan["endpoint"]
    params   = plan.get("params", {})

    # Handle changelog expansion
    if plan.get("needs_changelog"):
        params["expand"] = "changelog"

    url    = f"{JIRA_BASE_URL}{endpoint}"
    issues = []
    start  = 0

    # Paginate through all results
    while True:
        params["startAt"] = start
        response = requests.get(url, auth=AUTH, headers=JIRA_HEADERS, params=params)

        if not response.ok:
            logger.error("Jira HTTP %s: %s", response.status_code, response.text[:500])
            break

        res = response.json()

        # Single-issue endpoint (/rest/api/2/issue/{key}) returns the issue directly
        if "key" in res:
            issues.append(res)
            break

        if "issues" not in res:
            logger.error("Jira error: %s", res.get("errorMessages", res))
            break

        issues += res["issues"]
        start  += len(res["issues"])
        if start >= res["total"]:
            break

    logger.info("Fetched %d issues from Jira", len(issues))
    return issues


# ─────────────────────────────────────────────────────────
# STEP 3 — LLM Interprets Results → Human Answer
# ─────────────────────────────────────────────────────────
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
    res = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=LLM_HEADERS,
        json={
            "model"    : "claude-opus-4-6",
            "max_tokens": 2000,
            "messages" : [{"role": "user", "content": prompt}]
        }
    ).json()

    return res["content"][0]["text"]


# ─────────────────────────────────────────────────────────
# MAIN — Wire it all together
# ─────────────────────────────────────────────────────────
def ask(question):
    logger.info("Question: %s", question)

    # Step 1 — NLP → API plan
    logger.debug("Generating API plan...")
    plan = generate_api_plan(question)
    logger.debug("JQL: %s", plan["params"].get("jql"))
    logger.debug("Plan: %s", plan["explanation"])

    # Step 2 — Execute Jira API
    logger.debug("Calling Jira API...")
    issues = execute_jira_api(plan)

    # Step 3 — Interpret & answer
    logger.debug("Interpreting results...")
    answer = interpret_results(question, plan, issues)

    logger.info("Answer ready (%d chars)", len(answer))
    return answer



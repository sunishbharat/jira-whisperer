"""
Jira configuration.

All Jira-specific settings — connection, authentication, and field defaults.
Edit CORE_FIELDS and CUSTOM_FIELD_VARIANTS to tune what the LLM can see
for your Jira instance without touching any pipeline code.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# ===========================================================
# Connection
# ===========================================================

BASE_URL        = os.environ["JIRA_BASE_URL"]
API             = f"{BASE_URL}/rest/api/2"
DEFAULT_PROJECT = os.environ.get("JIRA_DEFAULT_PROJECT", "")
HEADERS         = {"Accept": "application/json"}

_user  = os.environ.get("JIRA_USER", "")
_token = os.environ.get("JIRA_API_TOKEN", "")
AUTH   = (_user, _token) if _user and _token else None


# ===========================================================
# Field Defaults
# Edit these to control which fields are available to the LLM.
# ===========================================================

# Core system fields sent to the LLM for query planning.
# Add or remove IDs here to widen/narrow what the LLM can select.
CORE_FIELDS: set[str] = {
    "summary", "status", "assignee", "reporter", "created",
    "updated", "resolutiondate", "issuetype", "priority",
    "description", "fixVersions", "components", "labels",
}

# Maps semantic names → known display-name variants (lowercase) used across
# Jira Cloud / Server flavours. Add entries here if your instance uses
# different names for sprint, story points, etc.
CUSTOM_FIELD_VARIANTS: dict[str, set[str]] = {
    "sprint"      : {"sprint", "sprint name"},
    "story_points": {"story points", "story point estimate",
                     "story point", "sp", "story_points"},
    "epic_link"   : {"epic link"},
    "epic_name"   : {"epic name"},
    "team"        : {"team", "squad"},
}


# ===========================================================
# Rate Limiter
# ===========================================================

MIN_INTERVAL = 1.0    # seconds between Jira requests

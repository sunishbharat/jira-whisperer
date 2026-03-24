"""
Application configuration.

All settings are read from environment variables (via .env).
This module is the single source of truth for configuration —
no other module should read os.environ directly.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# ===========================================================
# Jira Config
# ===========================================================

JIRA_BASE_URL    = os.environ["JIRA_BASE_URL"]
JIRA_API         = f"{JIRA_BASE_URL}/rest/api/2"
JIRA_DEFAULT_PROJECT = os.environ.get("JIRA_DEFAULT_PROJECT", "")
JIRA_HEADERS     = {"Accept": "application/json"}

_jira_user  = os.environ.get("JIRA_USER", "")
_jira_token = os.environ.get("JIRA_API_TOKEN", "")
JIRA_AUTH   = (_jira_user, _jira_token) if _jira_user and _jira_token else None


# ===========================================================
# Anthropic Config
# ===========================================================

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_MODEL   = os.environ.get("MODEL_NAME", "claude-opus-4-6")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_HEADERS = {
    "x-api-key"        : ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type"     : "application/json",
}


# ===========================================================
# Rate Limiter Config
# ===========================================================

JIRA_MIN_INTERVAL = 1.0    # seconds between Jira requests
LLM_MIN_INTERVAL  = 1.0    # seconds between Anthropic requests

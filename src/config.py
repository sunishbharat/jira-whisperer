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

JIRA_BASE_URL        = os.environ["JIRA_BASE_URL"]
JIRA_API             = f"{JIRA_BASE_URL}/rest/api/2"
JIRA_DEFAULT_PROJECT = os.environ.get("JIRA_DEFAULT_PROJECT", "")
JIRA_HEADERS         = {"Accept": "application/json"}

_jira_user  = os.environ.get("JIRA_USER", "")
_jira_token = os.environ.get("JIRA_API_TOKEN", "")
JIRA_AUTH   = (_jira_user, _jira_token) if _jira_user and _jira_token else None


# ===========================================================
# LLM Provider — set LLM_PROVIDER to "anthropic" or "huggingface"
# ===========================================================

# Reads LLM_PROVIDER from .env; defaults to "anthropic" only if not set
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic").lower()

# --- Anthropic (default) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = os.environ.get("MODEL_NAME", "claude-sonnet-4-6")
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_HEADERS = {
    "x-api-key"        : ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type"     : "application/json",
}

# --- HuggingFace Serverless Inference (free tier) ---
# Recommended model: mistralai/Mistral-7B-Instruct-v0.3
# Get a free token at https://huggingface.co/settings/tokens
HF_API_KEY = os.environ.get("HF_API_KEY", "")
HF_MODEL   = os.environ.get("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")
HF_API_URL = "https://router.huggingface.co/v1/chat/completions"
HF_HEADERS = {
    "Authorization": f"Bearer {HF_API_KEY}",
    "Content-Type" : "application/json",
}

if LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
    raise KeyError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
if LLM_PROVIDER == "huggingface" and not HF_API_KEY:
    raise KeyError("HF_API_KEY is required when LLM_PROVIDER=huggingface")


# ===========================================================
# Rate Limiter Config
# ===========================================================

JIRA_MIN_INTERVAL = 1.0    # seconds between Jira requests
LLM_MIN_INTERVAL  = 1.0    # seconds between LLM requests





# Best for testing FEATURE cycle time, transitions, sprints
#APACHE_PROJECTS = {
#    "KAFKA"  : "Apache Kafka       — ~15k issues, very active, clean workflows",
#    "SPARK"  : "Apache Spark       — ~30k issues, large dataset",
#    "FLINK"  : "Apache Flink       — ~10k issues, stream processing",
#    "HIVE"   : "Apache Hive        — ~15k issues, good bug/feature mix",
#    "HADOOP" : "Apache Hadoop      — ~20k issues, oldest changelog history",
#    "LUCENE" : "Apache Lucene      — ~10k issues, search engine project",
#    "ZOOKEEPER": "Apache ZooKeeper — ~5k issues, smaller, good for quick tests",
#    "LOG4J"  : "Apache Log4J       — ~2k issues, small, fast to fetch",
#    "HBASE"  : "Apache HBase       — ~10k issues, distributed DB",
#    "STORM"  : "Apache Storm       — ~5k issues, stream processing"
#}
# Jira Whisperer

> AI-powered natural language interface for Jira — ask questions in plain English, get answers via JQL and the Jira REST API.

## What it does

You type a question in plain English. Jira Whisperer:

1. Translates it into a JQL query using Claude
2. Fetches the matching issues from Jira REST API v2
3. Interprets the results and returns a clean, human-readable answer

```
[jwhisper]# Show all open bugs in project KAFKA created this quarter
[jwhisper]# Find issues that spent more than 10 days in QA last sprint
[jwhisper]# List unresolved blockers assigned to john.doe@company.com
```

## Requirements

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) package manager
- Anthropic API key
- Jira Cloud or Jira Server v9 (REST API v2)

## Setup

```bash
# 1. Clone and install dependencies
git clone https://github.com/your-org/jira-whisperer.git
cd jira-whisperer
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

Create a `.env` file in the project root:

```env
JIRA_BASE_URL=https://your-domain.atlassian.net   # No trailing slash
JIRA_USER=your@email.com                           # Leave empty for public instances
JIRA_API_TOKEN=your_api_token                      # Leave empty for public instances
ANTHROPIC_API_KEY=sk-ant-...
MODEL_NAME=claude-opus-4-6                         # Claude model to use
JIRA_DEFAULT_PROJECT=MYAPP                         # Optional: default project scope
```

| Variable | Required | Purpose |
|---|---|---|
| `JIRA_BASE_URL` | Yes | Jira base URL, no trailing slash |
| `JIRA_USER` | No | Jira username / email (leave empty for public instances) |
| `JIRA_API_TOKEN` | No | Jira API token (leave empty for public instances) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `MODEL_NAME` | Yes | Claude model ID (e.g. `claude-opus-4-6`) |
| `JIRA_DEFAULT_PROJECT` | No | Default project key used in JQL when none is specified |

## Running

```bash
uv run python main.py
```

You'll be dropped into an interactive REPL:

```
[jwhisper]# your question here
[jwhisper]# jw help       # show example queries
[jwhisper]# jw history    # show question history
[jwhisper]# jw quit       # exit
```

## Architecture

```
User question
     │
     ▼
generate_api_plan()   — Claude translates question → JQL + field selection
     │
     ▼
execute_jira_api()    — Calls /rest/api/2/search, paginates results
     │
     ▼
interpret_results()   — Claude formats issues → human-readable answer
```

### Key files

| File | Purpose |
|---|---|
| `main.py` | REPL entry point, logging setup |
| `src/jira_analyser.py` | Core pipeline: plan → fetch → interpret |
| `src/colors.py` | ANSI color constants and `ColorFormatter` for logging |

### Logging

Set `level=logging.DEBUG` in `main.py` to see step-by-step trace output including the full Jira request URL (pasteable directly into a browser for manual verification).

## Dependencies

| Package | Purpose |
|---|---|
| `anthropic` | Anthropic SDK (declared, API called via `requests`) |
| `requests` | HTTP client for Jira and Anthropic API calls |
| `rich` | Terminal formatting and markdown rendering |
| `pyfiglet` | ASCII banner |
| `python-dotenv` | `.env` file loading |

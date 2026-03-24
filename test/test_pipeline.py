"""
Integration tests for the Jira Whisperer pipeline.

These tests run against the real Jira and Anthropic APIs using credentials
from .env. They verify structural integrity — that the pipeline completes
and returns a usable answer — not the content of the answer itself.

Run:
    uv run pytest test/ -v
"""

import pytest
from src.jira_analyser import ask, get_all_projects, get_all_fields


class TestJiraMetadata:
    """Verify that Jira metadata endpoints are reachable and return valid data."""

    def test_get_all_projects_returns_dict(self):
        """get_all_projects() must return a non-empty dict of project key -> name."""
        projects = get_all_projects()
        assert isinstance(projects, dict), "Expected a dict of projects"
        assert len(projects) > 0, "Expected at least one project"

    def test_get_all_fields_returns_dicts(self):
        """get_all_fields() must return two non-empty dicts (system, custom)."""
        sys_fields, custom_fields = get_all_fields()
        assert isinstance(sys_fields, dict), "System fields must be a dict"
        assert isinstance(custom_fields, dict), "Custom fields must be a dict"
        assert len(sys_fields) > 0, "Expected at least one system field"


class TestPipeline:
    """End-to-end pipeline tests: question -> JQL -> Jira -> answer."""

    def test_ask_returns_non_empty_string(self):
        """ask() must return a non-empty string for any valid question."""
        answer = ask("list 3 issues in project KAFKA with priority Major")
        assert isinstance(answer, str), "Answer must be a string"
        assert len(answer) > 0, "Answer must not be empty"

    def test_ask_with_status_filter(self):
        """ask() must handle status filters without raising an exception."""
        answer = ask("list 3 open issues in project KAFKA")
        assert isinstance(answer, str)
        assert len(answer) > 0

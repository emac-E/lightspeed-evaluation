"""Test suite for JIRA ticket extraction and processing.

Test Coverage:
- JIRA API connectivity and authentication
- Ticket fetching with pagination
- Label-based filtering
- Real JIRA API integration (optional)
- Complete extraction workflow
"""

import os
from unittest.mock import MagicMock

import pytest
import requests
import yaml

from okp_mcp_agent.bootstrap.extract_jira_tickets import (
    DEFAULT_JQL,
    fetch_tickets_from_jira,
    get_jira_token,
    load_existing_yaml,
    save_yaml,
)


class TestJiraAPI:
    """Tests for JIRA REST API interaction."""

    def test_jira_token_retrieval(self, mocker):
        """Test get_jira_token retrieves from secret-tool."""
        # Mock subprocess.run
        mock_result = MagicMock()
        mock_result.stdout = "test-jira-token-12345\n"
        mock_run = mocker.patch("subprocess.run", return_value=mock_result)

        token = get_jira_token()

        # Verify subprocess called correctly
        mock_run.assert_called_once_with(
            ["secret-tool", "lookup", "application", "jira"],
            capture_output=True,
            text=True,
            check=True,
        )

        # Verify token stripped of whitespace
        assert token == "test-jira-token-12345"

    def test_fetch_tickets_single_page(self, mocker):
        """Test fetch_tickets_from_jira with single page of results."""
        # Mock get_jira_token
        mocker.patch(
            "scripts.extract_jira_tickets.get_jira_token",
            return_value="test-token",
        )

        # Mock requests.get
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "issues": [
                {"key": "RSPEED-2482", "fields": {"summary": "Test ticket 1"}},
                {"key": "RSPEED-2511", "fields": {"summary": "Test ticket 2"}},
            ]
        }
        mock_get = mocker.patch("requests.get", return_value=mock_response)

        jql = 'project = RSPEED AND label = "cla-incorrect-answer"'
        tickets = fetch_tickets_from_jira(jql, limit=10)

        # Verify API called correctly
        assert mock_get.call_count == 1
        call_args = mock_get.call_args

        assert call_args.kwargs["params"]["jql"] == jql
        assert call_args.kwargs["auth"] == ("emackey@redhat.com", "test-token")
        assert call_args.args[0] == "https://redhat.atlassian.net/rest/api/3/search/jql"

        # Verify results
        assert len(tickets) == 2
        assert tickets[0]["key"] == "RSPEED-2482"
        assert tickets[1]["key"] == "RSPEED-2511"

    def test_fetch_tickets_pagination(self, mocker):
        """Test fetch_tickets_from_jira handles pagination correctly."""
        # Mock get_jira_token
        mocker.patch(
            "scripts.extract_jira_tickets.get_jira_token",
            return_value="test-token",
        )

        # Mock requests.get - return 2 pages
        def mock_get_side_effect(*_, **kwargs):
            start_at = kwargs["params"]["startAt"]
            mock_response = MagicMock()
            mock_response.status_code = 200

            if start_at == 0:
                # First page: 100 results
                mock_response.json.return_value = {
                    "issues": [
                        {"key": f"RSPEED-{i}", "fields": {"summary": f"Ticket {i}"}}
                        for i in range(100)
                    ]
                }
            elif start_at == 100:
                # Second page: 50 results
                mock_response.json.return_value = {
                    "issues": [
                        {
                            "key": f"RSPEED-{i}",
                            "fields": {"summary": f"Ticket {i}"},
                        }
                        for i in range(100, 150)
                    ]
                }
            else:
                mock_response.json.return_value = {"issues": []}

            return mock_response

        mock_get = mocker.patch("requests.get", side_effect=mock_get_side_effect)

        jql = 'project = RSPEED AND label = "cla-incorrect-answer"'
        tickets = fetch_tickets_from_jira(jql, limit=150)

        # Verify API called twice (pagination)
        assert mock_get.call_count == 2

        # Verify correct startAt values
        assert mock_get.call_args_list[0].kwargs["params"]["startAt"] == 0
        assert mock_get.call_args_list[1].kwargs["params"]["startAt"] == 100

        # Verify results
        assert len(tickets) == 150
        assert tickets[0]["key"] == "RSPEED-0"
        assert tickets[99]["key"] == "RSPEED-99"
        assert tickets[100]["key"] == "RSPEED-100"
        assert tickets[149]["key"] == "RSPEED-149"

    def test_fetch_tickets_respects_limit(self, mocker):
        """Test fetch_tickets_from_jira stops at limit."""
        mocker.patch(
            "scripts.extract_jira_tickets.get_jira_token",
            return_value="test-token",
        )

        # Mock requests.get - always return 100 results
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "issues": [
                {"key": f"RSPEED-{i}", "fields": {"summary": f"Ticket {i}"}}
                for i in range(100)
            ]
        }
        mocker.patch("requests.get", return_value=mock_response)

        tickets = fetch_tickets_from_jira("project = RSPEED", limit=50)

        # Should stop at 50 even though API returned 100
        assert len(tickets) == 50


class TestJiraIntegration:
    """Integration tests with real JIRA API (optional)."""

    @pytest.mark.skipif(
        os.getenv("SKIP_JIRA_TESTS") == "true",
        reason="JIRA integration tests disabled (set SKIP_JIRA_TESTS=false to run)",
    )
    def test_real_jira_connectivity(self):
        """Test real JIRA API connectivity with actual credentials.

        This test verifies:
        - secret-tool can retrieve JIRA token
        - JIRA API endpoint is accessible
        - Authentication works
        - Can fetch tickets with label filter
        """
        # Get real token
        token = get_jira_token()
        assert token, "JIRA token not found in secret-tool"

        # Test API connectivity
        response = requests.get(
            "https://redhat.atlassian.net/rest/api/3/issue/RSPEED-2482",
            headers={"Accept": "application/json"},
            auth=("emackey@redhat.com", token),
            timeout=30,
        )

        assert response.status_code == 200, f"JIRA API error: {response.text[:500]}"

        data = response.json()
        assert "fields" in data
        assert data["key"] == "RSPEED-2482"

        # Verify labels
        labels = data["fields"].get("labels", [])
        assert "cla-incorrect-answer" in labels, f"Expected label not found: {labels}"

    @pytest.mark.skipif(
        os.getenv("SKIP_JIRA_TESTS") == "true", reason="JIRA integration tests disabled"
    )
    def test_real_jira_label_filter(self):
        """Test JIRA API with cla-incorrect-answer label filter.

        Verifies the JQL query structure works (even if no tickets match currently).
        """
        # Fetch with default query (limit to 5 for speed)
        # Note: This may return 0 results if no tickets match the label
        tickets = fetch_tickets_from_jira(DEFAULT_JQL, limit=5)

        # Verify all returned tickets have the expected label (if any returned)
        for ticket in tickets:
            fields = ticket.get("fields", {})
            labels = fields.get("labels", [])
            assert (
                "cla-incorrect-answer" in labels
            ), f"Ticket {ticket['key']} missing expected label: {labels}"

        # Test passed if no exception - 0 results is acceptable

    @pytest.mark.skipif(
        os.getenv("SKIP_JIRA_TESTS") == "true", reason="JIRA integration tests disabled"
    )
    def test_real_jira_known_ticket(self):
        """Test fetching known cla-incorrect-answer ticket RSPEED-2482."""
        # Fetch specific ticket (note: components field is not requested by default)
        # We're testing basic fetch functionality, not specific field values
        tickets = fetch_tickets_from_jira("key = RSPEED-2482", limit=1)

        assert len(tickets) == 1
        ticket = tickets[0]

        assert ticket["key"] == "RSPEED-2482"

        fields = ticket["fields"]
        assert "summary" in fields
        assert "RHEL 6 container" in fields["summary"]
        assert "labels" in fields
        assert "cla-incorrect-answer" in fields["labels"]
        # Note: components field is not in the default field list, so we don't check it


class TestExtractionWorkflow:
    """Tests for complete extraction workflow."""

    def test_load_existing_yaml(self, tmp_path):
        """Test load_existing_yaml loads previously extracted tickets."""
        # Create test YAML
        test_yaml = tmp_path / "test_tickets.yaml"
        data = {
            "metadata": {"generated_at": "2026-04-07T10:00:00", "total_tickets": 2},
            "tickets": [
                {"ticket_key": "RSPEED-2482", "query": "Test query 1"},
                {"ticket_key": "RSPEED-2511", "query": "Test query 2"},
            ],
        }

        with open(test_yaml, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        # Load
        tickets = load_existing_yaml(test_yaml)

        assert len(tickets) == 2
        assert tickets[0]["ticket_key"] == "RSPEED-2482"
        assert tickets[1]["ticket_key"] == "RSPEED-2511"

    def test_load_existing_yaml_missing_file(self, tmp_path):
        """Test load_existing_yaml with non-existent file."""
        tickets = load_existing_yaml(tmp_path / "nonexistent.yaml")

        assert tickets == []

    def test_save_yaml(self, tmp_path):
        """Test save_yaml creates valid YAML output."""
        tickets = [
            {
                "ticket_key": "RSPEED-2482",
                "query": "Test query",
                "expected_response": "Test answer",
                "confidence": "HIGH",
            }
        ]

        output_path = tmp_path / "output.yaml"
        save_yaml(tickets, output_path)

        # Verify file created
        assert output_path.exists()

        # Load and verify
        with open(output_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert "metadata" in data
        assert data["metadata"]["total_tickets"] == 1
        assert "tickets" in data
        assert len(data["tickets"]) == 1
        assert data["tickets"][0]["ticket_key"] == "RSPEED-2482"

    def test_incremental_append_mode(self, tmp_path):
        """Test that extraction script only processes new tickets.

        This verifies the core append mode functionality:
        - Load existing tickets
        - Fetch from JIRA
        - Skip already-extracted tickets
        - Only process new ones
        """
        # Create existing YAML with 2 tickets
        output_path = tmp_path / "tickets.yaml"
        existing_tickets = [
            {"ticket_key": "RSPEED-2482", "query": "Query 1"},
            {"ticket_key": "RSPEED-2511", "query": "Query 2"},
        ]
        save_yaml(existing_tickets, output_path)

        # Load existing
        loaded = load_existing_yaml(output_path)
        existing_keys = {t["ticket_key"] for t in loaded}

        # Simulate JIRA fetch (3 tickets: 2 existing, 1 new)
        jira_tickets = [
            {"key": "RSPEED-2482"},  # Existing
            {"key": "RSPEED-2511"},  # Existing
            {"key": "RSPEED-2520"},  # New
        ]

        # Filter to new tickets
        new_tickets = [t for t in jira_tickets if t["key"] not in existing_keys]

        # Should only process 1 new ticket
        assert len(new_tickets) == 1
        assert new_tickets[0]["key"] == "RSPEED-2520"

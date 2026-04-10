#!/usr/bin/env python3
"""Fetch JIRA tickets directly via REST API and generate test configs.

This bypasses the Claude Agent SDK and uses direct REST API calls for reliability.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class TicketQuery(BaseModel):
    """Structured ticket query extraction."""

    ticket_key: str
    query: str
    expected_response: str
    reasoning: str


# Standard metrics from system_okp_mcp_agent.yaml
STANDARD_METRICS = [
    "custom:url_retrieval_eval",
    "custom:keywords_eval",
    "ragas:context_precision_without_reference",
    "ragas:context_relevance",
    "custom:forbidden_claims_eval",
    "custom:answer_correctness",
]


def get_jira_token() -> str:
    """Get JIRA API token from secret-tool."""
    result = subprocess.run(
        ["secret-tool", "lookup", "application", "jira"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def fetch_tickets_rest_api(jql: str, limit: int = 200) -> list[dict[str, Any]]:
    """Fetch tickets using JIRA REST API directly with pagination.

    Args:
        jql: JQL query
        limit: Maximum results

    Returns:
        List of ticket dictionaries with full details
    """
    import requests

    token = get_jira_token()

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    all_issues = []
    start_at = 0
    max_results = 100  # JIRA API limit per request

    while len(all_issues) < limit:
        payload = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": min(max_results, limit - len(all_issues)),
            "fields": ["summary", "description", "assignee", "status", "created", "updated", "labels", "issuetype"],
        }

        response = requests.post(
            "https://redhat.atlassian.net/rest/api/3/search/jql",
            headers=headers,
            auth=("emackey@redhat.com", token),
            json=payload,
        )

        if response.status_code != 200:
            print(f"Error fetching tickets: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            break

        data = response.json()

        issues = data.get("issues", [])
        if not issues:
            break  # No more results

        all_issues.extend(issues)

        # Check if we've reached the end
        total = data.get("total")
        if total is not None and len(all_issues) >= total:
            break
        if len(issues) < max_results:
            break

        start_at += len(issues)

    return all_issues


def extract_query_simple(ticket: dict[str, Any]) -> TicketQuery:
    """Extract query and expected response from ticket (simple fallback).

    Args:
        ticket: JIRA ticket dict

    Returns:
        TicketQuery with extracted or placeholder data
    """
    key = ticket.get("key", "UNKNOWN")
    fields = ticket.get("fields", {})
    summary = fields.get("summary", "") or ""
    description = fields.get("description", "")

    # Extract plain text from Atlassian Document Format (ADF) if needed
    if isinstance(description, dict):
        # ADF format - extract text from content blocks
        text_parts = []
        def extract_text(node):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    text_parts.append(node.get("text", ""))
                if "content" in node:
                    for child in node["content"]:
                        extract_text(child)
            elif isinstance(node, list):
                for item in node:
                    extract_text(item)

        extract_text(description)
        description = " ".join(text_parts)

    description = str(description) if description else ""

    # Simple heuristic extraction
    query = summary
    expected_response = "TODO: Expected response not specified in ticket - requires SME input"
    reasoning = f"Used summary as query. Ticket: {key}"

    # Look for patterns in description
    desc_lower = description.lower()
    if "expected" in desc_lower or "should say" in desc_lower or "correct answer" in desc_lower:
        # Might have expected response
        lines = description.split("\n")
        for i, line in enumerate(lines):
            if "expected" in line.lower() or "should" in line.lower():
                if i + 1 < len(lines):
                    expected_response = lines[i + 1].strip()
                    reasoning = f"Extracted from description near 'expected' keyword"
                    break

    return TicketQuery(
        ticket_key=key,
        query=query if query else f"TODO: No query found in {key}",
        expected_response=expected_response,
        reasoning=reasoning,
    )


def generate_test_configs(tickets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate test configuration from tickets.

    Args:
        tickets: List of JIRA ticket dicts

    Returns:
        List of conversation group dicts
    """
    conversations = []

    for ticket in tickets:
        ticket_query = extract_query_simple(ticket)
        key = ticket_query.ticket_key

        print(f"   ✓ {key}: {ticket_query.query[:60]}...")

        conversation = {
            "conversation_group_id": key.replace("-", "_"),
            "metadata": {
                "jira_ticket": key,
                "jira_url": f"https://redhat.atlassian.net/browse/{key}",
                "extraction_reasoning": ticket_query.reasoning,
            },
            "turns": [
                {
                    "query": ticket_query.query,
                    # Will be discovered during bootstrap
                    "expected_urls": [],
                    "expected_response": ticket_query.expected_response,
                    "turn_metrics": STANDARD_METRICS,
                    # These will be discovered during bootstrapping
                    "expected_keywords": [],
                    "forbidden_claims": [],
                }
            ],
        }

        conversations.append(conversation)

    return conversations


def save_yaml_configs(
    conversations: list[dict[str, Any]],
    output_file: Path,
) -> tuple[Path, Path | None]:
    """Save conversations to YAML files, splitting by readiness.

    Args:
        conversations: List of conversation dicts
        output_file: Primary output path

    Returns:
        Tuple of (ready_file, sme_file)
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Split by readiness
    ready_conversations = []
    sme_needed_conversations = []

    for conv in conversations:
        expected_response = conv["turns"][0]["expected_response"]
        if expected_response.startswith("TODO:"):
            sme_needed_conversations.append(conv)
        else:
            ready_conversations.append(conv)

    # Save ready tickets
    if ready_conversations:
        ready_header = f"""# JIRA Open Tickets - Ready for Bootstrap
# Generated from JIRA REST API
# Total tickets: {len(ready_conversations)}

"""
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(ready_header)
            yaml.dump(
                ready_conversations,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        print(f"\n✅ Saved {len(ready_conversations)} ready tickets: {output_file}")

    # Save SME-needed tickets
    sme_file = None
    if sme_needed_conversations:
        sme_file = output_file.parent / "tickets_SME_needed.yaml"
        sme_header = f"""# JIRA Open Tickets - SME Input Required
# Total tickets needing SME input: {len(sme_needed_conversations)}

"""
        with open(sme_file, "w", encoding="utf-8") as f:
            f.write(sme_header)
            yaml.dump(
                sme_needed_conversations,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        print(f"⚠️  Saved {len(sme_needed_conversations)} SME-needed tickets: {sme_file}")

    return output_file, sme_file


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch JIRA tickets via REST API and generate test configs"
    )
    parser.add_argument(
        "--jql",
        type=str,
        default=(
            'project = RSPEED AND component = "command-line-assistant" '
            'AND resolution = Unresolved AND issuetype = Bug '
            'ORDER BY created DESC'
        ),
        help="JQL query",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum tickets to fetch (default: 200)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("config/jira_open_tickets.yaml"),
        help="Output file (default: config/jira_open_tickets.yaml)",
    )

    args = parser.parse_args()

    print("🎫 JIRA Ticket Fetcher (Direct REST API)")
    print("=" * 80)

    # Fetch tickets
    print(f"\n🔍 Fetching tickets...")
    print(f"   JQL: {args.jql}")
    print(f"   Limit: {args.limit}")

    tickets = fetch_tickets_rest_api(args.jql, args.limit)
    print(f"✅ Found {len(tickets)} tickets")

    if not tickets:
        print("❌ No tickets found")
        return 1

    # Generate configs
    print(f"\n📝 Generating test configs...")
    conversations = generate_test_configs(tickets)

    # Save to files
    ready_file, sme_file = save_yaml_configs(conversations, args.output)

    # Summary
    print(f"\n{'='*80}")
    print(f"✅ COMPLETE")
    print(f"{'='*80}")
    print(f"\n📊 Summary:")
    print(f"   Total tickets: {len(conversations)}")
    print(f"   Ready for bootstrap: {len([c for c in conversations if not c['turns'][0]['expected_response'].startswith('TODO:')])} → {ready_file}")
    if sme_file:
        print(f"   Need SME input: {len([c for c in conversations if c['turns'][0]['expected_response'].startswith('TODO:')])} → {sme_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fetch Open JIRA Tickets and Generate Test Config.

This script:
1. Uses Claude Agent SDK to call JIRA MCP and fetch open tickets
2. Intelligently extracts BOTH query and expected_response from tickets
3. Generates test config compatible with system_okp_mcp_agent.yaml
4. SPLITS OUTPUT into TWO files:
   - config/jira_open_tickets.yaml → Tickets ready for bootstrap (has expected_response)
   - config/tickets_SME_needed.yaml → Tickets needing SME input (missing expected_response)

Auto-Extracted Fields:
- query: User's question (from ticket summary/description)
- expected_response: Correct answer (from ticket if specified by SME, else TODO)
- conversation_group_id: Auto-generated from ticket key

Fields for Bootstrap Discovery:
- expected_urls: Empty (discovered during bootstrap)
- expected_keywords: Empty (discovered during bootstrap)
- forbidden_claims: Empty (discovered during bootstrap)

Output Files:
- jira_open_tickets.yaml: Ready for bootstrap workflow (has expected_response)
- tickets_SME_needed.yaml: Quarantined tickets needing SME input (TODO expected_response)

Usage:
    # Fetch all unassigned tickets
    python scripts/fetch_jira_open_tickets.py

    # Include assigned tickets too
    python scripts/fetch_jira_open_tickets.py --include-assigned

    # Limit number of tickets
    python scripts/fetch_jira_open_tickets.py --limit 20

    # Custom output file (SME file will be tickets_SME_needed.yaml in same dir)
    python scripts/fetch_jira_open_tickets.py --output config/custom_tickets.yaml
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from claude_agent_sdk import query, ClaudeAgentOptions
from pydantic import BaseModel, Field


class TicketQuery(BaseModel):
    """Extracted query and expected response from a JIRA ticket."""

    ticket_key: str = Field(description="JIRA ticket key (e.g., RSPEED-1234)")
    query: str = Field(description="The actual user question extracted from the ticket")
    expected_response: str = Field(description="The correct answer that the LLM should give (extracted from ticket or marked as TODO if not found)")
    reasoning: str = Field(description="Why these were chosen as the query and expected response")


async def fetch_jira_tickets_with_agent(
    jql: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch JIRA tickets using Claude Agent SDK with MCP.

    Args:
        jql: JQL query string
        limit: Maximum number of tickets to fetch

    Returns:
        List of ticket dictionaries
    """
    print(f"🔍 Fetching JIRA tickets via Claude Agent SDK...")
    print(f"   Query: {jql}")
    print(f"   Limit: {limit}")

    prompt = f"""Use the JIRA MCP tool to search for tickets with this JQL query:

{jql}

Fetch up to {limit} results. Return the raw JSON response from JIRA.

Important: Include fields: summary, description, assignee, status, created, updated, labels
"""

    try:
        options = ClaudeAgentOptions(
            model="claude-sonnet-4-6",
            max_turns=5,
            # Allow JIRA MCP search tool
            allowed_tools=["mcp__mcp-atlassian__jira_search"],
            permission_mode="auto",
        )

        # Iterate over the async generator
        final_message = None
        async for message in query(prompt=prompt, options=options):
            final_message = message

        # Extract JSON from response
        if not final_message:
            print(f"⚠️  No response from agent")
            return []

        # Extract text from the result
        text = ""
        if hasattr(final_message, 'result'):
            result = final_message.result
            # Result is likely a list of content blocks
            if isinstance(result, list):
                for item in result:
                    if hasattr(item, 'text'):
                        text += item.text
                    elif isinstance(item, dict) and 'text' in item:
                        text += item['text']
            elif isinstance(result, str):
                text = result
            else:
                text = str(result)
        else:
            text = str(final_message)


        # Look for JSON block with issues
        json_match = re.search(r'\{[\s\S]*"issues"[\s\S]*\}', text)
        if json_match:
            result = json.loads(json_match.group(0))
            if "issues" in result:
                issues = result["issues"]
                print(f"✅ Found {len(issues)} tickets")
                return issues

        print(f"⚠️  Could not parse JIRA response - no 'issues' field found")
        print(f"   Response text: {text[:500]}...")
        return []

    except Exception as e:
        print(f"❌ Error fetching JIRA tickets: {e}")
        print(f"   Make sure the mcp-atlassian MCP server is configured and authenticated")
        return []


async def extract_query_from_ticket(
    ticket: dict[str, Any],
    model: str = "claude-sonnet-4-6",
) -> TicketQuery:
    """Use Claude to intelligently extract the user query from a JIRA ticket.

    Args:
        ticket: JIRA ticket dictionary
        model: Claude model to use

    Returns:
        TicketQuery with extracted query
    """
    key = ticket.get("key", "UNKNOWN")
    fields = ticket.get("fields", {})
    summary = fields.get("summary", "")
    description = fields.get("description", "")

    prompt = f"""You are analyzing a JIRA ticket for the Red Hat Command Line Assistant (CLA) project.
The ticket is about an incorrect answer given by the LLM.

Extract TWO things from this ticket:
1. USER QUERY: The actual question the user asked
2. EXPECTED RESPONSE: The correct answer the LLM should give

Ticket: {key}
Summary: {summary}
Description:
{description}

Guidelines:
- QUERY: The actual question the user asked (not the JIRA summary)
  - Clear and concise
  - Phrased as the user would ask it
  - Often found in the description or embedded in the summary

- EXPECTED RESPONSE: The correct answer that should be given
  - Look for phrases like "should say", "correct answer is", "expected response"
  - May describe what facts should be included
  - May mention specific keywords or URLs that should be referenced
  - If not found in ticket, set to "TODO: Expected response not specified in ticket - requires SME input"

Examples:
Query: "Can I run a RHEL 6 container on RHEL 9?"
Expected: "RHEL 6 containers on RHEL 9 hosts are UNSUPPORTED per the official Red Hat Container Compatibility Matrix..."

Query: "Is SPICE available to help with RHEL VMs?"
Expected: "SPICE was REMOVED from the QEMU/KVM stack in RHEL 9 (deprecated in RHEL 8.3)..."

Return a JSON object with these fields:
{{
  "ticket_key": "{key}",
  "query": "The extracted user question",
  "expected_response": "The correct answer (or 'TODO: Expected response not specified in ticket - requires SME input' if not found)",
  "reasoning": "Brief explanation of what you extracted and from where"
}}

Return ONLY the JSON object, no other text.
"""

    try:
        options = ClaudeAgentOptions(
            model=model,
            max_turns=3,
            permission_mode="auto",
        )

        # Get the response
        final_message = None
        async for message in query(prompt=prompt, options=options):
            final_message = message

        # Parse the response text
        if final_message and hasattr(final_message, 'result'):
            text = ""
            result = final_message.result
            if isinstance(result, list):
                for item in result:
                    if hasattr(item, 'text'):
                        text += item.text
                    elif isinstance(item, dict) and 'text' in item:
                        text += item['text']
            elif isinstance(result, str):
                text = result
            else:
                text = str(result)

            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group(0))
                return TicketQuery(**data)

        # Fallback: use summary as query
        print(f"   ⚠️  Could not extract structured data for {key}, using summary")
        return TicketQuery(
            ticket_key=key,
            query=summary,
            expected_response="TODO: Expected response not found - requires SME input",
            reasoning="Fallback: using JIRA summary as query, expected response needs manual input",
        )

    except Exception as e:
        print(f"   ⚠️  Error extracting data for {key}: {e}")
        # Fallback: use summary
        return TicketQuery(
            ticket_key=key,
            query=summary,
            expected_response="TODO: Expected response not found - requires SME input",
            reasoning="Fallback due to error: using JIRA summary as query, expected response needs manual input",
        )


def filter_unassigned(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter to only unassigned tickets.

    Args:
        issues: List of JIRA issues

    Returns:
        List of unassigned issues
    """
    unassigned = []

    for issue in issues:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee")

        # Check if unassigned (null or empty)
        if assignee is None or not assignee:
            unassigned.append(issue)

    print(f"📋 Filtered to unassigned: {len(unassigned)}/{len(issues)} tickets")

    return unassigned


async def generate_test_config(
    issues: list[dict[str, Any]],
    include_assigned: bool = False,
    model: str = "claude-sonnet-4-6",
) -> list[dict[str, Any]]:
    """Generate test config YAML structure from JIRA issues.

    Args:
        issues: List of JIRA issues
        include_assigned: If True, include assigned tickets too
        model: Claude model to use for query extraction

    Returns:
        List of conversation group dictionaries
    """
    # Filter to unassigned if requested
    if not include_assigned:
        issues = filter_unassigned(issues)

    if not issues:
        print("⚠️  No tickets to process")
        return []

    # Standard metrics from system_okp_mcp_agent.yaml
    # These are the 6 metrics used for functional tests
    STANDARD_METRICS = [
        "custom:url_retrieval_eval",
        "custom:keywords_eval",
        "ragas:context_precision_without_reference",
        "ragas:context_relevance",
        "custom:forbidden_claims_eval",
        "custom:answer_correctness",
    ]

    conversations = []

    print(f"\n📝 Extracting queries and generating test config...")

    for issue in issues:
        key = issue.get("key", "UNKNOWN")
        fields = issue.get("fields", {})

        summary = fields.get("summary", "No summary")
        status = fields.get("status", {}).get("name", "Unknown")

        print(f"\n   Processing {key}: {summary[:60]}...")

        # Use Claude to extract the actual query and expected response
        ticket_query = await extract_query_from_ticket(issue, model)

        print(f"   ✓ Query: {ticket_query.query}")
        has_expected = not ticket_query.expected_response.startswith("TODO:")
        print(f"   ✓ Expected response: {'Found' if has_expected else 'Not found (needs SME input)'}")
        print(f"   ℹ️  {ticket_query.reasoning}")

        # Create conversation group
        conv_group_id = key.replace("-", "_")  # RSPEED-1234 -> RSPEED_1234

        conversation = {
            "conversation_group_id": conv_group_id,
            "tag": "jira-open-ticket",
            "description": f"{key}: {summary}",
            "turns": [
                {
                    "turn_id": "1",
                    "query": ticket_query.query,
                    # expected_urls will be discovered during bootstrapping
                    "expected_urls": [],
                    # expected_response extracted from ticket or marked as TODO
                    "expected_response": ticket_query.expected_response,
                    "turn_metrics": STANDARD_METRICS,
                    # These will be discovered during bootstrapping
                    "expected_keywords": [],
                    "forbidden_claims": [],
                }
            ],
        }

        conversations.append(conversation)

    print(f"\n✅ Generated {len(conversations)} test cases")

    return conversations


def save_yaml_configs(
    conversations: list[dict[str, Any]],
    output_file: Path,
) -> tuple[Path, Path | None]:
    """Save conversations to YAML files, splitting by whether SME input is needed.

    Args:
        conversations: List of conversation group dictionaries
        output_file: Path to primary output YAML file

    Returns:
        Tuple of (ready_file_path, sme_needed_file_path or None)
    """
    # Create parent directory if it doesn't exist
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Split conversations into two groups
    ready_conversations = []
    sme_needed_conversations = []

    for conv in conversations:
        expected_response = conv["turns"][0]["expected_response"]
        if expected_response.startswith("TODO:"):
            sme_needed_conversations.append(conv)
        else:
            ready_conversations.append(conv)

    # Save ready-to-bootstrap tickets
    if ready_conversations:
        ready_header = f"""# JIRA Open Tickets - Ready for Bootstrap
# Generated from JIRA query: project = RSPEED AND component = "command-line-assistant"
#                            AND resolution = Unresolved AND issuetype = Bug
#
# This config is compatible with system_okp_mcp_agent.yaml
#
# ✅ ALL TICKETS IN THIS FILE HAVE EXPECTED RESPONSES
#
# AUTO-EXTRACTED from JIRA tickets:
#   - query: The user's question (extracted by Claude from ticket)
#   - expected_response: The correct answer (extracted by Claude from ticket)
#
# WORKFLOW - Bootstrap Process for URL Discovery:
# 1. Run bootstrap to discover URLs and optimize Solr config:
#    python scripts/okp_mcp_agent.py bootstrap <TICKET-ID> --yolo
#    - Discovers which documents contain the answer
#    - Populates expected_urls with discovered URLs
#    - Extracts expected_keywords from the answer
#    - Optimizes Solr config to retrieve those docs
#
# 2. Or batch process all tickets:
#    for ticket in $(grep 'conversation_group_id:' {output_file.name} | awk '{{print $2}}'); do
#      python scripts/okp_mcp_agent.py bootstrap ${{ticket//_/-}} --yolo
#    done
#
# 3. Then run full evaluation:
#    ./run_okp_mcp_full_suite.sh --config {output_file}
#
# Metrics used (from system_okp_mcp_agent.yaml):
#   - custom:url_retrieval_eval (threshold: 0.7)
#   - custom:keywords_eval (boolean)
#   - ragas:context_precision_without_reference (threshold: 0.7)
#   - ragas:context_relevance (threshold: 0.7)
#   - custom:forbidden_claims_eval (threshold: 1.0)
#   - custom:answer_correctness (threshold: 0.75)
#
# Total tickets ready for bootstrap: {len(ready_conversations)}

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

        print(f"\n✅ Saved ready-to-bootstrap tickets: {output_file}")
        print(f"   Total tickets: {len(ready_conversations)}")

    # Save SME-needed tickets to separate file
    sme_file = None
    if sme_needed_conversations:
        sme_file = output_file.parent / "tickets_SME_needed.yaml"

        sme_header = f"""# JIRA Open Tickets - SME Input Required
# Generated from JIRA query: project = RSPEED AND component = "command-line-assistant"
#                            AND resolution = Unresolved AND issuetype = Bug
#
# ⚠️  ALL TICKETS IN THIS FILE NEED SME INPUT
#
# These tickets were missing expected_response in the JIRA ticket description.
# An SME needs to provide the correct answer before these can be processed.
#
# AUTO-EXTRACTED from JIRA tickets:
#   - query: The user's question (extracted by Claude from ticket)
#   - expected_response: Marked as "TODO" - NEEDS SME INPUT
#
# WORKFLOW:
# 1. For each ticket below, an SME should:
#    - Review the query
#    - Provide the correct expected_response (what the LLM should say)
#    - Update the JIRA ticket with this information for future reference
#    - Fill in the expected_response field in this YAML
#
# 2. Once expected_response is filled in, move the ticket to jira_open_tickets.yaml
#
# 3. Then run bootstrap to discover URLs:
#    python scripts/okp_mcp_agent.py bootstrap <TICKET-ID> --yolo
#
# Metrics used (from system_okp_mcp_agent.yaml):
#   - custom:url_retrieval_eval (threshold: 0.7)
#   - custom:keywords_eval (boolean)
#   - ragas:context_precision_without_reference (threshold: 0.7)
#   - ragas:context_relevance (threshold: 0.7)
#   - custom:forbidden_claims_eval (threshold: 1.0)
#   - custom:answer_correctness (threshold: 0.75)
#
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

        print(f"\n⚠️  Saved SME-needed tickets (quarantined): {sme_file}")
        print(f"   Total tickets needing SME input: {len(sme_needed_conversations)}")

    return output_file, sme_file


async def main_async(args: argparse.Namespace) -> int:
    """Main async entry point."""
    print("🎫 JIRA Ticket Fetcher - CLA Incorrect Answers")
    print("=" * 80)

    # Fetch tickets from JIRA
    issues = await fetch_jira_tickets_with_agent(args.jql, args.limit)

    if not issues:
        print("\n❌ No tickets found or error occurred")
        return 1

    # Generate test config with intelligent query extraction
    conversations = await generate_test_config(
        issues,
        args.include_assigned,
        args.model,
    )

    if not conversations:
        print("\n❌ No conversations generated")
        return 1

    # Save to YAML files (split by readiness)
    ready_file, sme_file = save_yaml_configs(conversations, args.output)

    # Next steps
    print("\n" + "=" * 80)
    print("✅ JIRA TICKETS FETCHED SUCCESSFULLY")
    print("=" * 80)

    # Count tickets with/without expected responses
    tickets_with_expected = sum(
        1 for c in conversations
        if not c["turns"][0]["expected_response"].startswith("TODO:")
    )
    tickets_need_sme = len(conversations) - tickets_with_expected

    print(f"\n📊 Extraction Summary:")
    print(f"   Total tickets fetched: {len(conversations)}")
    print(f"   ✅ Ready for bootstrap: {tickets_with_expected} → {ready_file.name}")
    print(f"   ⚠️  Need SME input: {tickets_need_sme}" + (f" → {sme_file.name}" if sme_file else ""))

    if tickets_with_expected > 0:
        print(f"\n🚀 Next steps for ready tickets ({ready_file}):")
        print(f"  1. Batch process with bootstrap to discover URLs:")
        print(f"     for ticket in $(grep 'conversation_group_id:' {ready_file} | awk '{{print $2}}'); do")
        print(f"       python scripts/okp_mcp_agent.py bootstrap ${{ticket//_/-}} --yolo")
        print(f"     done")
        print(f"\n  2. Then run full evaluation:")
        print(f"     ./run_okp_mcp_full_suite.sh --config {ready_file}")

    if sme_file:
        print(f"\n📝 Next steps for SME-needed tickets ({sme_file}):")
        print(f"  1. Assign to SMEs to fill in expected_response fields")
        print(f"  2. Once filled in, move tickets to {ready_file}")
        print(f"  3. Then run bootstrap as above")
        print(f"\n  💡 Tip: Update JIRA tickets with expected_response for future automation")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch open JIRA tickets and generate test config with intelligent query extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch all unassigned tickets (default)
  python scripts/fetch_jira_open_tickets.py

  # Include assigned tickets too
  python scripts/fetch_jira_open_tickets.py --include-assigned

  # Limit to first 20 tickets
  python scripts/fetch_jira_open_tickets.py --limit 20

  # Use faster model for extraction (cheaper)
  python scripts/fetch_jira_open_tickets.py --model claude-haiku-4

What Gets Auto-Extracted:
  - query: User's question (from ticket summary/description)
  - expected_response: Correct answer (from ticket if specified by SME)

Output Files:
  - config/jira_open_tickets.yaml
    → Tickets with expected_response found (ready for bootstrap)
  - config/tickets_SME_needed.yaml
    → Tickets without expected_response (quarantined for SME input)

Workflow:
  1. Run this script to fetch and split tickets
  2. For ready tickets: run bootstrap to discover URLs
     python scripts/okp_mcp_agent.py bootstrap RSPEED-XXXX --yolo
  3. For SME-needed tickets: assign to SMEs to fill in expected_response
  4. Once filled, move to jira_open_tickets.yaml and run bootstrap
        """,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("config/jira_open_tickets.yaml"),
        help="Output YAML file for ready tickets (default: config/jira_open_tickets.yaml). "
             "SME-needed tickets will be saved to tickets_SME_needed.yaml in the same directory.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of tickets to fetch (default: 100)",
    )
    parser.add_argument(
        "--include-assigned",
        action="store_true",
        help="Include assigned tickets (default: only unassigned)",
    )
    parser.add_argument(
        "--jql",
        type=str,
        default=(
            'project = RSPEED AND component = "command-line-assistant" '
            'AND resolution = Unresolved AND issuetype = Bug '
            'ORDER BY created DESC'
        ),
        help="Custom JQL query (default: CLA Bug tickets in RSPEED)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-6",
        choices=["claude-opus-4", "claude-sonnet-4-6", "claude-haiku-4"],
        help="Claude model for query extraction (default: claude-sonnet-4-6)",
    )

    args = parser.parse_args()

    # Run async main
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())

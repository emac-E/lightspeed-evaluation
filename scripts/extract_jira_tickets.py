#!/usr/bin/env python3
"""Extract JIRA tickets with multi-agent verification (Linux Expert + Solr Expert).

Stage 1: Fetch & Extract
-------------------------
Fetches JIRA tickets and extracts query/answer pairs using:
- Linux Expert Agent: Forms hypotheses with RHEL expertise
- Solr Expert Agent: Verifies against actual documentation
- Search Intelligence: Logs searches for fixing workflow

Features:
- Incremental append mode (default): Only processes new tickets
- Force rebuild: Re-extract all tickets from scratch
- Force re-extract: Update specific tickets
- Default JQL query for RSPEED CLA incorrect-answer tickets

Usage:
    # Default: append new tickets to existing YAML
    python scripts/extract_jira_tickets.py

    # Force rebuild everything
    python scripts/extract_jira_tickets.py --force-rebuild

    # Process specific tickets
    python scripts/extract_jira_tickets.py --tickets RSPEED-2482,RSPEED-2511

    # Custom JQL query
    python scripts/extract_jira_tickets.py --jql "project = RSPEED AND status = Open"

    # Force re-extract specific tickets (even if already processed)
    python scripts/extract_jira_tickets.py --tickets RSPEED-2482 --force-reextract
"""

import argparse
import asyncio
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml

# Add repo root to sys.path
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lightspeed_evaluation.agents import LinuxExpertAgent, SolrExpertAgent  # noqa: E402

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Default JQL query for RSPEED CLA incorrect-answer tickets
DEFAULT_JQL = (
    "project = RSPEED AND "
    'component = "command-line-assistant" AND '
    "resolution = Unresolved AND "
    'labels = "cla-incorrect-answer" '
    "ORDER BY created DESC"
)

# Default output path
DEFAULT_OUTPUT = REPO_ROOT / "config" / "extracted_tickets.yaml"


def get_jira_token() -> str:
    """Get JIRA API token from secret-tool."""
    result = subprocess.run(
        ["secret-tool", "lookup", "application", "jira"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def fetch_tickets_from_jira(jql: str, limit: int = 200) -> list[dict[str, Any]]:
    """Fetch tickets using JIRA REST API directly with pagination.

    Args:
        jql: JQL query
        limit: Maximum results

    Returns:
        List of ticket dictionaries with full details
    """
    token = get_jira_token()

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    all_issues = []
    start_at = 0
    max_results = 100  # JIRA API limit per request

    logger.info(f"Fetching tickets with JQL: {jql}")

    while len(all_issues) < limit:
        # Use GET with query parameters for the new /search/jql endpoint
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": min(max_results, limit - len(all_issues)),
            "fields": ",".join([
                "summary",
                "description",
                "assignee",
                "status",
                "created",
                "updated",
                "labels",
                "issuetype",
            ]),
        }

        response = requests.get(
            "https://redhat.atlassian.net/rest/api/3/search/jql",
            headers=headers,
            auth=("emackey@redhat.com", token),
            params=params,
            timeout=30,
        )

        if response.status_code != 200:
            logger.error(f"Error fetching tickets: {response.status_code}")
            logger.error(f"Response: {response.text[:500]}")
            break

        data = response.json()
        issues = data.get("issues", [])

        if not issues:
            break  # No more results

        # Add issues but don't exceed limit
        remaining = limit - len(all_issues)
        all_issues.extend(issues[:remaining])
        start_at += len(issues)

        logger.info(f"Fetched {len(all_issues)} tickets so far...")

        # Stop if we've reached the limit or no more pages
        if len(all_issues) >= limit or len(issues) < max_results:
            break

    logger.info(f"Total tickets fetched: {len(all_issues)}")
    return all_issues


def load_existing_yaml(path: Path) -> list[dict[str, Any]]:
    """Load existing extracted tickets from YAML.

    Args:
        path: Path to YAML file

    Returns:
        List of extracted ticket dictionaries
    """
    if not path.exists():
        logger.info(f"No existing YAML found at {path}")
        return []

    logger.info(f"Loading existing tickets from {path}")
    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or "tickets" not in data:
        logger.warning("YAML file exists but has no 'tickets' key")
        return []

    tickets = data["tickets"]
    logger.info(f"Loaded {len(tickets)} existing tickets")
    return tickets


def save_yaml(tickets: list[dict[str, Any]], path: Path) -> None:
    """Save extracted tickets to YAML.

    Args:
        tickets: List of extracted ticket dictionaries
        path: Output path
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat(),
            "total_tickets": len(tickets),
            "extraction_method": "multi_agent_linux_solr_expert",
        },
        "tickets": tickets,
    }

    with open(path, "w") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Saved {len(tickets)} tickets to {path}")


async def extract_ticket(
    ticket: dict[str, Any],
    linux_expert: LinuxExpertAgent,
    solr_expert: SolrExpertAgent,
) -> dict[str, Any]:
    """Extract query/answer from a single JIRA ticket.

    Args:
        ticket: JIRA ticket dictionary
        linux_expert: Linux Expert Agent
        solr_expert: Solr Expert Agent

    Returns:
        Extracted ticket dictionary for YAML
    """
    key = ticket.get("key", "UNKNOWN")
    fields = ticket.get("fields", {})

    # Set ticket key for search intelligence logging
    solr_expert.ticket_key = key

    # Extract with verification
    result = await linux_expert.extract_with_verification(ticket, solr_expert)

    # Format for YAML output
    return {
        "ticket_key": result.ticket_key,
        "query": result.query,
        "expected_response": result.expected_response,
        "confidence": result.confidence,
        "inferred": result.inferred,
        "sources": result.sources,
        "reasoning": result.reasoning,
        "extracted_at": datetime.utcnow().isoformat(),
        "jira_summary": fields.get("summary", ""),
        "jira_updated": fields.get("updated", ""),
    }


async def main():
    """Main extraction workflow."""
    parser = argparse.ArgumentParser(
        description="Extract JIRA tickets with multi-agent verification"
    )
    parser.add_argument(
        "--jql",
        type=str,
        default=DEFAULT_JQL,
        help=f"JQL query (default: {DEFAULT_JQL})",
    )
    parser.add_argument(
        "--tickets",
        type=str,
        help="Comma-separated ticket keys to process (e.g., RSPEED-2482,RSPEED-2511)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output YAML path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Re-extract all tickets (ignore existing YAML)",
    )
    parser.add_argument(
        "--force-reextract",
        action="store_true",
        help="Force re-extract tickets even if already processed",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum tickets to fetch from JIRA (default: 200)",
    )

    args = parser.parse_args()

    # Initialize agents
    logger.info("Initializing agents...")
    solr_expert = SolrExpertAgent()
    linux_expert = LinuxExpertAgent()

    # Load existing tickets (unless force rebuild)
    existing_tickets = [] if args.force_rebuild else load_existing_yaml(args.output)
    existing_keys = {t["ticket_key"] for t in existing_tickets}

    # Fetch tickets
    if args.tickets:
        # Process specific tickets
        ticket_keys = [k.strip() for k in args.tickets.split(",")]
        logger.info(f"Processing specific tickets: {ticket_keys}")

        jira_tickets = []
        for key in ticket_keys:
            # Fetch individual ticket
            tickets = fetch_tickets_from_jira(f"key = {key}", limit=1)
            if tickets:
                jira_tickets.extend(tickets)
            else:
                logger.warning(f"Ticket not found: {key}")
    else:
        # Fetch via JQL
        jira_tickets = fetch_tickets_from_jira(args.jql, limit=args.limit)

    # Filter to new tickets (unless force re-extract)
    if args.force_reextract:
        tickets_to_process = jira_tickets
        logger.info(f"Force re-extract: Processing {len(tickets_to_process)} tickets")
    else:
        tickets_to_process = [t for t in jira_tickets if t["key"] not in existing_keys]
        skipped = len(jira_tickets) - len(tickets_to_process)
        logger.info(
            f"Found {len(tickets_to_process)} new tickets ({skipped} already extracted)"
        )

    if not tickets_to_process:
        logger.info("No new tickets to process!")
        return

    # Process tickets
    logger.info(f"\n{'='*80}")
    logger.info(f"Processing {len(tickets_to_process)} tickets")
    logger.info(f"{'='*80}\n")

    newly_extracted = []
    for i, ticket in enumerate(tickets_to_process, 1):
        logger.info(f"\n[{i}/{len(tickets_to_process)}] Processing {ticket['key']}")

        try:
            extracted = await extract_ticket(ticket, linux_expert, solr_expert)
            newly_extracted.append(extracted)

            logger.info(f"  ✅ Extracted: {extracted['query'][:60]}...")
            logger.info(f"  Confidence: {extracted['confidence']}")

        except Exception as e:
            logger.error(f"  ❌ Failed to extract {ticket['key']}: {e}")
            continue

    # Merge with existing (remove old versions if force re-extract)
    if args.force_reextract:
        # Remove old versions of re-extracted tickets
        newly_extracted_keys = {t["ticket_key"] for t in newly_extracted}
        existing_tickets = [
            t for t in existing_tickets if t["ticket_key"] not in newly_extracted_keys
        ]

    all_tickets = existing_tickets + newly_extracted

    # Save merged YAML
    save_yaml(all_tickets, args.output)

    # Show search intelligence stats
    if solr_expert.search_intelligence_mgr:
        logger.info(f"\n{'='*80}")
        logger.info("SEARCH INTELLIGENCE STATS")
        logger.info(f"{'='*80}")
        stats = solr_expert.search_intelligence_mgr.get_stats()
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")

    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("EXTRACTION COMPLETE")
    logger.info(f"{'='*80}")
    logger.info(f"Total tickets in YAML: {len(all_tickets)}")
    logger.info(f"Newly extracted: {len(newly_extracted)}")
    logger.info(f"Output: {args.output}")

    # Show confidence breakdown
    high = sum(1 for t in newly_extracted if t["confidence"] == "HIGH")
    medium = sum(1 for t in newly_extracted if t["confidence"] == "MEDIUM")
    low = sum(1 for t in newly_extracted if t["confidence"] == "LOW")

    logger.info("\nConfidence breakdown (new tickets):")
    logger.info(f"  HIGH:   {high}")
    logger.info(f"  MEDIUM: {medium}")
    logger.info(f"  LOW:    {low}")


if __name__ == "__main__":
    import os
    import sys

    exit_code = 0
    interrupted = False

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        interrupted = True
        exit_code = 130
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        # Aggressive cleanup: Force kill any remaining Claude SDK subprocess tasks
        # This is necessary because Claude SDK spawns background tasks that don't
        # get properly cleaned up when the query finishes
        #
        # IMPORTANT: We use os._exit() instead of sys.exit() because sys.exit()
        # waits for background threads to finish, which causes hangs with Claude SDK
        if not interrupted:
            # On normal completion, try gentle cleanup first
            try:
                loop = asyncio.get_event_loop()
                if loop and not loop.is_closed():
                    pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                    if pending:
                        for task in pending:
                            task.cancel()
                        try:
                            loop.run_until_complete(asyncio.wait(pending, timeout=0.5))
                        except Exception:
                            pass
            except Exception:
                pass

        # Force exit to kill any lingering subprocess threads
        # This works for both normal completion AND Ctrl+C interruption
        os._exit(exit_code)

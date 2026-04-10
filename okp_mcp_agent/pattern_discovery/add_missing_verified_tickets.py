#!/usr/bin/env python3
"""Add YAMLs for verified tickets not covered by strict JQL query.

Identifies tickets that:
- Are in verified_tickets.yaml (have ground truth)
- But not returned by strict JQL query
- Creates a separate YAML for manual review

Usage:
    python scripts/add_missing_verified_tickets.py \
        --verified config/bootstrap_20260407/verified_tickets.yaml \
        --strict-jql-keys RSPEED-2657,RSPEED-2511,... \
        --output config/patterns/MISSING_FROM_JQL.yaml
"""

import argparse
import sys
from pathlib import Path

import yaml


def main():
    """Identify and create YAML for verified tickets missing from strict JQL."""
    parser = argparse.ArgumentParser(
        description="Add YAMLs for verified tickets not in strict JQL results"
    )
    parser.add_argument(
        "--verified",
        type=Path,
        required=True,
        help="Path to verified_tickets.yaml",
    )
    parser.add_argument(
        "--strict-jql-keys",
        type=str,
        help="Comma-separated list of ticket keys from strict JQL query",
    )
    parser.add_argument(
        "--strict-jql-file",
        type=Path,
        help="Or path to YAML with strict JQL tickets",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output YAML path for missing tickets",
    )

    args = parser.parse_args()

    # Load verified tickets
    if not args.verified.exists():
        print(f"❌ Verified tickets file not found: {args.verified}")
        sys.exit(1)

    with open(args.verified) as f:
        verified_data = yaml.safe_load(f)
    verified_tickets = verified_data.get("tickets", [])
    verified_keys = {t["ticket_key"] for t in verified_tickets}

    print(f"Loaded {len(verified_tickets)} verified tickets")

    # Get strict JQL keys
    if args.strict_jql_keys:
        strict_keys = {k.strip() for k in args.strict_jql_keys.split(",")}
    elif args.strict_jql_file:
        with open(args.strict_jql_file) as f:
            # Check if it's a text file or YAML
            content = f.read()
            if content.strip().startswith("-") or "tickets:" in content:
                # YAML format
                strict_data = yaml.safe_load(content)
                strict_tickets = strict_data.get("tickets", [])
                strict_keys = {t["ticket_key"] for t in strict_tickets}
            else:
                # Plain text, one key per line
                strict_keys = {line.strip() for line in content.split("\n") if line.strip()}
    else:
        print("❌ Must provide either --strict-jql-keys or --strict-jql-file")
        sys.exit(1)

    print(f"Strict JQL returned {len(strict_keys)} tickets")

    # Find missing
    missing_keys = verified_keys - strict_keys

    print(f"\nFound {len(missing_keys)} verified tickets NOT in strict JQL:")
    for key in sorted(missing_keys):
        print(f"  - {key}")

    if not missing_keys:
        print("\n✅ All verified tickets are covered by strict JQL")
        return

    # Get missing ticket data
    missing_tickets = [t for t in verified_tickets if t["ticket_key"] in missing_keys]

    # Convert to eval format
    conversations = []
    for ticket in missing_tickets:
        turn = {
            "query": ticket["query"],
            "expected_response": ticket["expected_response"],
            "turn_metrics": [
                "ragas:context_relevance",
                "custom:answer_correctness",
            ],
        }

        if ticket.get("sources"):
            turn["expected_urls"] = ticket["sources"]

        conversation = {
            "conversation_group_id": ticket["ticket_key"],
            "turns": [turn],
        }

        metadata = {}
        if ticket.get("confidence") and ticket["confidence"] != "UNKNOWN":
            metadata["confidence"] = ticket["confidence"]

        metadata["notes"] = (
            "Verified ticket with ground truth but NOT returned by strict JQL query"
        )

        if metadata:
            conversation["metadata"] = metadata

        conversations.append(conversation)

    # Write YAML
    args.output.parent.mkdir(parents=True, exist_ok=True)

    header = f"""# Verified Tickets Missing from Strict JQL Query
# Total tickets: {len(missing_tickets)}
# These tickets have ground truth but were not returned by:
# project = RSPEED AND component = "command-line-assistant" AND resolution = Unresolved AND labels = "cla-incorrect-answer"
#
# Possible reasons:
# - JIRA API caching/indexing issues
# - Label applied after query was run
# - Component field missing/different
#
"""

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("\n")
        yaml.dump(
            conversations, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )

    print(f"\n✅ Created: {args.output}")
    print(f"   {len(missing_tickets)} tickets")
    print("\nNext: Run pattern discovery on combined set")


if __name__ == "__main__":
    main()

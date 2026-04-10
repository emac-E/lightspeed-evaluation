#!/usr/bin/env python3
"""Convert bootstrap outputs to lightspeed-evaluation YAML format.

Takes extracted tickets and pattern assignments, produces pattern-specific
YAML files ready for lightspeed-evaluation runner.

Usage:
    python scripts/convert_bootstrap_to_eval_format.py \
        --tickets config/bootstrap_20260407/extracted_tickets.yaml \
        --patterns config/bootstrap_20260407/patterns_report.json \
        --tagged config/bootstrap_20260407/tickets_with_patterns.yaml \
        --output-dir config/patterns/

Output:
    - One YAML per pattern (e.g., AUTHENTICATION_ISSUES.yaml)
    - UNGROUPED.yaml (tickets not in any pattern)
    - NO_GROUND_TRUTH.yaml (tickets with missing/invalid ground truth)

Format matches jira_open_tickets.yaml for compatibility with lightspeed-evaluation.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import yaml


def load_inputs(
    tickets_file: Path,
    patterns_file: Path,
    tagged_file: Path
) -> tuple:
    """Load all input files.

    Returns:
        (tickets, patterns_data, tagged_tickets)
    """
    print(f"Loading inputs...")

    with open(tickets_file, encoding='utf-8') as f:
        tickets_data = yaml.safe_load(f)
        tickets = tickets_data.get('tickets', [])

    with open(patterns_file, encoding='utf-8') as f:
        patterns_data = json.load(f)

    with open(tagged_file, encoding='utf-8') as f:
        tagged_data = yaml.safe_load(f)
        tagged_tickets = tagged_data.get('tickets', [])

    print(f"  Loaded {len(tickets)} tickets")
    print(f"  Loaded {len(patterns_data.get('patterns', []))} patterns")
    print(f"  Loaded {len(tagged_tickets)} tagged tickets")

    return tickets, patterns_data, tagged_tickets


def convert_ticket_to_eval_format(ticket: dict, pattern_id: str = None) -> dict:
    """Convert single ticket to lightspeed-evaluation format.

    Args:
        ticket: Ticket from extracted_tickets.yaml
        pattern_id: Pattern ID if ticket is grouped, None if ungrouped

    Returns:
        Dict in lightspeed-evaluation conversation format
    """
    ticket_key = ticket['ticket_key']
    query = ticket.get('query', '')
    expected_response = ticket.get('expected_response', '')
    sources = ticket.get('sources', [])
    confidence = ticket.get('confidence', 'UNKNOWN')

    # Determine if ground truth is valid
    has_ground_truth = (
        expected_response and
        expected_response.strip() and
        not expected_response.upper().startswith('N/A') and
        not expected_response.upper().startswith('TODO:') and
        'not rhel-related' not in expected_response.lower() and
        'not a rhel support question' not in expected_response.lower() and
        'no documentation found' not in expected_response.lower()
    )

    # If no ground truth, leave blank for human to fill
    if not has_ground_truth:
        notes = expected_response if expected_response else 'Needs manual review - missing ground truth'
        expected_response = ""
        sources = []
    else:
        notes = None

    # Build metadata (minimal - only what's needed)
    metadata = {}

    if pattern_id:
        metadata['pattern_id'] = pattern_id

    if confidence != 'UNKNOWN':
        metadata['confidence'] = confidence

    if notes:
        metadata['notes'] = notes.strip()

    # Build turn (only include non-empty fields)
    turn = {
        'query': query,
        'expected_response': expected_response,
        'turn_metrics': [
            'custom:url_retrieval_eval',
            'ragas:context_relevance',
            'ragas:context_precision_without_reference',
            'custom:answer_correctness'
        ]
    }

    # Only add expected_urls if non-empty
    if sources:
        turn['expected_urls'] = sources

    # Build conversation
    conversation = {
        'conversation_group_id': ticket_key,
        'turns': [turn]
    }

    # Only add metadata if non-empty
    if metadata:
        conversation['metadata'] = metadata

    return conversation


def group_tickets_by_pattern(
    tickets: List[dict],
    tagged_tickets: List[dict]
) -> Dict[str, List[dict]]:
    """Group tickets by pattern_id.

    Returns:
        Dict mapping pattern_id → List[ticket]
    """
    # Build mapping ticket_key → pattern_id
    ticket_to_pattern = {}
    for tagged in tagged_tickets:
        ticket_key = tagged['ticket_key']
        pattern_id = tagged.get('pattern_id')
        if pattern_id:
            ticket_to_pattern[ticket_key] = pattern_id

    # Group tickets
    grouped = defaultdict(list)

    for ticket in tickets:
        ticket_key = ticket['ticket_key']
        pattern_id = ticket_to_pattern.get(ticket_key)

        # Determine grouping
        expected_response = ticket.get('expected_response', '')
        has_ground_truth = (
            expected_response and
            expected_response.strip() and
            not expected_response.upper().startswith('N/A') and
            'not rhel-related' not in expected_response.lower()
        )

        if not has_ground_truth:
            # No ground truth - separate file for human review
            grouped['NO_GROUND_TRUTH'].append(ticket)
        elif pattern_id:
            # Has pattern and ground truth
            grouped[pattern_id].append(ticket)
        else:
            # Has ground truth but no pattern (ungrouped)
            grouped['UNGROUPED'].append(ticket)

    return grouped


def write_pattern_yaml(
    pattern_id: str,
    tickets: List[dict],
    output_dir: Path,
    patterns_data: dict = None
):
    """Write pattern-specific YAML file.

    Args:
        pattern_id: Pattern identifier (or UNGROUPED/NO_GROUND_TRUTH)
        tickets: List of tickets in this pattern
        output_dir: Output directory
        patterns_data: Pattern metadata from patterns_report.json
    """
    # Convert tickets to eval format
    conversations = []
    for ticket in tickets:
        conv = convert_ticket_to_eval_format(
            ticket,
            pattern_id if pattern_id not in ['UNGROUPED', 'NO_GROUND_TRUTH'] else None
        )
        conversations.append(conv)

    # Build header comment
    if pattern_id == 'UNGROUPED':
        header = f"# Ungrouped Tickets - No Pattern Match\n# Total tickets: {len(tickets)}\n"
    elif pattern_id == 'NO_GROUND_TRUTH':
        header = f"# Tickets Missing Ground Truth - Needs Manual Review\n# Total tickets: {len(tickets)}\n# Fill in expected_response and expected_urls\n"
    else:
        # Find pattern metadata
        pattern_meta = None
        if patterns_data:
            for p in patterns_data.get('patterns', []):
                if p['pattern_id'] == pattern_id:
                    pattern_meta = p
                    break

        if pattern_meta:
            header = (
                f"# Pattern: {pattern_id}\n"
                f"# Description: {pattern_meta.get('description', 'N/A')}\n"
                f"# Total tickets: {len(tickets)}\n"
                f"# Problem Type: {pattern_meta.get('common_problem_type', 'N/A')}\n"
                f"# Components: {', '.join(pattern_meta.get('common_components', []))}\n"
            )
        else:
            header = f"# Pattern: {pattern_id}\n# Total tickets: {len(tickets)}\n"

    # Write YAML
    output_file = output_dir / f"{pattern_id}.yaml"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n')
        yaml.dump(conversations, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"  ✅ {output_file.name}: {len(tickets)} tickets")


def main():
    """Main conversion workflow."""
    parser = argparse.ArgumentParser(
        description="Convert bootstrap outputs to lightspeed-evaluation YAML format"
    )

    parser.add_argument(
        '--tickets',
        type=Path,
        required=True,
        help='Path to extracted_tickets.yaml'
    )
    parser.add_argument(
        '--patterns',
        type=Path,
        required=True,
        help='Path to patterns_report.json'
    )
    parser.add_argument(
        '--tagged',
        type=Path,
        required=True,
        help='Path to tickets_with_patterns.yaml'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        required=True,
        help='Output directory for pattern YAMLs'
    )

    args = parser.parse_args()

    # Validate inputs
    for input_file in [args.tickets, args.patterns, args.tagged]:
        if not input_file.exists():
            print(f"❌ Input file not found: {input_file}")
            sys.exit(1)

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load inputs
    tickets, patterns_data, tagged_tickets = load_inputs(
        args.tickets,
        args.patterns,
        args.tagged
    )

    # Group tickets by pattern
    print("\nGrouping tickets by pattern...")
    grouped = group_tickets_by_pattern(tickets, tagged_tickets)

    print(f"  Patterns: {len([k for k in grouped.keys() if k not in ['UNGROUPED', 'NO_GROUND_TRUTH']])}")
    print(f"  Ungrouped: {len(grouped.get('UNGROUPED', []))}")
    print(f"  No ground truth: {len(grouped.get('NO_GROUND_TRUTH', []))}")

    # Write pattern YAMLs
    print("\nWriting pattern YAMLs...")

    for pattern_id, pattern_tickets in sorted(grouped.items()):
        write_pattern_yaml(
            pattern_id,
            pattern_tickets,
            args.output_dir,
            patterns_data
        )

    # Summary
    print(f"\n{'='*80}")
    print("CONVERSION COMPLETE")
    print(f"{'='*80}")
    print(f"Output directory: {args.output_dir}")
    print(f"Total files created: {len(grouped)}")
    print()
    print("Pattern files:")
    for pattern_id, pattern_tickets in sorted(grouped.items()):
        if pattern_id not in ['UNGROUPED', 'NO_GROUND_TRUTH']:
            print(f"  - {pattern_id}.yaml ({len(pattern_tickets)} tickets)")
    print()
    if 'UNGROUPED' in grouped:
        print(f"  - UNGROUPED.yaml ({len(grouped['UNGROUPED'])} tickets)")
    if 'NO_GROUND_TRUTH' in grouped:
        print(f"  - NO_GROUND_TRUTH.yaml ({len(grouped['NO_GROUND_TRUTH'])} tickets)")
    print()
    print("Next steps:")
    print("  1. Review NO_GROUND_TRUTH.yaml and fill in missing expected_response/expected_urls")
    print("  2. Test with: uv run python -m lightspeed_evaluation.runner \\")
    print(f"       --config config/system_okp_mcp_agent.yaml \\")
    print(f"       --data config/patterns/AUTHENTICATION_ISSUES.yaml \\")
    print(f"       --metrics ragas:context_relevance,custom:answer_correctness")
    print()


if __name__ == '__main__':
    main()

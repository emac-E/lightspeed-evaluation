#!/usr/bin/env python3
"""Post-process extracted tickets to categorize them by ground truth availability.

Separates tickets into:
1. Verified - Has ground truth from documentation (fixable via search optimization)
2. No Ground Truth - Missing documentation or out of scope (not fixable)
3. Failed - Extraction errors or malformed entries

Usage:
    python scripts/categorize_extracted_tickets.py \
        --input config/bootstrap_20260407/extracted_tickets.yaml \
        --output-verified config/bootstrap_20260407/verified_tickets.yaml \
        --output-no-ground-truth config/bootstrap_20260407/no_ground_truth_tickets.yaml \
        --output-failed config/bootstrap_20260407/failed_tickets.yaml \
        --report config/bootstrap_20260407/categorization_report.json
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Tuple

import yaml


def categorize_ticket(ticket: dict) -> Tuple[str, str]:
    """Categorize a single ticket by ground truth availability.

    Args:
        ticket: Ticket dictionary with fields like ticket_key, query, expected_response, sources

    Returns:
        Tuple of (category, reason) where:
        - category: "verified", "no_ground_truth", or "failed"
        - reason: Specific reason for categorization
    """
    # Check for required fields
    if not ticket.get('ticket_key'):
        return ("failed", "missing_ticket_key")

    if not ticket.get('query'):
        return ("failed", "missing_query")

    if not ticket.get('expected_response'):
        return ("failed", "missing_expected_response")

    answer = ticket['expected_response']
    sources = ticket.get('sources', [])
    source_urls = ticket.get('source_urls', [])

    # Check for "N/A" or empty answer
    if answer.strip().upper() == "N/A":
        return ("no_ground_truth", "answer_na")

    # Check for common "no ground truth" phrases
    no_ground_truth_phrases = [
        "not rhel-related",
        "not related to rhel",
        "no documentation found",
        "insufficient information",
        "out of scope",
        "no relevant documentation",
        "documentation gap",
        "future version",
        "unreleased",
    ]

    answer_lower = answer.lower()
    for phrase in no_ground_truth_phrases:
        if phrase in answer_lower:
            return ("no_ground_truth", f"phrase_{phrase.replace(' ', '_')}")

    # Check for very short answers (likely placeholders)
    if len(answer.strip()) < 50:
        return ("no_ground_truth", "answer_too_short")

    # Check for sources
    has_sources = bool(sources) or bool(source_urls)

    if not has_sources:
        return ("no_ground_truth", "no_sources")

    # If we made it here, ticket has substantive answer + sources
    return ("verified", "has_ground_truth")


def categorize_tickets(
    input_file: Path,
    output_verified: Path,
    output_no_ground_truth: Path,
    output_failed: Path,
    report_file: Path,
):
    """Categorize extracted tickets into separate files.

    Args:
        input_file: Path to extracted_tickets.yaml
        output_verified: Path for verified tickets output
        output_no_ground_truth: Path for no ground truth tickets output
        output_failed: Path for failed tickets output
        report_file: Path for categorization report JSON
    """
    # Load input
    print(f"Loading tickets from: {input_file}")
    with open(input_file, encoding='utf-8') as f:
        data = yaml.safe_load(f)

    tickets = data.get('tickets', [])
    total_tickets = len(tickets)
    print(f"Total tickets to categorize: {total_tickets}")
    print()

    # Categorize each ticket
    categorized = {
        'verified': [],
        'no_ground_truth': [],
        'failed': [],
    }

    reason_counts = defaultdict(int)

    for ticket in tickets:
        category, reason = categorize_ticket(ticket)
        categorized[category].append(ticket)
        reason_counts[reason] += 1

        # Add categorization metadata to ticket
        ticket['categorization'] = {
            'category': category,
            'reason': reason,
        }

    # Write output files
    print("Writing categorized outputs...")

    # Verified tickets
    verified_data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_tickets': len(categorized['verified']),
            'source_file': str(input_file),
            'category': 'verified',
            'description': 'Tickets with verified ground truth from documentation',
        },
        'tickets': categorized['verified'],
    }

    with open(output_verified, 'w', encoding='utf-8') as f:
        yaml.dump(verified_data, f, default_flow_style=False, sort_keys=False)
    print(f"✅ Verified tickets: {len(categorized['verified'])} → {output_verified}")

    # No ground truth tickets
    no_gt_data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_tickets': len(categorized['no_ground_truth']),
            'source_file': str(input_file),
            'category': 'no_ground_truth',
            'description': 'Tickets without ground truth - missing documentation or out of scope',
        },
        'tickets': categorized['no_ground_truth'],
    }

    with open(output_no_ground_truth, 'w', encoding='utf-8') as f:
        yaml.dump(no_gt_data, f, default_flow_style=False, sort_keys=False)
    print(f"⚠️  No ground truth: {len(categorized['no_ground_truth'])} → {output_no_ground_truth}")

    # Failed tickets
    failed_data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_tickets': len(categorized['failed']),
            'source_file': str(input_file),
            'category': 'failed',
            'description': 'Tickets with extraction errors or malformed entries',
        },
        'tickets': categorized['failed'],
    }

    with open(output_failed, 'w', encoding='utf-8') as f:
        yaml.dump(failed_data, f, default_flow_style=False, sort_keys=False)
    print(f"❌ Failed: {len(categorized['failed'])} → {output_failed}")
    print()

    # Generate report
    report = {
        'generated_at': datetime.now().isoformat(),
        'input_file': str(input_file),
        'total_tickets': total_tickets,
        'categories': {
            'verified': {
                'count': len(categorized['verified']),
                'percentage': round(len(categorized['verified']) / total_tickets * 100, 1) if total_tickets > 0 else 0,
                'description': 'Tickets with verified ground truth from documentation',
            },
            'no_ground_truth': {
                'count': len(categorized['no_ground_truth']),
                'percentage': round(len(categorized['no_ground_truth']) / total_tickets * 100, 1) if total_tickets > 0 else 0,
                'description': 'Tickets without ground truth - missing documentation or out of scope',
                'reasons': dict(reason_counts),
            },
            'failed': {
                'count': len(categorized['failed']),
                'percentage': round(len(categorized['failed']) / total_tickets * 100, 1) if total_tickets > 0 else 0,
                'description': 'Tickets with extraction errors or malformed entries',
            },
        },
        'next_steps': {
            'pattern_discovery': f"Run on {output_verified.name} ({len(categorized['verified'])} tickets)",
            'documentation_gaps': f"Review {output_no_ground_truth.name} ({len(categorized['no_ground_truth'])} tickets)",
            'investigate_failures': f"Review {output_failed.name} ({len(categorized['failed'])} tickets)",
        },
    }

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f"📊 Report: {report_file}")
    print()

    # Print summary
    print("="*80)
    print("CATEGORIZATION SUMMARY")
    print("="*80)
    print()
    print(f"Total tickets: {total_tickets}")
    print()
    print(f"✅ Verified: {len(categorized['verified'])} ({report['categories']['verified']['percentage']}%)")
    print("   → Can be fixed via search optimization")
    print()
    print(f"⚠️  No ground truth: {len(categorized['no_ground_truth'])} ({report['categories']['no_ground_truth']['percentage']}%)")
    print("   → Missing documentation or out of scope")

    if categorized['no_ground_truth']:
        print()
        print("   Top reasons:")
        sorted_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)
        for reason, count in sorted_reasons[:5]:
            if reason.startswith('phrase_'):
                reason = reason.replace('phrase_', '').replace('_', ' ')
            print(f"     - {reason}: {count}")

    print()
    print(f"❌ Failed: {len(categorized['failed'])} ({report['categories']['failed']['percentage']}%)")
    print("   → Extraction errors or malformed entries")
    print()
    print("="*80)
    print("NEXT STEPS")
    print("="*80)
    print()
    print("1. Pattern discovery:")
    print(f"   python scripts/discover_ticket_patterns.py \\")
    print(f"       --input {output_verified} \\")
    print(f"       --output-tagged tickets_with_patterns.yaml \\")
    print(f"       --output-report patterns_report.json")
    print()
    print("2. Review documentation gaps:")
    print(f"   cat {output_no_ground_truth}")
    print()
    print("3. Investigate failures:")
    print(f"   cat {output_failed}")
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Categorize extracted tickets by ground truth availability"
    )

    parser.add_argument(
        '--input',
        type=Path,
        required=True,
        help='Path to extracted_tickets.yaml'
    )
    parser.add_argument(
        '--output-verified',
        type=Path,
        required=True,
        help='Path for verified tickets output'
    )
    parser.add_argument(
        '--output-no-ground-truth',
        type=Path,
        required=True,
        help='Path for no ground truth tickets output'
    )
    parser.add_argument(
        '--output-failed',
        type=Path,
        required=True,
        help='Path for failed tickets output'
    )
    parser.add_argument(
        '--report',
        type=Path,
        required=True,
        help='Path for categorization report JSON'
    )

    args = parser.parse_args()

    # Validate input exists
    if not args.input.exists():
        print(f"❌ Input file not found: {args.input}")
        sys.exit(1)

    # Create output directories if needed
    for output_path in [args.output_verified, args.output_no_ground_truth, args.output_failed, args.report]:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run categorization
    categorize_tickets(
        input_file=args.input,
        output_verified=args.output_verified,
        output_no_ground_truth=args.output_no_ground_truth,
        output_failed=args.output_failed,
        report_file=args.report,
    )


if __name__ == '__main__':
    main()

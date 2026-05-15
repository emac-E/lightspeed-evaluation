#!/usr/bin/env python3
"""
Analyze generality test failures to identify patterns.

Tests two hypotheses:
1. Failures related to query characteristics (length, grammar, topics)
2. Failures due to missing documentation in OKP
"""

import json
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd
import sys


def load_questions(json_path: Path) -> list[dict]:
    """Load questions from JSON file."""
    with open(json_path) as f:
        return json.load(f)


def load_results(csv_path: Path) -> pd.DataFrame:
    """Load evaluation results from CSV."""
    return pd.read_csv(csv_path)


def get_failed_questions(df: pd.DataFrame, metric: str = "custom:answer_correctness") -> set:
    """Get question IDs that failed for a specific metric."""
    failed_df = df[(df['metric_identifier'] == metric) & (df['result'] == 'FAIL')]

    # Extract question numbers from conversation_group_id
    failed_ids = set()
    for conv_id in failed_df['conversation_group_id'].unique():
        # Extract number from "rhel10_benchmark_qXX"
        if 'rhel10_benchmark_q' in conv_id:
            q_num = int(conv_id.split('_q')[-1])
            failed_ids.add(q_num)

    return failed_ids


def analyze_query_characteristics(questions: list[dict], failed_ids: set) -> dict:
    """Analyze if failures correlate with query characteristics."""

    # Categorize each question
    results = {
        'passed': [],
        'failed': []
    }

    for idx, q in enumerate(questions, 1):
        category = 'failed' if idx in failed_ids else 'passed'
        results[category].append({
            'q_num': idx,
            'length': q['metadata']['query_length'],
            'grammar': q['metadata']['query_style'],
            'topic': q['source_topic_slug'],
            'question': q['question'],
            'ground_truth': q['ground_truth_answer'],
        })

    # Compute statistics
    stats = {}

    for category in ['passed', 'failed']:
        items = results[category]
        stats[category] = {
            'count': len(items),
            'query_length': Counter(item['length'] for item in items),
            'query_style': Counter(item['grammar'] for item in items),
            'topics': Counter(item['topic'] for item in items),
            'avg_question_len': sum(len(item['question']) for item in items) / len(items) if items else 0,
        }

    return results, stats


def print_analysis(results: dict, stats: dict):
    """Print analysis results."""

    print("=" * 80)
    print("QUERY CHARACTERISTICS ANALYSIS")
    print("=" * 80)

    for category in ['failed', 'passed']:
        print(f"\n{category.upper()} Questions ({stats[category]['count']} total):")
        print(f"  Average question character length: {stats[category]['avg_question_len']:.1f}")

        print("\n  Query Length Distribution:")
        for length, count in stats[category]['query_length'].most_common():
            pct = 100 * count / stats[category]['count']
            print(f"    {length:15s}: {count:2d} ({pct:5.1f}%)")

        print("\n  Query Style Distribution:")
        for style, count in stats[category]['query_style'].most_common():
            pct = 100 * count / stats[category]['count']
            print(f"    {style:25s}: {count:2d} ({pct:5.1f}%)")

        print("\n  Topic Distribution:")
        for topic, count in sorted(stats[category]['topics'].items(), key=lambda x: -x[1])[:5]:
            pct = 100 * count / stats[category]['count']
            print(f"    {topic[:45]:45s}: {count:2d} ({pct:5.1f}%)")

    # Comparative analysis
    print("\n" + "=" * 80)
    print("COMPARATIVE ANALYSIS")
    print("=" * 80)

    # Query length comparison
    print("\nQuery Length - Failed vs Passed:")
    all_lengths = set(stats['failed']['query_length'].keys()) | set(stats['passed']['query_length'].keys())
    for length in sorted(all_lengths):
        failed_pct = 100 * stats['failed']['query_length'].get(length, 0) / stats['failed']['count']
        passed_pct = 100 * stats['passed']['query_length'].get(length, 0) / stats['passed']['count']
        diff = failed_pct - passed_pct
        symbol = "⚠️" if abs(diff) > 20 else ""
        print(f"  {length:15s}: Failed={failed_pct:5.1f}% | Passed={passed_pct:5.1f}% | Diff={diff:+6.1f}% {symbol}")

    # Query style comparison
    print("\nQuery Style - Failed vs Passed:")
    all_styles = set(stats['failed']['query_style'].keys()) | set(stats['passed']['query_style'].keys())
    for style in sorted(all_styles):
        failed_pct = 100 * stats['failed']['query_style'].get(style, 0) / stats['failed']['count']
        passed_pct = 100 * stats['passed']['query_style'].get(style, 0) / stats['passed']['count']
        diff = failed_pct - passed_pct
        symbol = "⚠️" if abs(diff) > 20 else ""
        print(f"  {style:25s}: Failed={failed_pct:5.1f}% | Passed={passed_pct:5.1f}% | Diff={diff:+6.1f}% {symbol}")


def print_failed_questions(results: dict):
    """Print detailed list of failed questions."""
    print("\n" + "=" * 80)
    print("FAILED QUESTIONS DETAIL")
    print("=" * 80)

    for item in sorted(results['failed'], key=lambda x: x['q_num']):
        print(f"\nQ{item['q_num']:02d} [{item['length']}, {item['grammar']}]")
        print(f"  Topic: {item['topic']}")
        print(f"  Question: {item['question'][:100]}{'...' if len(item['question']) > 100 else ''}")
        print(f"  Expected: {item['ground_truth'][:100]}{'...' if len(item['ground_truth']) > 100 else ''}")


def main():
    """Main analysis function."""
    # Current directory should be generality/
    current_dir = Path.cwd()
    if current_dir.name != 'generality':
        current_dir = Path(__file__).parent

    # Load data
    print("Loading data...")
    questions = load_questions(current_dir / "selected_questions.json")

    # Load results from all 3 runs
    all_failed_ids = set()
    for run_num in [1, 2, 3]:
        run_dir = current_dir / f"run{run_num}"
        csv_files = list(run_dir.glob("*_detailed.csv"))

        if csv_files:
            df = load_results(csv_files[0])
            failed_ids = get_failed_questions(df)
            all_failed_ids.update(failed_ids)
            print(f"  Run {run_num}: {len(failed_ids)} failures")

    print(f"\nTotal unique failures across all runs: {len(all_failed_ids)}")

    # Analyze
    results, stats = analyze_query_characteristics(questions, all_failed_ids)

    # Print results
    print_analysis(results, stats)
    print_failed_questions(results)

    # Save results
    output_file = current_dir / "failure_analysis.json"
    with open(output_file, 'w') as f:
        json.dump({
            'failed_question_ids': sorted(all_failed_ids),
            'failed_questions': results['failed'],
            'passed_questions': results['passed'],
            'statistics': {
                'failed': {
                    'count': stats['failed']['count'],
                    'avg_question_len': stats['failed']['avg_question_len'],
                    'query_length': dict(stats['failed']['query_length']),
                    'query_style': dict(stats['failed']['query_style']),
                    'topics': dict(stats['failed']['topics']),
                },
                'passed': {
                    'count': stats['passed']['count'],
                    'avg_question_len': stats['passed']['avg_question_len'],
                    'query_length': dict(stats['passed']['query_length']),
                    'query_style': dict(stats['passed']['query_style']),
                    'topics': dict(stats['passed']['topics']),
                }
            }
        }, f, indent=2)

    print(f"\n✓ Detailed analysis saved to: {output_file}")

    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("\nTo test Hypothesis 2 (missing OKP docs):")
    print("1. Search for topics in ~/Work/okp-mcp Solr database")
    print("2. Check if failed questions have missing/incomplete docs")
    print("\nYou can use the OKP MCP tools to search for topics like:")
    print("  - monitoring_and_managing_system_status_and_performance")
    print("  - composing_installing_and_managing_rhel_for_edge_images")
    print("  - etc.")


if __name__ == "__main__":
    main()

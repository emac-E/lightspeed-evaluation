#!/usr/bin/env python3
"""Calculate cost estimates for evaluation runs with multiple CSV files.

This script finds all detailed CSV files in an evaluation output directory
and aggregates token usage and cost estimates across all test suites.
"""

import argparse
import pandas as pd
import sys
from pathlib import Path


# Pricing per 1M tokens (as of March 2024)
PRICING = {
    "gemini-2.5-flash": {
        "input": 0.075,   # $0.075 per 1M input tokens
        "output": 0.30,   # $0.30 per 1M output tokens
        "name": "Gemini 2.5 Flash"
    },
    "gemini-2.0-flash": {
        "input": 0.10,
        "output": 0.40,
        "name": "Gemini 2.0 Flash"
    },
    "gemini-1.5-flash": {
        "input": 0.075,
        "output": 0.30,
        "name": "Gemini 1.5 Flash"
    },
    "gpt-4o": {
        "input": 2.50,
        "output": 10.00,
        "name": "GPT-4o"
    },
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60,
        "name": "GPT-4o Mini"
    },
    "claude-3.5-sonnet": {
        "input": 3.00,
        "output": 15.00,
        "name": "Claude 3.5 Sonnet"
    },
    "claude-3.5-haiku": {
        "input": 0.80,
        "output": 4.00,
        "name": "Claude 3.5 Haiku"
    }
}


def analyze_directory(eval_dir: Path) -> tuple[dict, list]:
    """Analyze all detailed CSV files in evaluation directory.

    Args:
        eval_dir: Path to evaluation output directory

    Returns:
        Tuple of (aggregated_stats, per_suite_stats)
    """
    # Find all detailed CSV files
    csv_files = list(eval_dir.rglob('*_detailed.csv'))

    if not csv_files:
        raise ValueError(f"No *_detailed.csv files found in {eval_dir}")

    total_questions = 0
    total_conversations = 0
    total_api_input = 0
    total_api_output = 0
    total_judge_input = 0
    total_judge_output = 0

    per_suite_stats = []

    for csv_file in sorted(csv_files):
        df = pd.read_csv(csv_file)

        # Get unique questions in this file
        unique_questions = df.groupby(['conversation_group_id', 'turn_id']).first()
        num_questions = len(unique_questions)
        num_conversations = df['conversation_group_id'].nunique()

        # Sum tokens
        api_input = df['api_input_tokens'].sum()
        api_output = df['api_output_tokens'].sum()
        judge_input = df['judge_llm_input_tokens'].sum()
        judge_output = df['judge_llm_output_tokens'].sum()

        # Accumulate totals
        total_questions += num_questions
        total_conversations += num_conversations
        total_api_input += api_input
        total_api_output += api_output
        total_judge_input += judge_input
        total_judge_output += judge_output

        suite_name = csv_file.parent.name
        per_suite_stats.append({
            'suite_name': suite_name,
            'num_questions': num_questions,
            'num_conversations': num_conversations,
            'api_input': api_input,
            'api_output': api_output,
            'judge_input': judge_input,
            'judge_output': judge_output
        })

    aggregated = {
        'num_questions': total_questions,
        'num_conversations': total_conversations,
        'num_suites': len(csv_files),
        'api_input_tokens': total_api_input,
        'api_output_tokens': total_api_output,
        'api_total_tokens': total_api_input + total_api_output,
        'judge_input_tokens': total_judge_input,
        'judge_output_tokens': total_judge_output,
        'judge_total_tokens': total_judge_input + total_judge_output,
        'total_input_tokens': total_api_input + total_judge_input,
        'total_output_tokens': total_api_output + total_judge_output,
        'total_all_tokens': total_api_input + total_api_output + total_judge_input + total_judge_output
    }

    return aggregated, per_suite_stats


def calculate_cost(tokens_input: int, tokens_output: int, model: str) -> float:
    """Calculate cost for given token usage.

    Args:
        tokens_input: Number of input tokens
        tokens_output: Number of output tokens
        model: Model identifier (key in PRICING dict)

    Returns:
        Total cost in USD
    """
    if model not in PRICING:
        raise ValueError(f"Unknown model: {model}. Available: {list(PRICING.keys())}")

    pricing = PRICING[model]
    cost_input = (tokens_input / 1_000_000) * pricing['input']
    cost_output = (tokens_output / 1_000_000) * pricing['output']

    return cost_input + cost_output


def print_per_suite_breakdown(per_suite_stats: list):
    """Print per-suite token usage breakdown.

    Args:
        per_suite_stats: List of per-suite statistics
    """
    print("=" * 110)
    print("PER-SUITE BREAKDOWN")
    print("=" * 110)
    print()
    print(f"{'Suite Name':<45} {'Questions':>10} {'Convs':>6} {'Judge Input':>15} {'Judge Output':>15}")
    print("-" * 110)

    for suite in per_suite_stats:
        print(
            f"{suite['suite_name']:<45} "
            f"{suite['num_questions']:>10,} "
            f"{suite['num_conversations']:>6,} "
            f"{suite['judge_input']:>15,} "
            f"{suite['judge_output']:>15,}"
        )

    print()


def print_cost_summary(stats: dict, llm_model: str, judge_model: str):
    """Print cost summary for full evaluation run.

    Args:
        stats: Aggregated token usage statistics
        llm_model: Model used for LLM being tested
        judge_model: Model used for judge LLM
    """
    print("=" * 110)
    print("EVALUATION COST ESTIMATE - FULL SUITE")
    print("=" * 110)
    print()

    print("Dataset Statistics:")
    print(f"  Total test suites: {stats['num_suites']}")
    print(f"  Total questions: {stats['num_questions']:,}")
    print(f"  Total conversations: {stats['num_conversations']:,}")
    print()

    # API (LLM being tested) costs
    api_cost = calculate_cost(
        stats['api_input_tokens'],
        stats['api_output_tokens'],
        llm_model
    )

    print(f"LLM Being Tested: {PRICING[llm_model]['name']}")
    print(f"  Input tokens:  {stats['api_input_tokens']:>15,}")
    print(f"  Output tokens: {stats['api_output_tokens']:>15,}")
    print(f"  Total tokens:  {stats['api_total_tokens']:>15,}")
    print(f"  Cost: ${api_cost:.2f}")
    if stats['num_questions'] > 0:
        print(f"  Avg per question: ${api_cost / stats['num_questions']:.4f}")
    print()

    # Judge LLM costs
    judge_cost = calculate_cost(
        stats['judge_input_tokens'],
        stats['judge_output_tokens'],
        judge_model
    )

    print(f"Judge LLM: {PRICING[judge_model]['name']}")
    print(f"  Input tokens:  {stats['judge_input_tokens']:>15,}")
    print(f"  Output tokens: {stats['judge_output_tokens']:>15,}")
    print(f"  Total tokens:  {stats['judge_total_tokens']:>15,}")
    print(f"  Cost: ${judge_cost:.2f}")
    if stats['num_questions'] > 0:
        print(f"  Avg per question: ${judge_cost / stats['num_questions']:.4f}")
    print()

    # Total
    total_cost = api_cost + judge_cost
    print("=" * 110)
    print(f"TOTAL COST: ${total_cost:.2f}")
    if stats['num_questions'] > 0:
        print(f"Cost per question: ${total_cost / stats['num_questions']:.4f}")
    print("=" * 110)
    print()

    # Per-question breakdown
    if stats['num_questions'] > 0:
        print("Per-Question Token Averages:")
        print(f"  LLM input:    {stats['api_input_tokens'] / stats['num_questions']:>10,.0f} tokens")
        print(f"  LLM output:   {stats['api_output_tokens'] / stats['num_questions']:>10,.0f} tokens")
        print(f"  Judge input:  {stats['judge_input_tokens'] / stats['num_questions']:>10,.0f} tokens")
        print(f"  Judge output: {stats['judge_output_tokens'] / stats['num_questions']:>10,.0f} tokens")
        print()


def print_comparison_table(stats: dict, llm_model: str):
    """Print cost comparison for different judge models.

    Args:
        stats: Token usage statistics
        llm_model: Model used for LLM being tested
    """
    print("=" * 110)
    print("COST COMPARISON: Different Judge LLM Options")
    print("=" * 110)
    print()

    # Calculate API cost (constant)
    api_cost = calculate_cost(
        stats['api_input_tokens'],
        stats['api_output_tokens'],
        llm_model
    )

    print(f"{'Judge Model':<30} {'Judge Cost':>12} {'Total Cost':>12} {'Per Question':>15} {'vs Cheapest':>15}")
    print("-" * 110)

    results = []
    for judge_model_key, pricing in PRICING.items():
        judge_cost = calculate_cost(
            stats['judge_input_tokens'],
            stats['judge_output_tokens'],
            judge_model_key
        )
        total_cost = api_cost + judge_cost
        per_question_cost = total_cost / stats['num_questions'] if stats['num_questions'] > 0 else 0

        results.append({
            'model': pricing['name'],
            'judge_cost': judge_cost,
            'total_cost': total_cost,
            'per_question': per_question_cost
        })

    # Sort by total cost
    results.sort(key=lambda x: x['total_cost'])
    cheapest_cost = results[0]['total_cost']

    for r in results:
        vs_cheapest = f"+${r['total_cost'] - cheapest_cost:.2f}"
        if r['total_cost'] == cheapest_cost:
            vs_cheapest = "CHEAPEST"

        print(
            f"{r['model']:<30} "
            f"${r['judge_cost']:>11.2f} "
            f"${r['total_cost']:>11.2f} "
            f"${r['per_question']:>14.4f} "
            f"{vs_cheapest:>15}"
        )

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Calculate cost estimates for evaluation runs with multiple CSV files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze full suite with Gemini 2.5 Flash for both LLM and judge
  python calculate_cost_estimate_multi.py \\
    eval_output/full_suite_20260323_152904 \\
    --llm-model gemini-2.5-flash \\
    --judge-model gemini-2.5-flash

  # Compare different judge models
  python calculate_cost_estimate_multi.py \\
    eval_output/full_suite_20260323_152904 \\
    --llm-model gemini-2.5-flash \\
    --comparison

  # Show per-suite breakdown
  python calculate_cost_estimate_multi.py \\
    eval_output/full_suite_20260323_152904 \\
    --llm-model gemini-2.5-flash \\
    --judge-model gemini-2.5-flash \\
    --show-suites

  # Show available models
  python calculate_cost_estimate_multi.py --list-models
        """
    )

    parser.add_argument(
        'eval_dir',
        nargs='?',
        type=Path,
        help='Path to evaluation output directory containing *_detailed.csv files'
    )
    parser.add_argument(
        '--llm-model',
        default='gemini-2.5-flash',
        choices=list(PRICING.keys()),
        help='Model used for LLM being tested (default: gemini-2.5-flash)'
    )
    parser.add_argument(
        '--judge-model',
        default='gemini-2.5-flash',
        choices=list(PRICING.keys()),
        help='Model used for judge LLM (default: gemini-2.5-flash)'
    )
    parser.add_argument(
        '--comparison',
        action='store_true',
        help='Show cost comparison for all judge model options'
    )
    parser.add_argument(
        '--show-suites',
        action='store_true',
        help='Show per-suite token usage breakdown'
    )
    parser.add_argument(
        '--list-models',
        action='store_true',
        help='List available models and pricing'
    )

    args = parser.parse_args()

    # List models
    if args.list_models:
        print("Available Models and Pricing (per 1M tokens):")
        print()
        print(f"{'Model':<30} {'Input Price':>15} {'Output Price':>15}")
        print("-" * 65)
        for key, pricing in sorted(PRICING.items()):
            print(
                f"{pricing['name']:<30} "
                f"${pricing['input']:>14.3f} "
                f"${pricing['output']:>14.3f}"
            )
        return 0

    # Validate eval_dir provided
    if not args.eval_dir:
        parser.error("eval_dir is required unless --list-models is used")

    if not args.eval_dir.exists():
        print(f"Error: Directory not found: {args.eval_dir}", file=sys.stderr)
        return 1

    # Analyze all CSV files
    print(f"Analyzing evaluation directory: {args.eval_dir}")
    print()

    try:
        stats, per_suite_stats = analyze_directory(args.eval_dir)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Show per-suite breakdown if requested
    if args.show_suites:
        print_per_suite_breakdown(per_suite_stats)

    # Print main cost summary
    print_cost_summary(stats, args.llm_model, args.judge_model)

    # Print comparison table if requested
    if args.comparison:
        print_comparison_table(stats, args.llm_model)

    return 0


if __name__ == '__main__':
    sys.exit(main())

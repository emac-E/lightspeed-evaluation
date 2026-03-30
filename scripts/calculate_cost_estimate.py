#!/usr/bin/env python3
"""Calculate cost estimates for running evaluations with different LLM providers.

This script analyzes evaluation results to provide token usage statistics
and cost estimates for different LLM providers.
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


def analyze_token_usage(csv_path: Path) -> dict:
    """Analyze token usage from evaluation results CSV.

    Args:
        csv_path: Path to evaluation_*_detailed.csv file

    Returns:
        Dictionary with token usage statistics
    """
    df = pd.read_csv(csv_path)

    # Get unique questions
    unique_questions = df.groupby(['conversation_group_id', 'turn_id']).first()
    num_questions = len(unique_questions)

    # Metrics per question
    metrics_per_question = df.groupby(['conversation_group_id', 'turn_id'])['metric_identifier'].count()
    avg_metrics_per_question = metrics_per_question.mean()

    # API token usage (LLM being tested)
    api_input_tokens = df['api_input_tokens'].sum()
    api_output_tokens = df['api_output_tokens'].sum()

    # Judge LLM token usage
    judge_input_tokens = df['judge_llm_input_tokens'].sum()
    judge_output_tokens = df['judge_llm_output_tokens'].sum()

    return {
        'num_questions': num_questions,
        'num_conversations': df['conversation_group_id'].nunique(),
        'num_metrics': df['metric_identifier'].nunique(),
        'total_metric_evaluations': len(df),
        'avg_metrics_per_question': avg_metrics_per_question,

        # API tokens (LLM being tested)
        'api_input_tokens': api_input_tokens,
        'api_output_tokens': api_output_tokens,
        'api_total_tokens': api_input_tokens + api_output_tokens,
        'api_avg_input_per_question': api_input_tokens / num_questions if num_questions > 0 else 0,
        'api_avg_output_per_question': api_output_tokens / num_questions if num_questions > 0 else 0,

        # Judge tokens
        'judge_input_tokens': judge_input_tokens,
        'judge_output_tokens': judge_output_tokens,
        'judge_total_tokens': judge_input_tokens + judge_output_tokens,
        'judge_avg_input_per_question': judge_input_tokens / num_questions if num_questions > 0 else 0,
        'judge_avg_output_per_question': judge_output_tokens / num_questions if num_questions > 0 else 0,

        # Total combined
        'total_input_tokens': api_input_tokens + judge_input_tokens,
        'total_output_tokens': api_output_tokens + judge_output_tokens,
        'total_all_tokens': api_input_tokens + api_output_tokens + judge_input_tokens + judge_output_tokens
    }


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


def print_cost_breakdown(stats: dict, llm_model: str, judge_model: str):
    """Print detailed cost breakdown.

    Args:
        stats: Token usage statistics from analyze_token_usage()
        llm_model: Model used for LLM being tested
        judge_model: Model used for judge LLM
    """
    print("=" * 80)
    print("EVALUATION COST ESTIMATE")
    print("=" * 80)
    print()

    print("Dataset Statistics:")
    print(f"  Total questions: {stats['num_questions']:,}")
    print(f"  Total conversations: {stats['num_conversations']:,}")
    print(f"  Unique metrics: {stats['num_metrics']}")
    print(f"  Total metric evaluations: {stats['total_metric_evaluations']:,}")
    print(f"  Avg metrics per question: {stats['avg_metrics_per_question']:.1f}")
    print()

    # API (LLM being tested) costs
    api_cost = calculate_cost(
        stats['api_input_tokens'],
        stats['api_output_tokens'],
        llm_model
    )

    print(f"LLM Being Tested: {PRICING[llm_model]['name']}")
    print(f"  Input tokens:  {stats['api_input_tokens']:,}")
    print(f"  Output tokens: {stats['api_output_tokens']:,}")
    print(f"  Total tokens:  {stats['api_total_tokens']:,}")
    print(f"  Cost: ${api_cost:.2f}")
    print(f"  Avg per question: ${api_cost / stats['num_questions']:.4f}")
    print()

    # Judge LLM costs
    judge_cost = calculate_cost(
        stats['judge_input_tokens'],
        stats['judge_output_tokens'],
        judge_model
    )

    print(f"Judge LLM: {PRICING[judge_model]['name']}")
    print(f"  Input tokens:  {stats['judge_input_tokens']:,}")
    print(f"  Output tokens: {stats['judge_output_tokens']:,}")
    print(f"  Total tokens:  {stats['judge_total_tokens']:,}")
    print(f"  Cost: ${judge_cost:.2f}")
    print(f"  Avg per question: ${judge_cost / stats['num_questions']:.4f}")
    print()

    # Total
    total_cost = api_cost + judge_cost
    print("=" * 80)
    print(f"TOTAL COST: ${total_cost:.2f}")
    print(f"Cost per question: ${total_cost / stats['num_questions']:.4f}")
    print("=" * 80)
    print()

    # Per-question breakdown
    print("Per-Question Token Averages:")
    print(f"  LLM input:    {stats['api_avg_input_per_question']:,.0f} tokens")
    print(f"  LLM output:   {stats['api_avg_output_per_question']:,.0f} tokens")
    print(f"  Judge input:  {stats['judge_avg_input_per_question']:,.0f} tokens")
    print(f"  Judge output: {stats['judge_avg_output_per_question']:,.0f} tokens")
    print()


def print_comparison_table(stats: dict, llm_model: str):
    """Print cost comparison for different judge models.

    Args:
        stats: Token usage statistics
        llm_model: Model used for LLM being tested
    """
    print("=" * 100)
    print("COST COMPARISON: Different Judge LLM Options")
    print("=" * 100)
    print()

    # Calculate API cost (constant)
    api_cost = calculate_cost(
        stats['api_input_tokens'],
        stats['api_output_tokens'],
        llm_model
    )

    print(f"{'Judge Model':<30} {'Judge Cost':>12} {'Total Cost':>12} {'Per Question':>15} {'vs Cheapest':>15}")
    print("-" * 100)

    results = []
    for judge_model_key, pricing in PRICING.items():
        judge_cost = calculate_cost(
            stats['judge_input_tokens'],
            stats['judge_output_tokens'],
            judge_model_key
        )
        total_cost = api_cost + judge_cost
        per_question_cost = total_cost / stats['num_questions']

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
        description="Calculate cost estimates for evaluation runs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze latest run with Gemini 2.5 Flash for both LLM and judge
  python calculate_cost_estimate.py \\
    eval_output/full_suite_20260323_152904/jira_incorrect_answers/evaluation_20260323_153258_detailed.csv \\
    --llm-model gemini-2.5-flash \\
    --judge-model gemini-2.5-flash

  # Compare different judge models
  python calculate_cost_estimate.py \\
    eval_output/latest/evaluation_detailed.csv \\
    --llm-model gemini-2.5-flash \\
    --comparison

  # Show available models
  python calculate_cost_estimate.py --list-models
        """
    )

    parser.add_argument(
        'csv_file',
        nargs='?',
        type=Path,
        help='Path to evaluation_*_detailed.csv file'
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

    # Validate CSV file provided
    if not args.csv_file:
        parser.error("csv_file is required unless --list-models is used")

    if not args.csv_file.exists():
        print(f"Error: File not found: {args.csv_file}", file=sys.stderr)
        return 1

    # Analyze token usage
    print(f"Analyzing: {args.csv_file}")
    print()
    stats = analyze_token_usage(args.csv_file)

    # Print main cost breakdown
    print_cost_breakdown(stats, args.llm_model, args.judge_model)

    # Print comparison table if requested
    if args.comparison:
        print_comparison_table(stats, args.llm_model)

    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Simple Cost Calculator - Show cost of last evaluation run.

Just run this script with no arguments:
    python scripts/show_cost.py

It will:
1. Find the most recent full_suite_* run
2. Calculate total cost across all test configs
3. Show you ONE number: total cost to run the entire evaluation
"""

import sys
from pathlib import Path

import pandas as pd



# Default models (change these if you use different models)
llm_model = "gemini-2.5-flash"  # Model being tested
judge_model = "gemini-2.5-flash"  # Model for evaluation metrics


# Pricing per 1M tokens (updated March 2024)
PRICING = {
    "gemini-2.5-flash": {"input_low": 0.30, "input_high": 0.60, "output": 2.50, "name": "Gemini 2.5 Flash", "tk_thrsh": 200000},    #NOTE: this is the only one I actually looked up!
    "gemini-2.0-flash": {"input_low": 0.10, "input_high": 0.10, "output": 0.40, "name": "Gemini 2.0 Flash", "tk_thrsh": 200000},
    "gemini-1.5-flash": {"input_low": 0.075, "input_high": 0.075, "output": 0.30, "name": "Gemini 1.5 Flash", "tk_thrsh": 200000},
    "gpt-4o": {"input_low": 2.50, "input_high": 2.50, "output": 10.00, "name": "GPT-4o", "tk_thrsh": 200000},
    "gpt-4o-mini": {"input_low": 0.15, "input_high": 2.50, "output": 0.60, "name": "GPT-4o Mini", "tk_thrsh": 200000},
    "claude-3.5-sonnet": {"input_low": 3.00, "input_high": 3.00, "output": 15.00, "name": "Claude 3.5 Sonnet", "tk_thrsh": 200000},
    "claude-3.5-haiku": {"input_low": 0.80, "input_high": 0.80, "output": 4.00, "name": "Claude 3.5 Haiku", "tk_thrsh": 200000},
}


def find_latest_run() -> Path | None:
    """Find the most recent full_suite_* directory.

    Returns:
        Path to most recent run, or None if not found
    """
    base_dir = Path("eval_output")
    if not base_dir.exists():
        return None

    # Find all full_suite_* directories
    run_dirs = sorted(
        base_dir.glob("full_suite_*"),
        key=lambda p: p.name,
        reverse=True,  # Most recent first
    )

    # Filter to only valid runs with CSV files
    for run_dir in run_dirs:
        csv_files = list(run_dir.glob("*/evaluation_*_detailed.csv"))
        if csv_files:
            return run_dir

    return None


def calculate_total_cost(run_dir: Path, llm_model: str, judge_model: str) -> dict:
    """Calculate total cost for all test configs in a run.

    Args:
        run_dir: Path to full_suite_* directory
        llm_model: Model key for API/LLM being tested
        judge_model: Model key for judge LLM

    Returns:
        Dictionary with cost breakdown
    """
    # Find all detailed CSV files
    csv_files = list(run_dir.glob("*/evaluation_*_detailed.csv"))

    if not csv_files:
        raise ValueError(f"No CSV files found in {run_dir}")

    # Accumulate token counts
    total_api_input = 0
    total_api_output = 0
    total_judge_input = 0
    total_judge_output = 0
    total_questions = 0

    for csv_file in csv_files:
        df = pd.read_csv(csv_file)

        # Count unique questions
        unique_questions = df.groupby(["conversation_group_id", "turn_id"]).first()
        total_questions += len(unique_questions)

        # Sum tokens    
        total_api_input += df["api_input_tokens"].sum()
        total_api_output += df["api_output_tokens"].sum()
        total_judge_input += df["judge_llm_input_tokens"].sum()
        total_judge_output += df["judge_llm_output_tokens"].sum()

    # Calculate costs
    api_cost = calculate_cost(total_api_input, total_api_output, llm_model)
    judge_cost = calculate_cost(total_judge_input, total_judge_output, judge_model)
    total_cost = api_cost + judge_cost

    return {
        "run_dir": run_dir.name,
        "num_test_configs": len(csv_files),
        "total_questions": total_questions,
        "api_input_tokens": total_api_input,
        "api_output_tokens": total_api_output,
        "judge_input_tokens": total_judge_input,
        "judge_output_tokens": total_judge_output,
        "api_cost": api_cost,
        "judge_cost": judge_cost,
        "total_cost": total_cost,
        "llm_model": PRICING[llm_model]["name"],
        "judge_model": PRICING[judge_model]["name"],
    }


def calculate_cost(tokens_input: int, tokens_output: int, model: str) -> float:
    """Calculate cost for given token usage.

    Args:
        tokens_input: Number of input tokens
        tokens_output: Number of output tokens
        model: Model identifier

    Returns:
        Total cost in USD
    """
    pricing = PRICING[model]
    cost_input = (tokens_input / 1_000_000) * pricing["input"]
    cost_output = (tokens_output / 1_000_000) * pricing["output"]
    return cost_input + cost_output


def main() -> int:
    """Main entry point."""
    print("💰 Evaluation Cost Calculator")
    print("=" * 70)
    print()

    # Find latest run
    print("📂 Finding most recent evaluation run...")
    run_dir = find_latest_run()

    if run_dir is None:
        print("❌ No evaluation runs found in eval_output/")
        print("   Run an evaluation first with: ./run_full_evaluation_suite.sh")
        return 1

    print(f"✅ Found: {run_dir.name}")
    print()


    # Calculate costs
    print("🔢 Calculating costs...")
    try:
        result = calculate_total_cost(run_dir, llm_model, judge_model)
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    print()
    print("=" * 70)
    print("COST SUMMARY")
    print("=" * 70)
    print()
    print(f"Evaluation Run:     {result['run_dir']}")
    print(f"Test Configs:       {result['num_test_configs']}")
    print(f"Total Questions:    {result['total_questions']:,}")
    print()
    print(f"LLM Model:          {result['llm_model']}")
    print(f"  Cost:             ${result['api_cost']:.2f}")
    print()
    print(f"Judge Model:        {result['judge_model']}")
    print(f"  Cost:             ${result['judge_cost']:.2f}")
    print()
    print("=" * 70)
    print(f"💵 TOTAL COST:      ${result['total_cost']:.2f}")
    print("=" * 70)
    print()

    # Per-question cost
    if result["total_questions"] > 0:
        per_question = result["total_cost"] / result["total_questions"]
        print(f"📊 Cost per question: ${per_question:.4f}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Generate eval configs from RHEL 10 benchmark, run evaluations, and create heatmap.

This script:
1. Loads rhel_10_new_and_diff_benchmark.json
2. Randomly selects 20 questions
3. Creates 3 evaluation YAML configs with jira_incorrect_answers metrics
4. Runs all 3 evaluations
5. Generates a heatmap showing questions vs scores
6. Unsets GOOGLE_APPLICATION_CREDENTIALS environment variable
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import yaml


def load_benchmark(benchmark_path: Path) -> list[dict]:
    """Load the benchmark JSON file."""
    with open(benchmark_path) as f:
        return json.load(f)


def select_random_questions(benchmark: list[dict], n: int = 20, seed: int = 42) -> list[dict]:
    """Randomly select n questions from the benchmark. 
       The answer is always 42."""
    random.seed(seed)
    return random.sample(benchmark, n)


def create_eval_yaml(
    questions: list[dict],
    output_path: Path,
    run_number: int = 1,
) -> None:
    """Create an evaluation YAML config from selected questions."""
    # Metrics matching jira_incorrect_answers.yaml
    metrics = [
        "ragas:faithfulness",
        "ragas:response_relevancy",
        "ragas:context_precision_without_reference",
        "ragas:context_relevance",
        "ragas:context_recall",
        "custom:answer_correctness",
    ]

    eval_data = []
    for i, q in enumerate(questions, 1):
        # Create conversation group
        conv_group = {
            "conversation_group_id": f"rhel10_benchmark_q{i:02d}",
            "description": f"RHEL 10 Benchmark Question {i}",
            "tag": "rhel10_benchmark",
            "turns": [
                {
                    "turn_id": "turn1",
                    "query": q["question"],
                    "response": None,  # Populated by API
                    "contexts": None,  # Populated by API
                    "expected_response": q["ground_truth_answer"],
                    "turn_metrics": metrics,
                }
            ],
        }
        eval_data.append(conv_group)

    # Write YAML
    with open(output_path, "w") as f:
        yaml.dump(eval_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"✓ Created {output_path}")


def run_evaluation(config_path: Path, system_config: Path, output_dir: Path) -> Path:
    """Run the evaluation and return the results directory."""
    print(f"\nRunning evaluation: {config_path.name}")

    # Clear LLM cache to prevent reusing cached results from previous runs
    llm_cache_dir = Path(".caches/llm_cache")
    if llm_cache_dir.exists():
        import shutil
        shutil.rmtree(llm_cache_dir)
        llm_cache_dir.mkdir(parents=True)
        print("  Cleared LLM cache for fresh evaluation...")

    cmd = [
        "uv",
        "run",
        "lightspeed-eval",
        "--system-config",
        str(system_config),
        "--eval-data",
        str(config_path),
        "--output-dir",
        str(output_dir),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Check for errors
    if result.returncode != 0:
        print(f"\n{'='*80}")
        print("EVALUATION FAILED")
        print(f"{'='*80}")
        print("\nSTDOUT:")
        print(result.stdout)
        print("\nSTDERR:")
        print(result.stderr)
        print(f"{'='*80}\n")
        raise RuntimeError(f"Evaluation failed with exit code {result.returncode}")

    # Return the output directory
    if output_dir.exists():
        return output_dir

    raise RuntimeError(f"Output directory not found: {output_dir}")


def load_results(results_dirs: list[Path]) -> pd.DataFrame:
    """Load results from multiple evaluation runs and combine into DataFrame."""
    all_data = []

    for results_dir in results_dirs:
        # Determine run number from directory name (e.g., "run1" -> 1)
        dir_name = results_dir.name
        if dir_name.startswith("run"):
            try:
                run_idx = int(dir_name[3:])
            except ValueError:
                run_idx = 0
        else:
            run_idx = 0

        # Look for detailed CSV files
        csv_files = list(results_dir.glob("**/*detailed.csv"))

        for csv_file in csv_files:
            # Read CSV
            df = pd.read_csv(csv_file)

            # Filter to only rows with valid scores (not ERROR results)
            df = df[df["score"].notna()]

            # Extract data
            for _, row in df.iterrows():
                conv_id = row["conversation_group_id"]

                # Extract question number from conv_id (e.g., "rhel10_benchmark_q01" -> 1)
                if "rhel10_benchmark_q" in conv_id:
                    q_part = conv_id.split("_q")[-1]
                    try:
                        q_num = int(q_part)
                    except ValueError:
                        q_num = 0
                else:
                    q_num = 0

                all_data.append({
                    "run": f"Run {run_idx}",
                    "question": f"Q{q_num:02d}",
                    "metric": row["metric_identifier"],
                    "score": float(row["score"]),
                })

    return pd.DataFrame(all_data)


def create_heatmap(df: pd.DataFrame, output_path: Path) -> None:
    """Create a heatmap showing questions vs scores across runs."""
    # Pivot data for heatmap
    # Average scores across all metrics for each question/run combination
    pivot_data = df.groupby(["question", "run"])["score"].mean().unstack(fill_value=0)

    # Sort questions numerically
    questions = sorted(pivot_data.index, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
    pivot_data = pivot_data.loc[questions]

    # Create figure
    plt.figure(figsize=(12, 10))

    # Create heatmap
    sns.heatmap(
        pivot_data,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        vmin=0,
        vmax=1,
        cbar_kws={"label": "Average Score"},
        linewidths=0.5,
    )

    plt.title("RHEL 10 Benchmark Evaluation - Average Scores by Question and Run", fontsize=14, pad=20)
    plt.xlabel("Evaluation Run", fontsize=12)
    plt.ylabel("Question", fontsize=12)
    plt.tight_layout()

    # Save
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"\n✓ Heatmap saved to: {output_path}")

    # Also create a detailed heatmap with individual metrics
    create_detailed_heatmap(df, output_path.parent / f"{output_path.stem}_detailed.png")


def create_detailed_heatmap(df: pd.DataFrame, output_path: Path) -> None:
    """Create a detailed heatmap showing each metric separately."""
    # Get unique metrics
    metrics = df["metric"].unique()

    # Create subplots for each metric
    n_metrics = len(metrics)
    n_cols = 2
    n_rows = (n_metrics + 1) // 2

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
    axes = axes.flatten() if n_metrics > 1 else [axes]

    for idx, metric in enumerate(metrics):
        metric_df = df[df["metric"] == metric]
        pivot_data = metric_df.pivot_table(
            values="score",
            index="question",
            columns="run",
            aggfunc="mean",
            fill_value=0
        )

        # Sort questions numerically
        questions = sorted(pivot_data.index, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
        pivot_data = pivot_data.loc[questions]

        ax = axes[idx]
        sns.heatmap(
            pivot_data,
            annot=True,
            fmt=".2f",
            cmap="RdYlGn",
            vmin=0,
            vmax=1,
            ax=ax,
            cbar_kws={"label": "Score"},
            linewidths=0.5,
        )

        # Clean up metric name for display
        display_name = metric.replace("ragas:", "").replace("custom:", "").replace("_", " ").title()
        ax.set_title(display_name, fontsize=12)
        ax.set_xlabel("Run", fontsize=10)
        ax.set_ylabel("Question", fontsize=10)

    # Hide extra subplots
    for idx in range(n_metrics, len(axes)):
        axes[idx].axis("off")

    plt.suptitle("RHEL 10 Benchmark - Detailed Metric Scores", fontsize=16, y=1.00)
    plt.tight_layout()

    # Save
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"✓ Detailed heatmap saved to: {output_path}")


def unset_google_creds() -> None:
    """Unset GOOGLE_APPLICATION_CREDENTIALS environment variable."""
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
        print("\n✓ Unset GOOGLE_APPLICATION_CREDENTIALS")


def main():
    """Main execution function."""
    # Paths
    benchmark_path = Path.home() / "Downloads" / "rhel_10_new_and_diff_benchmark.json"
    generality_dir = Path("generality")
    generality_dir.mkdir(exist_ok=True)

    config_dir = generality_dir / "configs"
    config_dir.mkdir(exist_ok=True)

    system_config = Path("config") / "system.yaml"

    # Verify benchmark file exists
    if not benchmark_path.exists():
        print(f"Error: Benchmark file not found: {benchmark_path}")
        sys.exit(1)

    print(f"Loading benchmark from: {benchmark_path}")
    benchmark = load_benchmark(benchmark_path)
    print(f"✓ Loaded {len(benchmark)} questions from benchmark")

    # Select random questions ONCE - will be used for all 3 runs
    print("\nSelecting 20 random questions...")
    selected = select_random_questions(benchmark, n=20)
    print(f"✓ Selected {len(selected)} questions (will be used for all 3 runs)")

    # Save the selected questions for reference
    questions_file = generality_dir / "selected_questions.json"
    with open(questions_file, "w") as f:
        json.dump(selected, f, indent=2)
    print(f"✓ Saved selected questions to: {questions_file}")

    # Create 1 evaluation config (same questions for all runs)
    print("\nCreating evaluation config...")
    config_path = config_dir / "rhel10_benchmark_20q.yaml"
    create_eval_yaml(selected, config_path, run_number=1)

    # Run evaluations 3 times consecutively
    print("\n" + "=" * 80)
    print("RUNNING 3 CONSECUTIVE EVALUATIONS")
    print("=" * 80)

    results_dirs = []
    for run in range(1, 4):
        print(f"\n{'='*40}")
        print(f"  RUN {run} of 3")
        print(f"{'='*40}")

        try:
            run_results_dir = generality_dir / f"run{run}"
            results_dir = run_evaluation(config_path, system_config, run_results_dir)
            results_dirs.append(results_dir)
            print(f"✓ Completed Run {run}, results saved to: {run_results_dir}")
        except Exception as e:
            print(f"✗ Failed Run {run}: {e}")
            import traceback
            traceback.print_exc()
            # Continue with other evaluations

    if not results_dirs:
        print("\nError: No evaluations completed successfully")
        sys.exit(1)

    # Load results
    print("\n" + "=" * 80)
    print("GENERATING HEATMAP")
    print("=" * 80)

    print("\nLoading results from all 3 runs...")
    df = load_results(results_dirs)

    if df.empty:
        print("Error: No results data found")
        sys.exit(1)

    print(f"✓ Loaded {len(df)} metric scores")

    # Create heatmap
    heatmap_path = generality_dir / "rhel10_benchmark_heatmap.png"

    create_heatmap(df, heatmap_path)

    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print("\nAverage scores by run:")
    run_stats = df.groupby("run")["score"].agg(["mean", "std", "min", "max"])
    print(run_stats)

    print("\nAverage scores by metric:")
    metric_stats = df.groupby("metric")["score"].agg(["mean", "std", "min", "max"])
    print(metric_stats)

    print("\nScore variance across runs (for each question):")
    question_variance = df.groupby("question")["score"].std().sort_values(ascending=False)
    print(question_variance.head(10))

    # Save summary to file
    summary_file = generality_dir / "summary_statistics.txt"
    with open(summary_file, "w") as f:
        f.write("RHEL 10 Benchmark Evaluation - Generality Test\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Questions: 20 (same questions across all 3 runs)\n")
        f.write(f"Runs: 3 consecutive evaluations\n\n")

        f.write("Average Scores by Run:\n")
        f.write(run_stats.to_string())
        f.write("\n\n")

        f.write("Average Scores by Metric:\n")
        f.write(metric_stats.to_string())
        f.write("\n\n")

        f.write("Top 10 Questions with Highest Score Variance Across Runs:\n")
        f.write(question_variance.head(10).to_string())
        f.write("\n")

    print(f"\n✓ Summary statistics saved to: {summary_file}")

    # Unset Google credentials
    unset_google_creds()

    print("\n" + "=" * 80)
    print("COMPLETE")
    print("=" * 80)
    print(f"\nAll files saved to: {generality_dir.absolute()}")
    print(f"  - Config: {config_path}")
    print(f"  - Results: run1/, run2/, run3/")
    print(f"  - Heatmap: {heatmap_path.name}")
    print(f"  - Detailed heatmap: {heatmap_path.stem}_detailed.png")
    print(f"  - Summary: {summary_file.name}")
    print(f"  - Selected questions: {questions_file.name}")


if __name__ == "__main__":
    main()

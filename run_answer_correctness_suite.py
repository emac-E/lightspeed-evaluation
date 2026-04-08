#!/usr/bin/env python3
"""Run answer correctness evaluation suite with RAG tracking.

This script runs multiple evaluation runs with full LLM responses (infer mode)
and generates heatmaps for:
- Answer correctness scores
- Score stability/variance
- RAG usage (whether tool calls happened)
- Tool usage distribution

Usage:
    python run_answer_correctness_suite.py \\
        --system-config config/system.yaml \\
        --eval-data config/chronically_failing_questions.yaml \\
        --output-dir ./answer_correctness_output \\
        --runs 5 \\
        --variant "baseline"
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def run_evaluation(
    system_config: str,
    eval_data: str,
    output_dir: Path,
    run_num: int,
) -> Path:
    """Run a single evaluation.

    Args:
        system_config: Path to system config
        eval_data: Path to evaluation data
        output_dir: Base output directory
        run_num: Run number (1-indexed)

    Returns:
        Path to the run's detailed CSV file
    """
    run_dir = output_dir / f"run_{run_num:03d}"

    cmd = [
        "uv",
        "run",
        "lightspeed-eval",
        "--system-config",
        system_config,
        "--eval-data",
        eval_data,
        "--output-dir",
        str(run_dir),
        "--cache-warmup",
    ]

    print(f"\n{'='*60}")
    print(f"Run {run_num}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        print(f"⚠️  Run {run_num} failed with exit code {result.returncode}")

    # Find the detailed CSV
    csv_files = list(run_dir.glob("*_detailed.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No detailed CSV found in {run_dir}")

    return csv_files[0]


def analyze_rag_and_tools(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze RAG usage and tool calls.

    Args:
        df: DataFrame with evaluation results

    Returns:
        DataFrame with added columns:
        - rag_used: bool, whether RAG was used (tool_calls not empty)
        - tools_called: list of tool names called
        - tool_name: primary tool name (first tool called, or "NO_RAG")
    """
    df = df.copy()

    def extract_rag_info(row):
        """Extract RAG and tool info from row."""
        tool_calls = row.get("tool_calls")

        # Check if tool_calls is empty/None
        if pd.isna(tool_calls) or tool_calls == "" or tool_calls == "[]":
            return False, [], "NO_RAG"

        # Parse tool_calls if it's a string
        if isinstance(tool_calls, str):
            import ast

            try:
                tool_calls = ast.literal_eval(tool_calls)
            except (ValueError, SyntaxError):
                return False, [], "NO_RAG"

        # Extract tool names
        if not tool_calls or not isinstance(tool_calls, list):
            return False, [], "NO_RAG"

        tools = []
        for turn in tool_calls:
            if isinstance(turn, list):
                for call in turn:
                    if isinstance(call, dict) and "tool_name" in call:
                        tools.append(call["tool_name"])

        if not tools:
            return False, [], "NO_RAG"

        return True, tools, tools[0]

    # Apply extraction
    results = df.apply(extract_rag_info, axis=1)
    df["rag_used"] = results.apply(lambda x: x[0])
    df["tools_called"] = results.apply(lambda x: x[1])
    df["tool_name"] = results.apply(lambda x: x[2])

    return df


def load_and_merge_runs(csv_files: list[Path]) -> pd.DataFrame:
    """Load all run CSVs and merge them.

    Args:
        csv_files: List of CSV file paths

    Returns:
        Merged DataFrame with run_id column
    """
    dfs = []
    for i, csv_file in enumerate(csv_files, 1):
        df = pd.read_csv(csv_file)
        df["run_id"] = i
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)


def create_answer_correctness_heatmaps(
    df: pd.DataFrame, output_dir: Path, answer_metric: str = "custom:answer_correctness"
):
    """Create heatmaps for answer correctness analysis.

    Args:
        df: DataFrame with all runs
        output_dir: Output directory for heatmaps
        answer_metric: Metric identifier for answer correctness
    """
    analysis_dir = output_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # Filter to answer correctness metric
    df_metric = df[df["metric_identifier"] == answer_metric].copy()

    if df_metric.empty:
        print(f"⚠️  No data for metric: {answer_metric}")
        return

    # Create pivot table: questions x runs
    pivot = df_metric.pivot_table(
        index="question",
        columns="run_id",
        values="score",
        aggfunc="first",
    )

    # Calculate statistics
    avg_scores = pivot.mean(axis=1)
    std_scores = pivot.std(axis=1)

    # Sort by average score (worst first)
    pivot = pivot.loc[avg_scores.sort_values().index]
    avg_scores = avg_scores.loc[pivot.index]
    std_scores = std_scores.loc[pivot.index]

    # 1. Heatmap: Average Scores
    fig, ax = plt.subplots(figsize=(10, max(8, len(pivot) * 0.4)))
    avg_matrix = avg_scores.to_frame("Average Score")

    sns.heatmap(
        avg_matrix,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        vmin=0,
        vmax=1,
        cbar_kws={"label": "Score"},
        ax=ax,
        linewidths=0.5,
        linecolor="gray",
    )

    ax.set_title(
        f"Answer Correctness - Average Scores\n{len(pivot.columns)} runs",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Questions", fontsize=12)
    ax.set_xlabel("")

    plt.tight_layout()
    plt.savefig(analysis_dir / "heatmap_answer_correctness_avg.png", dpi=300, bbox_inches="tight")
    plt.close()

    # 2. Heatmap: Score Stability (Standard Deviation)
    fig, ax = plt.subplots(figsize=(10, max(8, len(pivot) * 0.4)))
    std_matrix = std_scores.to_frame("Std Dev")

    # Invert colormap: white = stable (low std), orange = unstable (high std)
    sns.heatmap(
        std_matrix,
        annot=True,
        fmt=".3f",
        cmap="Oranges",
        vmin=0,
        vmax=std_scores.max(),
        cbar_kws={"label": "Standard Deviation"},
        ax=ax,
        linewidths=0.5,
        linecolor="gray",
    )

    ax.set_title(
        f"Answer Correctness - Stability (Std Dev)\n{len(pivot.columns)} runs",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Questions", fontsize=12)
    ax.set_xlabel("")

    plt.tight_layout()
    plt.savefig(analysis_dir / "heatmap_answer_correctness_stability.png", dpi=300, bbox_inches="tight")
    plt.close()

    # 3. Heatmap: Individual Run Scores
    fig, ax = plt.subplots(figsize=(max(12, len(pivot.columns) * 1.5), max(8, len(pivot) * 0.4)))

    sns.heatmap(
        pivot,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        vmin=0,
        vmax=1,
        cbar_kws={"label": "Score"},
        ax=ax,
        linewidths=0.5,
        linecolor="gray",
    )

    ax.set_title(
        "Answer Correctness - All Runs",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Questions", fontsize=12)
    ax.set_xlabel("Run ID", fontsize=12)

    plt.tight_layout()
    plt.savefig(analysis_dir / "heatmap_answer_correctness_all_runs.png", dpi=300, bbox_inches="tight")
    plt.close()

    print(f"✅ Generated answer correctness heatmaps in {analysis_dir}")


def create_rag_analysis_heatmaps(df: pd.DataFrame, output_dir: Path):
    """Create heatmaps for RAG usage analysis.

    Args:
        df: DataFrame with all runs (must have rag_used, tool_name columns)
        output_dir: Output directory for heatmaps
    """
    analysis_dir = output_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # 1. RAG Usage Rate by Question
    rag_pivot = df.pivot_table(
        index="question",
        columns="run_id",
        values="rag_used",
        aggfunc="first",
    )

    # Calculate RAG usage rate (percentage across runs)
    rag_rate = (rag_pivot.sum(axis=1) / rag_pivot.count(axis=1) * 100).to_frame("RAG Usage %")

    # Sort by RAG usage (lowest first to highlight RAG bypass)
    rag_rate = rag_rate.sort_values("RAG Usage %")

    fig, ax = plt.subplots(figsize=(10, max(8, len(rag_rate) * 0.4)))

    sns.heatmap(
        rag_rate,
        annot=True,
        fmt=".1f",
        cmap="RdYlGn",
        vmin=0,
        vmax=100,
        cbar_kws={"label": "RAG Usage (%)"},
        ax=ax,
        linewidths=0.5,
        linecolor="gray",
    )

    ax.set_title(
        f"RAG Usage Rate by Question\n{len(rag_pivot.columns)} runs",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Questions", fontsize=12)
    ax.set_xlabel("")

    plt.tight_layout()
    plt.savefig(analysis_dir / "heatmap_rag_usage.png", dpi=300, bbox_inches="tight")
    plt.close()

    # 2. Tool Distribution by Question
    # Count each tool type per question
    tool_counts = df.groupby(["question", "tool_name"]).size().unstack(fill_value=0)

    # Calculate percentages
    tool_pcts = tool_counts.div(tool_counts.sum(axis=1), axis=0) * 100

    # Sort by NO_RAG percentage (descending)
    if "NO_RAG" in tool_pcts.columns:
        tool_pcts = tool_pcts.sort_values("NO_RAG", ascending=False)

    fig, ax = plt.subplots(figsize=(max(12, len(tool_pcts.columns) * 2), max(8, len(tool_pcts) * 0.4)))

    sns.heatmap(
        tool_pcts,
        annot=True,
        fmt=".1f",
        cmap="YlOrRd",
        vmin=0,
        vmax=100,
        cbar_kws={"label": "Usage (%)"},
        ax=ax,
        linewidths=0.5,
        linecolor="gray",
    )

    ax.set_title(
        "Tool Usage Distribution by Question",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Questions", fontsize=12)
    ax.set_xlabel("Tool Name", fontsize=12)

    plt.tight_layout()
    plt.savefig(analysis_dir / "heatmap_tool_distribution.png", dpi=300, bbox_inches="tight")
    plt.close()

    print(f"✅ Generated RAG analysis heatmaps in {analysis_dir}")


def generate_summary_report(df: pd.DataFrame, output_dir: Path, answer_metric: str):
    """Generate text summary report.

    Args:
        df: DataFrame with all runs
        output_dir: Output directory
        answer_metric: Answer correctness metric identifier
    """
    analysis_dir = output_dir / "analysis"
    report_path = analysis_dir / "summary_report.txt"

    df_metric = df[df["metric_identifier"] == answer_metric]

    with open(report_path, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("Answer Correctness Evaluation Suite - Summary Report\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Total Runs: {df['run_id'].nunique()}\n")
        f.write(f"Total Questions: {df['question'].nunique()}\n")
        f.write(f"Answer Metric: {answer_metric}\n\n")

        # Answer correctness statistics
        if not df_metric.empty:
            pivot = df_metric.pivot_table(
                index="question", columns="run_id", values="score", aggfunc="first"
            )
            avg_scores = pivot.mean(axis=1)
            std_scores = pivot.std(axis=1)

            f.write("-" * 80 + "\n")
            f.write("Answer Correctness Statistics\n")
            f.write("-" * 80 + "\n")
            f.write(f"Average Score (all questions): {avg_scores.mean():.3f}\n")
            f.write(f"Median Score: {avg_scores.median():.3f}\n")
            f.write(f"Std Dev (across questions): {avg_scores.std():.3f}\n\n")

            f.write("Top 5 Best Questions (by average score):\n")
            for i, (q, score) in enumerate(avg_scores.nlargest(5).items(), 1):
                f.write(f"  {i}. [{score:.3f}] {q[:70]}...\n")

            f.write("\nTop 5 Worst Questions (by average score):\n")
            for i, (q, score) in enumerate(avg_scores.nsmallest(5).items(), 1):
                f.write(f"  {i}. [{score:.3f}] {q[:70]}...\n")

            f.write("\nMost Unstable Questions (by std dev):\n")
            for i, (q, std) in enumerate(std_scores.nlargest(5).items(), 1):
                f.write(f"  {i}. [σ={std:.3f}] {q[:70]}...\n")

        # RAG usage statistics
        if "rag_used" in df.columns:
            f.write("\n" + "-" * 80 + "\n")
            f.write("RAG Usage Statistics\n")
            f.write("-" * 80 + "\n")

            total_evals = len(df)
            rag_used_count = df["rag_used"].sum()
            rag_rate = rag_used_count / total_evals * 100

            f.write(f"RAG Used: {rag_used_count}/{total_evals} ({rag_rate:.1f}%)\n")
            f.write(f"RAG Bypassed: {total_evals - rag_used_count}/{total_evals} ({100-rag_rate:.1f}%)\n\n")

            # Per-question RAG usage
            rag_by_q = df.groupby("question")["rag_used"].agg(["sum", "count"])
            rag_by_q["rate"] = rag_by_q["sum"] / rag_by_q["count"] * 100
            rag_by_q = rag_by_q.sort_values("rate")

            f.write("Questions with Highest RAG Bypass (lowest RAG usage):\n")
            for i, (q, row) in enumerate(rag_by_q.head(5).iterrows(), 1):
                f.write(f"  {i}. [{row['rate']:.1f}% RAG] {q[:70]}...\n")

        # Tool usage statistics
        if "tool_name" in df.columns:
            f.write("\n" + "-" * 80 + "\n")
            f.write("Tool Usage Statistics\n")
            f.write("-" * 80 + "\n")

            tool_counts = df["tool_name"].value_counts()
            for tool, count in tool_counts.items():
                pct = count / len(df) * 100
                f.write(f"  {tool}: {count} ({pct:.1f}%)\n")

    print(f"✅ Generated summary report: {report_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run answer correctness evaluation suite with RAG tracking"
    )
    parser.add_argument(
        "--system-config",
        required=True,
        help="Path to system config (must use infer mode for LLM responses)",
    )
    parser.add_argument(
        "--eval-data",
        required=True,
        help="Path to evaluation data config",
    )
    parser.add_argument(
        "--output-dir",
        default="./answer_correctness_output",
        help="Base output directory",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of evaluation runs to execute",
    )
    parser.add_argument(
        "--variant",
        default=None,
        help="Optional variant name (appended to output dir)",
    )
    parser.add_argument(
        "--answer-metric",
        default="custom:answer_correctness",
        help="Answer correctness metric identifier",
    )

    args = parser.parse_args()

    # Setup output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suite_name = f"suite_{timestamp}"
    if args.variant:
        suite_name += f"_{args.variant}"

    output_dir = Path(args.output_dir) / suite_name
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*80}")
    print(f"Answer Correctness Evaluation Suite")
    print(f"{'='*80}")
    print(f"System Config: {args.system_config}")
    print(f"Eval Data: {args.eval_data}")
    print(f"Output Dir: {output_dir}")
    print(f"Runs: {args.runs}")
    print(f"Answer Metric: {args.answer_metric}")
    if args.variant:
        print(f"Variant: {args.variant}")
    print(f"{'='*80}\n")

    # Run evaluations
    csv_files = []
    for run_num in range(1, args.runs + 1):
        try:
            csv_file = run_evaluation(
                args.system_config,
                args.eval_data,
                output_dir,
                run_num,
            )
            csv_files.append(csv_file)
            print(f"✓ Run {run_num} complete: {csv_file}")
        except Exception as e:
            print(f"✗ Run {run_num} failed: {e}")
            sys.exit(1)

    # Merge and analyze
    print(f"\n{'='*80}")
    print(f"Analysis")
    print(f"{'='*80}\n")

    df_all = load_and_merge_runs(csv_files)

    # Analyze RAG and tools
    df_all = analyze_rag_and_tools(df_all)

    # Create merged CSV
    merged_csv = output_dir / f"all_runs.csv"
    df_all.to_csv(merged_csv, index=False)
    print(f"✅ Merged data saved: {merged_csv}")

    # Generate heatmaps
    create_answer_correctness_heatmaps(df_all, output_dir, args.answer_metric)
    create_rag_analysis_heatmaps(df_all, output_dir)

    # Generate summary report
    generate_summary_report(df_all, output_dir, args.answer_metric)

    print(f"\n{'='*80}")
    print(f"Suite Complete!")
    print(f"{'='*80}")
    print(f"Output directory: {output_dir}")
    print(f"Analysis directory: {output_dir / 'analysis'}")


if __name__ == "__main__":
    main()

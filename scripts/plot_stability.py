#!/usr/bin/env python3
"""Plot MCP Retrieval Suite Stability - Generate Heatmaps.

This script analyzes multiple runs from run_mcp_retrieval_suite.sh and generates:
1. Average Score Heatmap: Shows mean scores (green=high, red=low)
2. Stability Heatmap: Shows standard deviation (white=stable, orange=unstable)

Usage:
    python scripts/plot_stability.py --input-dir mcp_retrieval_output/suite_20260331_150000 \
                                     --output-dir mcp_retrieval_output/suite_20260331_150000/analysis
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def load_all_runs(input_dir: Path) -> pd.DataFrame:
    """Load all run_*.csv files from the input directory.

    Args:
        input_dir: Directory containing run_001.csv, run_002.csv, etc.

    Returns:
        DataFrame with all runs combined, including 'run_number' column
    """
    csv_files = sorted(input_dir.glob("run_*.csv"))

    if not csv_files:
        print(f"❌ Error: No run_*.csv files found in {input_dir}")
        sys.exit(1)

    print(f"📊 Found {len(csv_files)} run files")

    dfs = []
    for csv_file in csv_files:
        # Extract run number from filename (run_001.csv -> 1)
        run_number = int(csv_file.stem.split("_")[1])
        df = pd.read_csv(csv_file)
        df["run_number"] = run_number
        dfs.append(df)
        print(f"   - {csv_file.name}: {len(df)} rows")

    combined = pd.concat(dfs, ignore_index=True)
    print(f"✓ Loaded {len(combined)} total rows from {len(csv_files)} runs\n")

    return combined


def create_pivot_tables(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create pivot tables for average scores and standard deviation.

    Args:
        df: Combined dataframe from all runs

    Returns:
        Tuple of (mean_pivot, std_pivot) DataFrames
    """
    # Create question identifier (conversation_group_id/turn_id)
    df["question_id"] = df["conversation_group_id"] + "/" + df["turn_id"]

    # Group by question and metric, calculate mean and std across runs
    grouped = (
        df.groupby(["question_id", "metric_identifier"])["score"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )

    # Create pivot tables
    mean_pivot = grouped.pivot(
        index="question_id", columns="metric_identifier", values="mean"
    )
    std_pivot = grouped.pivot(
        index="question_id", columns="metric_identifier", values="std"
    )

    # Fill NaN with 0 for stability (missing = no variance = stable)
    std_pivot = std_pivot.fillna(0.0)

    print(f"📈 Pivot tables created:")
    print(f"   - Questions: {len(mean_pivot)}")
    print(f"   - Metrics: {len(mean_pivot.columns)}")
    print(f"   - Total cells: {mean_pivot.size}\n")

    return mean_pivot, std_pivot


def plot_score_heatmap(
    mean_pivot: pd.DataFrame, output_dir: Path, figsize: tuple = (12, 10)
) -> None:
    """Generate average score heatmap (green=high, red=low).

    Args:
        mean_pivot: Pivot table with average scores
        output_dir: Directory to save the plot
        figsize: Figure size (width, height)
    """
    plt.figure(figsize=figsize)

    # Create heatmap with RdYlGn colormap (red=low, yellow=mid, green=high)
    sns.heatmap(
        mean_pivot,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        vmin=0.0,
        vmax=1.0,
        cbar_kws={"label": "Average Score"},
        linewidths=0.5,
        linecolor="gray",
    )

    plt.title("MCP Retrieval Quality - Average Scores Across Runs", fontsize=14, pad=20)
    plt.xlabel("Metric", fontsize=12)
    plt.ylabel("Question", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()

    output_path = output_dir / "heatmap_scores.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"✓ Saved average score heatmap: {output_path}")
    plt.close()


def plot_stability_heatmap(
    std_pivot: pd.DataFrame, output_dir: Path, figsize: tuple = (12, 10)
) -> None:
    """Generate stability heatmap (white=stable, orange=unstable).

    Args:
        std_pivot: Pivot table with standard deviations
        output_dir: Directory to save the plot
        figsize: Figure size (width, height)
    """
    plt.figure(figsize=figsize)

    # Create heatmap with white->orange colormap (white=stable, orange=unstable)
    sns.heatmap(
        std_pivot,
        annot=True,
        fmt=".3f",
        cmap="Oranges",
        vmin=0.0,
        vmax=0.3,  # Cap at 0.3 std deviation for better color range
        cbar_kws={"label": "Standard Deviation (σ)"},
        linewidths=0.5,
        linecolor="gray",
    )

    plt.title(
        "MCP Retrieval Stability - Score Variance Across Runs", fontsize=14, pad=20
    )
    plt.xlabel("Metric", fontsize=12)
    plt.ylabel("Question", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()

    output_path = output_dir / "heatmap_stability.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"✓ Saved stability heatmap: {output_path}")
    plt.close()


def print_summary_statistics(mean_pivot: pd.DataFrame, std_pivot: pd.DataFrame) -> None:
    """Print summary statistics about scores and stability.

    Args:
        mean_pivot: Average scores pivot table
        std_pivot: Standard deviation pivot table
    """
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    for metric in mean_pivot.columns:
        mean_scores = mean_pivot[metric].dropna()
        std_scores = std_pivot[metric].dropna()

        if len(mean_scores) == 0:
            continue

        print(f"\n{metric}:")
        print(f"  Average Score: {mean_scores.mean():.3f} (±{mean_scores.std():.3f})")
        print(f"  Score Range: [{mean_scores.min():.3f}, {mean_scores.max():.3f}]")
        print(f"  Avg Stability (σ): {std_scores.mean():.3f}")
        print(
            f"  Most Stable: {std_scores.min():.3f} (question: {std_scores.idxmin()})"
        )
        print(
            f"  Least Stable: {std_scores.max():.3f} (question: {std_scores.idxmax()})"
        )

    print("\n" + "=" * 80 + "\n")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate heatmaps from MCP retrieval suite runs"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Input directory containing run_*.csv files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for heatmap images",
    )
    parser.add_argument(
        "--figsize",
        type=str,
        default="12,10",
        help="Figure size as 'width,height' (default: 12,10)",
    )

    args = parser.parse_args()

    # Parse figsize
    try:
        width, height = map(int, args.figsize.split(","))
        figsize = (width, height)
    except ValueError:
        print(f"❌ Error: Invalid figsize '{args.figsize}'. Use format 'width,height'")
        sys.exit(1)

    # Validate input directory
    if not args.input_dir.exists():
        print(f"❌ Error: Input directory does not exist: {args.input_dir}")
        sys.exit(1)

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🎯 MCP Retrieval Suite Stability Analysis")
    print(f"   Input: {args.input_dir}")
    print(f"   Output: {args.output_dir}\n")

    # Load data
    df = load_all_runs(args.input_dir)

    # Create pivot tables
    mean_pivot, std_pivot = create_pivot_tables(df)

    # Generate heatmaps
    print("📊 Generating heatmaps...")
    plot_score_heatmap(mean_pivot, args.output_dir, figsize)
    plot_stability_heatmap(std_pivot, args.output_dir, figsize)

    # Print summary statistics
    print_summary_statistics(mean_pivot, std_pivot)

    print(f"✅ Complete! Heatmaps saved to {args.output_dir}")


if __name__ == "__main__":
    main()

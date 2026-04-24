#!/usr/bin/env python3
"""Generate heatmaps from existing generality test results."""

import os
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Import the functions from the main script
import sys
sys.path.insert(0, str(Path(__file__).parent))

from rhel10_benchmark_eval import load_results, create_heatmap

def main():
    """Generate heatmaps from existing results."""
    generality_dir = Path("generality")

    # Load results from all 3 runs
    results_dirs = [
        generality_dir / "run1",
        generality_dir / "run2",
        generality_dir / "run3",
    ]

    print("Loading results from all 3 runs...")
    df = load_results(results_dirs)

    if df.empty:
        print("Error: No results data found")
        return

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
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
        print("\n✓ Unset GOOGLE_APPLICATION_CREDENTIALS")

    print("\n" + "=" * 80)
    print("COMPLETE")
    print("=" * 80)
    print(f"\nHeatmap: {heatmap_path}")
    print(f"Detailed heatmap: {heatmap_path.parent / f'{heatmap_path.stem}_detailed.png'}")
    print(f"Summary: {summary_file}")

if __name__ == "__main__":
    main()

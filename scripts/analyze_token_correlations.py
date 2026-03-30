#!/usr/bin/env python3
"""Analyze correlation between token usage and metric scores.

This script explores relationships like:
- Do larger contexts (more input tokens) lead to better scores?
- Does response length correlate with correctness?
- Are there optimal token ranges for different metrics?
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def load_latest_run() -> pd.DataFrame:
    """Load data from the most recent evaluation run."""
    base_dir = Path("eval_output")

    # Find most recent run
    all_runs = sorted(
        [d for d in base_dir.glob("full_suite_*") if d.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )

    for run_dir in all_runs:
        csv_files = list(run_dir.glob("*/evaluation_*_detailed.csv"))
        if csv_files:
            print(f"Loading data from: {run_dir.name}")
            all_data = []
            for csv_file in csv_files:
                test_config = csv_file.parent.name
                df = pd.read_csv(csv_file)
                df["test_config"] = test_config
                all_data.append(df)

            combined = pd.concat(all_data, ignore_index=True)
            print(f"  Loaded {len(combined)} rows from {len(csv_files)} test configs")
            return combined

    raise ValueError("No evaluation runs found")


def calculate_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate correlation between token metrics and scores."""
    token_cols = [
        "api_input_tokens",
        "api_output_tokens",
        "judge_llm_input_tokens",
        "judge_llm_output_tokens",
    ]

    # Filter to rows with complete data
    complete = df[df["score"].notna() & df["api_input_tokens"].notna()].copy()

    correlations = []
    for metric in complete["metric_identifier"].unique():
        metric_data = complete[complete["metric_identifier"] == metric]

        for token_col in token_cols:
            if metric_data[token_col].notna().sum() > 10:  # Need enough data
                corr = metric_data[["score", token_col]].corr().iloc[0, 1]
                correlations.append({
                    "metric": metric,
                    "token_type": token_col,
                    "correlation": corr,
                    "sample_size": len(metric_data),
                })

    return pd.DataFrame(correlations)


def analyze_token_bins(df: pd.DataFrame, metric: str, token_col: str, num_bins: int = 5) -> pd.DataFrame:
    """Analyze scores across token usage bins."""
    metric_data = df[df["metric_identifier"] == metric].copy()

    if len(metric_data) < 10:
        return pd.DataFrame()

    # Create bins
    metric_data["token_bin"] = pd.qcut(
        metric_data[token_col],
        q=num_bins,
        labels=[f"Q{i+1}" for i in range(num_bins)],
        duplicates="drop",
    )

    # Calculate stats per bin
    bin_stats = metric_data.groupby("token_bin", observed=True).agg(
        mean_score=("score", "mean"),
        median_score=("score", "median"),
        std_score=("score", "std"),
        count=("score", "count"),
        mean_tokens=(token_col, "mean"),
        min_tokens=(token_col, "min"),
        max_tokens=(token_col, "max"),
    ).reset_index()

    return bin_stats


def plot_correlation_heatmap(corr_df: pd.DataFrame, output_dir: Path) -> None:
    """Create heatmap of correlations."""
    # Pivot to create matrix
    pivot = corr_df.pivot(index="metric", columns="token_type", values="correlation")

    plt.figure(figsize=(12, 8))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".3f",
        cmap="RdYlGn",
        center=0,
        vmin=-1,
        vmax=1,
        cbar_kws={"label": "Correlation"},
    )
    plt.title("Correlation: Token Usage vs Metric Scores", fontsize=14, fontweight="bold")
    plt.xlabel("Token Type", fontsize=12)
    plt.ylabel("Metric", fontsize=12)
    plt.tight_layout()

    output_file = output_dir / "token_score_correlations.png"
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ Saved correlation heatmap: {output_file.name}")


def plot_token_vs_score_scatter(
    df: pd.DataFrame,
    metric: str,
    token_col: str,
    output_dir: Path,
) -> None:
    """Create scatter plot of tokens vs scores for a specific metric."""
    metric_data = df[df["metric_identifier"] == metric].copy()

    if len(metric_data) < 10:
        return

    _, ax = plt.subplots(figsize=(10, 6))

    # Scatter plot
    ax.scatter(
        metric_data[token_col],
        metric_data["score"],
        alpha=0.5,
        s=50,
    )

    # Add trend line
    z = np.polyfit(metric_data[token_col], metric_data["score"], 1)
    p = np.poly1d(z)
    x_trend = np.linspace(metric_data[token_col].min(), metric_data[token_col].max(), 100)
    ax.plot(x_trend, p(x_trend), "r--", alpha=0.8, linewidth=2, label="Trend")

    # Formatting
    ax.set_xlabel(token_col.replace("_", " ").title(), fontsize=12)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title(f"{metric}: {token_col.replace('_', ' ').title()} vs Score", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend()

    plt.tight_layout()
    safe_metric = metric.replace(":", "_").replace("/", "_")
    safe_token = token_col.replace("_", "-")
    output_file = output_dir / f"scatter_{safe_metric}_{safe_token}.png"
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close()


def plot_token_bins(bin_stats: pd.DataFrame, metric: str, token_col: str, output_dir: Path) -> None:
    """Plot score trends across token bins."""
    if len(bin_stats) == 0:
        return

    _, ax = plt.subplots(figsize=(10, 6))

    x_positions = range(len(bin_stats))

    # Bar plot of mean scores
    ax.bar(
        x_positions,
        bin_stats["mean_score"],
        alpha=0.7,
        color="steelblue",
        label="Mean Score",
    )

    # Error bars for std dev
    ax.errorbar(
        x_positions,
        bin_stats["mean_score"],
        yerr=bin_stats["std_score"],
        fmt="none",
        ecolor="black",
        capsize=5,
        alpha=0.5,
    )

    # Formatting
    ax.set_xlabel("Token Usage Quantile", fontsize=12)
    ax.set_ylabel("Mean Score", fontsize=12)
    ax.set_title(
        f"{metric}: Score by {token_col.replace('_', ' ').title()} Quantile",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x_positions)
    ax.set_xticklabels(bin_stats["token_bin"])
    ax.grid(True, alpha=0.3, axis="y")
    ax.legend()

    # Add token range labels
    for i, row in bin_stats.iterrows():
        ax.text(
            i,
            -0.05,
            f"{int(row['min_tokens'])}-{int(row['max_tokens'])}",
            ha="center",
            va="top",
            fontsize=8,
            rotation=0,
        )

    plt.tight_layout()
    safe_metric = metric.replace(":", "_").replace("/", "_")
    safe_token = token_col.replace("_", "-")
    output_file = output_dir / f"bins_{safe_metric}_{safe_token}.png"
    plt.savefig(output_file, dpi=150, bbox_inches="tight")
    plt.close()


def generate_summary_report(df: pd.DataFrame, corr_df: pd.DataFrame, output_file: Path) -> None:
    """Generate text summary of token-score relationships."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("TOKEN USAGE vs METRIC SCORE CORRELATION ANALYSIS\n")
        f.write("=" * 80 + "\n\n")

        # Overall token stats
        f.write("OVERALL TOKEN USAGE STATISTICS\n")
        f.write("-" * 80 + "\n")
        for col in ["api_input_tokens", "api_output_tokens", "judge_llm_input_tokens", "judge_llm_output_tokens"]:
            if col in df.columns and df[col].notna().sum() > 0:
                f.write(f"\n{col}:\n")
                f.write(f"  Mean:   {df[col].mean():>10.1f}\n")
                f.write(f"  Median: {df[col].median():>10.1f}\n")
                f.write(f"  Min:    {df[col].min():>10.1f}\n")
                f.write(f"  Max:    {df[col].max():>10.1f}\n")
                f.write(f"  Std:    {df[col].std():>10.1f}\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("CORRELATION ANALYSIS\n")
        f.write("=" * 80 + "\n\n")

        # Top positive correlations
        f.write("Strongest POSITIVE Correlations (more tokens → higher scores):\n")
        f.write("-" * 80 + "\n")
        top_positive = corr_df.nlargest(10, "correlation")
        for _, row in top_positive.iterrows():
            f.write(f"  {row['metric']:40s} {row['token_type']:25s} r={row['correlation']:+.3f} (n={row['sample_size']})\n")

        f.write("\n")
        f.write("Strongest NEGATIVE Correlations (more tokens → lower scores):\n")
        f.write("-" * 80 + "\n")
        top_negative = corr_df.nsmallest(10, "correlation")
        for _, row in top_negative.iterrows():
            f.write(f"  {row['metric']:40s} {row['token_type']:25s} r={row['correlation']:+.3f} (n={row['sample_size']})\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("INTERPRETATION GUIDE\n")
        f.write("=" * 80 + "\n\n")
        f.write("Correlation Values:\n")
        f.write("  +0.7 to +1.0: Strong positive (more tokens → better scores)\n")
        f.write("  +0.3 to +0.7: Moderate positive\n")
        f.write("  -0.3 to +0.3: Weak/no correlation\n")
        f.write("  -0.7 to -0.3: Moderate negative (more tokens → worse scores)\n")
        f.write("  -1.0 to -0.7: Strong negative\n\n")

        f.write("Token Types:\n")
        f.write("  api_input_tokens:  Context size (retrieved RAG chunks)\n")
        f.write("  api_output_tokens: Response length from LLM\n")
        f.write("  judge_llm_input:   Context + response for evaluation\n")
        f.write("  judge_llm_output:  Judge's reasoning length\n\n")

    print(f"  ✓ Saved summary report: {output_file.name}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze token usage vs metric score correlations")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: auto-generated in latest run)",
    )

    args = parser.parse_args()

    print("📊 Token-Score Correlation Analysis")
    print("=" * 80)

    # Load data
    print("\n📂 Loading evaluation data...")
    df = load_latest_run()

    # Set output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        base_dir = Path("eval_output")
        latest_run = sorted([d for d in base_dir.glob("full_suite_*") if d.is_dir()], reverse=True)[0]
        output_dir = latest_run / "token_analysis"

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n📁 Output directory: {output_dir}")

    # Calculate correlations
    print("\n🔢 Calculating correlations...")
    corr_df = calculate_correlations(df)
    print(f"  ✓ Calculated {len(corr_df)} correlation values")

    # Save correlation data
    corr_df.to_csv(output_dir / "token_correlations.csv", index=False)

    # Generate visualizations
    print("\n📊 Generating visualizations...")

    # Heatmap
    plot_correlation_heatmap(corr_df, output_dir)

    # Scatter plots for top correlations
    top_pairs = corr_df.nlargest(5, "correlation", keep="all")
    for _, row in top_pairs.iterrows():
        plot_token_vs_score_scatter(df, row["metric"], row["token_type"], output_dir)

    # Bin analysis for interesting metrics
    for metric in ["ragas:context_relevance", "ragas:faithfulness", "custom:answer_correctness"]:
        if metric in df["metric_identifier"].values:
            bin_stats = analyze_token_bins(df, metric, "api_input_tokens")
            if not bin_stats.empty:
                plot_token_bins(bin_stats, metric, "api_input_tokens", output_dir)

    # Generate summary report
    print("\n📝 Generating summary report...")
    generate_summary_report(df, corr_df, output_dir / "token_analysis_summary.txt")

    print("\n" + "=" * 80)
    print("✅ Analysis Complete!")
    print("=" * 80)
    print(f"\nOutput files:")
    print(f"  📊 Correlation CSV:  {output_dir / 'token_correlations.csv'}")
    print(f"  🔥 Heatmap:          {output_dir / 'token_score_correlations.png'}")
    print(f"  📈 Scatter plots:    {output_dir / 'scatter_*.png'}")
    print(f"  📊 Bin analysis:     {output_dir / 'bins_*.png'}")
    print(f"  📄 Summary report:   {output_dir / 'token_analysis_summary.txt'}")

    print(f"\nView summary:")
    print(f"  cat {output_dir / 'token_analysis_summary.txt'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Cross-Metric Correlation Analysis for LightSpeed Evaluation Framework.

This script analyzes correlations between different ragas metrics to:
- Validate that metrics measure what they claim
- Identify redundant metrics
- Detect anomalies where metrics disagree
- Recommend threshold calibrations
- Find cases where LLM bypasses RAG retrieval

Requirements:
- Minimum 2 data points (conversations/turns) for correlation analysis
- Recommended: 10+ data points for meaningful statistical analysis

Usage:
    python scripts/analyze_metric_correlations.py \\
        --input eval_output/evaluation_20260317_142455_detailed.csv \\
        --output analysis_output/

    # Multiple evaluation runs
    python scripts/analyze_metric_correlations.py \\
        --input eval_output/evaluation_20260317_142455_detailed.csv \\
                eval_output/evaluation_20260317_124528_detailed.csv \\
        --output analysis_output/ \\
        --compare-runs
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import kendalltau, pearsonr, spearmanr

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MetricCorrelationAnalyzer:
    """Analyzes correlations between evaluation metrics."""

    def __init__(self, csv_files: list[str], output_dir: str):
        """Initialize analyzer.

        Args:
            csv_files: List of paths to evaluation CSV files
            output_dir: Directory to save analysis outputs
        """
        self.csv_files = csv_files
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dataframes: dict[str, pd.DataFrame] = {}
        self.pivot_tables: dict[str, pd.DataFrame] = {}

    def load_data(self) -> None:
        """Load and preprocess evaluation data from CSV files."""
        logger.info(f"Loading {len(self.csv_files)} evaluation files...")

        for csv_file in self.csv_files:
            file_path = Path(csv_file)
            if not file_path.exists():
                logger.error(f"File not found: {csv_file}")
                continue

            logger.info(f"Loading {file_path.name}...")
            df = pd.read_csv(csv_file)

            # Filter to only rows with scores (exclude ERROR results without scores)
            df_scores = df[df["score"].notna()].copy()

            # Pivot to get one row per turn with columns for each metric
            pivot = df_scores.pivot_table(
                index=["conversation_group_id", "turn_id"],
                columns="metric_identifier",
                values="score",
                aggfunc="first",
            )

            run_name = file_path.stem
            self.dataframes[run_name] = df_scores
            self.pivot_tables[run_name] = pivot

            logger.info(
                f"  Loaded {len(df_scores)} score entries, "
                f"{len(pivot)} unique turns, "
                f"{len(pivot.columns)} metrics"
            )

    def calculate_correlations(self, run_name: str) -> dict[str, pd.DataFrame]:
        """Calculate correlation matrices using multiple methods.

        Args:
            run_name: Name of the evaluation run to analyze

        Returns:
            Dictionary with correlation matrices (pearson, spearman, kendall)
        """
        logger.info(f"Calculating correlations for {run_name}...")

        pivot = self.pivot_tables[run_name]

        # Check minimum data requirements
        if len(pivot) < 2:
            logger.warning(
                f"⚠️ Insufficient data for correlation analysis: "
                f"{len(pivot)} data points (need at least 2)"
            )
            logger.warning(f"   Skipping correlation calculations for {run_name}")
            return {}

        # Calculate different correlation types
        correlations = {
            "pearson": pivot.corr(method="pearson"),  # Linear relationships
            "spearman": pivot.corr(method="spearman"),  # Monotonic relationships
            "kendall": pivot.corr(method="kendall"),  # Rank-based
        }

        # Save to CSV
        for method, corr_matrix in correlations.items():
            output_file = self.output_dir / f"{run_name}_correlation_{method}.csv"
            corr_matrix.to_csv(output_file)
            logger.info(f"  Saved {method} correlation to {output_file}")

        return correlations

    def create_correlation_heatmap(
        self, run_name: str, correlations: dict[str, pd.DataFrame]
    ) -> None:
        """Create correlation heatmap visualizations.

        Args:
            run_name: Name of the evaluation run
            correlations: Dictionary of correlation matrices
        """
        if not correlations:
            logger.warning(f"  Skipping heatmap for {run_name} (no correlation data)")
            return

        logger.info(f"Creating correlation heatmaps for {run_name}...")

        # Create figure with subplots for each correlation type
        fig, axes = plt.subplots(1, 3, figsize=(20, 6))
        fig.suptitle(
            f"Metric Correlations - {run_name}", fontsize=16, fontweight="bold"
        )

        for idx, (method, corr_matrix) in enumerate(correlations.items()):
            sns.heatmap(
                corr_matrix,
                annot=True,
                fmt=".3f",
                cmap="coolwarm",
                center=0,
                vmin=-1,
                vmax=1,
                square=True,
                ax=axes[idx],
                cbar_kws={"label": "Correlation Coefficient"},
            )
            axes[idx].set_title(f"{method.capitalize()} Correlation", fontsize=12)
            axes[idx].tick_params(axis="x", rotation=45, labelsize=8)
            axes[idx].tick_params(axis="y", rotation=0, labelsize=8)

        plt.tight_layout()

        output_file = self.output_dir / f"{run_name}_correlation_heatmap.png"
        plt.savefig(output_file, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info(f"  Saved heatmap to {output_file}")

    def create_scatter_plots(self, run_name: str) -> None:
        """Create scatter plots for all metric pairs.

        Args:
            run_name: Name of the evaluation run
        """
        pivot = self.pivot_tables[run_name]

        # Check minimum data requirements
        if len(pivot) < 2:
            logger.warning(f"  Skipping scatter plots for {run_name} (need at least 2 data points)")
            return

        logger.info(f"Creating scatter plots for {run_name}...")

        metrics = list(pivot.columns)
        n_metrics = len(metrics)

        # Create pairwise scatter plots
        fig, axes = plt.subplots(n_metrics, n_metrics, figsize=(20, 20))
        fig.suptitle(
            f"Metric Pairwise Relationships - {run_name}",
            fontsize=16,
            fontweight="bold",
        )

        for i, metric_x in enumerate(metrics):
            for j, metric_y in enumerate(metrics):
                ax = axes[i, j]

                if i == j:
                    # Diagonal: histogram of single metric
                    pivot[metric_x].dropna().hist(ax=ax, bins=20, alpha=0.7, color="blue")
                    ax.set_ylabel("Frequency")
                    ax.set_title(metric_x.split(":")[-1], fontsize=8)
                else:
                    # Off-diagonal: scatter plot
                    valid_data = pivot[[metric_x, metric_y]].dropna()
                    if len(valid_data) > 1:  # Need at least 2 points for correlation
                        ax.scatter(
                            valid_data[metric_x],
                            valid_data[metric_y],
                            alpha=0.5,
                            s=20,
                        )

                        # Add trend line
                        z = np.polyfit(valid_data[metric_x], valid_data[metric_y], 1)
                        p = np.poly1d(z)
                        ax.plot(
                            valid_data[metric_x],
                            p(valid_data[metric_x]),
                            "r--",
                            alpha=0.5,
                            linewidth=1,
                        )

                        # Calculate correlation
                        corr, _ = pearsonr(valid_data[metric_x], valid_data[metric_y])
                        ax.text(
                            0.05,
                            0.95,
                            f"r={corr:.3f}",
                            transform=ax.transAxes,
                            fontsize=8,
                            verticalalignment="top",
                            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
                        )

                if j == 0:
                    ax.set_ylabel(metric_y.split(":")[-1], fontsize=8)
                else:
                    ax.set_ylabel("")

                if i == n_metrics - 1:
                    ax.set_xlabel(metric_x.split(":")[-1], fontsize=8)
                else:
                    ax.set_xlabel("")

                ax.tick_params(labelsize=6)
                ax.grid(True, alpha=0.3)

        plt.tight_layout()

        output_file = self.output_dir / f"{run_name}_scatter_matrix.png"
        plt.savefig(output_file, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info(f"  Saved scatter matrix to {output_file}")

    def detect_anomalies(self, run_name: str) -> pd.DataFrame:
        """Detect anomalous cases where metrics disagree.

        Args:
            run_name: Name of the evaluation run

        Returns:
            DataFrame containing anomalous cases
        """
        logger.info(f"Detecting anomalies for {run_name}...")

        pivot = self.pivot_tables[run_name]
        anomalies = []

        # Anomaly 1: High answer correctness despite poor context retrieval
        if (
            "custom:answer_correctness" in pivot.columns
            and "ragas:context_precision_without_reference" in pivot.columns
        ):
            rag_bypass = pivot[
                (pivot["ragas:context_precision_without_reference"] < 0.3)
                & (pivot["custom:answer_correctness"] > 0.9)
                & (pivot["ragas:context_precision_without_reference"].notna())
            ].copy()

            if len(rag_bypass) > 0:
                rag_bypass["anomaly_type"] = "RAG_BYPASS"
                rag_bypass["description"] = (
                    "LLM answered correctly despite poor context retrieval"
                )
                anomalies.append(rag_bypass)
                logger.info(
                    f"  Found {len(rag_bypass)} RAG bypass cases "
                    f"(correct answer, poor contexts)"
                )

        # Anomaly 2: Relevant contexts but unfaithful responses
        if (
            "ragas:context_relevance" in pivot.columns
            and "ragas:faithfulness" in pivot.columns
        ):
            unfaithful = pivot[
                (pivot["ragas:context_relevance"] > 0.5)
                & (pivot["ragas:faithfulness"] < 0.7)
                & (pivot["ragas:faithfulness"].notna())
            ].copy()

            if len(unfaithful) > 0:
                unfaithful["anomaly_type"] = "UNFAITHFUL_RESPONSE"
                unfaithful["description"] = (
                    "Relevant contexts but response not faithful to them"
                )
                anomalies.append(unfaithful)
                logger.info(
                    f"  Found {len(unfaithful)} unfaithful response cases "
                    f"(relevant contexts, low faithfulness)"
                )

        # Anomaly 3: All context scores near 0 but answer correct
        if (
            "ragas:context_relevance" in pivot.columns
            and "custom:answer_correctness" in pivot.columns
            and "ragas:context_precision_without_reference" in pivot.columns
        ):
            no_context = pivot[
                (pivot["ragas:context_relevance"] == 0.0)
                & (pivot["custom:answer_correctness"] > 0.8)
                & (pivot["ragas:context_precision_without_reference"] < 0.1)
            ].copy()

            if len(no_context) > 0:
                no_context["anomaly_type"] = "PARAMETRIC_KNOWLEDGE"
                no_context["description"] = (
                    "Correct answer with zero context scores (parametric knowledge)"
                )
                anomalies.append(no_context)
                logger.info(
                    f"  Found {len(no_context)} parametric knowledge cases "
                    f"(no contexts, correct answer)"
                )

        # Anomaly 4: High context metrics but low answer correctness
        if (
            "ragas:context_precision_without_reference" in pivot.columns
            and "custom:answer_correctness" in pivot.columns
        ):
            good_context_wrong_answer = pivot[
                (pivot["ragas:context_precision_without_reference"] > 0.7)
                & (pivot["custom:answer_correctness"] < 0.5)
            ].copy()

            if len(good_context_wrong_answer) > 0:
                good_context_wrong_answer["anomaly_type"] = "WRONG_DESPITE_GOOD_CONTEXT"
                good_context_wrong_answer["description"] = (
                    "Good context retrieval but incorrect answer"
                )
                anomalies.append(good_context_wrong_answer)
                logger.info(
                    f"  Found {len(good_context_wrong_answer)} wrong answer cases "
                    f"(good contexts, wrong answer)"
                )

        # Combine all anomalies
        if anomalies:
            all_anomalies = pd.concat(anomalies, ignore_index=False)
            output_file = self.output_dir / f"{run_name}_anomalies.csv"
            all_anomalies.to_csv(output_file)
            logger.info(f"  Saved {len(all_anomalies)} total anomalies to {output_file}")
            return all_anomalies
        else:
            logger.info("  No anomalies detected")
            return pd.DataFrame()

    def generate_summary_report(self, run_name: str) -> None:
        """Generate text summary report of findings.

        Args:
            run_name: Name of the evaluation run
        """
        logger.info(f"Generating summary report for {run_name}...")

        pivot = self.pivot_tables[run_name]
        df = self.dataframes[run_name]

        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append(f"CROSS-METRIC CORRELATION ANALYSIS REPORT")
        report_lines.append(f"Evaluation Run: {run_name}")
        report_lines.append("=" * 80)
        report_lines.append("")

        # Basic statistics
        report_lines.append("DATASET OVERVIEW")
        report_lines.append("-" * 80)
        report_lines.append(f"Total score entries: {len(df)}")
        report_lines.append(f"Unique conversations: {df['conversation_group_id'].nunique()}")
        report_lines.append(f"Unique turns evaluated: {len(pivot)}")
        report_lines.append(f"Metrics analyzed: {len(pivot.columns)}")
        report_lines.append("")
        report_lines.append("Metrics:")
        for metric in pivot.columns:
            report_lines.append(f"  - {metric}")
        report_lines.append("")

        # Metric statistics
        report_lines.append("METRIC STATISTICS")
        report_lines.append("-" * 80)
        report_lines.append(f"Total data points: {len(pivot)}")
        if len(pivot) < 2:
            report_lines.append("\n⚠️ WARNING: Insufficient data for statistical analysis")
            report_lines.append("   Correlation analysis requires at least 2 data points")
            report_lines.append("   Run evaluation on more test cases for full analysis")
        report_lines.append("")
        stats = pivot.describe().T
        for metric in pivot.columns:
            if metric in stats.index:
                metric_stats = stats.loc[metric]
                report_lines.append(f"\n{metric}:")
                report_lines.append(f"  Count:  {int(metric_stats['count'])}")
                report_lines.append(f"  Mean:   {metric_stats['mean']:.3f}")
                report_lines.append(f"  Median: {metric_stats['50%']:.3f}")
                report_lines.append(f"  Std:    {metric_stats['std']:.3f}")
                report_lines.append(
                    f"  Range:  [{metric_stats['min']:.3f}, {metric_stats['max']:.3f}]"
                )
        report_lines.append("")

        # Correlation summary
        report_lines.append("CORRELATION SUMMARY (Pearson)")
        report_lines.append("-" * 80)

        if len(pivot) < 2:
            report_lines.append("\n⚠️ Insufficient data for correlation analysis (need at least 2 data points)")
            report_lines.append("")
        else:
            corr = pivot.corr(method="pearson")

            # Extract correlation pairs
            corr_pairs = []
            for i in range(len(corr.columns)):
                for j in range(i + 1, len(corr.columns)):
                    metric1 = corr.columns[i]
                    metric2 = corr.columns[j]
                    corr_val = corr.iloc[i, j]
                    if not np.isnan(corr_val):
                        corr_pairs.append((metric1, metric2, corr_val))

            corr_pairs.sort(key=lambda x: abs(x[2]), reverse=True)

            report_lines.append("\nStrongest Correlations:")
            for m1, m2, val in corr_pairs[:5]:
                interpretation = "✅ Expected" if val > 0.5 else ""
                if val < -0.3:
                    interpretation = "⚠️ Suspicious (negative)"
                elif abs(val) < 0.2:
                    interpretation = "ℹ️ Weak/Independent"

                report_lines.append(f"  {val:+.3f}  {m1} ↔ {m2}  {interpretation}")

            report_lines.append("\nWeakest Correlations:")
            for m1, m2, val in corr_pairs[-5:]:
                report_lines.append(f"  {val:+.3f}  {m1} ↔ {m2}")
            report_lines.append("")

        # Anomaly summary
        anomaly_file = self.output_dir / f"{run_name}_anomalies.csv"
        if anomaly_file.exists():
            anomalies = pd.read_csv(anomaly_file)
            report_lines.append("ANOMALY SUMMARY")
            report_lines.append("-" * 80)
            anomaly_counts = anomalies["anomaly_type"].value_counts()
            for atype, count in anomaly_counts.items():
                report_lines.append(f"  {atype}: {count} cases")

            # List specific conversations
            report_lines.append("\nAnomalous Conversations (sample):")
            for idx, row in anomalies.head(10).iterrows():
                conv_id = row["conversation_group_id"] if "conversation_group_id" in row else idx[0]
                turn_id = row["turn_id"] if "turn_id" in row else idx[1]
                atype = row["anomaly_type"]
                report_lines.append(f"  - {conv_id}/{turn_id}: {atype}")
        report_lines.append("")

        # Recommendations
        report_lines.append("RECOMMENDATIONS")
        report_lines.append("-" * 80)

        # Check if faithfulness threshold should be adjusted
        if "ragas:faithfulness" in pivot.columns:
            faithfulness_mean = pivot["ragas:faithfulness"].mean()
            faithfulness_threshold = 0.8  # From config
            if faithfulness_mean < faithfulness_threshold:
                report_lines.append(
                    f"⚠️ Faithfulness mean ({faithfulness_mean:.3f}) is below "
                    f"threshold ({faithfulness_threshold})"
                )
                report_lines.append(
                    f"   Consider lowering threshold to 0.7 or investigating why "
                    f"scores are consistently low"
                )

        # Check for RAG bypass
        if anomaly_file.exists():
            anomalies = pd.read_csv(anomaly_file)
            if "RAG_BYPASS" in anomalies["anomaly_type"].values:
                bypass_count = len(anomalies[anomalies["anomaly_type"] == "RAG_BYPASS"])
                report_lines.append(
                    f"\n⚠️ Found {bypass_count} cases where LLM bypassed RAG retrieval"
                )
                report_lines.append(
                    "   This suggests either:"
                )
                report_lines.append(
                    "   - okp-mcp retrieval is failing for certain queries"
                )
                report_lines.append(
                    "   - LLM has strong parametric knowledge for these topics"
                )
                report_lines.append(
                    "   - Test data expected_response doesn't match retrieved contexts"
                )

        # Check for metric redundancy
        high_corr_pairs = [p for p in corr_pairs if p[2] > 0.85]
        if high_corr_pairs:
            report_lines.append(f"\nℹ️ High correlation between metrics:")
            for m1, m2, val in high_corr_pairs:
                report_lines.append(f"   {m1} ↔ {m2} ({val:.3f})")
            report_lines.append("   Consider if both metrics are needed")

        report_lines.append("")
        report_lines.append("=" * 80)

        # Write report
        report_text = "\n".join(report_lines)
        output_file = self.output_dir / f"{run_name}_summary_report.txt"
        output_file.write_text(report_text)
        logger.info(f"  Saved summary report to {output_file}")

        # Also print to console
        print("\n" + report_text)

    def compare_runs(self) -> None:
        """Compare metrics across multiple evaluation runs."""
        if len(self.pivot_tables) < 2:
            logger.warning("Need at least 2 runs to compare")
            return

        logger.info(f"Comparing {len(self.pivot_tables)} evaluation runs...")

        # Create comparison plots
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(
            "Metric Comparison Across Runs", fontsize=16, fontweight="bold"
        )

        # Plot 1: Score distributions
        ax = axes[0, 0]
        for run_name, pivot in self.pivot_tables.items():
            for metric in pivot.columns:
                scores = pivot[metric].dropna()
                ax.hist(scores, bins=20, alpha=0.3, label=f"{run_name}:{metric.split(':')[-1]}")
        ax.set_xlabel("Score")
        ax.set_ylabel("Frequency")
        ax.set_title("Score Distributions")
        ax.legend(fontsize=6)
        ax.grid(True, alpha=0.3)

        # Plot 2: Mean scores comparison
        ax = axes[0, 1]
        comparison_data = []
        for run_name, pivot in self.pivot_tables.items():
            means = pivot.mean()
            for metric, mean_val in means.items():
                comparison_data.append({
                    'run': run_name,
                    'metric': metric.split(':')[-1],
                    'mean_score': mean_val
                })
        comp_df = pd.DataFrame(comparison_data)
        comp_pivot = comp_df.pivot(index='metric', columns='run', values='mean_score')
        comp_pivot.plot(kind='bar', ax=ax)
        ax.set_ylabel("Mean Score")
        ax.set_title("Mean Scores by Metric")
        ax.legend(fontsize=8)
        ax.tick_params(axis='x', rotation=45, labelsize=8)
        ax.grid(True, alpha=0.3)

        # Plot 3: Correlation stability (how much correlations change between runs)
        ax = axes[1, 0]
        if len(self.pivot_tables) == 2:
            run_names = list(self.pivot_tables.keys())
            corr1 = self.pivot_tables[run_names[0]].corr()
            corr2 = self.pivot_tables[run_names[1]].corr()

            # Calculate difference
            corr_diff = corr2 - corr1
            sns.heatmap(
                corr_diff,
                annot=True,
                fmt=".3f",
                cmap="coolwarm",
                center=0,
                square=True,
                ax=ax,
                cbar_kws={"label": "Correlation Change"},
            )
            ax.set_title(f"Correlation Change: {run_names[1]} - {run_names[0]}")
            ax.tick_params(axis='x', rotation=45, labelsize=8)
            ax.tick_params(axis='y', rotation=0, labelsize=8)

        # Plot 4: Pass rate comparison
        ax = axes[1, 1]
        pass_rate_data = []
        for run_name, df in self.dataframes.items():
            for metric in df['metric_identifier'].unique():
                metric_data = df[df['metric_identifier'] == metric]
                total = len(metric_data)
                passed = len(metric_data[metric_data['result'] == 'PASS'])
                pass_rate = (passed / total * 100) if total > 0 else 0
                pass_rate_data.append({
                    'run': run_name,
                    'metric': metric.split(':')[-1],
                    'pass_rate': pass_rate
                })
        pr_df = pd.DataFrame(pass_rate_data)
        pr_pivot = pr_df.pivot(index='metric', columns='run', values='pass_rate')
        pr_pivot.plot(kind='bar', ax=ax)
        ax.set_ylabel("Pass Rate (%)")
        ax.set_title("Pass Rates by Metric")
        ax.legend(fontsize=8)
        ax.tick_params(axis='x', rotation=45, labelsize=8)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        output_file = self.output_dir / "run_comparison.png"
        plt.savefig(output_file, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info(f"  Saved run comparison to {output_file}")

    def run_analysis(self, compare_runs: bool = False) -> None:
        """Run complete analysis pipeline.

        Args:
            compare_runs: Whether to compare multiple runs
        """
        logger.info("Starting cross-metric correlation analysis...")

        # Load data
        self.load_data()

        if not self.pivot_tables:
            logger.error("No data loaded. Exiting.")
            return

        # Analyze each run
        for run_name in self.pivot_tables.keys():
            logger.info(f"\nAnalyzing {run_name}...")

            # Check data size
            n_data_points = len(self.pivot_tables[run_name])
            logger.info(f"  Data points: {n_data_points}")
            if n_data_points < 2:
                logger.warning(
                    f"  ⚠️ Only {n_data_points} data point(s) - correlation analysis requires at least 2"
                )
                logger.warning(
                    f"  ℹ️ Run evaluation on more test cases to enable full analysis"
                )

            # Calculate correlations
            correlations = self.calculate_correlations(run_name)

            # Create visualizations
            self.create_correlation_heatmap(run_name, correlations)
            self.create_scatter_plots(run_name)

            # Detect anomalies
            self.detect_anomalies(run_name)

            # Generate summary report
            self.generate_summary_report(run_name)

        # Compare runs if requested
        if compare_runs and len(self.pivot_tables) > 1:
            self.compare_runs()

        logger.info(f"\n✅ Analysis complete! Results saved to {self.output_dir}")
        logger.info(f"   - Correlation matrices (CSV)")
        logger.info(f"   - Heatmaps and scatter plots (PNG)")
        logger.info(f"   - Anomaly reports (CSV)")
        logger.info(f"   - Summary reports (TXT)")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze correlations between evaluation metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input",
        "-i",
        nargs="+",
        required=True,
        help="Input CSV file(s) from eval_output directory",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="analysis_output",
        help="Output directory for analysis results (default: analysis_output)",
    )
    parser.add_argument(
        "--compare-runs",
        action="store_true",
        help="Compare metrics across multiple evaluation runs",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        analyzer = MetricCorrelationAnalyzer(args.input, args.output)
        analyzer.run_analysis(compare_runs=args.compare_runs)
        return 0
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

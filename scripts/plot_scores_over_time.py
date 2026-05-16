#!/usr/bin/env python3
"""Plot Evaluation Scores Over Time - Time Series Analysis.

This script:
1. Finds all evaluation run directories
2. Loads detailed CSV files from all runs
3. Creates time-series plots showing how scores change over time
4. One line per question per metric

Usage:
    python scripts/plot_scores_over_time.py
    python scripts/plot_scores_over_time.py --output-dir analysis_output/time_series
    python scripts/plot_scores_over_time.py --base-dir eval_output --min-runs 3
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import yaml


def load_metric_thresholds(system_config_path: Path = Path("config/system.yaml")) -> dict:
    """Load metric thresholds from system config.

    Args:
        system_config_path: Path to system.yaml config file

    Returns:
        Dictionary mapping metric names to threshold values
    """
    if not system_config_path.exists():
        print(f"   ⚠️ Warning: System config not found at {system_config_path}")
        return {}

    with open(system_config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    thresholds = {}
    for level in ["turn_level", "conversation_level"]:
        metrics = config.get("metrics_metadata", {}).get(level, {})
        for metric_name, metadata in metrics.items():
            if "threshold" in metadata:
                thresholds[metric_name] = metadata["threshold"]

    return thresholds


def parse_timestamp_from_dirname(dirname: str) -> datetime | None:
    """Parse timestamp from directory name like 'full_suite_20260325_134310'.

    Args:
        dirname: Directory name

    Returns:
        Datetime object or None if parsing fails
    """
    try:
        # Extract timestamp part (after 'full_suite_')
        if dirname.startswith("full_suite_"):
            timestamp_str = dirname.replace("full_suite_", "")
            # Format: YYYYMMDD_HHMMSS
            return datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
    except (ValueError, IndexError):
        return None

    return None


def find_all_runs(base_dir: Path, min_runs: int = 2, min_date: datetime | None = None) -> list[tuple[Path, datetime]]:
    """Find all valid evaluation run directories with timestamps.

    Args:
        base_dir: Base directory containing evaluation runs
        min_runs: Minimum number of runs required
        min_date: Only include runs on or after this date (optional)

    Returns:
        List of (run_dir, timestamp) tuples, sorted by timestamp
    """
    all_run_dirs = list(base_dir.glob("full_suite_*"))

    # Filter to only directories that contain CSV files and have valid timestamps
    valid_runs = []
    for run_dir in all_run_dirs:
        csv_files = list(run_dir.glob("*/evaluation_*_detailed.csv"))
        if not csv_files:
            print(f"   ⚠️ Skipping {run_dir.name} (no CSV files found)")
            continue

        timestamp = parse_timestamp_from_dirname(run_dir.name)
        if timestamp is None:
            print(f"   ⚠️ Skipping {run_dir.name} (could not parse timestamp)")
            continue

        # Filter by minimum date if specified
        if min_date and timestamp < min_date:
            print(f"   ⚠️ Skipping {run_dir.name} (before {min_date.strftime('%Y-%m-%d')})")
            continue

        valid_runs.append((run_dir, timestamp))

    # Sort by timestamp
    valid_runs.sort(key=lambda x: x[1])

    if len(valid_runs) < min_runs:
        print(f"❌ Error: Found only {len(valid_runs)} valid run(s)")
        print(f"   Need at least {min_runs} runs with data in {base_dir}")
        return []

    return valid_runs


def load_run_data(run_dir: Path, timestamp: datetime) -> pd.DataFrame:
    """Load all detailed CSV files from a run directory.

    Args:
        run_dir: Run directory containing test config subdirectories
        timestamp: Timestamp of this run

    Returns:
        DataFrame with all evaluation results
    """
    csv_files = list(run_dir.glob("*/evaluation_*_detailed.csv"))

    if not csv_files:
        return pd.DataFrame()

    all_data = []
    for csv_file in csv_files:
        # Extract test config name from path
        test_config = csv_file.parent.name

        df = pd.read_csv(csv_file)
        df["test_config"] = test_config
        df["timestamp"] = timestamp
        df["run_name"] = run_dir.name
        all_data.append(df)

    combined = pd.concat(all_data, ignore_index=True)

    return combined


def calculate_median_scores_per_run(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate median scores per question per metric per run.

    Args:
        df: DataFrame with evaluation results from all runs

    Returns:
        DataFrame with median scores per (timestamp, conversation_group_id, metric, test_config)
    """
    required_cols = ["conversation_group_id", "test_config", "timestamp", "metric_identifier", "score"]
    missing = [col for col in required_cols if col not in df.columns]

    if missing:
        print(f"⚠️ Warning: Missing required columns: {missing}")
        return pd.DataFrame()

    # Group by timestamp, question, test config, and metric, then calculate median score
    medians = (
        df.groupby(["timestamp", "conversation_group_id", "test_config", "metric_identifier"])["score"]
        .median()
        .reset_index()
        .rename(columns={"metric_identifier": "metric", "score": "median_score"})
    )

    return medians


def create_time_series_plots(
    df: pd.DataFrame,
    output_dir: Path,
    max_questions_per_plot: int = 20,
    thresholds: dict | None = None,
) -> None:
    """Create time-series plots showing score evolution over time.

    Args:
        df: DataFrame with median scores over time
        output_dir: Directory to save plots
        max_questions_per_plot: Maximum number of questions to show per plot
        thresholds: Dictionary mapping metric names to threshold values
    """
    if thresholds is None:
        thresholds = {}

    metrics = sorted(df["metric"].unique())

    print(f"\n📊 Creating time-series plots for {len(metrics)} metrics...")

    # Set style
    sns.set_style("whitegrid")

    for metric in metrics:
        metric_data = df[df["metric"] == metric].copy()

        if len(metric_data) == 0:
            print(f"   ⚠️ Skipping {metric}: No data")
            continue

        # Check if we have at least 2 data points (runs) for this metric
        num_runs = metric_data["timestamp"].nunique()
        if num_runs < 2:
            print(f"   ⚠️ Skipping {metric}: Only {num_runs} run(s), need at least 2 for time-series")
            continue

        # Get unique questions for this metric
        questions = metric_data["conversation_group_id"].unique()
        num_questions = len(questions)

        print(f"   📈 {metric}: {num_questions} questions across {num_runs} runs")

        # If too many questions, create multiple plots
        if num_questions > max_questions_per_plot:
            # Split into chunks
            num_plots = (num_questions + max_questions_per_plot - 1) // max_questions_per_plot

            for plot_idx in range(num_plots):
                start_idx = plot_idx * max_questions_per_plot
                end_idx = min((plot_idx + 1) * max_questions_per_plot, num_questions)
                questions_subset = questions[start_idx:end_idx]

                subset_data = metric_data[metric_data["conversation_group_id"].isin(questions_subset)]

                plot_file = output_dir / f"timeseries_{metric}_part{plot_idx + 1}.png"
                _create_single_plot(
                    subset_data,
                    metric,
                    plot_file,
                    f"{metric} (Part {plot_idx + 1}/{num_plots})",
                    thresholds.get(metric),
                )
        else:
            # Single plot for all questions
            plot_file = output_dir / f"timeseries_{metric}.png"
            _create_single_plot(metric_data, metric, plot_file, metric, thresholds.get(metric))


def _create_single_plot(
    data: pd.DataFrame,
    metric: str,
    plot_file: Path,
    title: str,
    threshold: float | None = None,
) -> None:
    """Create a single time-series plot.

    Args:
        data: DataFrame with data for this plot
        metric: Metric name
        plot_file: Path to save plot
        title: Plot title
        threshold: Failure threshold to mark with red line
    """
    # Create figure
    _, ax = plt.subplots(figsize=(14, 8))

    # Get unique questions
    questions = data["conversation_group_id"].unique()

    # Create color palette - one color per question
    colors = sns.color_palette("husl", n_colors=len(questions))
    question_colors = dict(zip(questions, colors))

    # Get unique timestamps and create position mapping
    unique_timestamps = sorted(data["timestamp"].unique())
    timestamp_to_position = {ts: i for i, ts in enumerate(unique_timestamps)}

    # Add position column to data
    data_copy = data.copy()
    data_copy["x_position"] = data_copy["timestamp"].map(timestamp_to_position)

    # Plot each question as a separate line
    for question in questions:
        question_data = data_copy[data_copy["conversation_group_id"] == question].copy()
        question_data = question_data.sort_values("timestamp")

        # Get test config for this question (for legend)
        test_config = question_data["test_config"].iloc[0]
        color = question_colors[question]

        # Truncate question label for legend
        question_label = question[:60] + "..." if len(question) > 60 else question

        # Plot using x_position (evenly spaced) instead of timestamp
        ax.plot(
            question_data["x_position"],
            question_data["median_score"],
            marker="o",
            label=f"{question_label} ({test_config})",
            color=color,
            alpha=0.8,
            linewidth=2,
            markersize=8,
            linestyle="-",
        )

    # Add threshold line if available
    if threshold is not None:
        ax.axhline(
            y=threshold,
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"Failure Threshold ({threshold})",
            alpha=0.7,
        )

    # Formatting
    ax.set_xlabel("Evaluation Run Time", fontsize=12, fontweight="bold")
    ax.set_ylabel("Median Score", fontsize=12, fontweight="bold")
    ax.set_title(f"Score Trends Over Time: {title}", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)

    # Set x-axis ticks at integer positions with timestamp labels
    ax.set_xticks(range(len(unique_timestamps)))
    ax.set_xticklabels(
        [ts.strftime("%Y-%m-%d %H:%M") for ts in unique_timestamps],
        rotation=45,
        ha="right"
    )

    # Legend - place outside plot area if many questions
    if len(questions) > 10:
        ax.legend(
            loc="center left",
            bbox_to_anchor=(1, 0.5),
            fontsize=8,
            framealpha=0.9,
        )
    else:
        ax.legend(loc="best", fontsize=9, framealpha=0.9)

    # Set y-axis limits based on metric type
    y_min, y_max = ax.get_ylim()
    if y_min >= 0 and y_max <= 1.1:
        # Likely a 0-1 metric, set nice bounds
        ax.set_ylim(-0.05, 1.05)

    plt.tight_layout()
    plt.savefig(plot_file, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"      ✓ Saved {plot_file.name}")


def create_heatmap_plots(
    df: pd.DataFrame,
    output_dir: Path,
    thresholds: dict | None = None,
) -> None:
    """Create heatmap plots with questions on Y-axis and time on X-axis.

    Args:
        df: DataFrame with median scores over time
        output_dir: Directory to save plots
        thresholds: Dictionary mapping metric names to threshold values
    """
    if thresholds is None:
        thresholds = {}

    metrics = sorted(df["metric"].unique())
    print(f"\n📊 Creating heatmap plots for {len(metrics)} metrics...")

    # Set style
    sns.set_style("whitegrid")

    for metric in metrics:
        metric_data = df[df["metric"] == metric].copy()

        if len(metric_data) == 0:
            print(f"   ⚠️ Skipping {metric}: No data")
            continue

        # Check if we have at least 2 data points
        num_runs = metric_data["timestamp"].nunique()
        if num_runs < 2:
            print(f"   ⚠️ Skipping {metric}: Only {num_runs} run(s), need at least 2")
            continue

        # Pivot data: questions as rows, timestamps as columns
        pivot_data = metric_data.pivot_table(
            index=["conversation_group_id", "test_config"],
            columns="timestamp",
            values="median_score",
        )

        # Sort by test_config then question ID for grouping
        pivot_data = pivot_data.sort_index()

        # Skip if pivot is empty or has no valid data
        if pivot_data.empty or pivot_data.isna().all().all():
            print(f"   ⚠️ Skipping {metric}: No valid data after pivot")
            continue

        # Create figure
        _, ax = plt.subplots(figsize=(16, max(10, len(pivot_data) * 0.3)))

        # Create heatmap
        threshold = thresholds.get(metric)
        if threshold is not None:
            # Use diverging colormap centered on threshold
            vmin = min(pivot_data.min().min(), threshold - 0.2)
            vmax = max(pivot_data.max().max(), threshold + 0.2)
            sns.heatmap(
                pivot_data,
                ax=ax,
                cmap="RdYlGn",
                center=threshold,
                vmin=vmin,
                vmax=vmax,
                annot=True,
                fmt=".2f",
                linewidths=0.5,
                cbar_kws={"label": "Score"},
            )
        else:
            sns.heatmap(
                pivot_data,
                ax=ax,
                cmap="viridis",
                annot=True,
                fmt=".2f",
                linewidths=0.5,
                cbar_kws={"label": "Score"},
            )

        # Format timestamp column labels
        timestamp_labels = [ts.strftime("%Y-%m-%d %H:%M") for ts in pivot_data.columns]
        ax.set_xticklabels(timestamp_labels, rotation=45, ha="right")

        # Format row labels (question + test config)
        row_labels = [f"{q[0][:40]}... ({q[1]})" if len(q[0]) > 40 else f"{q[0]} ({q[1]})"
                      for q in pivot_data.index]
        ax.set_yticklabels(row_labels, rotation=0, fontsize=8)

        # Styling
        title = f"Score Heatmap: {metric}"
        if threshold is not None:
            title += f" (Threshold: {threshold})"
        ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
        ax.set_xlabel("Evaluation Run Time", fontsize=12, fontweight="bold")
        ax.set_ylabel("Question (Test Config)", fontsize=12, fontweight="bold")

        plt.tight_layout()
        plot_file = output_dir / f"heatmap_{metric}.png"
        plt.savefig(plot_file, dpi=150, bbox_inches="tight")
        plt.close()

        print(f"   ✓ {metric}: {len(pivot_data)} questions, saved to {plot_file.name}")


def create_boxplot_over_time(
    df: pd.DataFrame,
    output_dir: Path,
    thresholds: dict | None = None,
) -> None:
    """Create box plots showing score distribution at each timestamp.

    Args:
        df: DataFrame with median scores over time
        output_dir: Directory to save plots
        thresholds: Dictionary mapping metric names to threshold values
    """
    if thresholds is None:
        thresholds = {}

    metrics = sorted(df["metric"].unique())
    print(f"\n📊 Creating box plot time series for {len(metrics)} metrics...")

    sns.set_style("whitegrid")

    for metric in metrics:
        metric_data = df[df["metric"] == metric].copy()

        if len(metric_data) == 0:
            print(f"   ⚠️ Skipping {metric}: No data")
            continue

        num_runs = metric_data["timestamp"].nunique()
        if num_runs < 2:
            print(f"   ⚠️ Skipping {metric}: Only {num_runs} run(s), need at least 2")
            continue

        # Create figure
        _, ax = plt.subplots(figsize=(14, 8))

        # Create timestamp labels for x-axis
        unique_timestamps = sorted(metric_data["timestamp"].unique())
        timestamp_labels = [ts.strftime("%Y-%m-%d\n%H:%M") for ts in unique_timestamps]

        # Add numeric position for plotting
        metric_data["x_position"] = metric_data["timestamp"].map(
            {ts: i for i, ts in enumerate(unique_timestamps)}
        )

        # Prepare data for boxplot - group by x_position
        boxplot_data = []
        for pos in range(len(unique_timestamps)):
            scores = metric_data[metric_data["x_position"] == pos]["median_score"].tolist()
            boxplot_data.append(scores)

        # Create box plot using matplotlib (more stable than seaborn)
        bp = ax.boxplot(
            boxplot_data,
            positions=range(len(unique_timestamps)),
            widths=0.6,
            patch_artist=True,
            showfliers=True,
        )

        # Color the boxes
        colors = sns.color_palette("Set2", len(unique_timestamps))
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)

        # Overlay individual points
        for pos in range(len(unique_timestamps)):
            scores = metric_data[metric_data["x_position"] == pos]["median_score"].tolist()
            # Add small jitter to x positions to avoid overlapping points
            x_positions = [pos] * len(scores)
            ax.scatter(
                x_positions,
                scores,
                color="black",
                alpha=0.3,
                s=20,
                zorder=3,
            )

        # Add threshold line
        threshold = thresholds.get(metric)
        if threshold is not None:
            ax.axhline(
                y=threshold,
                color="red",
                linestyle="--",
                linewidth=2,
                label=f"Failure Threshold ({threshold})",
                alpha=0.7,
            )
            ax.legend(loc="best")

        # Styling
        ax.set_xticks(range(len(unique_timestamps)))
        ax.set_xticklabels(timestamp_labels)
        ax.set_xlabel("Evaluation Run Time", fontsize=12, fontweight="bold")
        ax.set_ylabel("Score Distribution", fontsize=12, fontweight="bold")
        ax.set_title(f"Score Distribution Over Time: {metric}", fontsize=14, fontweight="bold")
        ax.grid(True, alpha=0.3)

        # Set y-axis limits
        y_min, y_max = ax.get_ylim()
        if y_min >= 0 and y_max <= 1.1:
            ax.set_ylim(-0.05, 1.05)

        plt.tight_layout()
        plot_file = output_dir / f"boxplot_{metric}.png"
        plt.savefig(plot_file, dpi=150, bbox_inches="tight")
        plt.close()

        print(f"   ✓ {metric}: saved to {plot_file.name}")


def create_aggregated_trend_plots(
    df: pd.DataFrame,
    output_dir: Path,
    thresholds: dict | None = None,
) -> None:
    """Create aggregated trend plots with mean/median and confidence bands.

    Args:
        df: DataFrame with median scores over time
        output_dir: Directory to save plots
        thresholds: Dictionary mapping metric names to threshold values
    """
    if thresholds is None:
        thresholds = {}

    metrics = sorted(df["metric"].unique())
    print(f"\n📊 Creating aggregated trend plots for {len(metrics)} metrics...")

    sns.set_style("whitegrid")

    for metric in metrics:
        metric_data = df[df["metric"] == metric].copy()

        if len(metric_data) == 0:
            print(f"   ⚠️ Skipping {metric}: No data")
            continue

        num_runs = metric_data["timestamp"].nunique()
        if num_runs < 2:
            print(f"   ⚠️ Skipping {metric}: Only {num_runs} run(s), need at least 2")
            continue

        # Calculate statistics per timestamp
        stats = metric_data.groupby("timestamp").agg(
            mean_score=("median_score", "mean"),
            median_score=("median_score", "median"),
            std_score=("median_score", "std"),
            min_score=("median_score", "min"),
            max_score=("median_score", "max"),
            q25=("median_score", lambda x: x.quantile(0.25)),
            q75=("median_score", lambda x: x.quantile(0.75)),
        ).reset_index()

        # Create x positions
        stats = stats.sort_values("timestamp")
        x_positions = list(range(len(stats)))

        # Create figure
        _, ax = plt.subplots(figsize=(14, 8))

        # Plot mean line
        ax.plot(
            x_positions,
            stats["mean_score"],
            marker="o",
            label="Mean Score",
            color="blue",
            linewidth=2.5,
            markersize=10,
        )

        # Plot median line
        ax.plot(
            x_positions,
            stats["median_score"],
            marker="s",
            label="Median Score",
            color="green",
            linewidth=2.5,
            markersize=8,
        )

        # Add confidence band (std dev)
        ax.fill_between(
            x_positions,
            stats["mean_score"] - stats["std_score"],
            stats["mean_score"] + stats["std_score"],
            alpha=0.2,
            color="blue",
            label="±1 Std Dev",
        )

        # Add quartile range band
        ax.fill_between(
            x_positions,
            stats["q25"],
            stats["q75"],
            alpha=0.15,
            color="green",
            label="25th-75th Percentile",
        )

        # Add threshold line
        threshold = thresholds.get(metric)
        if threshold is not None:
            ax.axhline(
                y=threshold,
                color="red",
                linestyle="--",
                linewidth=2,
                label=f"Failure Threshold ({threshold})",
                alpha=0.7,
            )

        # Styling
        timestamp_labels = [ts.strftime("%Y-%m-%d %H:%M") for ts in stats["timestamp"]]
        ax.set_xticks(x_positions)
        ax.set_xticklabels(timestamp_labels, rotation=45, ha="right")
        ax.set_xlabel("Evaluation Run Time", fontsize=12, fontweight="bold")
        ax.set_ylabel("Score", fontsize=12, fontweight="bold")
        ax.set_title(f"Aggregated Score Trend: {metric}", fontsize=14, fontweight="bold")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=10)

        # Set y-axis limits
        y_min, y_max = ax.get_ylim()
        if y_min >= 0 and y_max <= 1.1:
            ax.set_ylim(-0.05, 1.05)

        plt.tight_layout()
        plot_file = output_dir / f"trend_{metric}.png"
        plt.savefig(plot_file, dpi=150, bbox_inches="tight")
        plt.close()

        print(f"   ✓ {metric}: saved to {plot_file.name}")


def create_faceted_plots(
    df: pd.DataFrame,
    output_dir: Path,
    thresholds: dict | None = None,
) -> None:
    """Create faceted plots with separate subplot per test config.

    Args:
        df: DataFrame with median scores over time
        output_dir: Directory to save plots
        thresholds: Dictionary mapping metric names to threshold values
    """
    if thresholds is None:
        thresholds = {}

    metrics = sorted(df["metric"].unique())
    print(f"\n📊 Creating faceted plots for {len(metrics)} metrics...")

    sns.set_style("whitegrid")

    for metric in metrics:
        metric_data = df[df["metric"] == metric].copy()

        if len(metric_data) == 0:
            print(f"   ⚠️ Skipping {metric}: No data")
            continue

        num_runs = metric_data["timestamp"].nunique()
        if num_runs < 2:
            print(f"   ⚠️ Skipping {metric}: Only {num_runs} run(s), need at least 2")
            continue

        # Get unique test configs and timestamps
        test_configs = sorted(metric_data["test_config"].unique())
        unique_timestamps = sorted(metric_data["timestamp"].unique())
        timestamp_to_position = {ts: i for i, ts in enumerate(unique_timestamps)}

        # Add position column
        metric_data["x_position"] = metric_data["timestamp"].map(timestamp_to_position)

        # Calculate grid layout
        n_configs = len(test_configs)
        n_cols = min(2, n_configs)
        n_rows = (n_configs + n_cols - 1) // n_cols

        # Create subplots
        fig, axes = plt.subplots(
            n_rows, n_cols, figsize=(14, 6 * n_rows), squeeze=False
        )
        axes = axes.flatten()

        # Plot each test config
        for idx, test_config in enumerate(test_configs):
            ax = axes[idx]
            config_data = metric_data[metric_data["test_config"] == test_config]

            # Get unique questions
            questions = config_data["conversation_group_id"].unique()
            colors = sns.color_palette("husl", n_colors=len(questions))
            question_colors = dict(zip(questions, colors))

            # Plot each question
            for question in questions:
                question_data = config_data[
                    config_data["conversation_group_id"] == question
                ].copy()
                question_data = question_data.sort_values("timestamp")

                question_label = (
                    question[:40] + "..." if len(question) > 40 else question
                )

                ax.plot(
                    question_data["x_position"],
                    question_data["median_score"],
                    marker="o",
                    label=question_label,
                    color=question_colors[question],
                    alpha=0.8,
                    linewidth=2,
                    markersize=8,
                )

            # Add threshold line
            threshold = thresholds.get(metric)
            if threshold is not None:
                ax.axhline(
                    y=threshold,
                    color="red",
                    linestyle="--",
                    linewidth=2,
                    alpha=0.7,
                    label=f"Threshold ({threshold})",
                )

            # Styling
            ax.set_title(f"{test_config}", fontsize=12, fontweight="bold")
            ax.set_xlabel("Time", fontsize=10, fontweight="bold")
            ax.set_ylabel("Score", fontsize=10, fontweight="bold")
            ax.grid(True, alpha=0.3)

            # Set x-axis ticks
            ax.set_xticks(range(len(unique_timestamps)))
            timestamp_labels = [
                ts.strftime("%m/%d\n%H:%M") for ts in unique_timestamps
            ]
            ax.set_xticklabels(timestamp_labels, fontsize=9)

            # Legend
            if len(questions) <= 8:
                ax.legend(loc="best", fontsize=8, framealpha=0.9)
            else:
                ax.legend(
                    loc="center left",
                    bbox_to_anchor=(1, 0.5),
                    fontsize=7,
                    framealpha=0.9,
                )

            # Set y-axis limits
            y_min, y_max = ax.get_ylim()
            if y_min >= 0 and y_max <= 1.1:
                ax.set_ylim(-0.05, 1.05)

        # Hide unused subplots
        for idx in range(n_configs, len(axes)):
            axes[idx].set_visible(False)

        # Overall title
        fig.suptitle(
            f"Score Trends by Test Config: {metric}",
            fontsize=16,
            fontweight="bold",
            y=0.995,
        )

        plt.tight_layout()
        plot_file = output_dir / f"faceted_{metric}.png"
        plt.savefig(plot_file, dpi=150, bbox_inches="tight")
        plt.close()

        print(f"   ✓ {metric}: {n_configs} configs, saved to {plot_file.name}")


def create_summary_csv(df: pd.DataFrame, output_file: Path) -> None:
    """Create CSV with all time-series data.

    Args:
        df: DataFrame with median scores over time
        output_file: Path to save CSV
    """
    # Sort for readability
    df_sorted = df.sort_values(["metric", "conversation_group_id", "timestamp"])

    # Save to CSV
    df_sorted.to_csv(output_file, index=False)

    print(f"\n✅ Time-series CSV saved: {output_file}")
    print(f"   Metrics: {df['metric'].nunique()}")
    print(f"   Questions: {df['conversation_group_id'].nunique()}")
    print(f"   Runs: {df['timestamp'].nunique()}")
    print(f"   Total data points: {len(df)}")


def generate_summary_report(df: pd.DataFrame, output_file: Path) -> None:
    """Generate text summary report.

    Args:
        df: DataFrame with median scores over time
        output_file: Path to save summary report
    """
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("Evaluation Scores Over Time - Summary Report\n")
        f.write("=" * 80 + "\n\n")

        # Overall statistics
        f.write("Overall Statistics:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Number of evaluation runs: {df['timestamp'].nunique()}\n")
        f.write(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}\n")
        f.write(f"Total questions tracked: {df['conversation_group_id'].nunique()}\n")
        f.write(f"Metrics evaluated: {df['metric'].nunique()}\n")
        f.write(f"Test configs: {df['test_config'].nunique()}\n\n")

        # Run details
        f.write("Evaluation Runs:\n")
        f.write("-" * 80 + "\n")
        for timestamp in sorted(df['timestamp'].unique()):
            run_data = df[df['timestamp'] == timestamp]
            f.write(f"  {timestamp}: {run_data['conversation_group_id'].nunique()} questions\n")
        f.write("\n")

        # Per-metric statistics
        f.write("Per-Metric Statistics:\n")
        f.write("-" * 80 + "\n\n")

        for metric in sorted(df["metric"].unique()):
            metric_data = df[df["metric"] == metric]

            f.write(f"Metric: {metric}\n")
            f.write(f"  Questions tracked: {metric_data['conversation_group_id'].nunique()}\n")
            f.write(f"  Runs: {metric_data['timestamp'].nunique()}\n")
            f.write(f"  Overall mean score: {metric_data['median_score'].mean():.3f}\n")
            f.write(f"  Overall std dev: {metric_data['median_score'].std():.3f}\n")
            f.write(f"  Score range: [{metric_data['median_score'].min():.3f}, {metric_data['median_score'].max():.3f}]\n")

            # Calculate trend (comparing first vs last run)
            first_run = metric_data['timestamp'].min()
            last_run = metric_data['timestamp'].max()

            first_mean = metric_data[metric_data['timestamp'] == first_run]['median_score'].mean()
            last_mean = metric_data[metric_data['timestamp'] == last_run]['median_score'].mean()
            trend = last_mean - first_mean

            f.write(f"  Trend (first to last run): {trend:+.3f}\n")
            f.write("\n")

    print(f"✅ Summary report saved: {output_file}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Plot evaluation scores over time with one line per question per metric"
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("eval_output"),
        help="Base directory containing evaluation runs (default: eval_output)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for plots (default: auto-generated)",
    )
    parser.add_argument(
        "--min-runs",
        type=int,
        default=2,
        help="Minimum number of runs required (default: 2)",
    )
    parser.add_argument(
        "--min-date",
        type=str,
        default=None,
        help="Only include runs on or after this date (format: YYYY-MM-DD, e.g., 2026-03-25)",
    )
    parser.add_argument(
        "--max-questions-per-plot",
        type=int,
        default=20,
        help="Maximum questions per plot before splitting (default: 20)",
    )
    parser.add_argument(
        "--plot-types",
        type=str,
        nargs="+",
        default=["line", "heatmap"],
        choices=["line", "heatmap", "boxplot", "trend", "faceted", "all"],
        help="Types of plots to generate (default: line, heatmap). Use 'all' for all types.",
    )

    args = parser.parse_args()

    # Parse min_date if provided
    min_date = None
    if args.min_date:
        try:
            min_date = datetime.strptime(args.min_date, "%Y-%m-%d")
            print(f"📅 Filtering runs: only including data from {args.min_date} onwards")
        except ValueError:
            print(f"❌ Error: Invalid date format '{args.min_date}'. Use YYYY-MM-DD (e.g., 2026-03-25)")
            return 1

    # Handle "all" option
    if "all" in args.plot_types:
        args.plot_types = ["line", "heatmap", "boxplot", "trend", "faceted"]

    print("📈 Plotting Evaluation Scores Over Time")
    print("=" * 80)

    # Find all valid runs
    print(f"\n📂 Searching for evaluation runs in: {args.base_dir}")
    runs = find_all_runs(args.base_dir, args.min_runs, min_date)

    if not runs:
        return 1

    print(f"\n✅ Found {len(runs)} valid evaluation runs:")
    for run_dir, timestamp in runs:
        print(f"   {timestamp}: {run_dir.name}")

    # Load data from all runs
    print("\n📊 Loading evaluation data from all runs...")
    all_data = []
    for run_dir, timestamp in runs:
        run_data = load_run_data(run_dir, timestamp)
        if not run_data.empty:
            all_data.append(run_data)
            print(f"   ✓ {timestamp}: {len(run_data)} records")

    if not all_data:
        print("❌ Error: Failed to load data from any runs")
        return 1

    combined_data = pd.concat(all_data, ignore_index=True)
    print(f"\n✅ Total records loaded: {len(combined_data)}")

    # Calculate median scores per run
    print("\n🔢 Calculating median scores per question per run...")
    median_scores = calculate_median_scores_per_run(combined_data)

    if median_scores.empty:
        print("❌ Error: No median scores calculated")
        return 1

    print(f"   ✓ Calculated {len(median_scores)} median score data points")

    # Set up output directory
    if args.output_dir is None:
        output_dir = Path("analysis_output") / "time_series"
    else:
        output_dir = args.output_dir

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n📁 Output directory: {output_dir}")

    # Load metric thresholds
    print("\n🔢 Loading metric thresholds from config...")
    thresholds = load_metric_thresholds()
    if thresholds:
        print(f"   ✓ Loaded {len(thresholds)} metric thresholds")
    else:
        print("   ⚠️ No thresholds loaded, plots will not show failure lines")

    # Create time-series CSV
    print("\n📝 Creating time-series CSV...")
    csv_file = output_dir / "scores_over_time.csv"
    create_summary_csv(median_scores, csv_file)

    # Create plots based on selected types
    print(f"\n📈 Generating plot types: {', '.join(args.plot_types)}")

    if "line" in args.plot_types:
        create_time_series_plots(
            median_scores,
            output_dir,
            max_questions_per_plot=args.max_questions_per_plot,
            thresholds=thresholds,
        )

    if "heatmap" in args.plot_types:
        create_heatmap_plots(median_scores, output_dir, thresholds)

    if "boxplot" in args.plot_types:
        create_boxplot_over_time(median_scores, output_dir, thresholds)

    if "trend" in args.plot_types:
        create_aggregated_trend_plots(median_scores, output_dir, thresholds)

    if "faceted" in args.plot_types:
        create_faceted_plots(median_scores, output_dir, thresholds)

    # Generate summary report
    summary_file = output_dir / "time_series_summary.txt"
    generate_summary_report(median_scores, summary_file)

    # Final summary
    print("\n" + "=" * 80)
    print("✅ Time-Series Analysis Complete!")
    print("=" * 80)
    print("\nOutput files:")
    print(f"  📊 Time-series CSV: {csv_file}")
    print(f"  📄 Summary report:  {summary_file}")
    print("\nGenerated plots:")
    if "line" in args.plot_types:
        print(f"  📈 Line plots:      {output_dir}/timeseries_*.png")
    if "heatmap" in args.plot_types:
        print(f"  🔥 Heatmaps:        {output_dir}/heatmap_*.png")
    if "boxplot" in args.plot_types:
        print(f"  📦 Box plots:       {output_dir}/boxplot_*.png")
    if "trend" in args.plot_types:
        print(f"  📊 Trend plots:     {output_dir}/trend_*.png")
    if "faceted" in args.plot_types:
        print(f"  🔲 Faceted plots:   {output_dir}/faceted_*.png")
    print("\nView all plots:")
    print(f"  ls {output_dir}/*.png")
    print("\nRead summary:")
    print(f"  cat {summary_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

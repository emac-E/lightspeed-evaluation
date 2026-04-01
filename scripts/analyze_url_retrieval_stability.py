#!/usr/bin/env python3
"""Analyze URL retrieval stability across multiple evaluation runs.

This script analyzes multiple evaluation runs to measure:
1. Content overlap stability - Do we get the same documents back?
2. Ranking stability - Do documents appear in consistent positions?
3. Expected URL tracking - Where do expected URLs rank?

Usage:
    python scripts/analyze_url_retrieval_stability.py \\
        --input eval_output/suite_*/run_*/evaluation_*_detailed.csv \\
        --output analysis_output/url_stability
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import kendalltau, spearmanr


def extract_urls_from_tool_calls_str(tool_calls_str: str) -> list[str]:
    """Extract ordered list of URLs from tool_calls string.

    Args:
        tool_calls_str: String representation of tool_calls from CSV

    Returns:
        List of URLs in retrieval order
    """
    if pd.isna(tool_calls_str) or not tool_calls_str or tool_calls_str == "[]":
        return []

    import ast

    try:
        tool_calls = ast.literal_eval(tool_calls_str)
    except (ValueError, SyntaxError):
        return []

    urls = []
    for turn in tool_calls:
        if not isinstance(turn, list):
            continue
        for call in turn:
            if not isinstance(call, dict):
                continue
            result = call.get("result")
            if isinstance(result, dict) and "contexts" in result:
                contexts = result.get("contexts", [])
                if isinstance(contexts, list):
                    for ctx in contexts:
                        if isinstance(ctx, dict) and "url" in ctx:
                            url = ctx["url"]
                            if url:
                                urls.append(url)

    return urls


def normalize_url(url: str) -> str:
    """Normalize URL for comparison."""
    from urllib.parse import urlparse

    if not url:
        return ""
    parsed = urlparse(url.strip())
    return (parsed.netloc + parsed.path.rstrip("/")).lower()


def calculate_jaccard_similarity(set1: set, set2: set) -> float:
    """Calculate Jaccard similarity between two sets.

    Args:
        set1: First set
        set2: Second set

    Returns:
        Jaccard similarity (0-1)
    """
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def calculate_ranking_correlation(
    urls1: list[str], urls2: list[str]
) -> tuple[float, float]:
    """Calculate ranking correlation between two URL lists.

    Args:
        urls1: First ordered URL list
        urls2: Second ordered URL list

    Returns:
        Tuple of (kendall_tau, spearman_rho)
    """
    # Find common URLs
    set1 = set(urls1)
    set2 = set(urls2)
    common = set1 & set2

    if len(common) < 2:
        return 0.0, 0.0

    # Build ranking vectors for common URLs
    rank1 = []
    rank2 = []

    for url in common:
        pos1 = urls1.index(url) + 1  # 1-indexed
        pos2 = urls2.index(url) + 1
        rank1.append(pos1)
        rank2.append(pos2)

    # Calculate correlations
    try:
        kendall, _ = kendalltau(rank1, rank2)
        spearman, _ = spearmanr(rank1, rank2)
    except ValueError:
        kendall, spearman = 0.0, 0.0

    return kendall, spearman


def analyze_url_stability(csv_files: list[Path]) -> pd.DataFrame:
    """Analyze URL retrieval stability across runs.

    Args:
        csv_files: List of detailed CSV files from evaluation runs

    Returns:
        DataFrame with stability metrics per question
    """
    # Load all runs
    dfs = []
    for i, csv_file in enumerate(csv_files, 1):
        df = pd.read_csv(csv_file)
        df["run_id"] = i
        dfs.append(df)

    df_all = pd.concat(dfs, ignore_index=True)

    # Filter to url_retrieval_eval metric
    df_url = df_all[
        df_all["metric_identifier"] == "custom:url_retrieval_eval"
    ].copy()

    if df_url.empty:
        raise ValueError("No url_retrieval_eval metric found in CSVs")

    # Extract URLs for each question-run combination
    df_url["retrieved_urls"] = df_url["tool_calls"].apply(
        extract_urls_from_tool_calls_str
    )
    df_url["retrieved_urls_normalized"] = df_url["retrieved_urls"].apply(
        lambda urls: [normalize_url(u) for u in urls]
    )

    # Parse expected URLs from reason field
    # Format: "Missing N: 'url1', 'url2' ... (N total)"
    def parse_expected_urls_from_reason(reason):
        """Extract expected URLs from reason field.

        The reason field contains lines like:
        "Missing 3: 'url1', 'url2' ... (3 total)"

        We extract the URLs mentioned after "Missing".
        """
        if pd.isna(reason):
            return []

        urls = []
        # Look for pattern: Missing N: 'url', 'url', ...
        import re
        missing_match = re.search(r"Missing \d+: (.+?)(?:\.\s|$)", reason)
        if missing_match:
            urls_text = missing_match.group(1)
            # Extract URLs in quotes
            url_matches = re.findall(r"'([^']+)'", urls_text)
            urls.extend(url_matches)

        # Also look for Matched URLs to get complete list
        matched_match = re.search(r"Matched \d+/(\d+):", reason)
        if matched_match:
            total_expected = int(matched_match.group(1))
            # If we have matched URLs, add them too
            matched_urls_match = re.search(r"Matched \d+/\d+: (.+?)(?:\.\s|$)", reason)
            if matched_urls_match:
                urls_text = matched_urls_match.group(1)
                # Extract URLs in quotes (before the position info)
                url_matches = re.findall(r"'([^']+)'", urls_text)
                # Remove position info like "(#1)"
                clean_urls = [re.sub(r'\s*\(#\d+\)', '', u) for u in url_matches]
                urls.extend(clean_urls)

        # Deduplicate and return
        return list(dict.fromkeys(urls))

    df_url["expected_urls_list"] = df_url["reason"].apply(parse_expected_urls_from_reason)

    # Calculate stability metrics per question
    stability_data = []

    for question in df_url["query"].unique():
        df_q = df_url[df_url["query"] == question]

        if len(df_q) < 2:
            continue  # Need at least 2 runs

        # Extract URL sets and lists for this question
        url_sets = []
        url_lists = []

        for _, row in df_q.iterrows():
            urls = row["retrieved_urls_normalized"]
            url_sets.append(set(urls))
            url_lists.append(urls)

        # Content overlap stability (pairwise Jaccard)
        jaccard_scores = []
        for i in range(len(url_sets)):
            for j in range(i + 1, len(url_sets)):
                jaccard = calculate_jaccard_similarity(url_sets[i], url_sets[j])
                jaccard_scores.append(jaccard)

        avg_jaccard = np.mean(jaccard_scores) if jaccard_scores else 0.0
        std_jaccard = np.std(jaccard_scores) if jaccard_scores else 0.0

        # Ranking stability (pairwise correlation)
        kendall_scores = []
        spearman_scores = []

        for i in range(len(url_lists)):
            for j in range(i + 1, len(url_lists)):
                kendall, spearman = calculate_ranking_correlation(
                    url_lists[i], url_lists[j]
                )
                kendall_scores.append(kendall)
                spearman_scores.append(spearman)

        avg_kendall = np.mean(kendall_scores) if kendall_scores else 0.0
        avg_spearman = np.mean(spearman_scores) if spearman_scores else 0.0

        # Expected URL tracking
        expected_urls = df_q.iloc[0]["expected_urls_list"]
        expected_normalized = [normalize_url(u) for u in expected_urls]

        # Track positions of expected URLs across runs
        expected_positions = defaultdict(list)

        for urls in url_lists:
            for exp_url in expected_normalized:
                if exp_url in urls:
                    pos = urls.index(exp_url) + 1  # 1-indexed
                    expected_positions[exp_url].append(pos)
                else:
                    expected_positions[exp_url].append(None)

        # Calculate position stability for each expected URL
        expected_url_metrics = []
        for exp_url, positions in expected_positions.items():
            found_positions = [p for p in positions if p is not None]
            if found_positions:
                avg_pos = np.mean(found_positions)
                std_pos = np.std(found_positions)
                found_rate = len(found_positions) / len(positions)
            else:
                avg_pos = None
                std_pos = None
                found_rate = 0.0

            expected_url_metrics.append(
                {
                    "url": exp_url,
                    "found_rate": found_rate,
                    "avg_position": avg_pos,
                    "std_position": std_pos,
                }
            )

        stability_data.append(
            {
                "query": question,
                "num_runs": len(df_q),
                "avg_jaccard": avg_jaccard,
                "std_jaccard": std_jaccard,
                "avg_kendall_tau": avg_kendall,
                "avg_spearman_rho": avg_spearman,
                "avg_f1_score": df_q["score"].mean(),
                "std_f1_score": df_q["score"].std(),
                "expected_url_metrics": expected_url_metrics,
            }
        )

    return pd.DataFrame(stability_data)


def create_stability_heatmaps(df: pd.DataFrame, output_dir: Path):
    """Create heatmaps for URL retrieval stability.

    Args:
        df: DataFrame with stability metrics
        output_dir: Output directory for heatmaps
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sort by Jaccard stability (worst first)
    df_sorted = df.sort_values("avg_jaccard")

    # 1. Content Overlap Stability (Jaccard)
    fig, ax = plt.subplots(figsize=(10, max(8, len(df) * 0.4)))

    jaccard_matrix = df_sorted[["avg_jaccard"]].copy()
    jaccard_matrix.index = df_sorted["query"]

    sns.heatmap(
        jaccard_matrix,
        annot=True,
        fmt=".3f",
        cmap="RdYlGn",
        vmin=0,
        vmax=1,
        cbar_kws={"label": "Jaccard Similarity"},
        ax=ax,
        linewidths=0.5,
        linecolor="gray",
    )

    ax.set_title(
        f"Content Overlap Stability (Jaccard Similarity)\n{df['num_runs'].iloc[0]} runs",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Questions", fontsize=12)
    ax.set_xlabel("")

    plt.tight_layout()
    plt.savefig(
        output_dir / "heatmap_content_overlap_stability.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()

    # 2. Ranking Stability (Kendall Tau)
    fig, ax = plt.subplots(figsize=(10, max(8, len(df) * 0.4)))

    kendall_matrix = df_sorted[["avg_kendall_tau"]].copy()
    kendall_matrix.index = df_sorted["query"]

    sns.heatmap(
        kendall_matrix,
        annot=True,
        fmt=".3f",
        cmap="RdYlGn",
        vmin=-1,
        vmax=1,
        cbar_kws={"label": "Kendall's Tau"},
        ax=ax,
        linewidths=0.5,
        linecolor="gray",
    )

    ax.set_title(
        f"Ranking Stability (Kendall's Tau)\n{df['num_runs'].iloc[0]} runs",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Questions", fontsize=12)
    ax.set_xlabel("")

    plt.tight_layout()
    plt.savefig(
        output_dir / "heatmap_ranking_stability.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    # 3. F1 Score Stability
    fig, ax = plt.subplots(figsize=(10, max(8, len(df) * 0.4)))

    f1_std_matrix = df_sorted[["std_f1_score"]].copy()
    f1_std_matrix.index = df_sorted["query"]

    sns.heatmap(
        f1_std_matrix,
        annot=True,
        fmt=".3f",
        cmap="Oranges",
        vmin=0,
        cbar_kws={"label": "Std Dev"},
        ax=ax,
        linewidths=0.5,
        linecolor="gray",
    )

    ax.set_title(
        f"F1 Score Stability (Std Dev)\n{df['num_runs'].iloc[0]} runs",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_ylabel("Questions", fontsize=12)
    ax.set_xlabel("")

    plt.tight_layout()
    plt.savefig(
        output_dir / "heatmap_f1_stability.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    print(f"✅ Generated stability heatmaps in {output_dir}")


def generate_stability_report(df: pd.DataFrame, output_dir: Path):
    """Generate text report with stability analysis.

    Args:
        df: DataFrame with stability metrics
        output_dir: Output directory
    """
    report_path = output_dir / "url_stability_report.txt"

    with open(report_path, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("URL Retrieval Stability Analysis\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Total Questions: {len(df)}\n")
        f.write(f"Runs per Question: {df['num_runs'].iloc[0]}\n\n")

        f.write("-" * 80 + "\n")
        f.write("Overall Stability Metrics\n")
        f.write("-" * 80 + "\n")
        f.write(
            f"Average Content Overlap (Jaccard): {df['avg_jaccard'].mean():.3f}\n"
        )
        f.write(
            f"Average Ranking Correlation (Kendall): {df['avg_kendall_tau'].mean():.3f}\n"
        )
        f.write(
            f"Average Ranking Correlation (Spearman): {df['avg_spearman_rho'].mean():.3f}\n"
        )
        f.write(f"Average F1 Score: {df['avg_f1_score'].mean():.3f}\n")
        f.write(f"Average F1 Std Dev: {df['std_f1_score'].mean():.3f}\n\n")

        f.write("-" * 80 + "\n")
        f.write("Most Stable Questions (by content overlap)\n")
        f.write("-" * 80 + "\n")
        for i, (_, row) in enumerate(
            df.nlargest(5, "avg_jaccard").iterrows(), 1
        ):
            f.write(
                f"{i}. [Jaccard={row['avg_jaccard']:.3f}] {row['query'][:70]}...\n"
            )

        f.write("\n" + "-" * 80 + "\n")
        f.write("Least Stable Questions (by content overlap)\n")
        f.write("-" * 80 + "\n")
        for i, (_, row) in enumerate(
            df.nsmallest(5, "avg_jaccard").iterrows(), 1
        ):
            f.write(
                f"{i}. [Jaccard={row['avg_jaccard']:.3f}] {row['query'][:70]}...\n"
            )

        f.write("\n" + "-" * 80 + "\n")
        f.write("Expected URL Position Tracking (sample)\n")
        f.write("-" * 80 + "\n")

        # Show expected URL metrics for first 3 questions
        for i, (_, row) in enumerate(df.head(3).iterrows(), 1):
            f.write(f"\n{i}. {row['query'][:70]}...\n")
            for url_metric in row["expected_url_metrics"]:
                if url_metric["avg_position"] is not None:
                    f.write(
                        f"   {url_metric['url'][:50]}: "
                        f"found {url_metric['found_rate']:.0%}, "
                        f"avg_pos={url_metric['avg_position']:.1f} "
                        f"(±{url_metric['std_position']:.1f})\n"
                    )
                else:
                    f.write(
                        f"   {url_metric['url'][:50]}: "
                        f"found {url_metric['found_rate']:.0%}, never retrieved\n"
                    )

    print(f"✅ Generated stability report: {report_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze URL retrieval stability across multiple runs"
    )
    parser.add_argument(
        "--input",
        nargs="+",
        required=True,
        help="Paths to detailed CSV files from evaluation runs",
    )
    parser.add_argument(
        "--output",
        default="./analysis_output/url_stability",
        help="Output directory for analysis results",
    )

    args = parser.parse_args()

    # Expand glob patterns and convert to Path objects
    csv_files = []
    for pattern in args.input:
        from glob import glob

        csv_files.extend([Path(f) for f in glob(pattern)])

    if not csv_files:
        print("❌ No CSV files found")
        return

    print(f"\n{'='*80}")
    print(f"URL Retrieval Stability Analysis")
    print(f"{'='*80}")
    print(f"CSV files: {len(csv_files)}")
    for csv_file in csv_files:
        print(f"  - {csv_file}")
    print(f"{'='*80}\n")

    # Analyze stability
    df_stability = analyze_url_stability(csv_files)

    # Save detailed metrics to CSV
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save main metrics (excluding nested dicts)
    df_export = df_stability.drop(columns=["expected_url_metrics"]).copy()
    csv_path = output_dir / "url_stability_metrics.csv"
    df_export.to_csv(csv_path, index=False)
    print(f"✅ Saved stability metrics: {csv_path}")

    # Save expected URL metrics as JSON
    expected_url_data = {
        row["query"]: row["expected_url_metrics"]
        for _, row in df_stability.iterrows()
    }
    json_path = output_dir / "expected_url_positions.json"
    with open(json_path, "w") as f:
        json.dump(expected_url_data, f, indent=2)
    print(f"✅ Saved expected URL positions: {json_path}")

    # Generate heatmaps
    create_stability_heatmaps(df_stability, output_dir)

    # Generate report
    generate_stability_report(df_stability, output_dir)

    print(f"\n{'='*80}")
    print(f"Analysis Complete!")
    print(f"{'='*80}")
    print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    main()

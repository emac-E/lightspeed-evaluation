#!/usr/bin/env python3
"""Analyze test failures and regressions from evaluation runs."""

import ast
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


def load_run_data(run_dir: Path) -> pd.DataFrame:
    """Load all detailed CSV files from a run directory."""
    csv_files = list(run_dir.glob("*/evaluation_*_detailed.csv"))

    if not csv_files:
        return pd.DataFrame()

    all_data = []
    for csv_file in csv_files:
        test_config = csv_file.parent.name
        df = pd.read_csv(csv_file)
        df["test_config"] = test_config
        all_data.append(df)

    return pd.concat(all_data, ignore_index=True)


def analyze_failures(df: pd.DataFrame) -> dict:
    """Analyze failures in the dataset."""
    # Filter to failed tests (result == "FAIL")
    failures = df[df["result"] == "FAIL"].copy()

    # Group by test config
    failures_by_config = failures.groupby("test_config").agg(
        total_failures=("result", "count"),
        unique_questions=("conversation_group_id", "nunique"),
        metrics_failed=("metric_identifier", lambda x: list(x.unique())),
    ).to_dict(orient="index")

    # Get failure details
    failure_details = []
    for _, row in failures.iterrows():
        failure_details.append({
            "test_config": row["test_config"],
            "question": row["conversation_group_id"],
            "turn_id": row["turn_id"],
            "metric": row["metric_identifier"],
            "score": row["score"],
            "threshold": row["threshold"],
            "reason": row["reason"][:200] if pd.notna(row["reason"]) else "N/A",
        })

    return {
        "by_config": failures_by_config,
        "details": failure_details,
        "total_failures": len(failures),
    }


def compare_runs(current_df: pd.DataFrame, previous_df: pd.DataFrame) -> dict:
    """Compare two runs to identify regressions."""
    # Merge on conversation_group_id, turn_id, test_config, and metric
    merge_keys = ["conversation_group_id", "turn_id", "test_config", "metric_identifier"]

    comparison = pd.merge(
        current_df[merge_keys + ["result", "score"]],
        previous_df[merge_keys + ["result", "score"]],
        on=merge_keys,
        how="outer",
        suffixes=("_current", "_previous"),
    )

    # Find regressions (passed before, failed now)
    regressions = comparison[
        (comparison["result_previous"] == "PASS") &
        (comparison["result_current"] == "FAIL")
    ]

    # Find improvements (failed before, passed now)
    improvements = comparison[
        (comparison["result_previous"] == "FAIL") &
        (comparison["result_current"] == "PASS")
    ]

    # Find new failures (not in previous run)
    new_failures = comparison[
        (comparison["result_current"] == "FAIL") &
        (comparison["result_previous"].isna())
    ]

    return {
        "regressions": len(regressions),
        "improvements": len(improvements),
        "new_failures": len(new_failures),
        "regression_details": regressions.to_dict(orient="records"),
        "improvement_details": improvements.to_dict(orient="records"),
    }


def find_worst_performing_test_config(df: pd.DataFrame) -> tuple:
    """Find the worst performing test config and analyze its failures.

    Returns:
        Tuple of (test_config_name, failure_rate, detailed_analysis)
    """
    # Calculate failure rates per test config
    config_stats = []
    for test_config in df["test_config"].unique():
        config_df = df[df["test_config"] == test_config]
        total = len(config_df)
        failures = len(config_df[config_df["result"] == "FAIL"])
        fail_rate = (failures / total * 100) if total > 0 else 0

        config_stats.append({
            "config": test_config,
            "total": total,
            "failures": failures,
            "fail_rate": fail_rate,
        })

    # Sort by failure count (absolute number)
    config_stats.sort(key=lambda x: x["failures"], reverse=True)
    worst_config = config_stats[0]["config"]

    # Analyze worst config
    worst_df = df[df["test_config"] == worst_config]

    # Get failure stats per question
    question_stats = []
    for question in worst_df["conversation_group_id"].unique():
        q_df = worst_df[worst_df["conversation_group_id"] == question]
        total = len(q_df)
        failures = len(q_df[q_df["result"] == "FAIL"])
        fail_rate = (failures / total * 100) if total > 0 else 0

        # Get failed metrics
        failed_metrics = q_df[q_df["result"] == "FAIL"]["metric_identifier"].tolist()

        question_stats.append({
            "question": question,
            "total": total,
            "failures": failures,
            "fail_rate": fail_rate,
            "failed_metrics": failed_metrics,
        })

    question_stats.sort(key=lambda x: x["failures"], reverse=True)

    return worst_config, config_stats[0], question_stats


def extract_urls_from_context(context_str: str) -> list:
    """Extract URLs from context string.

    Context can be a string representation of a list or a JSON string.
    The context may be structured as dictionaries or as formatted text with "URL: ..." lines.
    """
    if pd.isna(context_str) or not context_str:
        return []

    urls = []
    import re

    try:
        # Try parsing as Python list first
        try:
            contexts = ast.literal_eval(context_str)
        except (ValueError, SyntaxError):
            # Try JSON
            contexts = json.loads(context_str)

        # Extract URLs from each context item
        if isinstance(contexts, list):
            for ctx in contexts:
                if isinstance(ctx, dict):
                    # Look for URL field in dictionary
                    if "url" in ctx:
                        urls.append(ctx["url"])
                    elif "source" in ctx:
                        urls.append(ctx["source"])
                    elif "metadata" in ctx and isinstance(ctx["metadata"], dict):
                        if "url" in ctx["metadata"]:
                            urls.append(ctx["metadata"]["url"])
                        elif "source" in ctx["metadata"]:
                            urls.append(ctx["metadata"]["source"])
                elif isinstance(ctx, str):
                    # Extract URLs from formatted text like "URL: https://..."
                    url_pattern = r'URL:\s*(https?://[^\s\n]+)'
                    found_urls = re.findall(url_pattern, ctx)
                    urls.extend(found_urls)

                    # Also try general URL pattern if no "URL:" prefix found
                    if not found_urls:
                        general_pattern = r'https?://[^\s\'"<>\n]+'
                        found_urls = re.findall(general_pattern, ctx)
                        urls.extend(found_urls)

    except Exception:
        # If parsing fails, try to find URLs in raw string
        url_pattern = r'URL:\s*(https?://[^\s\n]+)'
        found_urls = re.findall(url_pattern, context_str)
        if found_urls:
            urls.extend(found_urls)
        else:
            # Fallback to general URL pattern
            general_pattern = r'https?://[^\s\'"<>\n]+'
            urls = re.findall(general_pattern, context_str)

    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return unique_urls


def find_worst_scoring_questions(df: pd.DataFrame, limit: int = 10) -> list:
    """Find questions with worst mean scores across all metrics.

    Returns:
        List of dictionaries with question info and mean scores
    """
    # Filter to failed tests only
    failures = df[df["result"] == "FAIL"].copy()

    # Calculate mean score per question
    question_scores = failures.groupby("conversation_group_id").agg(
        mean_score=("score", "mean"),
        num_failures=("result", "count"),
        test_config=("test_config", "first"),
        failed_metrics=("metric_identifier", lambda x: list(x.unique())),
    ).reset_index()

    # Sort by mean score (lowest first)
    question_scores = question_scores.sort_values("mean_score")

    return question_scores.head(limit).to_dict(orient="records")


def analyze_errors(df: pd.DataFrame) -> dict:
    """Analyze tests that resulted in ERROR status.

    Returns:
        Dictionary with error analysis
    """
    errors = df[df["result"] == "ERROR"].copy()

    if len(errors) == 0:
        return {"total_errors": 0, "details": []}

    # Group by error type
    error_details = []
    for _, row in errors.iterrows():
        error_details.append({
            "test_config": row["test_config"],
            "question": row["conversation_group_id"],
            "turn": row["turn_id"],
            "metric": row["metric_identifier"],
            "reason": row.get("reason", "N/A"),
        })

    # Count errors by metric
    errors_by_metric = errors.groupby("metric_identifier").size().to_dict()

    # Count errors by test config
    errors_by_config = errors.groupby("test_config").size().to_dict()

    return {
        "total_errors": len(errors),
        "details": error_details,
        "by_metric": errors_by_metric,
        "by_config": errors_by_config,
    }


def get_context_details_for_question(
    df: pd.DataFrame, question_id: str, test_config: str
) -> list:
    """Get detailed context information for a specific question.

    Returns:
        List of dictionaries with turn-by-turn context details
    """
    question_df = df[
        (df["conversation_group_id"] == question_id) &
        (df["test_config"] == test_config) &
        (df["result"] == "FAIL")
    ]

    context_details = []
    for _, row in question_df.iterrows():
        urls = extract_urls_from_context(row.get("contexts", ""))

        context_details.append({
            "turn": row["turn_id"],
            "metric": row["metric_identifier"],
            "score": row["score"],
            "threshold": row.get("threshold", "N/A"),
            "query": row.get("query", "N/A"),
            "response": row.get("response", "N/A"),
            "contexts_raw": row.get("contexts", "N/A"),
            "urls": urls,
            "reason": row.get("reason", "N/A"),
        })

    return context_details


def analyze_context_issues(df: pd.DataFrame, test_config: str) -> dict:
    """Analyze context quality issues for a specific test config.

    Returns:
        Dictionary with context analysis
    """
    config_df = df[df["test_config"] == test_config]
    failures = config_df[config_df["result"] == "FAIL"]

    # Analyze context-related failures
    context_metrics = [
        "ragas:context_relevance",
        "ragas:context_precision_without_reference",
        "ragas:context_recall",
    ]

    context_failures = failures[failures["metric_identifier"].isin(context_metrics)]

    # Get examples of bad contexts
    context_examples = []
    for _, row in context_failures.head(10).iterrows():
        if pd.notna(row.get("contexts")):
            context_examples.append({
                "question": row["conversation_group_id"],
                "turn": row["turn_id"],
                "metric": row["metric_identifier"],
                "score": row["score"],
                "query": row.get("query", "N/A")[:200],
                "contexts": row["contexts"][:500] if isinstance(row["contexts"], str) else str(row["contexts"])[:500],
                "response": row.get("response", "N/A")[:200],
            })

    return {
        "total_context_failures": len(context_failures),
        "examples": context_examples,
    }


def generate_report(
    current_run: Path,
    previous_run: Path,
    output_file: Path,
) -> None:
    """Generate failure analysis report."""
    # Load data
    print(f"Loading current run: {current_run.name}")
    current_df = load_run_data(current_run)

    print(f"Loading previous run: {previous_run.name}")
    previous_df = load_run_data(previous_run)

    if current_df.empty:
        print("❌ No data in current run")
        return

    # Analyze failures
    print("Analyzing failures...")
    failures = analyze_failures(current_df)

    # Find worst performing test config
    print("Finding worst performing test config...")
    worst_config, worst_stats, worst_questions = find_worst_performing_test_config(current_df)

    # Analyze context issues for worst config
    print("Analyzing context issues...")
    context_analysis = analyze_context_issues(current_df, worst_config)

    # Find worst scoring questions
    print("Finding worst scoring questions...")
    worst_scoring = find_worst_scoring_questions(current_df, limit=10)

    # Analyze errors
    print("Analyzing errors...")
    error_analysis = analyze_errors(current_df)

    # Compare with previous run
    regression_data = None
    if not previous_df.empty:
        print("Comparing with previous run...")
        regression_data = compare_runs(current_df, previous_df)

    # Calculate overall stats
    total_tests = len(current_df)
    total_pass = len(current_df[current_df["result"] == "PASS"])
    total_fail = len(current_df[current_df["result"] == "FAIL"])
    pass_rate = (total_pass / total_tests * 100) if total_tests > 0 else 0

    # Parse timestamp from directory name
    timestamp_str = current_run.name.replace("full_suite_", "")
    try:
        run_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        run_time_formatted = run_time.strftime("%B %d, %Y at %I:%M %p")
    except ValueError:
        run_time_formatted = timestamp_str

    # Write report
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("EVALUATION TEST FAILURE ANALYSIS\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Test Run Date: {run_time_formatted}\n")
        f.write(f"Run Directory: {current_run.name}\n")
        if regression_data:
            f.write(f"Previous Run: {previous_run.name}\n")
        f.write("\n")

        # Overall Summary
        f.write("=" * 80 + "\n")
        f.write("OVERALL SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total Test Evaluations: {total_tests:,}\n")
        f.write(f"Passed: {total_pass:,} ({total_pass/total_tests*100:.1f}%)\n")
        f.write(f"Failed: {total_fail:,} ({total_fail/total_tests*100:.1f}%)\n")
        f.write(f"Pass Rate: {pass_rate:.1f}%\n\n")

        # Regression Summary
        if regression_data:
            f.write("=" * 80 + "\n")
            f.write("REGRESSION SUMMARY (vs Previous Run)\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Regressions (Passed → Failed): {regression_data['regressions']}\n")
            f.write(f"Improvements (Failed → Passed): {regression_data['improvements']}\n")
            f.write(f"New Failures (Not in Previous): {regression_data['new_failures']}\n\n")

        # Failures by Test Config
        f.write("=" * 80 + "\n")
        f.write("FAILURES BY TEST CONFIG\n")
        f.write("=" * 80 + "\n\n")

        for config_name, config_data in failures["by_config"].items():
            f.write(f"{config_name}:\n")
            f.write(f"  Total Failures: {config_data['total_failures']}\n")
            f.write(f"  Unique Questions Affected: {config_data['unique_questions']}\n")
            f.write(f"  Metrics Failed: {', '.join(config_data['metrics_failed'])}\n")
            f.write("\n")

        # Worst Performing Test Config
        f.write("=" * 80 + "\n")
        f.write("WORST PERFORMING TEST CONFIG (Detailed Analysis)\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Test Config: {worst_config}\n")
        f.write(f"Total Tests: {worst_stats['total']}\n")
        f.write(f"Failures: {worst_stats['failures']}\n")
        f.write(f"Failure Rate: {worst_stats['fail_rate']:.1f}%\n\n")

        f.write("Failures by Question:\n")
        f.write("-" * 80 + "\n")
        for q_stat in worst_questions[:10]:  # Top 10 worst questions
            f.write(f"\n{q_stat['question']}:\n")
            f.write(f"  Tests: {q_stat['total']}\n")
            f.write(f"  Failures: {q_stat['failures']} ({q_stat['fail_rate']:.1f}%)\n")
            f.write(f"  Failed Metrics: {', '.join(set(q_stat['failed_metrics']))}\n")

        f.write("\n")

        # Context Analysis
        f.write("=" * 80 + "\n")
        f.write("CONTEXT QUALITY ANALYSIS (Worst Performing Test Config)\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Total Context-Related Failures: {context_analysis['total_context_failures']}\n\n")

        if context_analysis["examples"]:
            f.write("Example Context Issues:\n")
            f.write("-" * 80 + "\n\n")

            for idx, example in enumerate(context_analysis["examples"], 1):
                f.write(f"Example {idx}:\n")
                f.write(f"Question: {example['question']}\n")
                f.write(f"Turn: {example['turn']}\n")
                f.write(f"Metric: {example['metric']} (Score: {example['score']:.3f})\n\n")
                f.write(f"Query:\n{example['query']}\n\n")
                f.write(f"Retrieved Context:\n{example['contexts']}\n\n")
                f.write(f"Generated Response:\n{example['response']}\n")
                f.write("-" * 80 + "\n\n")
        else:
            f.write("No context examples available (contexts not in CSV)\n\n")

        # Worst Scoring Questions with Full Context URLs
        f.write("=" * 80 + "\n")
        f.write("WORST SCORING QUESTIONS (Lowest Mean Scores)\n")
        f.write("=" * 80 + "\n\n")

        for idx, q_info in enumerate(worst_scoring, 1):
            f.write(f"#{idx} - {q_info['conversation_group_id']}\n")
            f.write(f"Test Config: {q_info['test_config']}\n")
            f.write(f"Mean Score: {q_info['mean_score']:.3f}\n")
            f.write(f"Number of Failures: {q_info['num_failures']}\n")
            f.write(f"Failed Metrics: {', '.join(q_info['failed_metrics'])}\n")
            f.write("\n")

            # Get detailed context for this question
            context_details = get_context_details_for_question(
                current_df, q_info['conversation_group_id'], q_info['test_config']
            )

            for detail in context_details:
                f.write(f"  Turn: {detail['turn']}\n")
                f.write(f"  Metric: {detail['metric']} (Score: {detail['score']:.3f}, Threshold: {detail['threshold']})\n")
                f.write(f"  Query: {detail['query'][:200]}\n\n")

                if detail['urls']:
                    f.write(f"  Retrieved Context URLs ({len(detail['urls'])} chunks):\n")
                    for url_idx, url in enumerate(detail['urls'], 1):
                        f.write(f"    {url_idx}. {url}\n")
                    f.write("\n")
                else:
                    f.write("  No URLs found in context\n\n")

                f.write(f"  Response: {detail['response'][:300]}\n")
                f.write(f"  Failure Reason: {detail['reason'][:200]}\n")
                f.write("  " + "-" * 76 + "\n\n")

            f.write("-" * 80 + "\n\n")

        # Error Analysis Section
        if error_analysis['total_errors'] > 0:
            f.write("=" * 80 + "\n")
            f.write("ERROR ANALYSIS (Tests That Errored)\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"Total Errors: {error_analysis['total_errors']}\n\n")

            f.write("Errors by Test Config:\n")
            for config, count in sorted(error_analysis['by_config'].items(), key=lambda x: x[1], reverse=True):
                f.write(f"  {config}: {count} errors\n")
            f.write("\n")

            f.write("Errors by Metric:\n")
            for metric, count in sorted(error_analysis['by_metric'].items(), key=lambda x: x[1], reverse=True):
                f.write(f"  {metric}: {count} errors\n")
            f.write("\n")

            f.write("Error Details:\n")
            f.write("-" * 80 + "\n")
            for error in error_analysis['details']:
                f.write(f"Test Config: {error['test_config']}\n")
                f.write(f"Question: {error['question']}\n")
                f.write(f"Turn: {error['turn']}\n")
                f.write(f"Metric: {error['metric']}\n")
                f.write(f"Error Reason: {error['reason']}\n")
                f.write("-" * 80 + "\n")
            f.write("\n")
        else:
            f.write("=" * 80 + "\n")
            f.write("ERROR ANALYSIS\n")
            f.write("=" * 80 + "\n\n")
            f.write("✅ No errors occurred during this test run.\n\n")

        # Regression Details
        if regression_data and regression_data['regressions'] > 0:
            f.write("=" * 80 + "\n")
            f.write("REGRESSION DETAILS (Tests That Got Worse)\n")
            f.write("=" * 80 + "\n\n")

            for reg in regression_data['regression_details'][:20]:  # Limit to top 20
                f.write(f"Test Config: {reg['test_config']}\n")
                f.write(f"Question: {reg['conversation_group_id']}\n")
                f.write(f"Turn: {reg['turn_id']}\n")
                f.write(f"Metric: {reg['metric_identifier']}\n")
                f.write(f"Score: {reg['score_previous']:.3f} → {reg['score_current']:.3f}\n")
                f.write("-" * 80 + "\n")

        # Top Failures by Score
        f.write("=" * 80 + "\n")
        f.write("TOP FAILURES (Lowest Scores Below Threshold)\n")
        f.write("=" * 80 + "\n\n")

        # Sort failures by how far below threshold
        sorted_failures = sorted(
            failures["details"],
            key=lambda x: x["score"] - x["threshold"] if pd.notna(x["threshold"]) else -999
        )

        for failure in sorted_failures[:30]:  # Top 30 worst failures
            f.write(f"Test Config: {failure['test_config']}\n")
            f.write(f"Question: {failure['question']}\n")
            f.write(f"Turn: {failure['turn_id']}\n")
            f.write(f"Metric: {failure['metric']}\n")
            f.write(f"Score: {failure['score']:.3f} (Threshold: {failure['threshold']:.3f})\n")
            f.write(f"Delta: {failure['score'] - failure['threshold']:.3f}\n")
            f.write(f"Reason: {failure['reason']}\n")
            f.write("-" * 80 + "\n")

        # Failure Patterns
        f.write("\n" + "=" * 80 + "\n")
        f.write("FAILURE ANALYSIS BY METRIC\n")
        f.write("=" * 80 + "\n\n")

        current_failures = current_df[current_df["result"] == "FAIL"]
        failure_by_metric = current_failures.groupby("metric_identifier").agg(
            count=("result", "count"),
            avg_score=("score", "mean"),
            avg_threshold=("threshold", "mean"),
        ).sort_values("count", ascending=False)

        for metric, data in failure_by_metric.iterrows():
            f.write(f"{metric}:\n")
            f.write(f"  Failure Count: {int(data['count'])}\n")
            f.write(f"  Average Score: {data['avg_score']:.3f}\n")
            f.write(f"  Average Threshold: {data['avg_threshold']:.3f}\n")
            f.write(f"  Average Gap: {data['avg_score'] - data['avg_threshold']:.3f}\n")
            f.write("\n")

    print(f"\n✅ Report saved: {output_file}")


def main():
    """Main entry point."""
    # Get the two most recent runs
    base_dir = Path("eval_output")

    all_runs = sorted(
        [d for d in base_dir.glob("full_suite_*") if d.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )

    # Filter to runs with CSV files
    valid_runs = []
    for run_dir in all_runs:
        csv_files = list(run_dir.glob("*/evaluation_*_detailed.csv"))
        if csv_files:
            valid_runs.append(run_dir)

    if len(valid_runs) < 1:
        print("❌ No valid runs found")
        return 1

    current_run = valid_runs[0]
    previous_run = valid_runs[1] if len(valid_runs) > 1 else None

    print(f"Current run: {current_run.name}")
    if previous_run:
        print(f"Previous run: {previous_run.name}")

    output_file = current_run / "FAILURE_ANALYSIS.md"

    generate_report(current_run, previous_run, output_file)

    print(f"\nView report with:")
    print(f"  cat {output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

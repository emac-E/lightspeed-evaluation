#!/usr/bin/env python3
"""Compare error resolution between two evaluation runs.

This script tracks which questions had errors and whether they were resolved
in a subsequent run. Useful for tracking progress on fixing specific failures.

Usage:
    # Auto-compare last two runs (default)
    python scripts/compare_error_resolution.py

    # Compare specific runs
    python scripts/compare_error_resolution.py \\
        eval_output/full_suite_20260327_095952 \\
        eval_output/full_suite_20260327_141431

    # Or specific config
    python scripts/compare_error_resolution.py \\
        eval_output/run1/temporal_validity_tests_runnable \\
        eval_output/run2/temporal_validity_tests_runnable \\
        --output error_resolution_report.txt
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


def find_latest_runs(base_dir: Path = Path("eval_output"), n: int = 2) -> List[Path]:
    """Find the N most recent full_suite run directories.

    Args:
        base_dir: Base directory to search for runs
        n: Number of recent runs to return

    Returns:
        List of run directories, newest first
    """
    # Find all full_suite directories
    run_dirs = list(base_dir.glob("full_suite_*"))

    if not run_dirs:
        raise FileNotFoundError(f"No full_suite runs found in {base_dir}")

    # Sort by modification time, newest first
    run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return run_dirs[:n]


def find_detailed_csv(run_dir: Path) -> Path:
    """Find the detailed CSV in a run directory."""
    csv_files = list(run_dir.glob("*_detailed.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No detailed CSV found in {run_dir}")
    if len(csv_files) > 1:
        # Use the most recent
        csv_files.sort(key=lambda p: p.stat().st_mtime)
    return csv_files[-1]


def find_all_detailed_csvs(run_dir: Path) -> List[Path]:
    """Find all detailed CSVs in a full_suite run directory.

    Args:
        run_dir: Full suite run directory containing subdirectories per config

    Returns:
        List of paths to detailed CSV files
    """
    csv_files = []

    # Check if this is a full_suite directory with subdirectories
    subdirs = [d for d in run_dir.iterdir() if d.is_dir()]

    if subdirs:
        # This is a full_suite run, find CSVs in each config subdir
        for subdir in subdirs:
            config_csvs = list(subdir.glob("*_detailed.csv"))
            if config_csvs:
                # Use the most recent CSV in this subdir
                config_csvs.sort(key=lambda p: p.stat().st_mtime)
                csv_files.append(config_csvs[-1])
    else:
        # Single config directory, find CSV directly
        csv_files = list(run_dir.glob("*_detailed.csv"))
        if csv_files:
            csv_files.sort(key=lambda p: p.stat().st_mtime)
            csv_files = [csv_files[-1]]

    if not csv_files:
        raise FileNotFoundError(f"No detailed CSVs found in {run_dir}")

    return csv_files


def load_multiple_csvs(csv_paths: List[Path]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load and combine multiple CSV files.

    Returns:
        Tuple of (errors_df, all_data_df)
    """
    all_errors = []
    all_data = []

    for csv_path in csv_paths:
        df = pd.read_csv(csv_path)
        all_data.append(df)

        # Filter errors (result == 'ERROR')
        errors = df[df['result'] == 'ERROR']
        all_errors.append(errors)

    # Combine all dataframes
    combined_errors = pd.concat(all_errors, ignore_index=True) if all_errors else pd.DataFrame()
    combined_all = pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()

    return combined_errors, combined_all


def load_error_data(csv_path: Path) -> pd.DataFrame:
    """Load and filter error data from detailed CSV."""
    df = pd.read_csv(csv_path)

    # Keep only rows with errors (result == 'ERROR')
    errors = df[df['result'] == 'ERROR'].copy()

    # Also keep passing/failing for comparison
    all_data = df.copy()

    return errors, all_data


def compare_errors(
    baseline_errors: pd.DataFrame,
    baseline_all: pd.DataFrame,
    current_errors: pd.DataFrame,
    current_all: pd.DataFrame
) -> Dict[str, List[Dict]]:
    """Compare errors between baseline and current runs."""

    results = {
        'resolved': [],      # Was error, now passing
        'persisting': [],    # Still error
        'new_errors': [],    # Was passing/fail, now error
        'status_change': [], # Error to fail or fail to error (still not passing)
    }

    # Create lookup keys: conversation + turn + metric
    def make_key(row):
        return f"{row['conversation_group_id']}|{row['turn_id']}|{row['metric_identifier']}"

    # Build dictionaries for quick lookup
    baseline_error_keys = set(baseline_errors.apply(make_key, axis=1))
    current_error_keys = set(current_errors.apply(make_key, axis=1))

    # Build full status lookups
    baseline_status = {}
    for _, row in baseline_all.iterrows():
        key = make_key(row)
        baseline_status[key] = {
            'status': row['result'],
            'score': row['score'],
            'reason': row.get('reason', ''),
            'conversation': row['conversation_group_id'],
            'turn': row['turn_id'],
            'metric': row['metric_identifier'],
            'question': row.get('query', 'N/A')[:100],  # Truncate for display
        }

    current_status = {}
    for _, row in current_all.iterrows():
        key = make_key(row)
        current_status[key] = {
            'status': row['result'],
            'score': row['score'],
            'reason': row.get('reason', ''),
            'conversation': row['conversation_group_id'],
            'turn': row['turn_id'],
            'metric': row['metric_identifier'],
            'question': row.get('query', 'N/A')[:100],
        }

    # Find all unique keys
    all_keys = set(baseline_status.keys()) | set(current_status.keys())

    for key in all_keys:
        baseline = baseline_status.get(key, {'status': 'missing'})
        current = current_status.get(key, {'status': 'missing'})

        baseline_is_error = baseline['status'] == 'ERROR'
        current_is_error = current['status'] == 'ERROR'

        if baseline_is_error and not current_is_error:
            # Error resolved!
            if current['status'] == 'PASS':
                results['resolved'].append({
                    **current,
                    'baseline_reason': baseline.get('reason', ''),
                })

        elif baseline_is_error and current_is_error:
            # Error persists
            results['persisting'].append({
                **current,
                'baseline_reason': baseline.get('reason', ''),
            })

        elif not baseline_is_error and current_is_error:
            # New error
            results['new_errors'].append({
                **current,
                'baseline_status': baseline['status'],
                'baseline_score': baseline.get('score', 'N/A'),
            })

        elif baseline['status'] == 'FAIL' and current['status'] == 'ERROR':
            # Degraded from fail to error
            results['status_change'].append({
                **current,
                'baseline_status': 'FAIL',
                'change': 'FAIL → ERROR',
            })

        elif baseline['status'] == 'ERROR' and current['status'] == 'FAIL':
            # Improved from error to fail (still not passing though)
            results['status_change'].append({
                **current,
                'baseline_status': 'ERROR',
                'change': 'ERROR → FAIL',
            })

    return results


def generate_report(
    results: Dict[str, List[Dict]],
    baseline_path: Path,
    current_path: Path,
    output_path: Path = None
) -> str:
    """Generate human-readable report."""

    lines = []
    lines.append("=" * 80)
    lines.append("ERROR RESOLUTION REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Baseline: {baseline_path}")
    lines.append(f"Current:  {current_path}")
    lines.append("")

    # Summary
    lines.append("=" * 80)
    lines.append("SUMMARY")
    lines.append("=" * 80)
    lines.append(f"✅ Errors Resolved:  {len(results['resolved'])}")
    lines.append(f"⚠️  Errors Persisting: {len(results['persisting'])}")
    lines.append(f"🆕 New Errors:       {len(results['new_errors'])}")
    lines.append(f"🔄 Status Changes:   {len(results['status_change'])}")
    lines.append("")

    # Errors Resolved
    if results['resolved']:
        lines.append("=" * 80)
        lines.append("✅ ERRORS RESOLVED")
        lines.append("=" * 80)
        lines.append("")

        for item in results['resolved']:
            lines.append(f"Conversation: {item['conversation']}")
            lines.append(f"Turn:         {item['turn']}")
            lines.append(f"Metric:       {item['metric']}")
            lines.append(f"Status:       error → {item['status']}")
            lines.append(f"Score:        {item['score']}")
            lines.append(f"Question:     {item['question']}")
            if item.get('baseline_reason'):
                lines.append(f"Was Error:    {item['baseline_reason'][:200]}")
            lines.append("")

    # Persisting Errors
    if results['persisting']:
        lines.append("=" * 80)
        lines.append("⚠️  ERRORS PERSISTING")
        lines.append("=" * 80)
        lines.append("")

        # Group by metric
        by_metric = {}
        for item in results['persisting']:
            metric = item['metric']
            if metric not in by_metric:
                by_metric[metric] = []
            by_metric[metric].append(item)

        for metric, items in sorted(by_metric.items()):
            lines.append(f"--- {metric} ({len(items)} errors) ---")
            lines.append("")

            for item in items:
                lines.append(f"  {item['conversation']} / {item['turn']}")
                lines.append(f"  Question: {item['question']}")
                lines.append(f"  Error:    {item['reason'][:200]}")
                lines.append("")

    # New Errors
    if results['new_errors']:
        lines.append("=" * 80)
        lines.append("🆕 NEW ERRORS")
        lines.append("=" * 80)
        lines.append("")

        for item in results['new_errors']:
            lines.append(f"Conversation: {item['conversation']}")
            lines.append(f"Turn:         {item['turn']}")
            lines.append(f"Metric:       {item['metric']}")
            lines.append(f"Status:       {item['baseline_status']} → error")
            lines.append(f"Question:     {item['question']}")
            lines.append(f"Error:        {item['reason'][:200]}")
            lines.append("")

    # Status Changes
    if results['status_change']:
        lines.append("=" * 80)
        lines.append("🔄 STATUS CHANGES (error ↔ fail)")
        lines.append("=" * 80)
        lines.append("")

        for item in results['status_change']:
            lines.append(f"Conversation: {item['conversation']}")
            lines.append(f"Turn:         {item['turn']}")
            lines.append(f"Metric:       {item['metric']}")
            lines.append(f"Change:       {item['change']}")
            lines.append(f"Question:     {item['question']}")
            lines.append("")

    # Metrics breakdown
    lines.append("=" * 80)
    lines.append("ERROR BREAKDOWN BY METRIC")
    lines.append("=" * 80)
    lines.append("")

    # Collect all metrics
    all_metrics = set()
    for category in ['resolved', 'persisting', 'new_errors']:
        for item in results[category]:
            all_metrics.add(item['metric'])

    for metric in sorted(all_metrics):
        resolved_count = sum(1 for x in results['resolved'] if x['metric'] == metric)
        persisting_count = sum(1 for x in results['persisting'] if x['metric'] == metric)
        new_count = sum(1 for x in results['new_errors'] if x['metric'] == metric)

        total_baseline = persisting_count + resolved_count
        total_current = persisting_count + new_count

        lines.append(f"{metric}:")
        lines.append(f"  Baseline errors: {total_baseline}")
        lines.append(f"  Current errors:  {total_current}")
        lines.append(f"  Resolved:        {resolved_count}")
        lines.append(f"  New:             {new_count}")
        lines.append(f"  Persisting:      {persisting_count}")
        lines.append("")

    report = "\n".join(lines)

    if output_path:
        output_path.write_text(report)
        print(f"Report written to: {output_path}")

    return report


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compare error resolution between two evaluation runs. "
                    "If no arguments provided, auto-compares last two runs."
    )
    parser.add_argument(
        "baseline",
        nargs='?',
        type=Path,
        help="Baseline run directory (or specific CSV). Default: auto-detect 2nd most recent run",
    )
    parser.add_argument(
        "current",
        nargs='?',
        type=Path,
        help="Current run directory (or specific CSV). Default: auto-detect most recent run",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file for report (default: print to stdout)",
    )

    args = parser.parse_args()

    # Auto-detect runs if not provided
    if args.baseline is None or args.current is None:
        print("No runs specified, auto-detecting last two runs...")
        try:
            latest_runs = find_latest_runs()
            if len(latest_runs) < 2:
                print("Error: Need at least 2 runs to compare", file=sys.stderr)
                sys.exit(1)

            current_run = latest_runs[0]
            baseline_run = latest_runs[1]

            print(f"Current run:  {current_run.name}")
            print(f"Baseline run: {baseline_run.name}")
            print()

        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        current_run = args.current
        baseline_run = args.baseline

    # Load CSV files
    # Check if these are directories or specific CSV files
    try:
        if current_run.is_dir():
            # Try to load all CSVs from full_suite run
            current_csvs = find_all_detailed_csvs(current_run)
            print(f"Loading {len(current_csvs)} CSV(s) from current run: {current_run}")
            current_errors, current_all = load_multiple_csvs(current_csvs)
        else:
            print(f"Loading current:  {current_run}")
            current_errors, current_all = load_error_data(current_run)

        if baseline_run.is_dir():
            baseline_csvs = find_all_detailed_csvs(baseline_run)
            print(f"Loading {len(baseline_csvs)} CSV(s) from baseline run: {baseline_run}")
            baseline_errors, baseline_all = load_multiple_csvs(baseline_csvs)
        else:
            print(f"Loading baseline: {baseline_run}")
            baseline_errors, baseline_all = load_error_data(baseline_run)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Baseline: {len(baseline_errors)} errors out of {len(baseline_all)} evaluations")
    print(f"Current:  {len(current_errors)} errors out of {len(current_all)} evaluations")
    print("")

    # Compare
    results = compare_errors(
        baseline_errors,
        baseline_all,
        current_errors,
        current_all
    )

    # Generate report
    report = generate_report(results, baseline_run, current_run, args.output)

    if not args.output:
        print(report)


if __name__ == "__main__":
    main()

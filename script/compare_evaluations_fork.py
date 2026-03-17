#!/usr/bin/env python3
"""Compare evaluation runs and display differences in a formatted table."""
""" mostly authored by Claude, mistakes fixed by EM """

import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.table import Table


def find_latest_evaluations(output_dir: Path, n: int = 2) -> list[Path]:
    """Find the n most recent evaluation summary JSON files.

    Args:
        output_dir: Directory containing evaluation outputs
        n: Number of recent files to find

    Returns:
        List of paths to summary JSON files, sorted newest first
    """
    summary_files = sorted(
        output_dir.glob("evaluation_*_summary.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if len(summary_files) < n:
        raise ValueError(
            f"Need at least {n} evaluation runs, found {len(summary_files)}"
        )

    return summary_files[:n]


def load_detailed_csv(summary_path: Path) -> pd.DataFrame:
    """Load the detailed CSV file corresponding to a summary JSON.

    Args:
        summary_path: Path to summary JSON file

    Returns:
        DataFrame with detailed evaluation results
    """
    # Replace _summary.json with _detailed.csv
    csv_path = summary_path.parent / summary_path.name.replace(
        "_summary.json", "_detailed.csv"
    )

    if not csv_path.exists():
        raise FileNotFoundError(f"Detailed CSV not found: {csv_path}")

    return pd.read_csv(csv_path)


def create_comparison_table(
    df_current: pd.DataFrame, df_previous: Optional[pd.DataFrame] = None
) -> Table:
    """Create a rich table comparing current and previous evaluation runs.

    Args:
        df_current: Current evaluation detailed data
        df_previous: Previous evaluation detailed data (optional)

    Returns:
        Rich Table object
    """
    console = Console()
    table = Table(title="Evaluation Comparison", show_lines=True)

    # Define columns
    table.add_column("Conversation", style="cyan", no_wrap=True)
    table.add_column("Turn", style="cyan")
    table.add_column("Query", style="white", max_width=40)
    table.add_column("Response", style="white", max_width=40)
    table.add_column("Metric", style="magenta")
    table.add_column("Score (Current)", style="green", justify="right")
    table.add_column("Result (Current)", style="bold")

    if df_previous is not None:
        table.add_column("Score (Previous)", style="yellow", justify="right")
        table.add_column("Result (Previous)", style="bold")
        table.add_column("Δ Score", style="bold", justify="right")

    # Group by conversation and turn to show each question once with all metrics
    grouped = df_current.groupby(["conversation_group_id", "turn_id"])

    for (conv_id, turn_id), group in grouped:
        first_row = group.iloc[0]
        query = str(first_row.get("query", "N/A"))[:80]
        response = str(first_row.get("response", "N/A"))[:80]

        # Add a row for each metric
        for idx, row in group.iterrows():
            metric = row["metric_identifier"]
            score_current = row.get("score")
            result_current = row["result"]

            # Format score
            score_current_str = (
                f"{score_current:.4f}" if pd.notna(score_current) else "N/A"
            )

            # Get result color
            result_color = {
                "PASS": "green",
                "FAIL": "red",
                "ERROR": "yellow",
                "SKIPPED": "dim",
            }.get(result_current, "white")

            row_data = [
                conv_id if idx == group.index[0] else "",
                turn_id if idx == group.index[0] else "",
                query if idx == group.index[0] else "",
                response if idx == group.index[0] else "",
                metric,
                score_current_str,
                f"[{result_color}]{result_current}[/{result_color}]",
            ]

            if df_previous is not None:
                # Find matching row in previous run
                prev_match = df_previous[
                    (df_previous["conversation_group_id"] == conv_id)
                    & (df_previous["turn_id"] == turn_id)
                    & (df_previous["metric_identifier"] == metric)
                ]

                if not prev_match.empty:
                    score_prev = prev_match.iloc[0].get("score")
                    result_prev = prev_match.iloc[0]["result"]

                    score_prev_str = (
                        f"{score_prev:.4f}" if pd.notna(score_prev) else "N/A"
                    )

                    result_prev_color = {
                        "PASS": "green",
                        "FAIL": "red",
                        "ERROR": "yellow",
                        "SKIPPED": "dim",
                    }.get(result_prev, "white")

                    # Calculate delta
                    if pd.notna(score_current) and pd.notna(score_prev):
                        delta = score_current - score_prev
                        delta_color = "green" if delta > 0 else "red" if delta < 0 else "white"
                        delta_str = f"[{delta_color}]{delta:+.4f}[/{delta_color}]"
                    else:
                        delta_str = "N/A"

                    row_data.extend(
                        [
                            score_prev_str,
                            f"[{result_prev_color}]{result_prev}[/{result_prev_color}]",
                            delta_str,
                        ]
                    )
                else:
                    row_data.extend(["N/A", "[dim]N/A[/dim]", "N/A"])

            table.add_row(*row_data)

    return table


def print_summary_stats(
    summary_current: dict, summary_previous: Optional[dict] = None
) -> None:
    """Print summary statistics comparison.

    Args:
        summary_current: Current run summary data
        summary_previous: Previous run summary data (optional)
    """
    console = Console()

    console.print("\n[bold cyan]Overall Summary Statistics[/bold cyan]\n")

    stats_current = summary_current["summary_stats"]["overall"]

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Current", justify="right", style="green")

    if summary_previous is not None:
        table.add_column("Previous", justify="right", style="yellow")
        table.add_column("Δ", justify="right", style="bold")
        stats_previous = summary_previous["summary_stats"]["overall"]
    else:
        stats_previous = None

    # Add rows for key metrics
    metrics = [
        ("Total Evaluations", "TOTAL"),
        ("Pass", "PASS"),
        ("Fail", "FAIL"),
        ("Error", "ERROR"),
        ("Pass Rate (%)", "pass_rate"),
        ("Fail Rate (%)", "fail_rate"),
        ("Error Rate (%)", "error_rate"),
        ("Total Tokens", "total_tokens"),
        ("Judge LLM Tokens", "total_judge_llm_tokens"),
        ("API Tokens", "total_api_tokens"),
    ]

    for label, key in metrics:
        current_val = stats_current.get(key, 0)
        row_data = [label, f"{current_val:,}"]

        if stats_previous is not None:
            prev_val = stats_previous.get(key, 0)
            delta = current_val - prev_val

            # Format delta with color
            if "rate" in key.lower() or "total" in key.lower():
                delta_color = "green" if delta > 0 and "pass" in key.lower() else "red" if delta < 0 and "pass" in key.lower() else "white"
            else:
                delta_color = "white"

            row_data.extend([f"{prev_val:,}", f"[{delta_color}]{delta:+,}[/{delta_color}]"])

        table.add_row(*row_data)

    console.print(table)


def main() -> None:
    """Main entry point for the comparison script."""
    console = Console()

    # Get output directory from command line or use default
    if len(sys.argv) > 1:
        output_dir = Path(sys.argv[1])
    else:
        output_dir = Path("/home/emackey/Work/lightspeed-core/lightspeed-evaluation/eval_output")

    if not output_dir.exists():
        console.print(f"[red]Error: Directory not found: {output_dir}[/red]")
        sys.exit(1)

    try:
        # Find latest evaluation files
        summary_files = find_latest_evaluations(output_dir, n=2)
        console.print(
            f"\n[bold]Comparing evaluations:[/bold]\n"
            f"  Current:  {summary_files[0].name}\n"
            f"  Previous: {summary_files[1].name}\n"
        )

        # Load summary JSON files
        with open(summary_files[0]) as f:
            summary_current = json.load(f)

        with open(summary_files[1]) as f:
            summary_previous = json.load(f)

        # Load detailed CSV files
        df_current = load_detailed_csv(summary_files[0])
        df_previous = load_detailed_csv(summary_files[1])

        # Print summary statistics
        print_summary_stats(summary_current, summary_previous)

        # Create and print comparison table
        console.print("\n[bold cyan]Detailed Results Comparison[/bold cyan]\n")
        table = create_comparison_table(df_current, df_previous)
        console.print(table)

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("\n[yellow]Showing current run only (no comparison)[/yellow]\n")

        # Show only current run
        summary_files = find_latest_evaluations(output_dir, n=1)
        console.print(f"Current evaluation: {summary_files[0].name}\n")

        with open(summary_files[0]) as f:
            summary_current = json.load(f)

        df_current = load_detailed_csv(summary_files[0])

        print_summary_stats(summary_current)
        console.print("\n[bold cyan]Detailed Results[/bold cyan]\n")
        table = create_comparison_table(df_current)
        console.print(table)

    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

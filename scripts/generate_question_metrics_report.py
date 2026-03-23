#!/usr/bin/env python3
"""
Generate detailed per-question metrics report.

Shows each question with all its metric scores, making it easy to:
- Identify which questions perform poorly
- Compare metrics across different question types
- Debug specific test cases
- Share examples with teams
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

import pandas as pd


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max_length with ellipsis."""
    if not text or pd.isna(text):
        return "N/A"
    text = str(text).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def format_score(score: float, threshold: Optional[float] = None) -> str:
    """Format score with pass/fail indicator."""
    if pd.isna(score):
        return "N/A"

    score_str = f"{score:.3f}"

    if threshold is not None and not pd.isna(threshold):
        if score >= threshold:
            return f"{score_str} ✅"
        else:
            return f"{score_str} ❌"

    return score_str


def generate_question_report(
    csv_files: list[Path],
    output_file: Path,
    include_contexts: bool = False,
    include_responses: bool = False,
) -> None:
    """Generate detailed per-question metrics report.

    Args:
        csv_files: List of detailed CSV files to analyze
        output_file: Output markdown file path
        include_contexts: Include retrieved contexts in report
        include_responses: Include actual responses in report
    """
    # Load all CSV files
    dfs = []
    for csv_file in csv_files:
        if csv_file.exists():
            df = pd.read_csv(csv_file)
            df['source_file'] = csv_file.stem
            dfs.append(df)
        else:
            print(f"Warning: {csv_file} not found, skipping")

    if not dfs:
        print("Error: No CSV files loaded")
        return

    # Combine all data
    all_data = pd.concat(dfs, ignore_index=True)

    # Get unique questions (conversation + turn)
    questions = all_data.groupby(['conversation_group_id', 'turn_id', 'query']).first().reset_index()

    # Build report
    report_lines = [
        "# Question-Level Metrics Report",
        "",
        f"**Total Questions Analyzed:** {len(questions)}",
        f"**Source Files:** {len(csv_files)}",
        "",
        "This report shows each question with all its metric scores, making it easy to identify which questions perform poorly and why.",
        "",
        "---",
        "",
    ]

    # Group by conversation for better organization
    for conv_id in questions['conversation_group_id'].unique():
        conv_questions = questions[questions['conversation_group_id'] == conv_id]

        report_lines.append(f"## {conv_id}")
        report_lines.append("")

        for _, question_row in conv_questions.iterrows():
            turn_id = question_row['turn_id']
            query = question_row['query']

            report_lines.append(f"### {turn_id}")
            report_lines.append("")
            report_lines.append(f"**Query:** {query}")
            report_lines.append("")

            # Get all metrics for this question
            question_metrics = all_data[
                (all_data['conversation_group_id'] == conv_id) &
                (all_data['turn_id'] == turn_id)
            ]

            # Metrics table
            report_lines.append("**Metrics:**")
            report_lines.append("")
            report_lines.append("| Metric | Score | Threshold | Result | Reason |")
            report_lines.append("|--------|-------|-----------|--------|--------|")

            for _, metric_row in question_metrics.iterrows():
                metric_id = metric_row['metric_identifier']
                score = metric_row['score']
                threshold = metric_row.get('threshold', None)
                result = metric_row.get('result', 'N/A')
                reason = truncate_text(metric_row.get('reason', ''), 80)

                score_display = format_score(score, threshold)
                threshold_display = f"{threshold:.2f}" if not pd.isna(threshold) else "N/A"

                report_lines.append(
                    f"| {metric_id} | {score_display} | {threshold_display} | {result} | {reason} |"
                )

            report_lines.append("")

            # Optional: Include expected response
            expected = question_row.get('expected_response', '')
            if expected and not pd.isna(expected):
                report_lines.append(f"**Expected Response:**")
                report_lines.append("```")
                report_lines.append(str(expected).strip())
                report_lines.append("```")
                report_lines.append("")

            # Optional: Include actual response
            if include_responses:
                response = question_row.get('response', '')
                if response and not pd.isna(response):
                    report_lines.append(f"**Actual Response:**")
                    report_lines.append("```")
                    report_lines.append(str(response).strip())
                    report_lines.append("```")
                    report_lines.append("")

            # Optional: Include contexts
            if include_contexts:
                contexts = question_row.get('contexts', '')
                if contexts and not pd.isna(contexts):
                    report_lines.append(f"**Retrieved Contexts:**")
                    report_lines.append("<details>")
                    report_lines.append("<summary>Click to expand contexts</summary>")
                    report_lines.append("")
                    report_lines.append("```")
                    report_lines.append(str(contexts).strip()[:2000])  # Limit context length
                    if len(str(contexts)) > 2000:
                        report_lines.append("...")
                        report_lines.append(f"(truncated - full length: {len(str(contexts))} chars)")
                    report_lines.append("```")
                    report_lines.append("</details>")
                    report_lines.append("")

            # Token usage
            api_input_tokens = question_row.get('api_input_tokens', None)
            api_output_tokens = question_row.get('api_output_tokens', None)
            judge_input_tokens = question_row.get('judge_llm_input_tokens', None)
            judge_output_tokens = question_row.get('judge_llm_output_tokens', None)

            if not pd.isna(api_input_tokens) or not pd.isna(api_output_tokens):
                report_lines.append(f"**Token Usage:**")
                if not pd.isna(api_input_tokens):
                    report_lines.append(f"- API Input: {int(api_input_tokens)}")
                if not pd.isna(api_output_tokens):
                    report_lines.append(f"- API Output: {int(api_output_tokens)}")
                if not pd.isna(judge_input_tokens):
                    report_lines.append(f"- Judge Input: {int(judge_input_tokens)}")
                if not pd.isna(judge_output_tokens):
                    report_lines.append(f"- Judge Output: {int(judge_output_tokens)}")
                report_lines.append("")

            report_lines.append("---")
            report_lines.append("")

        report_lines.append("")

    # Summary statistics
    report_lines.append("## Summary Statistics")
    report_lines.append("")

    # Overall pass rate by metric
    report_lines.append("### Pass Rates by Metric")
    report_lines.append("")
    report_lines.append("| Metric | Pass | Fail | Error | Pass Rate |")
    report_lines.append("|--------|------|------|-------|-----------|")

    for metric in all_data['metric_identifier'].unique():
        metric_data = all_data[all_data['metric_identifier'] == metric]
        pass_count = len(metric_data[metric_data['result'] == 'PASS'])
        fail_count = len(metric_data[metric_data['result'] == 'FAIL'])
        error_count = len(metric_data[metric_data['result'] == 'ERROR'])
        total = len(metric_data)
        pass_rate = (pass_count / total * 100) if total > 0 else 0

        report_lines.append(
            f"| {metric} | {pass_count} | {fail_count} | {error_count} | {pass_rate:.1f}% |"
        )

    report_lines.append("")

    # Questions with most failures
    report_lines.append("### Questions with Most Failures")
    report_lines.append("")

    question_failures = all_data.groupby(['conversation_group_id', 'turn_id', 'query']).apply(
        lambda x: len(x[x['result'] == 'FAIL'])
    ).reset_index(name='fail_count')
    question_failures = question_failures.sort_values('fail_count', ascending=False).head(10)

    report_lines.append("| Conversation | Turn | Query | Failures |")
    report_lines.append("|--------------|------|-------|----------|")

    for _, row in question_failures.iterrows():
        query_short = truncate_text(row['query'], 60)
        report_lines.append(
            f"| {row['conversation_group_id']} | {row['turn_id']} | {query_short} | {row['fail_count']} |"
        )

    report_lines.append("")

    # Write report
    report_text = "\n".join(report_lines)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report_text)

    print(f"✅ Question metrics report generated: {output_file}")
    print(f"   Total questions: {len(questions)}")
    print(f"   Total metrics evaluated: {len(all_data)}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate detailed per-question metrics report"
    )
    parser.add_argument(
        "--input",
        nargs="+",
        type=Path,
        required=True,
        help="Input CSV file(s) with detailed evaluation results",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output markdown file (default: QUESTION_METRICS_REPORT.md in first input dir)",
    )
    parser.add_argument(
        "--include-contexts",
        action="store_true",
        help="Include retrieved contexts in report (makes report much longer)",
    )
    parser.add_argument(
        "--include-responses",
        action="store_true",
        help="Include actual responses in report (makes report longer)",
    )

    args = parser.parse_args()

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        # Use parent directory of first input file
        output_file = args.input[0].parent / "QUESTION_METRICS_REPORT.md"

    # Generate report
    generate_question_report(
        csv_files=args.input,
        output_file=output_file,
        include_contexts=args.include_contexts,
        include_responses=args.include_responses,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Generate comprehensive RAG quality report for okp-mcp developers.

This script analyzes evaluation outputs and creates a data-driven report
explaining retrieval quality issues with actual examples and metrics.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ============================================================================
# DATA LOADING
# ============================================================================

def load_all_detailed_csvs(output_base: Path) -> Optional[pd.DataFrame]:
    """Load all detailed CSV files from the evaluation run."""
    csv_files = list(output_base.glob("*/evaluation_*_detailed.csv"))

    if not csv_files:
        return None

    dfs = []
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            df['test_config'] = csv_file.parent.name
            dfs.append(df)
        except Exception as e:
            print(f"  ⚠ Failed to load {csv_file}: {e}")

    if not dfs:
        return None

    return pd.concat(dfs, ignore_index=True)


def load_correlation_summary(analysis_dir: Path) -> Optional[str]:
    """Load correlation analysis summary report(s)."""
    summary_files = list(analysis_dir.glob("*_summary_report.txt"))
    if not summary_files:
        return None

    summary_files.sort(key=lambda x: x.name)

    combined = []
    combined.append("=" * 80)
    combined.append("COMBINED CORRELATION ANALYSIS")
    combined.append(f"Total test configs analyzed: {len(summary_files)}")
    combined.append("=" * 80)
    combined.append("")

    for i, summary_file in enumerate(summary_files, 1):
        combined.append(f"\n{'=' * 80}")
        combined.append(f"TEST CONFIG {i}/{len(summary_files)}: {summary_file.stem}")
        combined.append("=" * 80)
        combined.append("")
        combined.append(summary_file.read_text())
        combined.append("")

    return "\n".join(combined)


def load_version_distribution(analysis_dir: Path) -> Optional[str]:
    """Load version distribution report."""
    version_files = list(analysis_dir.glob("*version_distribution_report.txt"))
    if version_files:
        version_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return version_files[0].read_text()
    return None


def load_anomalies(analysis_dir: Path) -> Optional[pd.DataFrame]:
    """Load anomalies CSV if available."""
    anomaly_files = list(analysis_dir.glob("*_anomalies.csv"))
    if anomaly_files:
        dfs = []
        for file in anomaly_files:
            try:
                df = pd.read_csv(file)
                dfs.append(df)
            except Exception:
                continue
        if dfs:
            return pd.concat(dfs, ignore_index=True)
    return None


# ============================================================================
# RAG BYPASS ANALYSIS
# ============================================================================

def analyze_rag_bypass(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze performance of questions that bypassed RAG vs used RAG.

    Returns:
        Dictionary with bypass analysis results
    """
    # Identify questions with/without contexts
    questions = {}

    for _, row in df.iterrows():
        qid = f"{row['conversation_group_id']}/{row['turn_id']}"
        test_config = row.get('test_config', 'unknown')

        if qid not in questions:
            # Check if contexts exist (either in contexts or tool_calls field)
            contexts_val = row.get('contexts', '')
            has_contexts = bool(pd.notna(contexts_val) and str(contexts_val).strip())

            tool_calls_val = row.get('tool_calls', '')
            if not has_contexts and pd.notna(tool_calls_val) and str(tool_calls_val).strip():
                # Check tool_calls structure
                try:
                    tool_calls = json.loads(row['tool_calls'])
                    if tool_calls and len(tool_calls) > 0:
                        if 'result' in tool_calls[0][0]:
                            contexts = tool_calls[0][0]['result'].get('contexts', [])
                            has_contexts = len(contexts) > 0
                except:
                    pass

            questions[qid] = {
                'query': row.get('query', ''),
                'test_config': test_config,
                'has_contexts': has_contexts,
                'metrics': {}
            }

        # Collect answer_correctness and response_relevancy
        metric = row['metric_identifier']
        if metric == 'custom:answer_correctness':
            try:
                questions[qid]['metrics']['answer_correctness'] = float(row['score']) if row['score'] else None
            except:
                pass
        elif metric == 'ragas:response_relevancy':
            try:
                questions[qid]['metrics']['response_relevancy'] = float(row['score']) if row['score'] else None
            except:
                pass

    # Separate into WITH vs WITHOUT RAG
    with_rag = []
    without_rag = []
    without_rag_questions = []

    for qid, data in questions.items():
        ac = data['metrics'].get('answer_correctness')
        if ac is not None:
            if data['has_contexts']:
                with_rag.append(ac)
            else:
                without_rag.append(ac)
                without_rag_questions.append({
                    'qid': qid,
                    'query': data['query'],
                    'test_config': data['test_config'],
                    'score': ac
                })

    return {
        'with_rag_count': len(with_rag),
        'with_rag_scores': with_rag,
        'with_rag_mean': sum(with_rag) / len(with_rag) if with_rag else 0,
        'with_rag_perfect': sum(1 for s in with_rag if s == 1.0),
        'without_rag_count': len(without_rag),
        'without_rag_scores': without_rag,
        'without_rag_mean': sum(without_rag) / len(without_rag) if without_rag else 0,
        'without_rag_perfect': sum(1 for s in without_rag if s == 1.0),
        'without_rag_questions': without_rag_questions,
    }


# ============================================================================
# METRIC ANALYSIS
# ============================================================================

def extract_metric_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Extract metric statistics from detailed CSV data."""
    stats = {}

    # Group by metric and calculate stats
    for metric in df['metric_identifier'].unique():
        metric_data = df[df['metric_identifier'] == metric]

        # Get scores (filter out non-numeric)
        scores = []
        for score_val in metric_data['score']:
            try:
                score = float(score_val) if score_val else None
                if score is not None:
                    scores.append(score)
            except:
                pass

        if scores:
            metric_key = metric.replace(':', '_').replace('-', '_')
            stats[f'{metric_key}_mean'] = sum(scores) / len(scores)
            stats[f'{metric_key}_min'] = min(scores)
            stats[f'{metric_key}_max'] = max(scores)
            stats[f'{metric_key}_count'] = len(scores)

            # Count PASS/FAIL
            pass_count = len(metric_data[metric_data['result'] == 'PASS'])
            total_count = len(metric_data[metric_data['result'].isin(['PASS', 'FAIL'])])
            if total_count > 0:
                stats[f'{metric_key}_pass_rate'] = pass_count / total_count

    return stats


def get_worst_questions(df: pd.DataFrame, metric: str, n: int = 5) -> List[Tuple[str, float, str]]:
    """Get N worst-performing questions for a given metric."""
    metric_data = df[df['metric_identifier'] == metric].copy()

    # Convert scores to float
    metric_data['score_float'] = pd.to_numeric(metric_data['score'], errors='coerce')
    metric_data = metric_data.dropna(subset=['score_float'])

    # Sort by score (ascending = worst first)
    worst = metric_data.nsmallest(n, 'score_float')

    results = []
    for _, row in worst.iterrows():
        qid = f"{row['conversation_group_id']}/{row['turn_id']}"
        score = row['score_float']
        query = row.get('query', 'N/A')
        results.append((qid, score, query))

    return results


# ============================================================================
# ISSUE DETECTION (DATA-DRIVEN)
# ============================================================================

def detect_issues(df: pd.DataFrame, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Detect issues based on actual data, not templates."""
    issues = []

    # Issue 1: Low Context Precision
    cp_mean = stats.get('ragas_context_precision_without_reference_mean', 1.0)
    if cp_mean < 0.5:
        worst = get_worst_questions(df, 'ragas:context_precision_without_reference', n=3)
        issues.append({
            'name': 'Over-Retrieval (Low Context Precision)',
            'severity': 'high',
            'mean_score': cp_mean,
            'threshold': 0.7,
            'description': f'Average context precision is {cp_mean:.3f}, meaning only {cp_mean*100:.1f}% of retrieved contexts are useful. You are retrieving {(1-cp_mean)*100:.1f}% noise.',
            'worst_examples': worst,
            'recommendation': f'Based on actual data: {len(worst)} questions have precision below {min(s for _, s, _ in worst):.3f}. Consider limiting result count or improving ranking.'
        })

    # Issue 2: Low Context Relevance
    cr_mean = stats.get('ragas_context_relevance_mean', 1.0)
    if cr_mean < 0.7:
        worst = get_worst_questions(df, 'ragas:context_relevance', n=3)
        issues.append({
            'name': 'Poor Ranking (Low Context Relevance)',
            'severity': 'high',
            'mean_score': cr_mean,
            'threshold': 0.7,
            'description': f'Average context relevance is {cr_mean:.3f}. Relevant documents are not ranking at the top.',
            'worst_examples': worst,
            'recommendation': f'Worst-performing queries show relevance as low as {min(s for _, s, _ in worst):.3f}. Review ranking algorithm and boosting parameters.'
        })

    # Issue 3: Low Faithfulness
    f_mean = stats.get('ragas_faithfulness_mean', 1.0)
    if f_mean < 0.7:
        worst = get_worst_questions(df, 'ragas:faithfulness', n=3)
        issues.append({
            'name': 'Low Faithfulness (LLM Not Using Contexts)',
            'severity': 'medium',
            'mean_score': f_mean,
            'threshold': 0.8,
            'description': f'Average faithfulness is {f_mean:.3f}, meaning LLM responses are only {f_mean*100:.1f}% based on retrieved contexts. LLM is using parametric knowledge instead.',
            'worst_examples': worst,
            'recommendation': f'{len([s for _, s, _ in worst if s < 0.5])} questions have faithfulness below 0.5. Retrieved contexts may not contain the needed information.'
        })

    # Issue 4: Low Answer Correctness
    ac_mean = stats.get('custom_answer_correctness_mean', 1.0)
    if ac_mean < 0.75:
        worst = get_worst_questions(df, 'custom:answer_correctness', n=3)
        issues.append({
            'name': 'Poor Answer Quality',
            'severity': 'critical',
            'mean_score': ac_mean,
            'threshold': 0.75,
            'description': f'Average answer correctness is {ac_mean:.3f}. Only {ac_mean*100:.1f}% of answers are correct.',
            'worst_examples': worst,
            'recommendation': f'{len([s for _, s, _ in worst if s == 0.0])} questions got completely incorrect answers. Review retrieval quality for these specific queries.'
        })

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda x: severity_order.get(x["severity"], 99))

    return issues


# ============================================================================
# REPORT GENERATION
# ============================================================================

def generate_report(
    output_dir: Path,
    df: Optional[pd.DataFrame],
    correlation_analysis_dir: Optional[Path] = None,
    version_analysis_dir: Optional[Path] = None,
    generation_time: Optional[datetime] = None,
    runtime_seconds: Optional[float] = None,
) -> str:
    """Generate comprehensive data-driven RAG quality report."""

    if generation_time is None:
        generation_time = datetime.now()

    timestamp_str = generation_time.strftime("%Y-%m-%d %H:%M:%S")

    # Load analysis results
    correlation_summary = None
    version_summary = None
    anomalies_df = None

    if correlation_analysis_dir and correlation_analysis_dir.exists():
        correlation_summary = load_correlation_summary(correlation_analysis_dir)
        anomalies_df = load_anomalies(correlation_analysis_dir)

    if version_analysis_dir and version_analysis_dir.exists():
        version_summary = load_version_distribution(version_analysis_dir)

    # Build report header
    report = f"""# RAG Retrieval Quality Report for okp-mcp Developers

**Generated:** {timestamp_str}
**Evaluation Run:** {output_dir.name}
"""

    if runtime_seconds is not None:
        minutes = int(runtime_seconds // 60)
        seconds = int(runtime_seconds % 60)
        report += f"**Evaluation Runtime:** {minutes}m {seconds}s\n"

    report += """
---

## Executive Summary

This report analyzes the retrieval quality of the okp-mcp server from the perspective of RAG (Retrieval-Augmented Generation) metrics. The metrics measure how well the retrieved contexts support correct LLM responses.

### What These Metrics Mean for okp-mcp

| Metric | What It Measures | okp-mcp Impact |
|--------|------------------|----------------|
| **context_precision** | % of retrieved contexts that are actually useful | **Over-retrieval:** Too many irrelevant docs sent to LLM |
| **context_relevance** | How well contexts match the query topic | **Ranking quality:** Are best docs at the top? |
| **faithfulness** | Does LLM use the retrieved contexts? | **Usability:** Can LLM extract info from your docs? |
| **answer_correctness** | Is the final answer correct? | **End result:** Does retrieval enable correct answers? |

---

"""

    # RAG Bypass Analysis
    if df is not None:
        report += "## RAG Bypass Performance Analysis\n\n"
        bypass_analysis = analyze_rag_bypass(df)

        if bypass_analysis['without_rag_count'] > 0 or bypass_analysis['with_rag_count'] > 0:
            report += "### Questions That Bypassed RAG (No Retrieval)\n\n"

            if bypass_analysis['without_rag_count'] > 0:
                report += f"- **Count:** {bypass_analysis['without_rag_count']} questions\n"
                report += f"- **Avg Answer Correctness:** {bypass_analysis['without_rag_mean']:.3f} ({bypass_analysis['without_rag_mean']*100:.1f}%)\n"
                report += f"- **Perfect Scores (1.0):** {bypass_analysis['without_rag_perfect']}/{bypass_analysis['without_rag_count']}\n\n"

                # List bypassed questions
                report += "**Questions that bypassed retrieval:**\n\n"
                for q in bypass_analysis['without_rag_questions'][:10]:  # Show up to 10
                    report += f"- `{q['qid']}` (score: {q['score']:.2f}): {q['query']}\n"
                report += "\n"
            else:
                report += "- **No questions bypassed RAG** - All questions used retrieval\n\n"

            report += "### Questions That Used RAG (With Retrieval)\n\n"

            if bypass_analysis['with_rag_count'] > 0:
                report += f"- **Count:** {bypass_analysis['with_rag_count']} questions\n"
                report += f"- **Avg Answer Correctness:** {bypass_analysis['with_rag_mean']:.3f} ({bypass_analysis['with_rag_mean']*100:.1f}%)\n"
                report += f"- **Perfect Scores (1.0):** {bypass_analysis['with_rag_perfect']}/{bypass_analysis['with_rag_count']}\n\n"

            # Interpretation
            if bypass_analysis['without_rag_count'] > 0 and bypass_analysis['with_rag_count'] > 0:
                diff = bypass_analysis['without_rag_mean'] - bypass_analysis['with_rag_mean']
                report += "### Interpretation\n\n"

                if diff > 0.1:
                    report += f"**LLM performs {diff*100:.1f}% BETTER when bypassing RAG.** This suggests:\n\n"
                    report += "- LLM has strong parametric knowledge for these questions\n"
                    report += "- Retrieved contexts may be adding noise rather than signal\n"
                    report += "- This is **SMART adaptive behavior** - LLM skips retrieval when it would hurt performance\n\n"
                    report += "**Recommendation:** Don't force mandatory tool use. Instead, fix retrieval quality so LLM chooses to use it.\n\n"
                elif diff < -0.1:
                    report += f"**LLM performs {abs(diff)*100:.1f}% WORSE when bypassing RAG.** This suggests:\n\n"
                    report += "- RAG is providing valuable information\n"
                    report += "- LLM should be using retrieval more often\n"
                    report += "- Consider prompting to encourage tool use for these question types\n\n"
                else:
                    report += "**RAG bypass has minimal impact on performance** (< 10% difference).\n\n"

        report += "---\n\n"

    # Metric Performance Analysis
    report += "## Metric Performance Analysis\n\n"

    if correlation_summary:
        report += "```\n"
        report += correlation_summary
        report += "\n```\n\n"
    else:
        report += "⚠️ **Correlation analysis not available** - Cannot generate detailed insights without metric data.\n\n"

    # Version Distribution
    if version_summary:
        report += "### RHEL Version Filtering Analysis\n\n"
        report += "```\n"
        report += version_summary
        report += "\n```\n\n"

    report += "---\n\n"

    # Data-Driven Issue Detection
    report += "## Issues Detected (Based on Actual Data)\n\n"

    if df is not None:
        stats = extract_metric_stats(df)
        issues = detect_issues(df, stats)

        if issues:
            for i, issue in enumerate(issues, 1):
                severity_emoji = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢"
                }

                report += f"### {i}. {issue['name']} {severity_emoji.get(issue['severity'], '')}\n\n"
                report += f"**Severity:** {issue['severity'].upper()}\n\n"
                report += f"**Current Score:** {issue['mean_score']:.3f} (target: {issue['threshold']:.2f})\n\n"
                report += f"**Description:** {issue['description']}\n\n"

                if issue.get('worst_examples'):
                    report += "**Worst-Performing Questions:**\n\n"
                    for qid, score, query in issue['worst_examples']:
                        # Truncate query
                        query_short = query[:80] + "..." if len(query) > 80 else query
                        report += f"- `{qid}` (score: {score:.3f}): {query_short}\n"
                    report += "\n"

                report += f"**Recommendation:** {issue['recommendation']}\n\n"
                report += "---\n\n"
        else:
            report += "✅ **No major issues detected!**\n\n"
            report += "All metrics are within acceptable ranges.\n\n"
    else:
        report += "⚠️ **Cannot analyze issues** - No detailed CSV data available.\n\n"

    # Anomaly Examples
    if anomalies_df is not None and not anomalies_df.empty:
        report += "## Specific Anomalous Cases\n\n"
        report += "These cases show specific retrieval problems:\n\n"

        top_anomalies = anomalies_df.head(10)
        report += "| Conversation | Anomaly Type | Description |\n"
        report += "|--------------|--------------|-------------|\n"

        for _, row in top_anomalies.iterrows():
            conv_id = row.get("conversation_group_id", "N/A")
            anomaly_type = row.get("anomaly_type", "N/A")
            desc = str(row.get("description", ""))[:60] + "..." if len(str(row.get("description", ""))) > 60 else str(row.get("description", ""))
            report += f"| {conv_id} | {anomaly_type} | {desc} |\n"

        report += f"\n**Total anomalies detected:** {len(anomalies_df)}\n\n"
        report += "---\n\n"

    # Next Steps
    report += """## Next Steps

1. **Review worst-performing questions** (listed above with actual scores)
2. **Compare baseline vs current run** to track improvements
3. **Run MCP direct mode** to iterate quickly on retrieval changes:
   ```bash
   ./run_mcp_retrieval_suite.sh --runs 5
   ```
4. **Re-run full evaluation** after fixes to measure impact

---

## Analysis Files Location

"""

    if correlation_analysis_dir:
        report += f"- Correlation analysis: `{correlation_analysis_dir.relative_to(Path.cwd())}/`\n"
    if version_analysis_dir:
        report += f"- Version analysis: `{version_analysis_dir.relative_to(Path.cwd())}/`\n"

    report += "\n---\n\n"
    report += "*Generated by LightSpeed Evaluation Framework*\n"

    return report


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate data-driven okp-mcp RAG quality report"
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        required=True,
        help="Base output directory from evaluation run",
    )
    parser.add_argument(
        "--correlation-analysis",
        type=Path,
        help="Path to correlation analysis directory",
    )
    parser.add_argument(
        "--version-analysis",
        type=Path,
        help="Path to version distribution analysis directory",
    )
    parser.add_argument(
        "--runtime-seconds",
        type=float,
        help="Total runtime of evaluation in seconds",
    )

    args = parser.parse_args()

    output_file = args.output_base / "RAG_QUALITY_REPORT_FOR_OKP_MCP.md"

    print(f"Generating data-driven RAG quality report...")
    print(f"  Output base: {args.output_base}")

    # Load detailed CSVs for data-driven analysis
    print(f"  Loading detailed CSV files...")
    df = load_all_detailed_csvs(args.output_base)
    if df is not None:
        print(f"    ✓ Loaded {len(df)} rows from CSV files")
    else:
        print(f"    ⚠ No CSV files found - report will have limited insights")

    # Check correlation analysis
    if args.correlation_analysis:
        print(f"  Correlation analysis dir: {args.correlation_analysis}")
        if args.correlation_analysis.exists():
            summary_files = list(args.correlation_analysis.glob("*_summary_report.txt"))
            if summary_files:
                print(f"    ✓ Found {len(summary_files)} summary report(s)")
            else:
                print(f"    ⚠ No summary reports found")
        else:
            print(f"    ✗ Directory does not exist")

    # Check version analysis
    if args.version_analysis:
        print(f"  Version analysis dir: {args.version_analysis}")
        if args.version_analysis.exists():
            version_files = list(args.version_analysis.glob("*version_distribution_report.txt"))
            if version_files:
                print(f"    ✓ Found version report")
            else:
                print(f"    ⚠ No version report found")
        else:
            print(f"    ✗ Directory does not exist")

    print()

    generation_time = datetime.now()

    report = generate_report(
        output_dir=args.output_base,
        df=df,
        correlation_analysis_dir=args.correlation_analysis,
        version_analysis_dir=args.version_analysis,
        generation_time=generation_time,
        runtime_seconds=args.runtime_seconds,
    )

    # Write report
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report)

    print(f"✓ Report generated: {output_file}")
    print(f"\nView the report:")
    print(f"  cat {output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Generate comprehensive RAG quality report for okp-mcp developers.

This script analyzes evaluation outputs and creates a focused report
explaining retrieval quality issues in terms that make sense for
okp-mcp developers working on the Solr-based retrieval system.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ============================================================================
# ISSUE DETECTION PATTERNS
# ============================================================================

ISSUE_PATTERNS = {
    "over_retrieval": {
        "name": "Over-Retrieval",
        "severity": "high",
        "metric_check": lambda m: m.get("context_precision_mean", 1.0) < 0.5,
        "threshold": 0.5,
        "metric": "context_precision",
        "symptom": "context_precision scores consistently below 0.5",
        "root_cause": "okp-mcp returns too many contexts (often 100-250+ instead of 10-20)",
        "why_matters": [
            "LLM must wade through noise to find signal",
            "Increases token costs",
            "Slows response time",
            "Buries relevant docs among irrelevant ones"
        ],
        "fix_title": "Limit Result Count",
        "fix_code": """# In okp-mcp Solr query
solr_params = {
    'rows': 10,  # Limit to top 10 results (currently unlimited or very high)
    'q': query,
}""",
        "expected_improvement": "context_precision +30-50%"
    },

    "poor_ranking": {
        "name": "Poor Ranking",
        "severity": "high",
        "metric_check": lambda m: m.get("context_relevance_mean", 1.0) < 0.7,
        "threshold": 0.7,
        "metric": "context_relevance",
        "symptom": "context_relevance below 0.7, relevant docs not in top positions",
        "root_cause": "Boilerplate (legal notices, warnings) ranks higher than actual documentation",
        "why_matters": [
            "LLM sees boilerplate first",
            "Wastes token budget on non-content",
            "Reduces context window for actual docs"
        ],
        "fix_title": "Boost Content Over Metadata",
        "fix_code": """# Boost content over metadata
solr_params = {
    'qf': 'content^5.0 title^2.0 metadata^1.0',  # Weight content 5x higher
    'defType': 'edismax',
}""",
        "expected_improvement": "context_relevance +20-30%"
    },

    "low_faithfulness": {
        "name": "Low Faithfulness",
        "severity": "medium",
        "metric_check": lambda m: m.get("faithfulness_mean", 1.0) < 0.7,
        "threshold": 0.7,
        "metric": "faithfulness",
        "symptom": "faithfulness scores below 0.7",
        "root_cause": "LLM cannot extract useful information from retrieved contexts, or contexts don't contain needed information",
        "why_matters": [
            "LLM forced to use parametric knowledge instead of RAG",
            "Defeats purpose of retrieval system",
            "May produce outdated or incorrect answers"
        ],
        "fix_title": "Improve Context Quality",
        "fix_code": """# Filter out low-quality contexts
def is_useful_context(doc):
    # Minimum content length
    if len(doc.get('content', '')) < 100:
        return False

    # Filter out boilerplate
    if doc.get('type') in ['legal_notice', 'warning', 'metadata']:
        return False

    return True

contexts = [doc for doc in solr_results if is_useful_context(doc)]""",
        "expected_improvement": "faithfulness +15-25%"
    },

    "version_filtering": {
        "name": "Missing Version Filtering",
        "severity": "high",
        "metric_check": lambda m: m.get("version_accuracy", 1.0) < 0.8,
        "threshold": 0.8,
        "metric": "version_accuracy",
        "symptom": "RHEL 10 queries return RHEL 9 or RHEL 8 documentation",
        "root_cause": "Version not boosted in retrieval query",
        "why_matters": [
            "Outdated commands (e.g., ISC DHCP for RHEL 10)",
            "Wrong package names",
            "Deprecated syntax",
            "User gets incorrect instructions"
        ],
        "fix_title": "Add Version Boost",
        "fix_code": """# Extract and boost target version
import re

def extract_rhel_version(query):
    patterns = [r'RHEL\\s*(\\d+)', r'Red Hat Enterprise Linux\\s*(\\d+)']
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)
    return None  # Default to latest if not specified

target_version = extract_rhel_version(query)
if target_version:
    solr_params['bq'] = f'version:{target_version}^10.0'  # Boost 10x""",
        "expected_improvement": "version_accuracy 50% → 80%+"
    },

    "boilerplate_pollution": {
        "name": "Boilerplate Pollution",
        "severity": "medium",
        "metric_check": lambda m: (
            m.get("context_precision_mean", 1.0) < 0.4 and
            m.get("context_relevance_mean", 1.0) < 0.6
        ),
        "threshold": 0.4,
        "metric": "context_precision + context_relevance",
        "symptom": "High % of contexts are legal notices, deprecation warnings, title fragments",
        "root_cause": "No content filtering before sending to LLM",
        "why_matters": [
            "Wastes 50-90% of context window",
            "Dilutes signal-to-noise ratio",
            "Increases context_precision penalty"
        ],
        "fix_title": "Filter Boilerplate",
        "fix_code": """# Filter out boilerplate before returning contexts
def is_useful_context(doc):
    content = doc.get('content', '')
    doc_type = doc.get('type', '')
    title = doc.get('title', '')

    # Too short - likely metadata fragment
    if len(content) < 100:
        return False

    # Known boilerplate types
    if doc_type in ['legal_notice', 'warning', 'metadata', 'copyright']:
        return False

    # Generic deprecation warnings (unless version-specific)
    if 'deprecated' in title.lower():
        if not any(f'RHEL {v}' in content for v in ['8', '9', '10']):
            return False

    return True

filtered_contexts = [doc for doc in solr_results if is_useful_context(doc)]""",
        "expected_improvement": "context_precision +25-40%"
    },

    "poor_answer_quality": {
        "name": "Poor Answer Quality",
        "severity": "critical",
        "metric_check": lambda m: m.get("answer_correctness_mean", 1.0) < 0.75,
        "threshold": 0.75,
        "metric": "answer_correctness",
        "symptom": "answer_correctness below 0.75, despite good retrieval metrics",
        "root_cause": "Retrieved contexts contain correct information, but LLM produces incorrect answers",
        "why_matters": [
            "End users get wrong instructions",
            "Defeats entire purpose of the system",
            "May damage user trust and adoption"
        ],
        "fix_title": "Improve Context Presentation",
        "fix_code": """# Improve context presentation to LLM
def format_context_for_llm(contexts):
    formatted = []
    for i, ctx in enumerate(contexts, 1):
        # Add metadata to help LLM understand context
        context_block = f'''
--- Context {i} ---
Source: {ctx.get('source', 'Unknown')}
Version: {ctx.get('version', 'Unknown')}
Type: {ctx.get('doc_type', 'Documentation')}

{ctx['content']}
---
'''
        formatted.append(context_block)
    return '\\n'.join(formatted)""",
        "expected_improvement": "answer_correctness +10-20%"
    }
}


# ============================================================================
# METRIC EXTRACTION
# ============================================================================

def extract_metric_stats(summary_text: str) -> Dict[str, float]:
    """Extract and aggregate metric statistics from correlation summary report(s).

    Handles both single reports and combined reports from multiple test configs.
    Computes overall averages across all configs.
    """
    stats = {}

    if not summary_text:
        return stats

    # Track all values for each metric to compute averages
    metric_values = {}

    # Parse metric statistics section
    lines = summary_text.split('\n')
    current_metric = None

    for line in lines:
        # Detect metric name
        if line.strip() and not line.startswith(' ') and ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                metric_name = parts[0].strip()
                if any(m in metric_name for m in ['context_precision', 'context_relevance',
                                                    'faithfulness', 'answer_correctness']):
                    current_metric = metric_name

        # Extract mean value
        if current_metric and 'Mean:' in line:
            match = re.search(r'Mean:\s*([\d.]+)', line)
            if match:
                mean_val = float(match.group(1))
                metric_key = f"{current_metric}_mean"

                # Collect all values
                if metric_key not in metric_values:
                    metric_values[metric_key] = []
                metric_values[metric_key].append(mean_val)

        # Extract pass rate
        if current_metric and ('Pass Rate' in line or 'PASS' in line):
            match = re.search(r'([\d.]+)%', line)
            if match:
                pass_rate = float(match.group(1)) / 100.0
                metric_key = f"{current_metric}_pass_rate"

                if metric_key not in metric_values:
                    metric_values[metric_key] = []
                metric_values[metric_key].append(pass_rate)

    # Compute overall averages
    for metric_key, values in metric_values.items():
        if values:
            stats[metric_key] = sum(values) / len(values)

    return stats


def extract_version_accuracy(version_text: str) -> Optional[float]:
    """Extract version accuracy from version distribution report."""
    if not version_text:
        return None

    # Look for average version accuracy
    match = re.search(r'Average version accuracy:\s*([\d.]+)%', version_text)
    if match:
        return float(match.group(1)) / 100.0

    return None


# ============================================================================
# ISSUE DETECTION
# ============================================================================

def detect_issues(
    correlation_summary: Optional[str],
    version_summary: Optional[str]
) -> List[Tuple[str, Dict[str, Any]]]:
    """Detect which issues apply based on metric values.

    Returns:
        List of (issue_key, issue_config) tuples, sorted by severity
    """
    # Extract metrics
    metrics = extract_metric_stats(correlation_summary or "")

    # Add version accuracy if available
    version_acc = extract_version_accuracy(version_summary or "")
    if version_acc is not None:
        metrics["version_accuracy"] = version_acc

    # Detect which issues apply
    detected = []
    for issue_key, issue_config in ISSUE_PATTERNS.items():
        if issue_config["metric_check"](metrics):
            detected.append((issue_key, issue_config))

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    detected.sort(key=lambda x: severity_order.get(x[1]["severity"], 99))

    return detected


# ============================================================================
# FILE LOADING
# ============================================================================

def load_correlation_summary(analysis_dir: Path) -> Optional[str]:
    """Load correlation analysis summary report(s).

    Combines multiple summary reports if they exist (one per test config).
    """
    # Try exact name first
    summary_file = analysis_dir / "summary_report.txt"
    if summary_file.exists():
        return summary_file.read_text()

    # Try pattern match for files like "evaluation_TIMESTAMP_detailed_summary_report.txt"
    summary_files = list(analysis_dir.glob("*_summary_report.txt"))
    if summary_files:
        # Sort by timestamp for consistent ordering
        summary_files.sort(key=lambda x: x.name)

        # Combine all summary reports
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

    return None


def load_version_distribution(analysis_dir: Path) -> Optional[str]:
    """Load version distribution report."""
    # Try exact name first
    version_report = analysis_dir / "version_distribution_report.txt"
    if version_report.exists():
        return version_report.read_text()

    # Try pattern match
    version_files = list(analysis_dir.glob("*version_distribution_report.txt"))
    if version_files:
        version_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return version_files[0].read_text()

    return None


def load_anomalies(analysis_dir: Path) -> Optional[pd.DataFrame]:
    """Load anomalies CSV if available."""
    # Try exact name first
    anomalies_file = analysis_dir / "anomalies.csv"
    if anomalies_file.exists():
        return pd.read_csv(anomalies_file)

    # Try pattern match for files like "evaluation_TIMESTAMP_detailed_anomalies.csv"
    anomaly_files = list(analysis_dir.glob("*_anomalies.csv"))
    if anomaly_files:
        # Combine all anomaly files if multiple exist
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
# REPORT GENERATION
# ============================================================================

def generate_report(
    output_dir: Path,
    correlation_analysis_dir: Optional[Path] = None,
    version_analysis_dir: Optional[Path] = None,
    timestamp: Optional[str] = None,
) -> str:
    """Generate comprehensive RAG quality report."""

    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Load analysis results
    correlation_summary = None
    version_summary = None
    anomalies_df = None
    correlation_dir_status = None
    version_dir_status = None

    if correlation_analysis_dir:
        if correlation_analysis_dir.exists():
            correlation_summary = load_correlation_summary(correlation_analysis_dir)
            anomalies_df = load_anomalies(correlation_analysis_dir)
            if not correlation_summary:
                correlation_dir_status = f"Directory exists but summary_report.txt not found in {correlation_analysis_dir}"
        else:
            correlation_dir_status = f"Directory not found: {correlation_analysis_dir}"
    else:
        correlation_dir_status = "No correlation analysis directory specified"

    if version_analysis_dir:
        if version_analysis_dir.exists():
            version_summary = load_version_distribution(version_analysis_dir)
            if not version_summary:
                version_dir_status = f"Directory exists but version_distribution_report.txt not found in {version_analysis_dir}"
        else:
            version_dir_status = f"Directory not found: {version_analysis_dir}"
    else:
        version_dir_status = "No version analysis directory specified"

    # Detect issues
    detected_issues = detect_issues(correlation_summary, version_summary)

    # Build report
    report = f"""# RAG Retrieval Quality Report for okp-mcp Developers

**Generated:** {timestamp}
**Evaluation Run:** {output_dir.name}

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

## Critical Issues Found

"""

    # Add correlation analysis section
    if correlation_summary:
        report += "### Metric Performance Analysis\n\n"
        report += "```\n"
        report += correlation_summary
        report += "\n```\n\n"
    else:
        report += "⚠️ **Correlation analysis not available**\n\n"
        if correlation_dir_status:
            report += f"**Reason:** {correlation_dir_status}\n\n"
        report += "**To fix:**\n"
        report += "1. Ensure evaluation ran successfully (check for CSV files)\n"
        report += "2. Verify correlation analysis step completed (look for summary_report.txt)\n"
        report += "3. Re-run: `python scripts/analyze_metric_correlations.py --input eval_output/*/evaluation_*_detailed.csv --output analysis_output/correlation/`\n\n"

    # Add version distribution section
    if version_summary:
        report += "### RHEL Version Filtering Analysis\n\n"
        report += "```\n"
        report += version_summary
        report += "\n```\n\n"
    else:
        report += "⚠️ **Version distribution analysis not available**\n\n"
        if version_dir_status:
            report += f"**Reason:** {version_dir_status}\n\n"
        report += "**Note:** Version analysis only runs for temporal validity tests. If you didn't run temporal tests, this is expected.\n\n"
        report += "**To fix (if needed):**\n"
        report += "1. Run temporal tests: `lightspeed-eval --eval-data config/temporal_validity_tests_runnable.yaml`\n"
        report += "2. Run version analysis: `python scripts/analyze_version_distribution.py --input <csv> --test-config config/temporal_validity_tests_runnable.yaml`\n\n"

    # Add root cause analysis - DYNAMIC based on detected issues
    report += "---\n\n"
    report += "## Root Cause Analysis\n\n"

    if detected_issues:
        report += f"**{len(detected_issues)} issue(s) detected** based on metric analysis:\n\n"

        for i, (issue_key, issue) in enumerate(detected_issues, 1):
            severity_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢"
            }

            report += f"### {i}. {issue['name']} {severity_emoji.get(issue['severity'], '')}\n\n"
            report += f"**Severity:** {issue['severity'].upper()}\n\n"
            report += f"**Symptom:** {issue['symptom']}\n\n"
            report += f"**Root Cause:** {issue['root_cause']}\n\n"
            report += "**Why This Matters:**\n"
            for matter in issue['why_matters']:
                report += f"- {matter}\n"
            report += "\n"

            report += f"**Fix - {issue['fix_title']}:**\n"
            report += "```python\n"
            report += issue['fix_code']
            report += "\n```\n\n"

            report += f"**Expected Improvement:** {issue['expected_improvement']}\n\n"
            report += "---\n\n"
    else:
        report += "✅ **No major issues detected!**\n\n"
        report += "Metrics are within acceptable ranges. Continue monitoring for any degradation.\n\n"
        report += "**Recommendations:**\n"
        report += "- Maintain current retrieval configuration\n"
        report += "- Monitor metrics over time for any regression\n"
        report += "- Consider A/B testing optimizations for marginal improvements\n\n"

    # Add anomaly examples if available
    if anomalies_df is not None and not anomalies_df.empty:
        report += "## Specific Examples\n\n"
        report += "### Anomalous Cases Detected\n\n"
        report += "These cases show specific retrieval problems:\n\n"

        # Show top 10 anomalies
        top_anomalies = anomalies_df.head(10)
        report += "| Conversation | Anomaly Type | Description |\n"
        report += "|--------------|--------------|-------------|\n"

        for _, row in top_anomalies.iterrows():
            conv_id = row.get("conversation_group_id", "N/A")
            anomaly_type = row.get("anomaly_type", "N/A")
            # Truncate description
            desc = str(row.get("description", ""))[:60] + "..." if len(str(row.get("description", ""))) > 60 else str(row.get("description", ""))
            report += f"| {conv_id} | {anomaly_type} | {desc} |\n"

        report += "\n"
        report += f"**Total anomalies detected:** {len(anomalies_df)}\n\n"
        report += "See full list in `anomalies.csv`\n\n"

    # Add recommended action plan - DYNAMIC based on detected issues
    report += "---\n\n"
    report += "## Recommended Action Plan\n\n"

    if detected_issues:
        # Separate by severity
        critical = [i for i in detected_issues if i[1]["severity"] == "critical"]
        high = [i for i in detected_issues if i[1]["severity"] == "high"]
        medium = [i for i in detected_issues if i[1]["severity"] == "medium"]

        if critical:
            report += "### 🔴 Critical (Fix Immediately)\n\n"
            for issue_key, issue in critical:
                report += f"1. **{issue['name']}**\n"
                report += f"   - Implement: {issue['fix_title']}\n"
                report += f"   - Expected: {issue['expected_improvement']}\n\n"

        if high:
            report += "### 🟠 High Priority (This Week)\n\n"
            for issue_key, issue in high:
                report += f"1. **{issue['name']}**\n"
                report += f"   - Implement: {issue['fix_title']}\n"
                report += f"   - Expected: {issue['expected_improvement']}\n\n"

        if medium:
            report += "### 🟡 Medium Priority (Next 2-4 Weeks)\n\n"
            for issue_key, issue in medium:
                report += f"1. **{issue['name']}**\n"
                report += f"   - Implement: {issue['fix_title']}\n"
                report += f"   - Expected: {issue['expected_improvement']}\n\n"
    else:
        report += "✅ **System is performing well**\n\n"
        report += "Continue with normal operations and monitoring.\n\n"

    # Add validation section
    report += "---\n\n"
    report += "## Validation\n\n"
    report += "Run this evaluation suite again after fixes:\n\n"
    report += "```bash\n"
    report += "./run_full_evaluation_suite.sh\n"
    report += "```\n\n"
    report += "Compare reports to measure improvement.\n\n"

    # Add appendix
    report += """---

## Appendix: Understanding the Metrics

### context_precision_without_reference

**Formula:** (Useful contexts) / (Total contexts retrieved)

**Example:**
- Query: "Install DHCP in RHEL 10"
- Retrieved 200 contexts
- Only 8 mention Kea DHCP (correct for RHEL 10)
- Score: 8/200 = 0.04 (4%)

**okp-mcp Takeaway:** You're retrieving 192 irrelevant contexts (96% noise)

### context_relevance

**Formula:** LLM judges how well contexts match query intent

**Example:**
- Query: "Install DHCP in RHEL 10"
- Top 3 contexts:
  1. "Legal notice" (not relevant)
  2. "RHEL 9 deprecated features" (wrong version)
  3. "Kea DHCP installation" (relevant!)
- Score: 0.33 (1 out of 3 relevant)

**okp-mcp Takeaway:** Relevant doc is at position 3, should be position 1

### faithfulness

**Formula:** LLM checks if response claims are supported by contexts

**Example:**
- Contexts say: "RHEL 10 uses Kea"
- Response says: "RHEL 10 uses Kea for DHCP"
- Score: 1.0 (faithful)

But:
- Contexts say: "RHEL 9 uses ISC DHCP"
- Response says: "RHEL 10 uses Kea for DHCP"
- Score: 0.0 (not faithful - info not in contexts)

**okp-mcp Takeaway:** If faithfulness is low, contexts don't contain needed info

### answer_correctness

**Formula:** LLM compares response to expected correct answer

**Example:**
- Expected: "Use Kea package for DHCP in RHEL 10"
- Response: "Use Kea package for DHCP in RHEL 10"
- Score: 1.0 (correct)

**okp-mcp Takeaway:** High score despite low precision means LLM found signal in noise (lucky!) or used parametric knowledge (bypassed RAG)

---

## Key Takeaways for okp-mcp Team

"""

    if detected_issues:
        report += f"1. **{len(detected_issues)} issues detected** - See Root Cause Analysis section\n"
        critical_high = [i for i in detected_issues if i[1]["severity"] in ["critical", "high"]]
        if critical_high:
            report += f"2. **{len(critical_high)} critical/high priority issues** - Immediate attention needed\n"
        report += "3. **Fixes are straightforward** - Most are simple Solr parameter changes\n"
        report += "4. **Quick wins available** - Some fixes can improve metrics 30-50%\n"
    else:
        report += "1. **System is healthy** - No major issues detected\n"
        report += "2. **Continue monitoring** - Metrics are within acceptable ranges\n"
        report += "3. **Consider optimizations** - Room for marginal improvements\n"

    report += "\n**These are NOT test framework bugs** - they are accurate measurements of current retrieval quality.\n\n"
    report += "---\n\n"
    report += "**Questions?** Contact evaluation team or see full analysis in the output directory.\n\n"
    report += "**Analysis Location:**\n"
    report += f"- Correlation analysis: `{correlation_analysis_dir.name if correlation_analysis_dir else 'N/A'}/`\n"
    report += f"- Version analysis: `{version_analysis_dir.name if version_analysis_dir else 'N/A'}/`\n\n"
    report += "---\n\n"
    report += "*Generated by LightSpeed Evaluation Framework*\n"

    return report


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate okp-mcp RAG quality report from evaluation outputs"
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
        "--output-file",
        type=Path,
        help="Output report file path (default: <output-base>/RAG_QUALITY_REPORT.md)",
    )

    args = parser.parse_args()

    # Determine output file
    if args.output_file:
        output_file = args.output_file
    else:
        output_file = args.output_base / "RAG_QUALITY_REPORT_FOR_OKP_MCP.md"

    # Generate report
    print(f"Generating RAG quality report...")
    print(f"  Output base: {args.output_base}")

    # Check correlation analysis
    if args.correlation_analysis:
        print(f"  Correlation analysis dir: {args.correlation_analysis}")
        if args.correlation_analysis.exists():
            # Check for exact name
            summary_file = args.correlation_analysis / "summary_report.txt"
            if summary_file.exists():
                print(f"    ✓ Found summary_report.txt")
            else:
                # Check for pattern match
                summary_files = list(args.correlation_analysis.glob("*_summary_report.txt"))
                if summary_files:
                    print(f"    ✓ Found {len(summary_files)} summary report file(s)")
                    if len(summary_files) > 1:
                        print(f"      (will combine all {len(summary_files)} test configs)")
                else:
                    print(f"    ⚠ No summary report files found - correlation data will be missing from report")
        else:
            print(f"    ✗ Directory does not exist")
    else:
        print(f"  Correlation analysis: Not specified")

    # Check version analysis
    if args.version_analysis:
        print(f"  Version analysis dir: {args.version_analysis}")
        if args.version_analysis.exists():
            # Check for exact name
            version_file = args.version_analysis / "version_distribution_report.txt"
            if version_file.exists():
                print(f"    ✓ Found version_distribution_report.txt")
            else:
                # Check for pattern match
                version_files = list(args.version_analysis.glob("*version_distribution_report.txt"))
                if version_files:
                    print(f"    ✓ Found version report: {version_files[0].name}")
                else:
                    print(f"    ⚠ No version distribution report found - version data will be missing from report")
        else:
            print(f"    ✗ Directory does not exist")
    else:
        print(f"  Version analysis: Not specified")

    print()

    report = generate_report(
        output_dir=args.output_base,
        correlation_analysis_dir=args.correlation_analysis,
        version_analysis_dir=args.version_analysis,
    )

    # Write report
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(report)

    print(f"\n✓ Report generated: {output_file}")
    print(f"\nView the report:")
    print(f"  cat {output_file}")
    print(f"  # or")
    print(f"  less {output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

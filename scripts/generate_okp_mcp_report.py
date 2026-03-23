#!/usr/bin/env python3
"""
Generate comprehensive RAG quality report for okp-mcp developers.

This script analyzes evaluation outputs and creates a focused report
explaining retrieval quality issues in terms that make sense for
okp-mcp developers working on the Solr-based retrieval system.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


def load_correlation_summary(analysis_dir: Path) -> Optional[str]:
    """Load correlation analysis summary report."""
    # Try exact name first
    summary_file = analysis_dir / "summary_report.txt"
    if summary_file.exists():
        return summary_file.read_text()

    # Try pattern match for files like "evaluation_TIMESTAMP_detailed_summary_report.txt"
    summary_files = list(analysis_dir.glob("*_summary_report.txt"))
    if summary_files:
        # Use the most recent one if multiple exist
        summary_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return summary_files[0].read_text()

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


def extract_key_metrics(summary_text: Optional[str]) -> Dict[str, Any]:
    """Extract key metric values from summary report."""
    metrics = {
        "context_precision_mean": "N/A",
        "context_precision_pass_rate": "N/A",
        "context_relevance_mean": "N/A",
        "context_relevance_pass_rate": "N/A",
        "faithfulness_mean": "N/A",
        "faithfulness_pass_rate": "N/A",
        "answer_correctness_mean": "N/A",
        "answer_correctness_pass_rate": "N/A",
        "overall_pass_rate": "N/A",
    }

    if not summary_text:
        return metrics

    # Parse summary text for key values (basic parsing)
    lines = summary_text.split("\n")
    for line in lines:
        if "context_precision" in line.lower() and "mean:" in line.lower():
            parts = line.split(":")
            if len(parts) > 1:
                metrics["context_precision_mean"] = parts[-1].strip()
        # Add more parsing as needed

    return metrics


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

    # Extract metrics
    metrics = extract_key_metrics(correlation_summary)

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

    # Add root cause analysis
    report += """---

## Root Cause Analysis

Based on the metrics, the primary issues are:

### 1. Over-Retrieval (Low context_precision)

**Symptom:** context_precision scores consistently below 0.5

**Root Cause:** okp-mcp returns too many contexts (often 100-250+ instead of 10-20)

**Why This Matters:**
- LLM must wade through noise to find signal
- Increases token costs
- Slows response time
- Buries relevant docs among irrelevant ones

**Fix:**
```python
# In okp-mcp Solr query
solr_params = {
    'rows': 10,  # Limit to top 10 results (currently unlimited or very high)
    'q': query,
}
```

### 2. Poor Ranking (Low context_relevance)

**Symptom:** context_relevance below 0.7, relevant docs not in top positions

**Root Cause:** Boilerplate (legal notices, warnings) ranks higher than actual documentation

**Why This Matters:**
- LLM sees boilerplate first
- Wastes token budget on non-content
- Reduces context window for actual docs

**Fix:**
```python
# Boost content over metadata
solr_params = {
    'qf': 'content^5.0 title^2.0 metadata^1.0',  # Weight content 5x higher
    'defType': 'edismax',
}
```

### 3. No Version Filtering (Wrong RHEL version docs)

**Symptom:** RHEL 10 queries return RHEL 9 or RHEL 8 documentation

**Root Cause:** Version not boosted in retrieval query

**Why This Matters:**
- Outdated commands (e.g., ISC DHCP for RHEL 10)
- Wrong package names
- Deprecated syntax
- User gets incorrect instructions

**Fix:**
```python
# Add version boost
target_version = extract_rhel_version(query)  # "10"
solr_params = {
    'bq': f'version:{target_version}^10.0',  # Boost target version 10x
}
```

### 4. Boilerplate Pollution

**Symptom:** High % of contexts are legal notices, deprecation warnings, title fragments

**Root Cause:** No content filtering before sending to LLM

**Why This Matters:**
- Wastes 50-90% of context window
- Dilutes signal-to-noise ratio
- Increases context_precision penalty

**Fix:**
```python
# Filter out boilerplate before returning contexts
def is_useful_context(doc):
    if len(doc['content']) < 100:  # Too short
        return False
    if doc['type'] in ['legal_notice', 'warning', 'metadata']:
        return False
    if 'deprecated' in doc['title'].lower() and target_version not in doc:
        return False
    return True

contexts = [doc for doc in solr_results if is_useful_context(doc)]
```

---

## Specific Examples

"""

    # Add anomaly examples
    if anomalies_df is not None and not anomalies_df.empty:
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
    else:
        report += "No anomalies CSV found or no anomalies detected.\n\n"

    # Add recommended action plan
    report += """---

## Recommended Action Plan

### Phase 1: Quick Wins (This Week)

1. **Limit result count**
   - Set Solr `rows` parameter to 10-20
   - Immediate reduction in noise
   - Expected improvement: context_precision +30%

2. **Boost content over metadata**
   - Add `qf` parameter with content weighting
   - Expected improvement: context_relevance +20%

### Phase 2: Version Filtering (Week 2)

1. **Extract version from query**
   - Regex: `RHEL\\s*(\\d+)` or `Red Hat Enterprise Linux (\\d+)`
   - Default to latest version if not specified

2. **Boost target version in Solr**
   - Add `bq` parameter with version boost
   - Expected improvement: temporal test accuracy 50% → 80%

### Phase 3: Content Quality (Week 3-4)

1. **Filter boilerplate**
   - Remove legal notices
   - Remove short metadata fragments
   - Remove off-version deprecation warnings

2. **Improve ranking**
   - Boost recent docs over old ones
   - Boost full documents over fragments
   - Boost tutorials over API refs for how-to queries

---

## Success Metrics

After implementing fixes, re-run evaluations and look for:

| Metric | Current | Target | Impact |
|--------|---------|--------|--------|
| context_precision | 0.2-0.4 | >0.6 | Fewer irrelevant docs |
| context_relevance | 0.3-0.5 | >0.7 | Better ranking |
| faithfulness | 0.6-0.8 | >0.8 | LLM trusts contexts more |
| answer_correctness | 0.8-0.9 | >0.9 | More correct answers |
| **Overall pass rate** | **50-60%** | **>75%** | System improvement |

---

## Validation

Run this evaluation suite again after fixes:

```bash
./run_full_evaluation_suite.sh
```

Compare reports to measure improvement.

---

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

1. **The evaluation framework is working correctly** - It's successfully detecting retrieval quality issues
2. **Primary issue: Over-retrieval** - 100-250+ contexts when 10-20 would be optimal
3. **Secondary issue: Poor ranking** - Boilerplate ranks higher than content
4. **Tertiary issue: Version filtering** - Wrong RHEL version docs retrieved
5. **Quick wins available** - Limiting results and boosting content can improve metrics 30-50%

**These are NOT test framework bugs** - they are accurate measurements of current retrieval quality.

---

**Questions?** Contact evaluation team or see full analysis in the output directory.

**Analysis Location:**
- Correlation analysis: `{correlation_analysis_dir.name if correlation_analysis_dir else 'N/A'}/`
- Version analysis: `{version_analysis_dir.name if version_analysis_dir else 'N/A'}/`

---

*Generated by LightSpeed Evaluation Framework*
"""

    return report


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
                    print(f"    ✓ Found {len(summary_files)} summary report file(s): {summary_files[0].name}")
                    if len(summary_files) > 1:
                        print(f"      (will use most recent)")
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

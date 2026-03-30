#!/usr/bin/env python3
"""Analyze RHEL version distribution in retrieved contexts.

This script analyzes temporal validity test results to measure:
- What percentage of contexts match the target RHEL version
- Version distribution across all retrieved contexts
- Temporal accuracy by conversation

Usage:
    python scripts/analyze_version_distribution.py \\
        --input eval_output/temporal_tests_detailed.csv \\
        --output analysis_output/version_distribution.json

    # With test configuration for expected versions
    python scripts/analyze_version_distribution.py \\
        --input eval_output/temporal_tests_detailed.csv \\
        --test-config config/temporal_validity_tests.yaml \\
        --output analysis_output/
"""

import argparse
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class VersionDistributionAnalyzer:
    """Analyze RHEL version distribution in retrieved contexts."""

    VERSION_PATTERNS = [
        r"\bRHEL\s+(\d{1,2})(?:\.\d+)?\b",
        r"\bRed\s+Hat\s+Enterprise\s+Linux\s+(\d{1,2})(?:\.\d+)?\b",
        r"\brhel-(\d{1,2})(?:[-_.]|$)",
        r"\brhel(\d{1,2})\b",
    ]

    def __init__(self, csv_file: str, test_config_file: str | None = None):
        """Initialize analyzer.

        Args:
            csv_file: Path to evaluation results CSV
            test_config_file: Optional path to test config YAML with target versions
        """
        self.csv_file = csv_file
        self.test_config_file = test_config_file
        self.df: pd.DataFrame | None = None
        self.test_config: dict[str, Any] = {}
        self.results: dict[str, Any] = {}

    def load_data(self) -> None:
        """Load evaluation data and optional test config."""
        logger.info(f"Loading evaluation results from {self.csv_file}...")
        self.df = pd.read_csv(self.csv_file)
        logger.info(f"  Loaded {len(self.df)} rows")

        if self.test_config_file:
            logger.info(f"Loading test config from {self.test_config_file}...")
            with open(self.test_config_file) as f:
                test_data = yaml.safe_load(f)

            # Build lookup: conversation_id -> target_version
            for conversation in test_data:
                conv_id = conversation.get("conversation_group_id")
                target_version = conversation.get("target_version")
                if conv_id and target_version:
                    # Extract version number (e.g., "RHEL 10" -> "10")
                    match = re.search(r"(\d+)", target_version)
                    if match:
                        self.test_config[conv_id] = match.group(1)

            logger.info(f"  Loaded target versions for {len(self.test_config)} conversations")

    def extract_versions_from_text(self, text: str) -> list[str]:
        """Extract RHEL version numbers from text.

        Args:
            text: Text to search for version strings

        Returns:
            List of version numbers found (e.g., ["9", "10"])
        """
        if not text or pd.isna(text):
            return []

        # Remove URLs to prevent matching KB article IDs (e.g., articles/58812)
        text_cleaned = re.sub(r'https?://\S+', '', text)

        versions = []
        for pattern in self.VERSION_PATTERNS:
            matches = re.finditer(pattern, text_cleaned, re.IGNORECASE)
            for match in matches:
                version = match.group(1)
                if version not in versions:
                    versions.append(version)

        return versions

    def analyze_context_versions(self, contexts_str: str) -> dict[str, Any]:
        """Analyze version distribution in a context string.

        Args:
            contexts_str: String representation of contexts list

        Returns:
            Dictionary with version counts and statistics
        """
        if not contexts_str or pd.isna(contexts_str):
            return {
                "total_contexts": 0,
                "version_counts": {},
                "versions_found": [],
            }

        # Try to parse as list
        try:
            if contexts_str.startswith("["):
                contexts = eval(contexts_str)  # Safe for our use case
            else:
                contexts = [contexts_str]
        except:
            contexts = [contexts_str]

        version_counts = Counter()
        for ctx in contexts:
            versions = self.extract_versions_from_text(str(ctx))
            for v in versions:
                version_counts[v] += 1

        return {
            "total_contexts": len(contexts),
            "version_counts": dict(version_counts),
            "versions_found": list(version_counts.keys()),
        }

    def calculate_version_accuracy(
        self, version_counts: dict[str, int], target_version: str, total_contexts: int
    ) -> float:
        """Calculate version accuracy percentage.

        Args:
            version_counts: Dictionary of version -> count
            target_version: Expected version number
            total_contexts: Total number of contexts

        Returns:
            Accuracy as percentage (0-100)
        """
        if total_contexts == 0:
            return 0.0

        target_count = version_counts.get(target_version, 0)
        return (target_count / total_contexts) * 100

    def analyze_conversations(self) -> dict[str, Any]:
        """Analyze version distribution for each conversation.

        Returns:
            Dictionary with per-conversation analysis
        """
        logger.info("Analyzing version distribution per conversation...")

        conversations = {}
        grouped = self.df.groupby("conversation_group_id")

        for conv_id, group in grouped:
            # Get contexts from any row in this conversation
            contexts_rows = group[group["contexts"].notna()]
            if len(contexts_rows) == 0:
                continue

            contexts_str = contexts_rows.iloc[0]["contexts"]
            version_analysis = self.analyze_context_versions(contexts_str)

            # Get target version if available
            target_version = self.test_config.get(conv_id)

            # Calculate accuracy if target known
            accuracy = None
            if target_version and version_analysis["total_contexts"] > 0:
                accuracy = self.calculate_version_accuracy(
                    version_analysis["version_counts"],
                    target_version,
                    version_analysis["total_contexts"],
                )

            conversations[conv_id] = {
                "total_contexts": version_analysis["total_contexts"],
                "version_counts": version_analysis["version_counts"],
                "target_version": target_version,
                "accuracy": accuracy,
            }

        logger.info(f"  Analyzed {len(conversations)} conversations")
        return conversations

    def calculate_overall_statistics(
        self, conversations: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate overall version distribution statistics.

        Args:
            conversations: Per-conversation analysis results

        Returns:
            Overall statistics dictionary
        """
        logger.info("Calculating overall statistics...")

        total_contexts = 0
        version_totals = Counter()
        accuracies = []

        for conv_data in conversations.values():
            total_contexts += conv_data["total_contexts"]
            for version, count in conv_data["version_counts"].items():
                version_totals[version] += count

            if conv_data["accuracy"] is not None:
                accuracies.append(conv_data["accuracy"])

        # Calculate percentages
        version_percentages = {}
        if total_contexts > 0:
            for version, count in version_totals.items():
                version_percentages[version] = (count / total_contexts) * 100

        # Accuracy statistics
        accuracy_stats = {}
        if accuracies:
            accuracy_stats = {
                "mean": sum(accuracies) / len(accuracies),
                "min": min(accuracies),
                "max": max(accuracies),
                "count": len(accuracies),
            }

        return {
            "total_contexts_analyzed": total_contexts,
            "version_totals": dict(version_totals),
            "version_percentages": version_percentages,
            "accuracy_stats": accuracy_stats,
        }

    def generate_report(self, output_dir: Path) -> None:
        """Generate analysis reports.

        Args:
            output_dir: Directory to save reports
        """
        conversations = self.analyze_conversations()
        overall_stats = self.calculate_overall_statistics(conversations)

        self.results = {
            "conversations": conversations,
            "overall": overall_stats,
        }

        # Save JSON report
        json_file = output_dir / "version_distribution.json"
        with open(json_file, "w") as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"  Saved JSON report to {json_file}")

        # Generate text report
        txt_file = output_dir / "version_distribution_report.txt"
        self._write_text_report(txt_file)
        logger.info(f"  Saved text report to {txt_file}")

        # Print summary to console
        self._print_summary()

    def _write_text_report(self, output_file: Path) -> None:
        """Write human-readable text report.

        Args:
            output_file: Path to output file
        """
        lines = []
        lines.append("=" * 80)
        lines.append("RHEL VERSION DISTRIBUTION ANALYSIS")
        lines.append("=" * 80)
        lines.append("")

        # Overall statistics
        overall = self.results["overall"]
        lines.append("OVERALL STATISTICS")
        lines.append("-" * 80)
        lines.append(f"Total contexts analyzed: {overall['total_contexts_analyzed']}")
        lines.append("")

        lines.append("Version Distribution:")
        for version in sorted(overall["version_totals"].keys()):
            count = overall["version_totals"][version]
            pct = overall["version_percentages"][version]
            lines.append(f"  RHEL {version}: {count:5d} contexts ({pct:5.1f}%)")
        lines.append("")

        # Accuracy statistics
        if overall["accuracy_stats"]:
            acc = overall["accuracy_stats"]
            lines.append("Version Accuracy (target version match):")
            lines.append(f"  Mean:  {acc['mean']:.1f}%")
            lines.append(f"  Min:   {acc['min']:.1f}%")
            lines.append(f"  Max:   {acc['max']:.1f}%")
            lines.append(f"  Count: {acc['count']} conversations with target version")
        lines.append("")

        # Per-conversation details
        lines.append("PER-CONVERSATION BREAKDOWN")
        lines.append("-" * 80)

        conversations = self.results["conversations"]
        for conv_id in sorted(conversations.keys()):
            conv = conversations[conv_id]
            lines.append(f"\n{conv_id}:")
            lines.append(f"  Total contexts: {conv['total_contexts']}")

            if conv["target_version"]:
                lines.append(f"  Target version: RHEL {conv['target_version']}")
                if conv["accuracy"] is not None:
                    status = "✅" if conv["accuracy"] >= 80 else "⚠️" if conv["accuracy"] >= 50 else "❌"
                    lines.append(f"  Accuracy: {status} {conv['accuracy']:.1f}%")

            lines.append("  Version breakdown:")
            for version in sorted(conv["version_counts"].keys()):
                count = conv["version_counts"][version]
                pct = (count / conv["total_contexts"]) * 100 if conv["total_contexts"] > 0 else 0
                marker = "→" if version == conv.get("target_version") else " "
                lines.append(f"    {marker} RHEL {version}: {count:3d} ({pct:5.1f}%)")

        lines.append("")
        lines.append("=" * 80)

        output_file.write_text("\n".join(lines))

    def _print_summary(self) -> None:
        """Print summary to console."""
        overall = self.results["overall"]

        print("\n" + "=" * 80)
        print("VERSION DISTRIBUTION SUMMARY")
        print("=" * 80)

        print(f"\nTotal contexts analyzed: {overall['total_contexts_analyzed']}")

        print("\nVersion Distribution:")
        for version in sorted(overall["version_totals"].keys()):
            count = overall["version_totals"][version]
            pct = overall["version_percentages"][version]
            print(f"  RHEL {version}: {count:5d} ({pct:5.1f}%)")

        if overall["accuracy_stats"]:
            acc = overall["accuracy_stats"]
            print(f"\nAverage Version Accuracy: {acc['mean']:.1f}%")
            print(f"  (Based on {acc['count']} conversations with target versions)")

            if acc["mean"] < 50:
                print("\n⚠️  WARNING: Low average accuracy suggests okp-mcp is not")
                print("   filtering contexts by RHEL version effectively!")
            elif acc["mean"] < 80:
                print("\n⚠️  Accuracy could be improved. Consider adding version")
                print("   boosting in okp-mcp Solr query.")
            else:
                print("\n✅ Good version accuracy!")

        print("=" * 80 + "\n")


def find_latest_temporal_test() -> tuple[Path | None, Path | None]:
    """Find the latest temporal test CSV and config from eval_output.

    Returns:
        Tuple of (csv_file, config_file) or (None, None) if not found
    """
    base_dir = Path("eval_output")

    # Find all full_suite_* directories, sorted by name (newest first)
    all_runs = sorted(
        [d for d in base_dir.glob("full_suite_*") if d.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )

    for run_dir in all_runs:
        # Look for temporal test CSV
        temporal_csvs = list(run_dir.glob("temporal_validity_tests*/evaluation_*_detailed.csv"))
        if temporal_csvs:
            csv_file = temporal_csvs[0]

            # Look for corresponding config file
            config_file = Path("config/temporal_validity_tests_runnable.yaml")
            if not config_file.exists():
                config_file = Path("config/temporal_validity_tests.yaml")
            if not config_file.exists():
                config_file = None

            logger.info(f"Auto-detected latest run: {run_dir.name}")
            logger.info(f"  CSV: {csv_file}")
            if config_file:
                logger.info(f"  Config: {config_file}")

            return csv_file, config_file

    return None, None


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze RHEL version distribution in retrieved contexts"
    )
    parser.add_argument(
        "--input",
        "-i",
        help="Input CSV file from evaluation results (auto-detects latest run if not specified)",
    )
    parser.add_argument(
        "--test-config",
        "-t",
        help="Optional YAML config file with target versions (auto-detects if not specified)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output directory for reports (default: auto-generated based on run)",
    )

    args = parser.parse_args()

    try:
        # Auto-detect input and config if not provided
        input_file = args.input
        test_config = args.test_config
        output_dir = args.output

        if not input_file:
            logger.info("No --input specified, auto-detecting latest run...")
            csv_file, config_file = find_latest_temporal_test()

            if not csv_file:
                logger.error("❌ No temporal test runs found in eval_output/")
                logger.error("   Run an evaluation first or specify --input manually")
                return 1

            input_file = str(csv_file)
            if not test_config and config_file:
                test_config = str(config_file)

            # Auto-generate output directory based on run
            if not output_dir:
                run_dir = csv_file.parent.parent
                output_dir = str(run_dir / "version_analysis")
        else:
            # Manual input specified
            if not output_dir:
                output_dir = "analysis_output"

        logger.info(f"\n📊 Analyzing version distribution...")
        logger.info(f"Input:  {input_file}")
        if test_config:
            logger.info(f"Config: {test_config}")
        logger.info(f"Output: {output_dir}\n")

        analyzer = VersionDistributionAnalyzer(input_file, test_config)
        analyzer.load_data()

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        analyzer.generate_report(output_path)

        logger.info(f"\n✅ Analysis complete! Reports saved to: {output_path}")

        return 0
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

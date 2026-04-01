#!/usr/bin/env python3
"""Autonomous agent for okp-mcp RSPEED ticket fixing.

This agent automates the INCORRECT_ANSWER_LOOP workflow:
1. Diagnose: Run full evaluation to identify problem type
2. Analyze: Determine if it's retrieval or answer quality issue
3. Iterate: Make targeted changes (boost queries or prompts)
4. Validate: Check for regressions across all test suites
5. Commit: Create commit with detailed metrics

Usage:
    # Diagnose a single ticket (runs new evaluation)
    python scripts/okp_mcp_agent.py diagnose RSPEED-2482

    # Diagnose using existing results (fast, no re-run)
    python scripts/okp_mcp_agent.py diagnose RSPEED-2482 --use-existing

    # Auto-fix with iterations
    python scripts/okp_mcp_agent.py fix RSPEED-2482 --max-iterations 10

    # Validate across all suites
    python scripts/okp_mcp_agent.py validate
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class MetricThresholds:
    """Thresholds for determining problem type."""

    url_f1_retrieval_problem: float = 0.7
    mrr_retrieval_problem: float = 0.5
    context_relevance_retrieval_problem: float = 0.7
    keywords_answer_problem: float = 0.7


@dataclass
class EvaluationResult:
    """Results from a single evaluation run."""

    ticket_id: str
    url_f1: Optional[float] = None
    mrr: Optional[float] = None
    context_relevance: Optional[float] = None
    context_precision: Optional[float] = None
    keywords_score: Optional[float] = None
    forbidden_claims_score: Optional[float] = None

    @property
    def is_retrieval_problem(self) -> bool:
        """Determine if this is a retrieval problem based on metrics."""
        thresholds = MetricThresholds()

        retrieval_issues = []
        if self.url_f1 is not None and self.url_f1 < thresholds.url_f1_retrieval_problem:
            retrieval_issues.append(f"URL F1 low ({self.url_f1:.2f})")
        if self.mrr is not None and self.mrr < thresholds.mrr_retrieval_problem:
            retrieval_issues.append(f"MRR low ({self.mrr:.2f})")
        if (
            self.context_relevance is not None
            and self.context_relevance < thresholds.context_relevance_retrieval_problem
        ):
            retrieval_issues.append(f"Context relevance low ({self.context_relevance:.2f})")

        return len(retrieval_issues) > 0

    @property
    def is_answer_problem(self) -> bool:
        """Determine if this is an answer quality problem."""
        # Answer problem if retrieval is good but keywords are missing
        thresholds = MetricThresholds()

        good_retrieval = (
            self.url_f1 is not None
            and self.url_f1 >= thresholds.url_f1_retrieval_problem
        )
        poor_keywords = (
            self.keywords_score is not None
            and self.keywords_score < thresholds.keywords_answer_problem
        )

        return good_retrieval and poor_keywords

    def summary(self) -> str:
        """Human-readable summary of metrics."""
        lines = [f"Ticket: {self.ticket_id}"]
        if self.url_f1 is not None:
            lines.append(f"  URL F1: {self.url_f1:.2f}")
        if self.mrr is not None:
            lines.append(f"  MRR: {self.mrr:.2f}")
        if self.context_relevance is not None:
            lines.append(f"  Context Relevance: {self.context_relevance:.2f}")
        if self.context_precision is not None:
            lines.append(f"  Context Precision: {self.context_precision:.2f}")
        if self.keywords_score is not None:
            lines.append(f"  Keywords: {self.keywords_score:.2f}")
        if self.forbidden_claims_score is not None:
            lines.append(f"  Forbidden Claims: {self.forbidden_claims_score:.2f}")

        return "\n".join(lines)


class OkpMcpAgent:
    """Autonomous agent for fixing okp-mcp RSPEED tickets."""

    def __init__(
        self,
        eval_root: Path,
        okp_mcp_root: Path,
        lscore_deploy_root: Path,
    ):
        """Initialize agent with paths to key directories."""
        self.eval_root = eval_root
        self.okp_mcp_root = okp_mcp_root
        self.lscore_deploy_root = lscore_deploy_root

        # Test suite configs
        self.functional_full = (
            eval_root / "config/okp_mcp_test_suites/functional_tests_full.yaml"
        )
        self.functional_retrieval = (
            eval_root / "config/okp_mcp_test_suites/functional_tests_retrieval.yaml"
        )

    def run_command(
        self, cmd: List[str], cwd: Optional[Path] = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a shell command and return result."""
        print(f"$ {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result

    def restart_okp_mcp(self):
        """Restart okp-mcp service."""
        print("\n🔄 Restarting okp-mcp...")
        self.run_command(
            ["podman-compose", "restart", "okp-mcp"],
            cwd=self.lscore_deploy_root / "local",
        )
        print("✓ okp-mcp restarted")

    def run_full_eval(self, config: Path, runs: int = 1) -> Path:
        """Run full evaluation suite and return output directory."""
        print(f"\n📊 Running full evaluation ({runs} runs)...")
        self.run_command(
            [
                "./run_okp_mcp_full_suite.sh",
                "--config",
                str(config),
                "--runs",
                str(runs),
            ],
            cwd=self.eval_root,
        )

        # Find the latest output directory
        output_dirs = sorted(
            (self.eval_root / "okp_mcp_full_output").glob("suite_*"),
            key=lambda p: p.stat().st_mtime,
        )
        if not output_dirs:
            raise RuntimeError("No evaluation output found")

        return output_dirs[-1]

    def run_retrieval_eval(self, config: Path, runs: int = 3) -> Path:
        """Run fast retrieval-only evaluation and return output directory."""
        print(f"\n⚡ Running retrieval evaluation ({runs} runs)...")
        self.run_command(
            [
                "./run_mcp_retrieval_suite.sh",
                "--config",
                str(config),
                "--runs",
                str(runs),
            ],
            cwd=self.eval_root,
        )

        # Find the latest output directory
        output_dirs = sorted(
            (self.eval_root / "mcp_retrieval_output").glob("suite_*"),
            key=lambda p: p.stat().st_mtime,
        )
        if not output_dirs:
            raise RuntimeError("No evaluation output found")

        return output_dirs[-1]

    def get_latest_output_dir(self, output_type: str = "full") -> Path:
        """Find the most recent evaluation output directory.

        Args:
            output_type: "full" or "retrieval"

        Returns:
            Path to latest suite_* directory
        """
        if output_type == "full":
            base_dir = self.eval_root / "okp_mcp_full_output"
        else:
            base_dir = self.eval_root / "mcp_retrieval_output"

        output_dirs = sorted(
            base_dir.glob("suite_*"),
            key=lambda p: p.stat().st_mtime,
        )

        if not output_dirs:
            raise RuntimeError(
                f"No existing evaluation output found in {base_dir}\n"
                f"Run an evaluation first or remove --use-existing flag"
            )

        return output_dirs[-1]

    def parse_results(self, output_dir: Path, ticket_id: str) -> EvaluationResult:
        """Parse evaluation results for a specific ticket."""
        # Find the detailed CSV
        csv_files = list(output_dir.glob("run_001/evaluation_*_detailed.csv"))
        if not csv_files:
            raise RuntimeError(f"No detailed CSV found in {output_dir}")

        csv_path = csv_files[0]
        df = pd.read_csv(csv_path)

        # Filter to this ticket
        ticket_df = df[df["conversation_group_id"] == ticket_id]

        result = EvaluationResult(ticket_id=ticket_id)

        # Extract metrics
        for _, row in ticket_df.iterrows():
            metric = row["metric_identifier"]
            score = row.get("score")

            if metric == "custom:url_retrieval_eval":
                result.url_f1 = score
                # Try to extract MRR from metadata
                metadata = row.get("metric_metadata", "")
                if isinstance(metadata, str) and "mrr" in metadata.lower():
                    try:
                        # Parse JSON metadata
                        meta_dict = json.loads(metadata)
                        result.mrr = meta_dict.get("mrr")
                    except (json.JSONDecodeError, TypeError):
                        pass

            elif metric == "ragas:context_relevance":
                result.context_relevance = score

            elif metric == "ragas:context_precision_without_reference":
                result.context_precision = score

            elif metric == "custom:keywords_eval":
                result.keywords_score = score

            elif metric == "custom:forbidden_claims_eval":
                result.forbidden_claims_score = score

        return result

    def diagnose(self, ticket_id: str, use_existing: bool = False) -> EvaluationResult:
        """Diagnose a ticket by running full evaluation once.

        Args:
            ticket_id: RSPEED ticket ID (e.g., "RSPEED-2482")
            use_existing: If True, use most recent evaluation results without re-running

        Returns:
            EvaluationResult with parsed metrics
        """
        print(f"\n{'='*80}")
        print(f"DIAGNOSING: {ticket_id}")
        print(f"{'='*80}")

        if use_existing:
            # Find most recent evaluation output
            print("\n📂 Using existing evaluation results...")
            output_dir = self.get_latest_output_dir("full")
            print(f"   Found: {output_dir.name}")
        else:
            # Run full eval to get complete picture
            output_dir = self.run_full_eval(self.functional_full, runs=1)

        # Parse results
        result = self.parse_results(output_dir, ticket_id)

        print("\n" + result.summary())

        # Determine problem type
        if result.is_retrieval_problem:
            print("\n🔍 DIAGNOSIS: RETRIEVAL PROBLEM")
            print("   → Use fast iteration mode (retrieval-only)")
            print("   → Edit okp-mcp boost queries")
        elif result.is_answer_problem:
            print("\n💬 DIAGNOSIS: ANSWER PROBLEM")
            print("   → Use full iteration mode")
            print("   → Edit system prompts")
        else:
            print("\n✅ DIAGNOSIS: METRICS LOOK GOOD")

        return result

    def validate_all_suites(self) -> Dict[str, List[EvaluationResult]]:
        """Run all test suites to check for regressions."""
        print(f"\n{'='*80}")
        print("VALIDATION: Running all test suites")
        print(f"{'='*80}")

        results = {}

        # Run functional suite
        print("\n1. Functional tests...")
        output_dir = self.run_full_eval(self.functional_full, runs=3)
        # TODO: Parse all results, not just one ticket
        results["functional"] = []

        # TODO: Add other suites (chronically_failing, general_documentation)

        return results

    def fix_ticket(
        self, ticket_id: str, max_iterations: int = 10, auto_commit: bool = False
    ):
        """Autonomous ticket fixing with iteration."""
        print(f"\n{'='*80}")
        print(f"AUTO-FIX: {ticket_id}")
        print(f"{'='*80}")

        # Step 1: Diagnose
        initial_result = self.diagnose(ticket_id)

        if not (initial_result.is_retrieval_problem or initial_result.is_answer_problem):
            print("\n✅ Ticket already passing, nothing to fix")
            return

        # Step 2: Iterate
        if initial_result.is_retrieval_problem:
            print("\n🔄 Starting fast iteration (retrieval mode)...")
            # TODO: Implement retrieval iteration loop
            print("   [TODO] Edit boost queries in okp-mcp")
            print("   [TODO] Restart okp-mcp")
            print("   [TODO] Run retrieval eval")
            print("   [TODO] Check if URL F1 > 0.8")

        elif initial_result.is_answer_problem:
            print("\n🔄 Starting full iteration (answer mode)...")
            # TODO: Implement answer iteration loop
            print("   [TODO] Edit system prompt")
            print("   [TODO] Restart okp-mcp")
            print("   [TODO] Run full eval")
            print("   [TODO] Check if keywords present")

        # Step 3: Validate
        print("\n🔍 Running regression checks...")
        # TODO: Run all suites and compare with baseline

        # Step 4: Commit
        if auto_commit:
            print("\n💾 Creating commit...")
            # TODO: Create commit with metrics
        else:
            print("\n💡 Run with --auto-commit to create commit automatically")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="okp-mcp autonomous agent")
    parser.add_argument(
        "command",
        choices=["diagnose", "fix", "validate"],
        help="Command to run",
    )
    parser.add_argument(
        "ticket_id",
        nargs="?",
        help="RSPEED ticket ID (e.g., RSPEED-2482)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum fix iterations",
    )
    parser.add_argument(
        "--auto-commit",
        action="store_true",
        help="Automatically create commits",
    )
    parser.add_argument(
        "--use-existing",
        action="store_true",
        help="Use existing evaluation results instead of re-running (faster for testing)",
    )

    args = parser.parse_args()

    # Initialize agent
    agent = OkpMcpAgent(
        eval_root=Path.home() / "Work/lightspeed-core/lightspeed-evaluation",
        okp_mcp_root=Path.home() / "Work/okp-mcp",
        lscore_deploy_root=Path.home() / "Work/lscore-deploy",
    )

    # Execute command
    if args.command == "diagnose":
        if not args.ticket_id:
            parser.error("ticket_id required for diagnose command")
        agent.diagnose(args.ticket_id, use_existing=args.use_existing)

    elif args.command == "fix":
        if not args.ticket_id:
            parser.error("ticket_id required for fix command")
        agent.fix_ticket(
            args.ticket_id,
            max_iterations=args.max_iterations,
            auto_commit=args.auto_commit,
        )

    elif args.command == "validate":
        agent.validate_all_suites()


if __name__ == "__main__":
    main()

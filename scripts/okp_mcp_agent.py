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

# LLM advisor for AI-powered suggestions (Phase 2)
try:
    from okp_mcp_llm_advisor import OkpMcpLLMAdvisor, MetricSummary

    LLM_ADVISOR_AVAILABLE = True
except ImportError:
    LLM_ADVISOR_AVAILABLE = False
    print(
        "⚠️  LLM advisor not available (okp_mcp_llm_advisor.py not found or missing dependencies)"
    )


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
    query: Optional[str] = None  # User query from CSV

    # Retrieval metrics (available in both retrieval-only and full modes)
    url_f1: Optional[float] = None
    mrr: Optional[float] = None
    context_relevance: Optional[float] = None
    context_precision: Optional[float] = None

    # Answer quality metrics (only in full mode with /v1/infer)
    keywords_score: Optional[float] = None
    forbidden_claims_score: Optional[float] = None
    faithfulness: Optional[float] = None  # ragas:faithfulness - answer grounded in context
    answer_correctness: Optional[float] = None  # custom:answer_correctness - vs expected answer
    response_relevancy: Optional[float] = None  # ragas:response_relevancy - addresses question

    # RAG usage tracking
    tool_calls: Optional[str] = None  # Raw tool_calls from CSV
    contexts: Optional[str] = None  # Raw contexts from CSV
    rag_used: bool = False  # Was RAG/search tool called?
    docs_retrieved: bool = False  # Were any documents retrieved?

    @property
    def is_retrieval_problem(self) -> bool:
        """Determine if this is a retrieval problem based on metrics."""
        thresholds = MetricThresholds()

        retrieval_issues = []
        if (
            self.url_f1 is not None
            and self.url_f1 < thresholds.url_f1_retrieval_problem
        ):
            retrieval_issues.append(f"URL F1 low ({self.url_f1:.2f})")
        if self.mrr is not None and self.mrr < thresholds.mrr_retrieval_problem:
            retrieval_issues.append(f"MRR low ({self.mrr:.2f})")
        if (
            self.context_relevance is not None
            and self.context_relevance < thresholds.context_relevance_retrieval_problem
        ):
            retrieval_issues.append(
                f"Context relevance low ({self.context_relevance:.2f})"
            )

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

    @property
    def has_metrics(self) -> bool:
        """Check if any metrics were successfully parsed."""
        return any(
            [
                self.url_f1 is not None,
                self.mrr is not None,
                self.context_relevance is not None,
                self.context_precision is not None,
                self.keywords_score is not None,
                self.forbidden_claims_score is not None,
                self.faithfulness is not None,
                self.answer_correctness is not None,
                self.response_relevancy is not None,
            ]
        )

    @property
    def is_retrieval_only_mode(self) -> bool:
        """Detect if this was retrieval-only mode (no answer metrics)."""
        # Retrieval-only mode has URL F1 but no answer quality metrics
        has_retrieval = self.url_f1 is not None or self.context_relevance is not None
        has_answer = any(
            [
                self.keywords_score is not None,
                self.faithfulness is not None,
                self.answer_correctness is not None,
            ]
        )
        return has_retrieval and not has_answer

    def summary(self) -> str:
        """Human-readable summary of metrics."""
        lines = [f"Ticket: {self.ticket_id}"]

        if not self.has_metrics:
            lines.append("  ⚠️  No metrics found (check if evaluation ran successfully)")
            return "\n".join(lines)

        # RAG usage status
        if self.rag_used:
            if self.docs_retrieved:
                lines.append(
                    f"  RAG Status: ✅ Used, {self.num_docs_retrieved()} docs retrieved"
                )
            else:
                lines.append("  RAG Status: ⚠️  Used, but NO documents retrieved")
        else:
            lines.append("  RAG Status: ❌ NOT used (LLM used general knowledge only)")

        # Retrieval Metrics
        if self.url_f1 is not None:
            lines.append(f"  URL F1: {self.url_f1:.2f}")
        if self.mrr is not None:
            lines.append(f"  MRR: {self.mrr:.2f}")
        if self.context_relevance is not None:
            lines.append(f"  Context Relevance: {self.context_relevance:.2f}")
        if self.context_precision is not None:
            lines.append(f"  Context Precision: {self.context_precision:.2f}")

        # Answer Quality Metrics (only in full mode)
        if self.keywords_score is not None:
            lines.append(f"  Keywords: {self.keywords_score:.2f}")
        if self.faithfulness is not None:
            lines.append(f"  Faithfulness: {self.faithfulness:.2f}")
        if self.answer_correctness is not None:
            lines.append(f"  Answer Correctness: {self.answer_correctness:.2f}")
        if self.response_relevancy is not None:
            lines.append(f"  Response Relevancy: {self.response_relevancy:.2f}")
        if self.forbidden_claims_score is not None:
            lines.append(f"  Forbidden Claims: {self.forbidden_claims_score:.2f}")

        return "\n".join(lines)

    def num_docs_retrieved(self) -> int:
        """Count how many documents were retrieved."""
        if not self.docs_retrieved or not self.contexts:
            return 0

        # Try to count documents in contexts (rough heuristic)
        contexts_str = str(self.contexts)
        # Count URLs in the contexts
        import re

        urls = re.findall(r'https?://[^\s"]+', contexts_str)
        return len(urls) if urls else 1  # At least 1 if contexts exist


class OkpMcpAgent:
    """Autonomous agent for fixing okp-mcp RSPEED tickets."""

    def __init__(
        self,
        eval_root: Path,
        okp_mcp_root: Path,
        lscore_deploy_root: Path,
        worktree_root: Optional[Path] = None,
        interactive: bool = True,
        enable_llm_advisor: bool = True,
    ):
        """Initialize agent with paths to key directories.

        Args:
            eval_root: Path to lightspeed-evaluation repo
            okp_mcp_root: Path to okp-mcp repo
            lscore_deploy_root: Path to lscore-deploy repo
            worktree_root: Base directory for worktrees (default: ~/Work/okp-mcp-worktrees)
            interactive: If True, ask for confirmation before making changes
            enable_llm_advisor: If True, use LLM advisor for AI-powered suggestions (requires Vertex AI)
        """
        self.eval_root = eval_root
        self.okp_mcp_root = okp_mcp_root
        self.lscore_deploy_root = lscore_deploy_root
        self.worktree_root = worktree_root or (Path.home() / "Work/okp-mcp-worktrees")
        self.interactive = interactive

        # Test suite configs
        self.functional_full = (
            eval_root / "config/okp_mcp_test_suites/functional_tests_full.yaml"
        )
        self.functional_retrieval = (
            eval_root / "config/okp_mcp_test_suites/functional_tests_retrieval.yaml"
        )

        # Initialize LLM advisor (Phase 2)
        self.llm_advisor = None
        if enable_llm_advisor and LLM_ADVISOR_AVAILABLE:
            try:
                self.llm_advisor = OkpMcpLLMAdvisor(
                    model="claude-sonnet-4-5@20250929",
                    okp_mcp_root=okp_mcp_root,
                    use_tiered_models=True,
                    simple_model="claude-haiku-4-5@20251001",
                    complex_model="claude-sonnet-4-5@20250929",
                )
                print("✅ LLM advisor initialized")
            except Exception as e:
                print(f"⚠️  LLM advisor initialization failed: {e}")
                print("   Continuing without AI-powered suggestions")
                self.llm_advisor = None

    def run_command(
        self, cmd: List[str], cwd: Optional[Path] = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a shell command and return result."""
        print(f"$ {' '.join(cmd)}")
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=check
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result

    def ask_approval(self, question: str, default: bool = False) -> bool:
        """Ask user for approval in interactive mode.

        Args:
            question: Question to ask
            default: Default answer if non-interactive

        Returns:
            True if approved, False otherwise
        """
        if not self.interactive:
            return default

        choices = "[Y/n]" if default else "[y/N]"
        response = input(f"\n{question} {choices}: ").strip().lower()

        if not response:
            return default

        return response in ("y", "yes")

    def create_worktree(
        self, ticket_id: str, branch_name: Optional[str] = None
    ) -> Path:
        """Create a git worktree for isolated development.

        Args:
            ticket_id: RSPEED ticket ID
            branch_name: Optional custom branch name

        Returns:
            Path to the worktree directory
        """
        if not branch_name:
            branch_name = f"fix/{ticket_id.lower()}"

        worktree_dir = self.worktree_root / branch_name.replace("/", "-")

        print(f"\n🌳 Creating worktree for {ticket_id}...")
        print(f"   Branch: {branch_name}")
        print(f"   Directory: {worktree_dir}")

        # Create worktree directory if it doesn't exist
        self.worktree_root.mkdir(parents=True, exist_ok=True)

        # Check if worktree already exists
        if worktree_dir.exists():
            if self.ask_approval(
                f"Worktree {worktree_dir} already exists. Remove and recreate?"
            ):
                self.run_command(
                    ["git", "worktree", "remove", str(worktree_dir), "--force"],
                    cwd=self.okp_mcp_root,
                    check=False,
                )
            else:
                print("   Using existing worktree")
                return worktree_dir

        # Create new worktree
        self.run_command(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_dir)],
            cwd=self.okp_mcp_root,
        )

        print(f"✓ Worktree created at {worktree_dir}")
        return worktree_dir

    def cleanup_worktree(self, worktree_dir: Path):
        """Remove a worktree after work is complete.

        Args:
            worktree_dir: Path to worktree to remove
        """
        if self.ask_approval(f"Remove worktree {worktree_dir}?", default=False):
            print("\n🧹 Cleaning up worktree...")
            self.run_command(
                ["git", "worktree", "remove", str(worktree_dir), "--force"],
                cwd=self.okp_mcp_root,
            )
            print("✓ Worktree removed")

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

    def _get_num_docs(self, contexts: Optional[str]) -> int:
        """Extract number of documents from contexts field."""
        if not contexts or pd.isna(contexts):
            return 0

        try:
            # Try to parse as JSON array
            import json

            contexts_list = json.loads(contexts)
            if isinstance(contexts_list, list):
                return len(contexts_list)
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: count non-empty string
        return 1 if str(contexts).strip() and str(contexts).strip() != "[]" else 0

    def _get_llm_boost_suggestion(self, result: EvaluationResult):
        """Get LLM suggestion for boost query improvements."""
        if not self.llm_advisor or not result.query:
            return

        print("\n" + "=" * 80)
        print("💡 AI-POWERED SUGGESTION (Boost Query)")
        print("=" * 80)

        try:
            # Convert EvaluationResult to MetricSummary
            metrics = MetricSummary(
                ticket_id=result.ticket_id,
                query=result.query,
                url_f1=result.url_f1,
                mrr=result.mrr,
                context_relevance=result.context_relevance,
                context_precision=result.context_precision,
                keywords_score=result.keywords_score,
                forbidden_claims_score=result.forbidden_claims_score,
                rag_used=result.rag_used,
                docs_retrieved=result.docs_retrieved,
                num_docs=self._get_num_docs(result.contexts),
            )

            # Get suggestion
            suggestion = self.llm_advisor.suggest_boost_query_changes(metrics)

            # Display suggestion
            print(f"\n📝 Reasoning:\n{suggestion.reasoning}\n")
            print(f"📄 File: {suggestion.file_path}")
            print(f"✏️  Change: {suggestion.suggested_change}\n")
            print(f"📈 Expected Improvement:\n{suggestion.expected_improvement}\n")
            print(f"🎯 Confidence: {suggestion.confidence}")

            if suggestion.code_snippet:
                print(f"\n💻 Code Snippet:\n{suggestion.code_snippet}")

        except Exception as e:
            print(f"\n⚠️  Failed to get LLM suggestion: {e}")
            print("   Continuing without AI-powered suggestion")

    def _get_llm_prompt_suggestion(self, result: EvaluationResult):
        """Get LLM suggestion for system prompt improvements."""
        if not self.llm_advisor or not result.query:
            return

        print("\n" + "=" * 80)
        print("💡 AI-POWERED SUGGESTION (System Prompt)")
        print("=" * 80)

        try:
            # Convert EvaluationResult to MetricSummary
            metrics = MetricSummary(
                ticket_id=result.ticket_id,
                query=result.query,
                url_f1=result.url_f1,
                mrr=result.mrr,
                context_relevance=result.context_relevance,
                context_precision=result.context_precision,
                keywords_score=result.keywords_score,
                forbidden_claims_score=result.forbidden_claims_score,
                rag_used=result.rag_used,
                docs_retrieved=result.docs_retrieved,
                num_docs=self._get_num_docs(result.contexts),
            )

            # Get suggestion
            suggestion = self.llm_advisor.suggest_prompt_changes(metrics)

            # Display suggestion
            print(f"\n📝 Reasoning:\n{suggestion.reasoning}\n")
            print(f"✏️  Suggested Change:\n{suggestion.suggested_change}\n")
            print(f"📈 Expected Improvement:\n{suggestion.expected_improvement}\n")
            print(f"🎯 Confidence: {suggestion.confidence}")

        except Exception as e:
            print(f"\n⚠️  Failed to get LLM suggestion: {e}")
            print("   Continuing without AI-powered suggestion")

    def parse_results(self, output_dir: Path, ticket_id: str) -> EvaluationResult:
        """Parse evaluation results for a specific ticket.

        Args:
            output_dir: Path to evaluation output directory
            ticket_id: Ticket ID (e.g., "RSPEED-2482" or "RSPEED_2482")

        Returns:
            EvaluationResult with parsed metrics
        """
        # Find the detailed CSV
        csv_files = list(output_dir.glob("run_001/evaluation_*_detailed.csv"))
        if not csv_files:
            raise RuntimeError(f"No detailed CSV found in {output_dir}")

        csv_path = csv_files[0]
        df = pd.read_csv(csv_path)

        # Normalize ticket ID (CSV uses underscores, users might type hyphens)
        normalized_ticket_id = ticket_id.replace("-", "_")

        # Filter to this ticket
        ticket_df = df[df["conversation_group_id"] == normalized_ticket_id]

        if ticket_df.empty:
            available_tickets = df["conversation_group_id"].unique()[:10]
            raise RuntimeError(
                f"Ticket '{ticket_id}' (normalized to '{normalized_ticket_id}') not found in CSV.\n"
                f"Available tickets: {', '.join(available_tickets)}"
            )

        result = EvaluationResult(ticket_id=ticket_id)

        # Extract tool_calls, contexts, and query (same across all rows for a ticket)
        if not ticket_df.empty:
            first_row = ticket_df.iloc[0]
            result.tool_calls = first_row.get("tool_calls")
            result.contexts = first_row.get("contexts")
            result.query = first_row.get("query", first_row.get("user_input"))

            # Check if RAG was used
            if pd.notna(result.tool_calls) and result.tool_calls:
                # Check if search/retrieval tool was called
                tool_calls_str = str(result.tool_calls).lower()
                result.rag_used = any(
                    keyword in tool_calls_str
                    for keyword in ["search", "portal", "retrieve", "mcp"]
                )

            # Check if documents were retrieved
            if pd.notna(result.contexts) and result.contexts:
                contexts_str = str(result.contexts).strip()
                result.docs_retrieved = (
                    contexts_str != ""
                    and contexts_str != "[]"
                    and contexts_str != "null"
                )

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

            elif metric == "ragas:faithfulness":
                result.faithfulness = score

            elif metric == "custom:answer_correctness":
                result.answer_correctness = score

            elif metric == "ragas:response_relevancy":
                result.response_relevancy = score

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

        # Check if we have metrics to analyze
        if not result.has_metrics:
            print("\n❌ DIAGNOSIS: NO METRICS FOUND")
            print("   → Check if the evaluation completed successfully")
            print("   → Check if this ticket is in the test suite")
            return result

        # Check RAG usage first
        if not result.rag_used:
            print("\n⚠️  DIAGNOSIS: RAG NOT USED")
            print("   → LLM answered from general knowledge only")
            print("   → System prompt may need adjustment to force tool usage")
            print("   → Or RAG tool may not be configured correctly")
            return result

        if result.rag_used and not result.docs_retrieved:
            print("\n⚠️  DIAGNOSIS: RAG CALLED BUT NO DOCUMENTS RETRIEVED")
            print("   → okp-mcp search returned empty results")
            print("   → Query reformulation may be needed")
            print("   → Check Solr index has relevant documents")
            return result

        # Determine problem type (RAG was used and returned docs)
        if result.is_retrieval_problem:
            print("\n🔍 DIAGNOSIS: RETRIEVAL PROBLEM")
            if result.url_f1 == 0.0:
                print("   → Wrong documents retrieved (URL F1 = 0.00)")
                print("   → None of the expected docs were returned")
            else:
                print(f"   → Some expected docs missing (URL F1 = {result.url_f1:.2f})")
            print("   → Use fast iteration mode (retrieval-only)")
            print("   → Edit okp-mcp boost queries")

            # Get LLM suggestion for boost query changes
            self._get_llm_boost_suggestion(result)

        elif result.is_answer_problem:
            print("\n💬 DIAGNOSIS: ANSWER PROBLEM")
            print("   → Right documents retrieved BUT keywords missing")
            print("   → LLM not using the retrieved documents effectively")
            print("   → Use full iteration mode")
            print("   → Edit system prompts to emphasize using context")

            # Get LLM suggestion for prompt changes
            self._get_llm_prompt_suggestion(result)

        else:
            print("\n✅ DIAGNOSIS: METRICS LOOK GOOD")
            print("   → All thresholds passed")
            print("   → Expected documents retrieved and answer is correct")

        return result

    def validate_all_suites(self) -> Dict[str, List[EvaluationResult]]:
        """Run all test suites to check for regressions."""
        print(f"\n{'='*80}")
        print("VALIDATION: Running all test suites")
        print(f"{'='*80}")

        results = {}

        # Run functional suite
        print("\n1. Functional tests...")
        _output_dir = self.run_full_eval(self.functional_full, runs=3)
        # TODO: Parse all results from _output_dir, not just one ticket
        results["functional"] = []

        # TODO: Add other suites (chronically_failing, general_documentation)

        return results

    def fix_ticket(
        self,
        ticket_id: str,
        max_iterations: int = 10,
        use_worktree: bool = False,
        worktree_name: Optional[str] = None,
        suggest_only: bool = False,
    ):
        """Autonomous ticket fixing with iteration.

        Args:
            ticket_id: RSPEED ticket ID
            max_iterations: Maximum number of iteration attempts
            use_worktree: If True, work in an isolated git worktree
            worktree_name: Optional custom worktree/branch name
            suggest_only: If True, suggest changes but don't apply them
        """
        print(f"\n{'='*80}")
        print(f"AUTO-FIX: {ticket_id}")
        print(f"{'='*80}")

        # Setup: Create worktree if requested
        working_dir = self.okp_mcp_root
        if use_worktree:
            working_dir = self.create_worktree(ticket_id, worktree_name)
            print(f"\n📂 Working in isolated worktree: {working_dir}")

        try:
            # Step 1: Diagnose
            initial_result = self.diagnose(ticket_id)

            if not (
                initial_result.is_retrieval_problem or initial_result.is_answer_problem
            ):
                print("\n✅ Ticket already passing, nothing to fix")
                return

            # Step 2: Iterate (TODO - Phase 2)
            if initial_result.is_retrieval_problem:
                print("\n🔄 Fast iteration mode (retrieval)...")
                print("   [TODO - Phase 2] LLM suggests boost query changes")
                print("   [TODO - Phase 2] Apply changes after approval")
                print("   [TODO - Phase 2] Iterate until URL F1 > 0.8")

            elif initial_result.is_answer_problem:
                print("\n🔄 Full iteration mode (answer)...")
                print("   [TODO - Phase 2] LLM suggests prompt changes")
                print("   [TODO - Phase 2] Apply changes after approval")
                print("   [TODO - Phase 2] Iterate until keywords present")

            # Step 3: Validate (TODO - Phase 2)
            print("\n🔍 Regression checks...")
            print("   [TODO - Phase 2] Run all test suites")
            print("   [TODO - Phase 2] Compare with baseline")

            # Step 4: Review
            if use_worktree:
                print("\n📝 Review changes in worktree:")
                print(f"   cd {working_dir}")
                print("   git diff main")
                print("\n   When ready to merge:")
                print("   git checkout main")
                print(f"   git merge {worktree_name or f'fix/{ticket_id.lower()}'}")
                print("\n   Or to discard:")
                print(f"   git worktree remove {working_dir}")

        finally:
            # Cleanup: Ask if worktree should be removed
            if use_worktree and not suggest_only:
                self.cleanup_worktree(working_dir)


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
        help="Maximum fix iterations (for 'fix' command)",
    )
    parser.add_argument(
        "--use-existing",
        action="store_true",
        help="Use existing evaluation results instead of re-running (faster for testing)",
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="Work in an isolated git worktree (safer, recommended for 'fix' command)",
    )
    parser.add_argument(
        "--worktree-name",
        type=str,
        help="Custom worktree/branch name (default: fix/<ticket-id>)",
    )
    parser.add_argument(
        "--suggest-only",
        action="store_true",
        help="Suggest changes but don't apply them (for 'fix' command)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without asking for approval (use with caution)",
    )

    args = parser.parse_args()

    # Initialize agent
    agent = OkpMcpAgent(
        eval_root=Path.home() / "Work/lightspeed-core/lightspeed-evaluation",
        okp_mcp_root=Path.home() / "Work/okp-mcp",
        lscore_deploy_root=Path.home() / "Work/lscore-deploy",
        interactive=not args.non_interactive,
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
            use_worktree=args.worktree,
            worktree_name=args.worktree_name,
            suggest_only=args.suggest_only,
        )

    elif args.command == "validate":
        agent.validate_all_suites()


if __name__ == "__main__":
    main()

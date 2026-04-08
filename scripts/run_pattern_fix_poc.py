#!/usr/bin/env python3
"""Pattern Fix Loop - Proof of Concept

Implements the simplified fix loop with smart routing between Solr optimization
and full retrieval path testing.

Usage:
    # Run POC on small pattern
    python scripts/run_pattern_fix_poc.py RHEL10_DEPRECATED_FEATURES

    # Custom thresholds
    python scripts/run_pattern_fix_poc.py CONTAINER_UNSUPPORTED_CONFIG \
        --max-iterations 15 \
        --answer-threshold 0.75 \
        --stability-runs 5

Output:
    - Git branch: fix/pattern-{pattern_id}
    - Diagnostics: .diagnostics/{pattern_id}/
    - Review report: .diagnostics/{pattern_id}/REVIEW_REPORT.md
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# Add repo root to sys.path
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import base agent
from scripts.okp_mcp_agent import (
    OkpMcpAgent,
    EvaluationResult,
)


@dataclass
class PhaseResult:
    """Result from a fix loop phase."""

    phase_name: str
    success: bool
    iterations: int = 0
    final_metrics: Dict = field(default_factory=dict)
    reason: str = ""


@dataclass
class PatternFixResult:
    """Complete result from pattern fix loop."""

    pattern_id: str
    total_tickets: int
    tickets_tested: int

    # Phase results
    baseline: Optional[PhaseResult] = None
    optimization: Optional[PhaseResult] = None
    answer_validation: Optional[PhaseResult] = None
    stability: Optional[PhaseResult] = None

    # Overall status
    success: bool = False
    branch_name: str = ""
    diagnostics_dir: Path = Path()

    # Timing
    start_time: str = ""
    end_time: str = ""
    duration_seconds: float = 0.0


class PatternFixAgent(OkpMcpAgent):
    """Fix loop agent for pattern-based ticket resolution."""

    def __init__(self, pattern_id: str, **kwargs):
        """Initialize pattern fix agent.

        Args:
            pattern_id: Pattern identifier
            **kwargs: Passed to OkpMcpAgent
        """
        super().__init__(**kwargs)
        self.pattern_id = pattern_id
        self.pattern_tickets = []
        self.branch_name = f"fix/pattern-{pattern_id.lower().replace('_', '-')}"

    def load_pattern_tickets(self, patterns_dir: Path) -> None:
        """Load tickets for this pattern from YAML.

        Args:
            patterns_dir: Directory containing pattern YAMLs
        """
        pattern_file = patterns_dir / f"{self.pattern_id}.yaml"

        if not pattern_file.exists():
            raise FileNotFoundError(f"Pattern file not found: {pattern_file}")

        print(f"Loading pattern tickets from: {pattern_file}")

        with open(pattern_file) as f:
            # Skip header comments
            content = f.read()
            lines = [line for line in content.split('\n') if not line.startswith('#')]
            yaml_content = '\n'.join(lines)
            conversations = yaml.safe_load(yaml_content)

        if not conversations:
            raise ValueError(f"No conversations found in {pattern_file}")

        # Extract ticket info
        for conv in conversations:
            ticket_id = conv['conversation_group_id']
            turn = conv['turns'][0]

            self.pattern_tickets.append({
                'ticket_id': ticket_id,
                'query': turn['query'],
                'expected_response': turn.get('expected_response', ''),
                'expected_urls': turn.get('expected_urls', []),
            })

        print(f"✅ Loaded {len(self.pattern_tickets)} tickets for pattern {self.pattern_id}")

    def create_pattern_branch(self) -> None:
        """Create git branch for this pattern's fixes."""
        import subprocess

        print(f"\n📌 Creating branch: {self.branch_name}")

        # Check if branch already exists
        result = subprocess.run(
            ["git", "branch", "--list", self.branch_name],
            cwd=self.okp_mcp_root,
            capture_output=True,
            text=True
        )

        if result.stdout.strip():
            print(f"⚠️  Branch already exists, switching to it")
            subprocess.run(
                ["git", "checkout", self.branch_name],
                cwd=self.okp_mcp_root,
                check=True
            )
        else:
            subprocess.run(
                ["git", "checkout", "-b", self.branch_name],
                cwd=self.okp_mcp_root,
                check=True
            )

        print(f"✅ On branch: {self.branch_name}")

    def run_fix_loop(
        self,
        max_iterations: int = 15,
        answer_threshold: float = 0.75,
        stability_runs: int = 3,
    ) -> PatternFixResult:
        """Run complete fix loop with all phases.

        Args:
            max_iterations: Max iterations for optimization phases
            answer_threshold: Minimum answer_correctness to pass
            stability_runs: Number of runs for stability check

        Returns:
            PatternFixResult with complete status
        """
        start_time = datetime.now()

        result = PatternFixResult(
            pattern_id=self.pattern_id,
            total_tickets=len(self.pattern_tickets),
            tickets_tested=0,
            start_time=start_time.isoformat(),
            diagnostics_dir=Path(f".diagnostics/{self.pattern_id}")
        )

        # Create branch
        self.create_pattern_branch()
        result.branch_name = self.branch_name

        print(f"\n{'='*80}")
        print(f"PATTERN FIX LOOP: {self.pattern_id}")
        print(f"{'='*80}")
        print(f"Tickets: {len(self.pattern_tickets)}")
        print(f"Branch: {self.branch_name}")
        print(f"Max iterations: {max_iterations}")
        print(f"Answer threshold: {answer_threshold}")
        print(f"Stability runs: {stability_runs}")
        print(f"{'='*80}\n")

        # Use first ticket as representative for optimization
        # (Later: could use multiple tickets or aggregate metrics)
        test_ticket = self.pattern_tickets[0]
        ticket_id = test_ticket['ticket_id']
        result.tickets_tested = 1

        print(f"📋 Testing with representative ticket: {ticket_id}\n")

        # PHASE 1: Initial Full Baseline
        print(f"\n{'='*80}")
        print("PHASE 1: INITIAL BASELINE")
        print(f"{'='*80}\n")

        baseline_result = self.run_baseline(ticket_id)
        result.baseline = baseline_result

        if not baseline_result.success:
            result.success = False
            result.end_time = datetime.now().isoformat()
            result.duration_seconds = (datetime.now() - start_time).total_seconds()
            return result

        # Check if already passing
        if self._is_passing(baseline_result.final_metrics, answer_threshold):
            print("✅ Already passing! Skipping optimization.")
            result.success = True
            result.end_time = datetime.now().isoformat()
            result.duration_seconds = (datetime.now() - start_time).total_seconds()
            return result

        # PHASE 2: Smart Routing - Optimization
        print(f"\n{'='*80}")
        print("PHASE 2: SMART OPTIMIZATION")
        print(f"{'='*80}\n")

        opt_result = self.run_optimization(
            ticket_id,
            baseline_result.final_metrics,
            max_iterations
        )
        result.optimization = opt_result

        if not opt_result.success:
            print("⚠️  Optimization did not improve metrics significantly")
            # Don't fail - continue to answer validation anyway

        # PHASE 3: Answer Correctness Validation
        print(f"\n{'='*80}")
        print("PHASE 3: ANSWER VALIDATION")
        print(f"{'='*80}\n")

        answer_result = self.run_answer_validation(ticket_id, answer_threshold)
        result.answer_validation = answer_result

        if not answer_result.success:
            result.success = False
            result.end_time = datetime.now().isoformat()
            result.duration_seconds = (datetime.now() - start_time).total_seconds()
            return result

        # PHASE 4: Stability Check
        print(f"\n{'='*80}")
        print("PHASE 4: STABILITY CHECK")
        print(f"{'='*80}\n")

        stability_result = self.run_stability_check(
            ticket_id, answer_threshold, stability_runs
        )
        result.stability = stability_result

        result.success = stability_result.success
        result.end_time = datetime.now().isoformat()
        result.duration_seconds = (datetime.now() - start_time).total_seconds()

        return result

    def run_baseline(self, ticket_id: str) -> PhaseResult:
        """Phase 1: Run full baseline evaluation.

        Args:
            ticket_id: Ticket to evaluate

        Returns:
            PhaseResult with baseline metrics
        """
        print("🔍 Running full baseline evaluation...")
        print("   Metrics: url_retrieval, context_relevance, context_precision,")
        print("           answer_correctness, faithfulness, response_relevancy")

        try:
            # Run full diagnosis with all metrics
            result = self.diagnose(ticket_id, use_existing=False)

            metrics = {
                'url_f1': result.url_f1 or 0.0,
                'mrr': result.mrr or 0.0,
                'context_relevance': result.context_relevance or 0.0,
                'context_precision': result.context_precision or 0.0,
                'answer_correctness': result.answer_correctness or 0.0,
                'faithfulness': result.faithfulness or 0.0,
                'response_relevancy': result.response_relevancy or 0.0,
            }

            print("\n📊 Baseline Metrics:")
            print(f"   URL F1:             {metrics['url_f1']:.2f}")
            print(f"   MRR:                {metrics['mrr']:.2f}")
            print(f"   Context Relevance:  {metrics['context_relevance']:.2f}")
            print(f"   Context Precision:  {metrics['context_precision']:.2f}")
            print(f"   Answer Correctness: {metrics['answer_correctness']:.2f}")
            print(f"   Faithfulness:       {metrics['faithfulness']:.2f}")
            print(f"   Response Relevancy: {metrics['response_relevancy']:.2f}")

            # Determine problem type
            is_retrieval = result.is_retrieval_problem
            is_answer = result.is_answer_problem

            print(f"\n🔍 Problem Analysis:")
            print(f"   Retrieval Problem: {is_retrieval}")
            print(f"   Answer Problem:    {is_answer}")

            return PhaseResult(
                phase_name="baseline",
                success=True,
                final_metrics=metrics,
                reason=f"retrieval_problem={is_retrieval}, answer_problem={is_answer}"
            )

        except Exception as e:
            print(f"❌ Baseline failed: {e}")
            return PhaseResult(
                phase_name="baseline",
                success=False,
                reason=str(e)
            )

    def run_optimization(
        self,
        ticket_id: str,
        baseline_metrics: Dict,
        max_iterations: int
    ) -> PhaseResult:
        """Phase 2: Smart routing optimization.

        Routes to appropriate optimization path based on problem type:
        - Retrieval problem → Fast retrieval optimization (Solr changes)
        - Answer problem → Prompt optimization (needs full evaluation)

        Args:
            ticket_id: Ticket to optimize
            baseline_metrics: Baseline metrics from Phase 1
            max_iterations: Max optimization iterations

        Returns:
            PhaseResult with optimization outcome
        """
        print("🎯 Analyzing problem type for smart routing...")

        # Determine problem type
        is_retrieval = self._is_retrieval_problem(baseline_metrics)
        is_answer = self._is_answer_problem(baseline_metrics)

        print(f"   Retrieval Problem: {is_retrieval}")
        print(f"   Answer Problem:    {is_answer}")

        if is_retrieval:
            # Route A: Fast retrieval optimization (Solr config changes)
            print("\n📍 Route A: RETRIEVAL OPTIMIZATION")
            print("   Testing: Solr config changes (qf, pf, mm, highlighting, etc.)")
            print("   Mode: Retrieval-only (no response generation)")
            print("   Speed: ~15-20 sec/iteration")
            return self.run_retrieval_optimization(
                ticket_id, baseline_metrics, max_iterations
            )
        elif is_answer:
            # Route B: Prompt optimization (system prompt changes)
            print("\n📍 Route B: PROMPT OPTIMIZATION")
            print("   Testing: System prompt changes (instructions, grounding, etc.)")
            print("   Mode: Full evaluation (WITH response generation)")
            print("   Speed: ~30-60 sec/iteration")
            return self.run_prompt_optimization(
                ticket_id, baseline_metrics, max_iterations
            )
        else:
            print("\n⚠️  No clear problem identified - trying retrieval optimization")
            return self.run_retrieval_optimization(
                ticket_id, baseline_metrics, max_iterations
            )

    def run_retrieval_optimization(
        self,
        ticket_id: str,
        baseline_metrics: Dict,
        max_iterations: int
    ) -> PhaseResult:
        """Route A: Fast retrieval optimization (Solr config changes).

        Uses retrieval-only mode - NO response generation needed.
        Tests: qf boosting, pf phrase matching, mm, highlighting, field weights.

        Args:
            ticket_id: Ticket to optimize
            baseline_metrics: Baseline metrics
            max_iterations: Max iterations

        Returns:
            PhaseResult with optimization outcome
        """
        print(f"   Max iterations: {max_iterations}")
        print(f"   Early exit: F1 > 0 (any expected docs found)\n")

        try:
            iteration = 0
            current_f1 = baseline_metrics.get('url_f1', 0.0)
            current_ctx_rel = baseline_metrics.get('context_relevance', 0.0)

            while iteration < max_iterations:
                iteration += 1
                print(f"\n--- Iteration {iteration}/{max_iterations} ---")

                # Use retrieval-only mode (faster, no LLM response generation)
                result = self.diagnose_retrieval_only(ticket_id, iteration=iteration)

                if result.url_f1 and result.url_f1 > current_f1:
                    print(f"✅ Improved! F1: {current_f1:.2f} → {result.url_f1:.2f}")
                    current_f1 = result.url_f1

                if result.context_relevance and result.context_relevance > current_ctx_rel:
                    print(f"✅ Improved! Context Rel: {current_ctx_rel:.2f} → {result.context_relevance:.2f}")
                    current_ctx_rel = result.context_relevance

                # Early exit if we found ANY expected docs
                # F1 can be "low" (e.g., 0.4) but still have all right docs
                # Example: 3 expected docs, 10 retrieved (with all 3) → F1=0.46
                # Don't keep optimizing - test answer instead!
                if current_f1 > 0.0:
                    print(f"\n🎯 Found expected docs! Exiting to test answer quality.")
                    print(f"   F1: {current_f1:.2f} (may be 'low' due to extra docs retrieved)")
                    print(f"   Context Relevance: {current_ctx_rel:.2f}")
                    print(f"   → Will test if answer is correct with these docs")
                    break

            final_metrics = {
                'url_f1': current_f1,
                'context_relevance': current_ctx_rel,
            }

            improved = current_f1 > baseline_metrics.get('url_f1', 0.0)

            return PhaseResult(
                phase_name="retrieval_optimization",
                success=improved,
                iterations=iteration,
                final_metrics=final_metrics,
                reason=f"F1: {baseline_metrics.get('url_f1', 0):.2f} → {current_f1:.2f}"
            )

        except Exception as e:
            print(f"❌ Retrieval optimization failed: {e}")
            return PhaseResult(
                phase_name="retrieval_optimization",
                success=False,
                iterations=iteration,
                reason=str(e)
            )

    def run_prompt_optimization(
        self,
        ticket_id: str,
        baseline_metrics: Dict,
        max_iterations: int
    ) -> PhaseResult:
        """Route B: Prompt optimization (system prompt changes).

        Uses FULL evaluation mode - response generation required.
        Tests: system prompt changes, grounding instructions, RAG usage.

        Args:
            ticket_id: Ticket to optimize
            baseline_metrics: Baseline metrics
            max_iterations: Max iterations

        Returns:
            PhaseResult with optimization outcome
        """
        print(f"   Max iterations: {max_iterations}")
        print(f"   Early exit: answer_correctness > 0.75\n")

        try:
            iteration = 0
            current_ans_corr = baseline_metrics.get('answer_correctness', 0.0)
            current_faithful = baseline_metrics.get('faithfulness', 0.0)

            while iteration < max_iterations:
                iteration += 1
                print(f"\n--- Iteration {iteration}/{max_iterations} ---")

                # MUST use full evaluation (need to see answer quality)
                result = self.diagnose(ticket_id, use_existing=False)

                if result.answer_correctness and result.answer_correctness > current_ans_corr:
                    print(f"✅ Improved! Answer: {current_ans_corr:.2f} → {result.answer_correctness:.2f}")
                    current_ans_corr = result.answer_correctness

                if result.faithfulness and result.faithfulness > current_faithful:
                    print(f"✅ Improved! Faithfulness: {current_faithful:.2f} → {result.faithfulness:.2f}")
                    current_faithful = result.faithfulness

                # Early exit if good enough
                if current_ans_corr > 0.75 and current_faithful > 0.8:
                    print(f"\n🎯 Good enough! Exiting optimization early.")
                    print(f"   Answer Correctness: {current_ans_corr:.2f}")
                    print(f"   Faithfulness: {current_faithful:.2f}")
                    break

            final_metrics = {
                'answer_correctness': current_ans_corr,
                'faithfulness': current_faithful,
            }

            improved = current_ans_corr > baseline_metrics.get('answer_correctness', 0.0)

            return PhaseResult(
                phase_name="prompt_optimization",
                success=improved,
                iterations=iteration,
                final_metrics=final_metrics,
                reason=f"Answer: {baseline_metrics.get('answer_correctness', 0):.2f} → {current_ans_corr:.2f}"
            )

        except Exception as e:
            print(f"❌ Prompt optimization failed: {e}")
            return PhaseResult(
                phase_name="prompt_optimization",
                success=False,
                iterations=iteration,
                reason=str(e)
            )

    def _is_retrieval_problem(self, metrics: Dict) -> bool:
        """Determine if this is a retrieval problem.

        Args:
            metrics: Baseline metrics

        Returns:
            True if retrieval needs optimization
        """
        url_f1 = metrics.get('url_f1', 0.0)
        ctx_rel = metrics.get('context_relevance', 0.0)
        ctx_prec = metrics.get('context_precision', 0.0)

        # Retrieval problem if any retrieval metric is low
        return (
            url_f1 < 0.5 or
            ctx_rel < 0.7 or
            ctx_prec < 0.7
        )

    def _is_answer_problem(self, metrics: Dict) -> bool:
        """Determine if this is an answer quality problem.

        Args:
            metrics: Baseline metrics

        Returns:
            True if answer quality needs optimization
        """
        url_f1 = metrics.get('url_f1', 0.0)
        ctx_rel = metrics.get('context_relevance', 0.0)
        ans_corr = metrics.get('answer_correctness', 0.0)
        faithful = metrics.get('faithfulness', 0.0)

        # Answer problem if retrieval is good but answer is bad
        retrieval_good = url_f1 >= 0.5 and ctx_rel >= 0.7
        answer_bad = ans_corr < 0.75 or faithful < 0.8

        return retrieval_good and answer_bad

    def run_answer_validation(
        self,
        ticket_id: str,
        threshold: float
    ) -> PhaseResult:
        """Phase 3: Validate answer correctness.

        Args:
            ticket_id: Ticket to validate
            threshold: Minimum answer_correctness score

        Returns:
            PhaseResult with answer validation outcome
        """
        print("📝 Validating answer correctness...")
        print(f"   Threshold: {threshold}")

        try:
            # Run full diagnosis with response generation
            result = self.diagnose(ticket_id, use_existing=False)

            answer_correct = result.answer_correctness or 0.0
            faithful = result.faithfulness or 0.0

            print(f"\n📊 Answer Metrics:")
            print(f"   Answer Correctness: {answer_correct:.2f}")
            print(f"   Faithfulness:       {faithful:.2f}")

            passing = answer_correct >= threshold and faithful >= 0.8

            if passing:
                print(f"✅ Answer validation PASSED")
            else:
                print(f"❌ Answer validation FAILED")
                if answer_correct < threshold:
                    print(f"   Answer correctness too low: {answer_correct:.2f} < {threshold}")
                if faithful < 0.8:
                    print(f"   Faithfulness too low: {faithful:.2f} < 0.8")

            return PhaseResult(
                phase_name="answer_validation",
                success=passing,
                iterations=1,
                final_metrics={
                    'answer_correctness': answer_correct,
                    'faithfulness': faithful,
                },
                reason=f"answer_correctness={answer_correct:.2f}, faithfulness={faithful:.2f}"
            )

        except Exception as e:
            print(f"❌ Answer validation failed: {e}")
            return PhaseResult(
                phase_name="answer_validation",
                success=False,
                reason=str(e)
            )

    def run_stability_check(
        self,
        ticket_id: str,
        threshold: float,
        num_runs: int
    ) -> PhaseResult:
        """Phase 4: Check answer stability across multiple runs.

        Args:
            ticket_id: Ticket to test
            threshold: Minimum answer_correctness per run
            num_runs: Number of stability runs

        Returns:
            PhaseResult with stability check outcome
        """
        print(f"🔄 Running stability check ({num_runs} runs)...")
        print(f"   Threshold: {threshold} per run")
        print(f"   Max variance: 0.05")

        try:
            runs = []

            for i in range(1, num_runs + 1):
                print(f"\n   Run {i}/{num_runs}...")
                result = self.diagnose(ticket_id, use_existing=False)

                answer_correct = result.answer_correctness or 0.0
                faithful = result.faithfulness or 0.0

                runs.append({
                    'run': i,
                    'answer_correctness': answer_correct,
                    'faithfulness': faithful,
                })

                print(f"      Answer: {answer_correct:.2f}, Faithfulness: {faithful:.2f}")

            # Calculate variance
            scores = [r['answer_correctness'] for r in runs]
            mean = sum(scores) / len(scores)
            variance = sum((s - mean) ** 2 for s in scores) / len(scores)

            # Check all pass
            all_pass = all(r['answer_correctness'] >= threshold for r in runs)
            low_variance = variance < 0.05

            print(f"\n📊 Stability Results:")
            print(f"   Mean:     {mean:.2f}")
            print(f"   Variance: {variance:.4f}")
            print(f"   All pass: {all_pass}")
            print(f"   Stable:   {low_variance}")

            stable = all_pass and low_variance

            if stable:
                print(f"✅ Stability check PASSED")
            else:
                print(f"❌ Stability check FAILED")
                if not all_pass:
                    failing = [r for r in runs if r['answer_correctness'] < threshold]
                    print(f"   {len(failing)} runs failed threshold")
                if not low_variance:
                    print(f"   High variance: {variance:.4f} >= 0.05")

            return PhaseResult(
                phase_name="stability",
                success=stable,
                iterations=num_runs,
                final_metrics={
                    'mean_answer_correctness': mean,
                    'variance': variance,
                    'runs': runs,
                },
                reason=f"mean={mean:.2f}, variance={variance:.4f}, all_pass={all_pass}"
            )

        except Exception as e:
            print(f"❌ Stability check failed: {e}")
            return PhaseResult(
                phase_name="stability",
                success=False,
                iterations=num_runs,
                reason=str(e)
            )

    def _is_passing(self, metrics: Dict, answer_threshold: float) -> bool:
        """Check if metrics indicate passing ticket.

        Args:
            metrics: Metric dictionary
            answer_threshold: Minimum answer_correctness

        Returns:
            True if passing
        """
        url_f1 = metrics.get('url_f1', 0.0)
        ctx_rel = metrics.get('context_relevance', 0.0)
        ans_corr = metrics.get('answer_correctness', 0.0)
        faith = metrics.get('faithfulness', 0.0)

        return (
            url_f1 >= 0.5 and
            ctx_rel >= 0.7 and
            ans_corr >= answer_threshold and
            faith >= 0.8
        )

    def generate_review_report(self, result: PatternFixResult) -> None:
        """Generate human review report.

        Args:
            result: Complete pattern fix result
        """
        report_path = result.diagnostics_dir / "REVIEW_REPORT.md"
        result.diagnostics_dir.mkdir(parents=True, exist_ok=True)

        status_emoji = "✅" if result.success else "❌"
        status_text = "SUCCESS" if result.success else "FAILED"

        duration_min = result.duration_seconds / 60

        report = f"""# Pattern Fix Review: {result.pattern_id}

## Summary
- **Status:** {status_emoji} {status_text}
- **Tickets Tested:** {result.tickets_tested}/{result.total_tickets}
- **Duration:** {duration_min:.1f} minutes
- **Branch:** {result.branch_name}

## Phase Results

### Phase 1: Baseline
"""

        if result.baseline:
            if result.baseline.success:
                report += f"✅ **SUCCESS**\n\n"
                report += f"Metrics:\n"
                for k, v in result.baseline.final_metrics.items():
                    report += f"- {k}: {v:.2f}\n"
                report += f"\nReason: {result.baseline.reason}\n"
            else:
                report += f"❌ **FAILED**\n\nReason: {result.baseline.reason}\n"
        else:
            report += "❌ Not run\n"

        report += f"\n### Phase 2: Optimization\n"

        if result.optimization:
            if result.optimization.success:
                report += f"✅ **SUCCESS** ({result.optimization.iterations} iterations)\n\n"
                report += f"Final Metrics:\n"
                for k, v in result.optimization.final_metrics.items():
                    report += f"- {k}: {v:.2f}\n"
                report += f"\nReason: {result.optimization.reason}\n"
            else:
                report += f"⚠️  **NO IMPROVEMENT** ({result.optimization.iterations} iterations)\n\n"
                report += f"Reason: {result.optimization.reason}\n"
        else:
            report += "❌ Not run\n"

        report += f"\n### Phase 3: Answer Validation\n"

        if result.answer_validation:
            if result.answer_validation.success:
                report += f"✅ **PASSED**\n\n"
                report += f"Metrics:\n"
                for k, v in result.answer_validation.final_metrics.items():
                    report += f"- {k}: {v:.2f}\n"
            else:
                report += f"❌ **FAILED**\n\nReason: {result.answer_validation.reason}\n"
        else:
            report += "❌ Not run\n"

        report += f"\n### Phase 4: Stability Check\n"

        if result.stability:
            if result.stability.success:
                report += f"✅ **STABLE** ({result.stability.iterations} runs)\n\n"
                report += f"Metrics:\n"
                report += f"- Mean: {result.stability.final_metrics.get('mean_answer_correctness', 0):.2f}\n"
                report += f"- Variance: {result.stability.final_metrics.get('variance', 0):.4f}\n"
            else:
                report += f"❌ **UNSTABLE**\n\nReason: {result.stability.reason}\n"
        else:
            report += "❌ Not run\n"

        report += f"""

## Artifacts
- **Branch:** `{result.branch_name}`
- **Diagnostics:** `.diagnostics/{result.pattern_id}/`
- **Git Log:** `git log {result.branch_name} --oneline`

## Next Steps

"""

        if result.success:
            report += f"""1. Review branch commits:
   ```bash
   git checkout {result.branch_name}
   git log --oneline
   ```

2. Review diagnostics:
   ```bash
   cat .diagnostics/{result.pattern_id}/iteration_summary.txt
   ```

3. Test manually (optional):
   ```bash
   uv run lightspeed-eval \\
       --config config/system_cla.yaml \\
       --data config/patterns_v2/{result.pattern_id}.yaml
   ```

4. Merge if satisfied:
   ```bash
   git checkout main
   git merge --squash {result.branch_name}
   git commit -m "fix: {result.pattern_id} - improved retrieval and answer quality"
   ```
"""
        else:
            report += f"""1. Review what failed:
   ```bash
   cat .diagnostics/{result.pattern_id}/iteration_summary.txt
   ```

2. Check diagnostics for insights:
   ```bash
   ls .diagnostics/{result.pattern_id}/
   ```

3. Possible issues:
   - Bad ground truth (check expected_response)
   - Insufficient documentation (docs don't exist)
   - Retrieval optimization limit (need different approach)
   - Unstable LLM responses (need prompt tuning)

4. Manual investigation recommended
"""

        with open(report_path, 'w') as f:
            f.write(report)

        print(f"\n📄 Review report generated: {report_path}")


def main():
    """Main entry point for POC."""
    parser = argparse.ArgumentParser(
        description="Pattern fix loop proof of concept"
    )

    parser.add_argument(
        'pattern_id',
        help='Pattern ID to fix (e.g., RHEL10_DEPRECATED_FEATURES)'
    )
    parser.add_argument(
        '--patterns-dir',
        type=Path,
        default=REPO_ROOT / "config" / "patterns_v2",
        help='Directory containing pattern YAMLs (default: config/patterns_v2)'
    )
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=10,
        help='Max optimization iterations (default: 10)'
    )
    parser.add_argument(
        '--answer-threshold',
        type=float,
        default=0.75,
        help='Minimum answer_correctness to pass (default: 0.75)'
    )
    parser.add_argument(
        '--stability-runs',
        type=int,
        default=3,
        help='Number of stability check runs (default: 3)'
    )

    args = parser.parse_args()

    # Initialize agent
    print(f"🚀 Pattern Fix Loop POC")
    print(f"{'='*80}\n")

    agent = PatternFixAgent(pattern_id=args.pattern_id)

    # Load pattern tickets
    try:
        agent.load_pattern_tickets(args.patterns_dir)
    except Exception as e:
        print(f"❌ Failed to load pattern: {e}")
        sys.exit(1)

    # Run fix loop
    try:
        result = agent.run_fix_loop(
            max_iterations=args.max_iterations,
            answer_threshold=args.answer_threshold,
            stability_runs=args.stability_runs,
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fix loop failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Generate review report
    try:
        agent.generate_review_report(result)
    except Exception as e:
        print(f"⚠️  Failed to generate review report: {e}")

    # Print final summary
    print(f"\n{'='*80}")
    print(f"PATTERN FIX LOOP COMPLETE")
    print(f"{'='*80}")
    print(f"Pattern: {result.pattern_id}")
    print(f"Status: {'✅ SUCCESS' if result.success else '❌ FAILED'}")
    print(f"Duration: {result.duration_seconds / 60:.1f} minutes")
    print(f"Branch: {result.branch_name}")
    print(f"Diagnostics: {result.diagnostics_dir}")
    print(f"{'='*80}\n")

    if result.success:
        print("✅ Pattern fix successful!")
        print(f"   Review: cat {result.diagnostics_dir}/REVIEW_REPORT.md")
        print(f"   Merge:  git merge --squash {result.branch_name}")
        sys.exit(0)
    else:
        print("❌ Pattern fix failed")
        print(f"   Review diagnostics: ls {result.diagnostics_dir}/")
        print(f"   Check report: cat {result.diagnostics_dir}/REVIEW_REPORT.md")
        sys.exit(1)


if __name__ == '__main__':
    main()

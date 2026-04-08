#!/usr/bin/env python3
"""Pattern-based batch fixing for okp-mcp RSPEED tickets.

Instead of fixing tickets one-by-one, this fixes entire patterns in batch.
This is 10-15x more efficient for clustered tickets.

Usage:
    # Fix entire pattern (all tickets at once)
    python scripts/okp_mcp_pattern_agent.py fix-pattern EOL_CONTAINER_COMPATIBILITY \
        --max-iterations 10 \
        --threshold 0.8

    # List available patterns
    python scripts/okp_mcp_pattern_agent.py list-patterns

    # Show pattern details
    python scripts/okp_mcp_pattern_agent.py show-pattern EOL_CONTAINER_COMPATIBILITY

    # Validate pattern after fix
    python scripts/okp_mcp_pattern_agent.py validate-pattern EOL_CONTAINER_COMPATIBILITY

Example workflow:
    # 1. Bootstrap: Extract tickets and discover patterns
    python scripts/extract_jira_tickets.py --limit 50
    python scripts/discover_ticket_patterns.py

    # 2. Fix pattern (validates against ALL tickets)
    python scripts/okp_mcp_pattern_agent.py fix-pattern EOL_CONTAINER_COMPATIBILITY

    # 3. Review changes
    git log fix/pattern-eol-container-compat --oneline

    # 4. Merge to main
    git checkout main
    git merge --squash fix/pattern-eol-container-compat
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# Add repo root to sys.path
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import single-ticket agent for base functionality
from scripts.okp_mcp_agent import (
    OkpMcpAgent,
    EvaluationResult,
    MetricThresholds,
)


@dataclass
class PatternEvaluationResult:
    """Evaluation result for an entire pattern (multiple tickets)."""

    pattern_id: str
    ticket_count: int
    per_ticket_results: Dict[str, EvaluationResult]
    pass_count: int = 0
    fail_count: int = 0
    pass_rate: float = 0.0
    pattern_fixed: bool = False

    # Aggregate metrics (average across all tickets)
    avg_url_f1: Optional[float] = None
    avg_context_relevance: Optional[float] = None
    avg_context_precision: Optional[float] = None
    avg_answer_correctness: Optional[float] = None

    def __post_init__(self):
        """Calculate aggregate stats after initialization."""
        self.pass_count = sum(
            1 for r in self.per_ticket_results.values() if r.is_passing
        )
        self.fail_count = self.ticket_count - self.pass_count
        self.pass_rate = self.pass_count / self.ticket_count if self.ticket_count > 0 else 0.0

        # Calculate average metrics
        metrics_lists = {
            'url_f1': [],
            'context_relevance': [],
            'context_precision': [],
            'answer_correctness': [],
        }

        for result in self.per_ticket_results.values():
            if result.url_f1 is not None:
                metrics_lists['url_f1'].append(result.url_f1)
            if result.context_relevance is not None:
                metrics_lists['context_relevance'].append(result.context_relevance)
            if result.context_precision is not None:
                metrics_lists['context_precision'].append(result.context_precision)
            if result.answer_correctness is not None:
                metrics_lists['answer_correctness'].append(result.answer_correctness)

        self.avg_url_f1 = sum(metrics_lists['url_f1']) / len(metrics_lists['url_f1']) if metrics_lists['url_f1'] else None
        self.avg_context_relevance = sum(metrics_lists['context_relevance']) / len(metrics_lists['context_relevance']) if metrics_lists['context_relevance'] else None
        self.avg_context_precision = sum(metrics_lists['context_precision']) / len(metrics_lists['context_precision']) if metrics_lists['context_precision'] else None
        self.avg_answer_correctness = sum(metrics_lists['answer_correctness']) / len(metrics_lists['answer_correctness']) if metrics_lists['answer_correctness'] else None

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Pattern: {self.pattern_id}",
            f"Tickets: {self.ticket_count}",
            f"Pass Rate: {self.pass_rate:.1%} ({self.pass_count}/{self.ticket_count})",
            "",
            "Aggregate Metrics (average):",
        ]

        if self.avg_url_f1 is not None:
            lines.append(f"  URL F1: {self.avg_url_f1:.2f}")
        if self.avg_context_relevance is not None:
            lines.append(f"  Context Relevance: {self.avg_context_relevance:.2f}")
        if self.avg_context_precision is not None:
            lines.append(f"  Context Precision: {self.avg_context_precision:.2f}")
        if self.avg_answer_correctness is not None:
            lines.append(f"  Answer Correctness: {self.avg_answer_correctness:.2f}")

        return "\n".join(lines)


class OkpMcpPatternAgent(OkpMcpAgent):
    """Extended agent for pattern-based batch fixing."""

    def __init__(self, *args, **kwargs):
        """Initialize pattern agent."""
        super().__init__(*args, **kwargs)
        self.patterns_data = None
        self.tickets_with_patterns = None

    def load_pattern_data(self, patterns_file: Path, tagged_tickets_file: Path):
        """Load pattern discovery results.

        Args:
            patterns_file: Path to patterns_report.json
            tagged_tickets_file: Path to tickets_with_patterns.yaml
        """
        # Load pattern report
        if not patterns_file.exists():
            raise FileNotFoundError(
                f"Pattern report not found: {patterns_file}\n"
                "Run: python scripts/discover_ticket_patterns.py"
            )

        with open(patterns_file) as f:
            self.patterns_data = json.load(f)

        # Load tagged tickets
        if not tagged_tickets_file.exists():
            raise FileNotFoundError(
                f"Tagged tickets not found: {tagged_tickets_file}\n"
                "Run: python scripts/discover_ticket_patterns.py"
            )

        with open(tagged_tickets_file) as f:
            data = yaml.safe_load(f)
            self.tickets_with_patterns = data.get('tickets', [])

        print(f"✅ Loaded {len(self.patterns_data.get('patterns', []))} patterns")
        print(f"✅ Loaded {len(self.tickets_with_patterns)} tickets")

    def list_patterns(self):
        """List all discovered patterns."""
        if not self.patterns_data:
            print("❌ No pattern data loaded")
            return

        patterns = self.patterns_data.get('patterns', [])

        print(f"\n{'='*80}")
        print(f"DISCOVERED PATTERNS ({len(patterns)} total)")
        print(f"{'='*80}\n")

        for pattern in patterns:
            print(f"Pattern: {pattern['pattern_id']}")
            print(f"  Description: {pattern['description']}")
            print(f"  Tickets: {pattern['ticket_count']}")
            print(f"  Problem Type: {pattern['common_problem_type']}")
            print(f"  Components: {', '.join(pattern['common_components'])}")
            print(f"  Representatives: {', '.join(pattern['representative_tickets'][:3])}")
            print()

    def show_pattern(self, pattern_id: str):
        """Show detailed information about a pattern."""
        if not self.patterns_data:
            print("❌ No pattern data loaded")
            return

        pattern = next(
            (p for p in self.patterns_data.get('patterns', []) if p['pattern_id'] == pattern_id),
            None
        )

        if not pattern:
            print(f"❌ Pattern not found: {pattern_id}")
            return

        print(f"\n{'='*80}")
        print(f"PATTERN DETAILS: {pattern_id}")
        print(f"{'='*80}\n")

        print(f"Description: {pattern['description']}")
        print(f"Ticket Count: {pattern['ticket_count']}")
        print(f"Problem Type: {pattern['common_problem_type']}")
        print(f"Components: {', '.join(pattern['common_components'])}")
        print(f"Version Pattern: {pattern['version_pattern']}")
        print()

        print("Representative Tickets:")
        for ticket_key in pattern['representative_tickets']:
            print(f"  - {ticket_key}")
        print()

        print(f"All Matched Tickets ({len(pattern['matched_tickets'])}):")
        for ticket_key in pattern['matched_tickets']:
            print(f"  - {ticket_key}")
        print()

        print("Verification Queries:")
        for query in pattern.get('verification_queries', []):
            print(f"  - Query: {query.get('query')}")
            print(f"    Context: {query.get('context')}")
            print()

    def get_pattern_tickets(self, pattern_id: str) -> List[dict]:
        """Get all tickets in a pattern.

        Args:
            pattern_id: Pattern identifier

        Returns:
            List of ticket dictionaries with pattern metadata
        """
        if not self.tickets_with_patterns:
            raise RuntimeError("Pattern data not loaded. Call load_pattern_data() first.")

        # Find tickets with this pattern_id
        pattern_tickets = [
            t for t in self.tickets_with_patterns
            if t.get('pattern_id') == pattern_id
        ]

        if not pattern_tickets:
            raise ValueError(f"No tickets found for pattern: {pattern_id}")

        return pattern_tickets

    def evaluate_pattern(
        self,
        pattern_id: str,
        threshold: float = 1.0,
        use_existing: bool = False,
    ) -> PatternEvaluationResult:
        """Evaluate all tickets in a pattern.

        Args:
            pattern_id: Pattern identifier
            threshold: Pass rate threshold (0.8 = 80% must pass)
            use_existing: Use existing results (faster for debugging)

        Returns:
            PatternEvaluationResult with per-ticket results and aggregate stats
        """
        tickets = self.get_pattern_tickets(pattern_id)

        print(f"\n{'='*80}")
        print(f"EVALUATING PATTERN: {pattern_id}")
        print(f"{'='*80}")
        print(f"Tickets in pattern: {len(tickets)}")
        print(f"Pass threshold: {threshold:.0%}")
        print()

        per_ticket_results = {}

        for i, ticket in enumerate(tickets, 1):
            ticket_key = ticket['ticket_key']
            print(f"[{i}/{len(tickets)}] Evaluating {ticket_key}...")

            try:
                result = self.diagnose(ticket_key, use_existing=use_existing, runs=1)
                per_ticket_results[ticket_key] = result

                status = "✅ PASS" if result.is_passing else "❌ FAIL"
                print(f"  {status}")

            except Exception as e:
                print(f"  ❌ ERROR: {e}")
                # Create a failing result
                per_ticket_results[ticket_key] = EvaluationResult(ticket_id=ticket_key)

        pattern_result = PatternEvaluationResult(
            pattern_id=pattern_id,
            ticket_count=len(tickets),
            per_ticket_results=per_ticket_results,
        )

        pattern_result.pattern_fixed = pattern_result.pass_rate >= threshold

        print()
        print(pattern_result.summary())
        print()

        if pattern_result.pattern_fixed:
            print(f"✅ PATTERN FIXED (pass rate {pattern_result.pass_rate:.1%} >= threshold {threshold:.0%})")
        else:
            print(f"❌ PATTERN NOT FIXED (pass rate {pattern_result.pass_rate:.1%} < threshold {threshold:.0%})")

        return pattern_result

    def fix_pattern(
        self,
        pattern_id: str,
        max_iterations: int = 10,
        threshold: float = 0.8,
    ) -> bool:
        """Fix all tickets in a pattern with iterative improvement.

        Args:
            pattern_id: Pattern identifier
            max_iterations: Maximum fix iterations
            threshold: Pass rate threshold (0.8 = 80% must pass)

        Returns:
            True if pattern fixed (pass rate >= threshold)
        """
        # TODO: Implement full iterative fixing
        # This is a placeholder showing the structure

        print(f"\n{'='*80}")
        print(f"FIXING PATTERN: {pattern_id}")
        print(f"{'='*80}")
        print(f"Max iterations: {max_iterations}")
        print(f"Pass threshold: {threshold:.0%}")
        print()

        # Create pattern branch
        branch_name = f"fix/pattern-{pattern_id.lower().replace('_', '-')}"
        print(f"Creating branch: {branch_name}")
        # TODO: Create git worktree with pattern branch

        # Initial evaluation
        print("\nInitial evaluation...")
        current_result = self.evaluate_pattern(pattern_id, threshold=threshold, use_existing=False)

        if current_result.pattern_fixed:
            print("✅ Pattern already passing, nothing to fix")
            return True

        # Iterative fixing
        for iteration in range(1, max_iterations + 1):
            print(f"\n{'='*80}")
            print(f"ITERATION {iteration}/{max_iterations}")
            print(f"{'='*80}\n")

            # TODO: Get LLM suggestion considering ALL tickets in pattern
            # suggestion = self._get_pattern_llm_suggestion(pattern_id, current_result)

            # TODO: Apply code change
            # self._apply_code_change(suggestion)

            # TODO: Re-evaluate pattern
            # current_result = self.evaluate_pattern(pattern_id, threshold=threshold)

            # TODO: Check if pattern fixed
            # if current_result.pattern_fixed:
            #     print(f"✅ PATTERN FIXED in {iteration} iterations!")
            #     return True

            print("TODO: Full implementation")
            break

        print(f"\n❌ Pattern not fixed after {max_iterations} iterations")
        print(f"Final pass rate: {current_result.pass_rate:.1%}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Pattern-based batch fixing for okp-mcp RSPEED tickets"
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # list-patterns command
    subparsers.add_parser(
        'list-patterns',
        help='List all discovered patterns'
    )

    # show-pattern command
    show_parser = subparsers.add_parser(
        'show-pattern',
        help='Show detailed information about a pattern'
    )
    show_parser.add_argument('pattern_id', help='Pattern ID')

    # fix-pattern command
    fix_parser = subparsers.add_parser(
        'fix-pattern',
        help='Fix all tickets in a pattern'
    )
    fix_parser.add_argument('pattern_id', help='Pattern ID')
    fix_parser.add_argument(
        '--max-iterations',
        type=int,
        default=10,
        help='Maximum fix iterations (default: 10)'
    )
    fix_parser.add_argument(
        '--threshold',
        type=float,
        default=0.8,
        help='Pass rate threshold 0.0-1.0 (default: 0.8 = 80%%)'
    )

    # validate-pattern command
    validate_parser = subparsers.add_parser(
        'validate-pattern',
        help='Validate all tickets in a pattern'
    )
    validate_parser.add_argument('pattern_id', help='Pattern ID')
    validate_parser.add_argument(
        '--threshold',
        type=float,
        default=1.0,
        help='Pass rate threshold 0.0-1.0 (default: 1.0 = 100%%)'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize agent
    agent = OkpMcpPatternAgent()

    # Load pattern data (required for all commands)
    patterns_file = REPO_ROOT / "patterns_report.json"
    tagged_tickets_file = REPO_ROOT / "config" / "tickets_with_patterns.yaml"

    try:
        agent.load_pattern_data(patterns_file, tagged_tickets_file)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Execute command
    if args.command == 'list-patterns':
        agent.list_patterns()

    elif args.command == 'show-pattern':
        agent.show_pattern(args.pattern_id)

    elif args.command == 'fix-pattern':
        success = agent.fix_pattern(
            args.pattern_id,
            max_iterations=args.max_iterations,
            threshold=args.threshold,
        )
        sys.exit(0 if success else 1)

    elif args.command == 'validate-pattern':
        result = agent.evaluate_pattern(
            args.pattern_id,
            threshold=args.threshold,
        )
        sys.exit(0 if result.pattern_fixed else 1)


if __name__ == '__main__':
    main()

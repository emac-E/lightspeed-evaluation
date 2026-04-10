#!/usr/bin/env python3
"""Test de-escalation logic for cost optimization.

Tests that the agent can de-escalate from expensive models to cheaper ones
when metrics are good and stable.
"""

import sys
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Mock EvaluationResult for testing
from dataclasses import dataclass
from typing import Optional


@dataclass
class MockEvaluationResult:
    """Mock evaluation result for testing de-escalation logic.

    This is a lightweight mock of the full EvaluationResult class from okp_mcp_agent.py,
    containing only the metrics needed for de-escalation decisions.

    De-escalation criteria:
        - url_f1 > 0.7: Good document retrieval
        - context_relevance > 0.7: Retrieved docs are relevant to query
        - answer_correctness > 0.8: Answer quality is high

    Usage:
        result = MockEvaluationResult(url_f1=0.8, context_relevance=0.9, answer_correctness=0.85)
        should_deescalate = agent.should_deescalate_model("complex", result, consecutive_successes=2)

    Attributes:
        url_f1: F1 score for expected URL retrieval (0.0-1.0), None if not available
        context_relevance: Ragas context_relevance score (0.0-1.0), None if not available
        answer_correctness: Custom answer correctness score (0.0-1.0), None if not available
    """

    url_f1: Optional[float] = None
    context_relevance: Optional[float] = None
    answer_correctness: Optional[float] = None


def test_deescalation_logic():
    """Test the de-escalation decision logic."""
    # Import the agent (this will work since we're in the right directory)
    from scripts.okp_mcp_agent import OkpMcpAgent

    # Create a minimal agent instance (don't need full initialization)
    agent = OkpMcpAgent.__new__(OkpMcpAgent)

    print("Testing De-escalation Logic")
    print("=" * 80)

    # Test 1: Not enough consecutive successes
    print("\n1. Testing: Not enough stability (1 success)")
    result = MockEvaluationResult(
        url_f1=0.8,
        context_relevance=0.8,
        answer_correctness=0.9
    )
    deescalate = agent.should_deescalate_model("complex", result, consecutive_successes=1)
    assert deescalate is None, "Should not de-escalate with only 1 success"
    print("   ✅ Correctly stays at complex (not enough stability)")

    # Test 2: Enough successes, good metrics → DE-ESCALATE
    print("\n2. Testing: Stable and good metrics (2 successes)")
    deescalate = agent.should_deescalate_model("complex", result, consecutive_successes=2)
    assert deescalate == "medium", "Should de-escalate from complex to medium"
    print("   ✅ Correctly de-escalates: complex → medium")

    # Test 3: Enough successes but metrics not good
    print("\n3. Testing: Stable but poor metrics (2 successes)")
    poor_result = MockEvaluationResult(
        url_f1=0.3,  # Too low
        context_relevance=0.5,  # Too low
        answer_correctness=0.6  # Too low
    )
    deescalate = agent.should_deescalate_model("complex", poor_result, consecutive_successes=2)
    assert deescalate is None, "Should not de-escalate with poor metrics"
    print("   ✅ Correctly stays at complex (metrics not good enough)")

    # Test 4: De-escalate from medium to simple
    print("\n4. Testing: De-escalate from medium to simple")
    deescalate = agent.should_deescalate_model("medium", result, consecutive_successes=2)
    assert deescalate == "simple", "Should de-escalate from medium to simple"
    print("   ✅ Correctly de-escalates: medium → simple")

    # Test 5: Already at cheapest model
    print("\n5. Testing: Already at cheapest model (simple)")
    deescalate = agent.should_deescalate_model("simple", result, consecutive_successes=2)
    assert deescalate is None, "Should not de-escalate from simple (already cheapest)"
    print("   ✅ Correctly stays at simple (already cheapest)")

    # Test 6: Edge case - borderline metrics
    print("\n6. Testing: Borderline metrics (exactly at threshold)")
    borderline_result = MockEvaluationResult(
        url_f1=0.7,  # Exactly at threshold
        context_relevance=0.7,  # Exactly at threshold
        answer_correctness=0.8  # Exactly at threshold
    )
    deescalate = agent.should_deescalate_model("complex", borderline_result, consecutive_successes=2)
    assert deescalate is None, "Should not de-escalate with borderline metrics (needs > not >=)"
    print("   ✅ Correctly stays at complex (metrics at threshold, not above)")

    # Test 7: Slightly above threshold
    print("\n7. Testing: Metrics slightly above threshold")
    good_result = MockEvaluationResult(
        url_f1=0.71,  # Slightly above
        context_relevance=0.71,  # Slightly above
        answer_correctness=0.81  # Slightly above
    )
    deescalate = agent.should_deescalate_model("complex", good_result, consecutive_successes=2)
    assert deescalate == "medium", "Should de-escalate when above threshold"
    print("   ✅ Correctly de-escalates: complex → medium")

    print("\n" + "=" * 80)
    print("All de-escalation tests passed! ✅")
    print("\nDe-escalation Summary:")
    print("- Requires 2+ consecutive successes")
    print("- Requires URL F1 > 0.7, context relevance > 0.7, answer correctness > 0.8")
    print("- De-escalates: complex → medium → simple")
    print("- Saves costs: Opus → Sonnet (10x cheaper), Sonnet → Haiku (2x cheaper)")
    print("=" * 80)


if __name__ == "__main__":
    test_deescalation_logic()

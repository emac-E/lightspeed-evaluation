"""Forbidden claims evaluation metric.

This metric verifies that known-incorrect claims do NOT appear in the response.
Used primarily for regression testing - ensuring that previously incorrect answers
don't resurface after code changes.

Scoring:
- Score = 1.0 if NO forbidden claims appear in the response
- Score = 0.0 if ANY forbidden claims appear in the response
- Partial scores: (total_claims - found_claims) / total_claims

Example usage in eval data:
    turns:
      - turn_id: 1
        query: "Can I run a RHEL 6 container on RHEL 9?"
        forbidden_claims:
          - "viable strategy"
          - "fully supported"
        turn_metrics:
          - custom:forbidden_claims_eval
"""

from typing import Optional

from lightspeed_evaluation.core.models import TurnData


def evaluate_forbidden_claims(
    _conv_data,
    _turn_idx: Optional[int],
    turn_data: Optional[TurnData],
    is_conversation: bool,
) -> tuple[Optional[float], str]:
    """Evaluate that forbidden claims do NOT appear in the response.

    This metric checks if known-incorrect phrases appear in the LLM response.
    Returns 1.0 if no forbidden claims found, 0.0 if any found.

    Args:
        _conv_data: Conversation data (unused)
        _turn_idx: Turn index (unused)
        turn_data: Turn data containing response and forbidden_claims
        is_conversation: Whether this is conversation-level evaluation

    Returns:
        tuple: (score: float, reason: str)
            - score: 1.0 (no forbidden claims) or 0.0 (forbidden claims found)
            - reason: Details about which claims were found or not found
    """
    # Validate inputs
    if is_conversation:
        return None, "Forbidden claims eval is a turn-level metric"

    if turn_data is None:
        return None, "TurnData is required for forbidden claims evaluation"

    if not turn_data.forbidden_claims:
        return (
            None,
            "No forbidden claims provided for forbidden claims evaluation",
        )

    if not turn_data.response:
        return (
            None,
            "No response provided for forbidden claims evaluation",
        )

    response_lower = turn_data.response.lower()

    # Check for forbidden claims (case-insensitive)
    found_claims = []
    for claim in turn_data.forbidden_claims:
        if claim.lower() in response_lower:
            found_claims.append(claim)

    # Calculate score
    total_claims = len(turn_data.forbidden_claims)
    if found_claims:
        # Partial scoring: percentage of forbidden claims successfully avoided
        score = (total_claims - len(found_claims)) / total_claims
    else:
        score = 1.0

    # Build reason
    if found_claims:
        found_str = ", ".join(f"'{claim}'" for claim in found_claims[:3])
        if len(found_claims) > 3:
            found_str += f" ... ({len(found_claims)} total)"

        reason = (
            f"Forbidden claims found: {found_str}. "
            f"Score: {score:.2f} ({total_claims - len(found_claims)}/{total_claims} avoided)"
        )
    else:
        reason = (
            f"No forbidden claims found. "
            f"All {total_claims} known-incorrect phrases avoided."
        )

    return score, reason

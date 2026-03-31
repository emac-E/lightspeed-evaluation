"""URL retrieval evaluation utilities.

This metric evaluates how well the RAG system retrieved expected documentation URLs.
It compares URLs retrieved via tool calls against a list of expected URLs.

Scoring:
- Precision: What % of retrieved URLs are in the expected set?
- Recall: What % of expected URLs were retrieved?
- F1 Score: Harmonic mean of precision and recall (returned as main score)
"""

from typing import Any, Optional
from urllib.parse import urlparse

from lightspeed_evaluation.core.models import TurnData


def normalize_url(url: str) -> str:
    """Normalize URL for comparison by removing protocol, trailing slashes, etc.

    Args:
        url: Raw URL string

    Returns:
        Normalized URL for comparison
    """
    if not url:
        return ""

    # Parse URL
    parsed = urlparse(url.strip())

    # Reconstruct without protocol, trailing slash, fragments, or query params
    # Keep: domain + path
    normalized = parsed.netloc + parsed.path.rstrip('/')

    return normalized.lower()


def extract_urls_from_tool_calls(tool_calls: Optional[list[list[dict[str, Any]]]]) -> list[str]:
    """Extract all URLs from tool call results.

    Looks for:
    - tool_calls[i][j]['result']['contexts'][k]['url']
    - URLs in text responses that match access.redhat.com pattern

    Args:
        tool_calls: Nested list of tool call dictionaries

    Returns:
        List of normalized URLs found in tool calls
    """
    if not tool_calls:
        return []

    urls = set()

    for turn_calls in tool_calls:
        if not turn_calls:
            continue

        for call in turn_calls:
            if not isinstance(call, dict):
                continue

            # Check for contexts in result
            result = call.get('result')
            if isinstance(result, dict) and 'contexts' in result:
                contexts = result['contexts']
                if isinstance(contexts, list):
                    for ctx in contexts:
                        if isinstance(ctx, dict) and 'url' in ctx:
                            url = ctx['url']
                            if url and isinstance(url, str):
                                urls.add(normalize_url(url))

    return list(urls)


def calculate_url_metrics(
    retrieved_urls: list[str], expected_urls: list[str]
) -> tuple[float, float, float, list[str], list[str], list[str]]:
    """Calculate precision, recall, and F1 for URL retrieval.

    Args:
        retrieved_urls: List of normalized URLs that were retrieved
        expected_urls: List of normalized URLs that should have been retrieved

    Returns:
        Tuple of (precision, recall, f1, matched, missing, extra):
        - precision: % of retrieved URLs that are expected
        - recall: % of expected URLs that were retrieved
        - f1: Harmonic mean of precision and recall
        - matched: List of expected URLs that were found
        - missing: List of expected URLs that were NOT found
        - extra: List of retrieved URLs that were NOT expected
    """
    if not expected_urls:
        return 0.0, 0.0, 0.0, [], [], list(retrieved_urls)

    if not retrieved_urls:
        return 0.0, 0.0, 0.0, [], list(expected_urls), []

    # Normalize all URLs
    expected_set = {normalize_url(url) for url in expected_urls}
    retrieved_set = {normalize_url(url) for url in retrieved_urls}

    # Calculate matches
    matched = list(expected_set & retrieved_set)
    missing = list(expected_set - retrieved_set)
    extra = list(retrieved_set - expected_set)

    # Calculate metrics
    precision = len(matched) / len(retrieved_set) if retrieved_set else 0.0
    recall = len(matched) / len(expected_set) if expected_set else 0.0
    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return precision, recall, f1, matched, missing, extra


def evaluate_url_retrieval(
    _conv_data: Any,
    _turn_idx: Optional[int],
    turn_data: Optional[TurnData],
    is_conversation: bool,
) -> tuple[Optional[float], str]:
    """Evaluate URL retrieval quality using precision, recall, and F1 score.

    This metric checks if the RAG system retrieved the expected documentation URLs.
    Returns F1 score as the main metric (0.0 to 1.0).

    Args:
        _conv_data: Conversation data (unused)
        _turn_idx: Turn index (unused)
        turn_data: Turn data containing tool_calls and expected_urls
        is_conversation: Whether this is conversation-level evaluation

    Returns:
        tuple: (score: float, reason: str)
            - score: F1 score (0.0 to 1.0), or None if not applicable
            - reason: Detailed breakdown including precision, recall, and URL lists
    """
    # Validate inputs
    if is_conversation:
        return None, "URL retrieval eval is a turn-level metric"

    if turn_data is None:
        return None, "TurnData is required for URL retrieval evaluation"

    if not turn_data.expected_urls:
        return None, "No expected URLs provided for URL retrieval evaluation"

    if not turn_data.tool_calls:
        # No tool calls means no URLs retrieved
        missing_urls = ", ".join(f"'{url}'" for url in turn_data.expected_urls[:3])
        if len(turn_data.expected_urls) > 3:
            missing_urls += f", ... ({len(turn_data.expected_urls)} total)"

        reason = (
            f"URL retrieval failed: No tool calls executed. "
            f"Expected {len(turn_data.expected_urls)} URLs: {missing_urls}"
        )
        return 0.0, reason

    # Extract URLs from tool calls
    retrieved_urls = extract_urls_from_tool_calls(turn_data.tool_calls)

    # Calculate metrics
    precision, recall, f1, matched, missing, extra = calculate_url_metrics(
        retrieved_urls, turn_data.expected_urls
    )

    # Build detailed reason
    reason_parts = [
        f"URL retrieval: F1={f1:.2f}, Precision={precision:.2f}, Recall={recall:.2f}"
    ]

    if matched:
        matched_str = ", ".join(f"'{url}'" for url in matched[:2])
        if len(matched) > 2:
            matched_str += f" ... ({len(matched)} total)"
        reason_parts.append(f"Matched {len(matched)}/{len(turn_data.expected_urls)}: {matched_str}")

    if missing:
        missing_str = ", ".join(f"'{url}'" for url in missing[:2])
        if len(missing) > 2:
            missing_str += f" ... ({len(missing)} total)"
        reason_parts.append(f"Missing {len(missing)}: {missing_str}")

    if extra:
        extra_str = ", ".join(f"'{url}'" for url in extra[:2])
        if len(extra) > 2:
            extra_str += f" ... ({len(extra)} total)"
        reason_parts.append(f"Extra {len(extra)} unexpected: {extra_str}")

    reason = ". ".join(reason_parts)

    return f1, reason

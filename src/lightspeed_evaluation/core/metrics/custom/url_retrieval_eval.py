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
    """Normalize URL for comparison by extracting document identifier.

    Handles both full URLs and short-form paths from okp-mcp:
    - https://access.redhat.com/solutions/1136173/index.html → solutions/1136173
    - solutions/1136173 → solutions/1136173
    - documentation/en-us/red_hat.../index → documentation/en-us/red_hat...

    Args:
        url: Raw URL string (full URL or short-form path)

    Returns:
        Normalized document identifier for comparison
    """
    if not url:
        return ""

    # Parse URL
    url_stripped = url.strip()
    parsed = urlparse(url_stripped)

    # Extract path (works for both full URLs and short-form paths)
    path = parsed.path if parsed.path else url_stripped

    # Remove common suffixes
    path = path.rstrip("/")
    if path.endswith("/index.html"):
        path = path[:-11]  # Remove /index.html
    elif path.endswith("/index"):
        path = path[:-6]  # Remove /index

    # Remove leading slash if present
    path = path.lstrip("/")

    return path.lower()


def extract_urls_from_contexts(contexts: list[str]) -> list[str]:
    """Extract URLs from contexts field (okp-mcp format).

    The contexts field contains formatted text like:
    "**Title**\\nType: Article | Applicability: RHEL\\nURL: https://access.redhat.com/solutions/123\\nContent: ..."

    Args:
        contexts: List of context strings from turn_data.contexts

    Returns:
        List of normalized URLs extracted from contexts (in order)
    """
    import re

    urls = []

    # Pattern matches: "URL: https://access.redhat.com/..."
    # Captures until whitespace or newline
    url_pattern = r'URL:\s*(https://[^\s\n]+)'

    for context in contexts:
        if not isinstance(context, str):
            continue

        matches = re.findall(url_pattern, context)
        for url in matches:
            # Clean up trailing punctuation/markup
            url = url.rstrip('\\nContent:').rstrip()
            normalized = normalize_url(url)
            if normalized:
                urls.append(normalized)

    return urls


def extract_urls_from_tool_calls(
    tool_calls: Optional[list[list[dict[str, Any]]]], preserve_order: bool = False
) -> list[str]:
    """Extract all URLs from tool call results.

    Looks for:
    - tool_calls[i][j]['result']['contexts'][k]['url']
    - URLs in text responses that match access.redhat.com pattern

    Args:
        tool_calls: Nested list of tool call dictionaries
        preserve_order: If True, preserve ranking order and allow duplicates.
                       If False, return unique URLs (legacy behavior)

    Returns:
        List of normalized URLs found in tool calls
        If preserve_order=True, maintains retrieval order (may have duplicates)
        If preserve_order=False, returns unique set as list
    """
    if not tool_calls:
        return []

    if preserve_order:
        # Preserve order, track positions
        urls_ordered = []
    else:
        # Legacy behavior: unique set
        urls = set()

    for turn_calls in tool_calls:
        if not turn_calls:
            continue

        for call in turn_calls:
            if not isinstance(call, dict):
                continue

            # Check for contexts in result
            result = call.get("result")
            if isinstance(result, dict) and "contexts" in result:
                contexts = result["contexts"]
                if isinstance(contexts, list):
                    for ctx in contexts:
                        if isinstance(ctx, dict) and "url" in ctx:
                            url = ctx["url"]
                            if url and isinstance(url, str):
                                normalized = normalize_url(url)
                                if preserve_order:
                                    urls_ordered.append(normalized)
                                else:
                                    urls.add(normalized)

    return urls_ordered if preserve_order else list(urls)


def get_url_rankings(
    retrieved_urls_ordered: list[str], expected_urls: list[str]
) -> dict[str, Optional[int]]:
    """Get ranking positions of expected URLs in retrieved results.

    Args:
        retrieved_urls_ordered: Ordered list of retrieved URLs (preserves ranking)
        expected_urls: List of expected URLs to look for

    Returns:
        Dict mapping expected_url -> position (1-indexed) or None if not found
    """
    rankings = {}

    # Build position map (first occurrence of each URL)
    url_positions = {}
    for i, url in enumerate(retrieved_urls_ordered, 1):
        normalized = normalize_url(url)
        if normalized not in url_positions:
            url_positions[normalized] = i

    # Map expected URLs to their positions
    for expected_url in expected_urls:
        normalized = normalize_url(expected_url)
        rankings[normalized] = url_positions.get(normalized)

    return rankings


def calculate_ranking_metrics(rankings: dict[str, Optional[int]]) -> dict[str, float]:
    """Calculate ranking quality metrics.

    Args:
        rankings: Dict mapping expected_url -> position (or None if not found)

    Returns:
        Dict with ranking metrics:
        - mrr: Mean Reciprocal Rank (1/position, higher is better)
        - avg_position: Average position of found URLs (lower is better)
        - found_in_top_3: Percentage found in top 3
        - found_in_top_5: Percentage found in top 5
    """
    positions = [pos for pos in rankings.values() if pos is not None]
    total = len(rankings)

    if not positions:
        return {
            "mrr": 0.0,
            "avg_position": 0.0,
            "found_in_top_3": 0.0,
            "found_in_top_5": 0.0,
        }

    # Mean Reciprocal Rank
    mrr = sum(1.0 / pos for pos in positions) / total

    # Average position (for found URLs only)
    avg_position = sum(positions) / len(positions)

    # Top-K metrics
    found_in_top_3 = sum(1 for pos in positions if pos <= 3) / total
    found_in_top_5 = sum(1 for pos in positions if pos <= 5) / total

    return {
        "mrr": mrr,
        "avg_position": avg_position,
        "found_in_top_3": found_in_top_3,
        "found_in_top_5": found_in_top_5,
    }


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

    # Extract URLs from tool calls (preserve order for ranking)
    retrieved_urls_ordered = extract_urls_from_tool_calls(
        turn_data.tool_calls, preserve_order=True
    )

    # FALLBACK: If no URLs in tool_calls, try extracting from contexts field
    # This handles okp-mcp format where contexts are separate from tool_calls
    if not retrieved_urls_ordered and turn_data.contexts:
        retrieved_urls_ordered = extract_urls_from_contexts(turn_data.contexts)

    retrieved_urls_unique = list(
        dict.fromkeys(retrieved_urls_ordered)
    )  # Dedupe while preserving order

    # Calculate metrics
    precision, recall, f1, matched, missing, extra = calculate_url_metrics(
        retrieved_urls_unique, turn_data.expected_urls
    )

    # Calculate ranking metrics for expected URLs
    rankings = get_url_rankings(retrieved_urls_ordered, turn_data.expected_urls)
    ranking_metrics = calculate_ranking_metrics(rankings)

    # Build detailed reason
    reason_parts = [
        f"URL retrieval: F1={f1:.2f}, Precision={precision:.2f}, Recall={recall:.2f}"
    ]

    # Add ranking summary
    if any(pos is not None for pos in rankings.values()):
        reason_parts.append(
            f"Ranking: MRR={ranking_metrics['mrr']:.3f}, "
            f"Avg_Pos={ranking_metrics['avg_position']:.1f}, "
            f"Top3={ranking_metrics['found_in_top_3']:.0%}, "
            f"Top5={ranking_metrics['found_in_top_5']:.0%}"
        )

    if matched:
        # Show matched URLs with their positions
        matched_with_pos = []
        for url in matched[:3]:
            pos = rankings.get(normalize_url(url))
            pos_str = f"#{pos}" if pos else "not found"
            matched_with_pos.append(f"'{url}' ({pos_str})")
        matched_str = ", ".join(matched_with_pos)
        if len(matched) > 3:
            matched_str += f" ... ({len(matched)} total)"
        reason_parts.append(
            f"Matched {len(matched)}/{len(turn_data.expected_urls)}: {matched_str}"
        )

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

"""URL Validation Agent - validates retrieved URLs against expected URLs.

This agent provides feedback for iterative query refinement by:
- Comparing retrieved URLs to expected URLs
- Calculating precision, recall, and F1 score
- Identifying specific issues (missing URLs, irrelevant URLs, ranking problems)
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class URLValidationAgent:
    """URL Validation agent for feedback loops.

    Compares retrieved URLs from Solr to expected URLs and provides:
    - Score (0.0-1.0) based on URL F1
    - List of specific issues for refinement
    """

    def validate_urls(
        self,
        query: str,
        retrieved_urls: List[str],
        expected_urls: List[str]
    ) -> Dict[str, Any]:
        """
        Validate retrieved URLs against expected URLs.

        Args:
            query: Original query (for context in issues)
            retrieved_urls: URLs retrieved by agent
            expected_urls: Expected URLs from test data

        Returns:
            Dictionary with:
            - score (float): URL F1 score (0.0-1.0)
            - precision (float): Precision score
            - recall (float): Recall score
            - issues (List[str]): Specific problems identified
            - retrieved_count (int): Number of URLs retrieved
            - expected_count (int): Number of expected URLs
        """
        logger.info(
            f"URLValidationAgent: Validating {len(retrieved_urls)} retrieved "
            f"vs {len(expected_urls)} expected URLs"
        )

        # Normalize URLs (strip trailing slashes, /index.html suffix, lowercase)
        def normalize_url(url: str) -> str:
            normalized = url.rstrip("/").lower()
            # Remove /index.html suffix if present
            if normalized.endswith("/index.html"):
                normalized = normalized[:-11]  # len("/index.html") = 11
            return normalized

        retrieved_set = {normalize_url(url) for url in retrieved_urls if url}
        expected_set = {normalize_url(url) for url in expected_urls if url}

        # Calculate metrics
        if not expected_set:
            # No expected URLs - can't validate
            return {
                "score": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "issues": ["No expected URLs provided for validation"],
                "retrieved_count": len(retrieved_urls),
                "expected_count": 0
            }

        # True positives: URLs in both sets
        true_positives = retrieved_set & expected_set

        # False positives: Retrieved but not expected
        false_positives = retrieved_set - expected_set

        # False negatives: Expected but not retrieved
        false_negatives = expected_set - retrieved_set

        # Calculate precision, recall, F1
        precision = len(true_positives) / len(retrieved_set) if retrieved_set else 0.0
        recall = len(true_positives) / len(expected_set) if expected_set else 0.0
        f1_score = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        # Identify issues
        issues = []

        if recall < 0.5:
            missing_count = len(false_negatives)
            issues.append(
                f"Low recall ({recall:.2f}): Missing {missing_count}/{len(expected_set)} expected URLs"
            )

        if precision < 0.5 and false_positives:
            issues.append(
                f"Low precision ({precision:.2f}): Retrieved {len(false_positives)} irrelevant URLs"
            )

        if not true_positives:
            issues.append("No expected URLs found in retrieved results")

        if retrieved_urls and expected_urls:
            # Check ranking: Are expected URLs in top positions?
            top_5_retrieved = {
                normalize_url(url) for url in retrieved_urls[:5] if url
            }
            top_5_matches = top_5_retrieved & expected_set

            if len(top_5_matches) < min(5, len(expected_set)):
                issues.append(
                    f"Ranking issue: Only {len(top_5_matches)} expected URLs in top 5 results"
                )

        if not issues:
            issues.append("Validation passed")

        result = {
            "score": f1_score,
            "precision": precision,
            "recall": recall,
            "f1": f1_score,
            "issues": issues,
            "retrieved_count": len(retrieved_urls),
            "expected_count": len(expected_urls),
            "true_positives": len(true_positives),
            "false_positives": len(false_positives),
            "false_negatives": len(false_negatives)
        }

        logger.info(
            f"URLValidationAgent: Score={f1_score:.3f}, "
            f"Precision={precision:.3f}, Recall={recall:.3f}"
        )

        return result

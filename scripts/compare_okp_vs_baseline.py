#!/usr/bin/env python3
"""
Compare okp-mcp retrieval with baseline Simple and RAG agents using feedback loops.

This script compares three retrieval approaches:
1. Simple Solr agent + feedback loop (iterative improvement based on URL validation)
2. RAG Solr agent + feedback loop (iterative improvement based on URL validation)
3. okp-mcp (cached results, no feedback loop due to cache limitations)

For each query in the specified pattern, the script:
- Runs Simple agent search, gets URL validation score, refines query if needed (max 3 iterations)
- Runs RAG agent search with same feedback loop
- Loads okp-mcp cached results
- Compares final scores and iteration counts

The goal is to see if feedback-based iterative refinement helps Simple and RAG agents
outperform okp-mcp, and to understand the iteration patterns.
"""

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from okp_mcp_agent.agents.simple_solr_agent import SimpleSolrAgent
from okp_mcp_agent.agents.rag_solr_agent import RAGSolrAgent
from okp_mcp_agent.agents.url_validation_agent import URLValidationAgent
from okp_mcp_agent.agents.content_relevance_agent import ContentRelevanceAgent

import httpx


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class FeedbackSearchResult:
    """Result of search with feedback loop."""

    query: str
    approach: str  # "simple", "rag", "okp-mcp"
    iterations: int
    final_score: float  # URL F1 score
    final_urls: List[str]
    final_content_relevance: float = 0.0  # Content-based relevance score
    iteration_history: List[Dict] = field(default_factory=list)
    # Each iteration: {"iteration": int, "score": float, "urls": List[str], "issues": List[str], "adjustment": str, "content_relevance": float}
    tokens_used: int = 0
    success: bool = False  # True if score >= threshold

    def add_iteration(self, iteration: int, score: float, urls: List[str],
                     issues: List[str], adjustment: str = "", content_relevance: float = 0.0):
        """Add an iteration to the history."""
        self.iteration_history.append({
            "iteration": iteration,
            "score": score,
            "urls": urls,
            "issues": issues,
            "adjustment": adjustment,
            "content_relevance": content_relevance
        })


# ============================================================================
# FEEDBACK LOOP IMPLEMENTATION
# ============================================================================

def search_with_feedback(
    query: str,
    expected_urls: List[str],
    agent,
    agent_type: str,  # "simple" or "rag"
    max_iterations: int = 3,
    success_threshold: float = 0.7,
) -> FeedbackSearchResult:
    """
    Search with iterative feedback loop.

    Args:
        query: User query
        expected_urls: Expected URLs for validation
        agent: SimpleSolrAgent or RAGSolrAgent instance
        agent_type: "simple" or "rag"
        max_iterations: Maximum refinement attempts
        success_threshold: Score to consider successful

    Returns:
        FeedbackSearchResult with iteration history
    """
    result = FeedbackSearchResult(
        query=query,
        approach=agent_type,
        iterations=0,
        final_score=0.0,
        final_urls=[]
    )

    validator = URLValidationAgent()
    content_evaluator = ContentRelevanceAgent()
    current_query = query
    current_rows = 10  # Default for RAG agent

    for iteration in range(1, max_iterations + 1):
        result.iterations = iteration

        # Execute search
        if agent_type == "simple":
            search_results = agent.search(current_query)
        else:  # rag
            search_results = agent.search_with_rag(current_query, rows=current_rows)

        # Extract URLs from search results
        # Solr stores URLs in the "id" field which contains the resource path
        retrieved_urls = []
        for doc in search_results:
            # id field contains path like "/articles/123/index.html"
            # We need to prepend the base URL
            doc_id = doc.get("id", "")
            if doc_id:
                # Convert to full URL
                full_url = f"https://access.redhat.com{doc_id}"
                retrieved_urls.append(full_url)

        # Validate URLs (exact matching)
        validation_result = validator.validate_urls(
            query=current_query,
            retrieved_urls=retrieved_urls,
            expected_urls=expected_urls
        )

        score = validation_result.get("score", 0.0)
        issues = validation_result.get("issues", [])

        # Evaluate content relevance (semantic matching)
        content_result = content_evaluator.evaluate_relevance(
            query=current_query,
            retrieved_docs=search_results,
            top_k=5
        )
        content_relevance = content_result.get("avg_relevance", 0.0)

        # Record iteration
        adjustment = ""
        result.add_iteration(iteration, score, retrieved_urls, issues, adjustment, content_relevance)

        # Check success
        if score >= success_threshold:
            result.final_score = score
            result.final_urls = retrieved_urls
            result.final_content_relevance = content_relevance
            result.success = True
            break

        # Last iteration - no point refining
        if iteration == max_iterations:
            result.final_score = score
            result.final_urls = retrieved_urls
            result.final_content_relevance = content_relevance
            result.success = False
            break

        # Refine query for next iteration
        refined_query, adjustment, new_rows = _refine_query(
            original_query=query,
            current_query=current_query,
            issues=issues,
            agent_type=agent_type,
            iteration=iteration,
            current_rows=current_rows
        )

        # Update adjustment in history
        result.iteration_history[-1]["adjustment"] = adjustment
        current_query = refined_query
        current_rows = new_rows

    return result


def _refine_query(
    original_query: str,
    current_query: str,
    issues: List[str],
    agent_type: str,
    iteration: int,
    current_rows: int = 10
) -> Tuple[str, str, int]:
    """
    Refine query based on validation issues.

    Args:
        original_query: Original user query
        current_query: Current query (may have been refined)
        issues: List of validation issues
        agent_type: "simple" or "rag"
        iteration: Current iteration number
        current_rows: Current number of rows to retrieve

    Returns:
        Tuple of (refined_query, adjustment_description, rows)
    """
    # Simple strategy: field-specific searches
    if agent_type == "simple":
        if iteration == 1:
            # Try boosting title field (use correct Solr field names)
            return (
                f"title:({original_query})^2.0 OR content:({original_query}) OR main_content:({original_query})^1.5",
                "Boosted title and main_content fields",
                current_rows
            )
        elif iteration == 2:
            # Try exact phrase
            return (
                f'"{original_query}"',
                "Used exact phrase match",
                current_rows
            )
        else:
            return (current_query, "No further refinement", current_rows)

    # RAG strategy: parameter adjustments
    else:  # rag
        if iteration == 1:
            # Increase result count for RAG to have more candidates
            return (
                original_query,
                "Increased result count to 15",
                15
            )
        elif iteration == 2:
            # Try with different parameters - RAG agent doesn't support mm in query string
            # Instead, just retrieve more documents
            return (
                original_query,
                "Increased result count to 20",
                20
            )
        else:
            return (current_query, "No further refinement", current_rows)


def load_okp_mcp_cached_results(
    query: str,
    expected_urls: List[str],
    cache_dir: Path
) -> FeedbackSearchResult:
    """
    Load okp-mcp cached results for comparison.

    Note: okp-mcp cache is limited to 3 queries, so this only works for BOOTLOADER pattern.

    Args:
        query: User query
        expected_urls: Expected URLs for validation
        cache_dir: Directory containing okp-mcp cached results

    Returns:
        FeedbackSearchResult with cached data
    """
    result = FeedbackSearchResult(
        query=query,
        approach="okp-mcp",
        iterations=1,  # Cached, so only 1 "iteration"
        final_score=0.0,
        final_urls=[]
    )

    # TODO: Load from cache file
    # For now, placeholder implementation
    result.add_iteration(
        iteration=1,
        score=0.0,
        urls=[],
        issues=["Cache not implemented yet"],
        adjustment="N/A (cached)"
    )
    result.final_score = 0.0
    result.final_urls = []
    result.success = False

    return result


# ============================================================================
# GROUND TRUTH VERIFICATION
# ============================================================================

def verify_ground_truth(
    expected_urls: List[str],
    solr_url: str = "http://localhost:8983/solr",
    collection: str = "portal"
) -> Dict[str, Any]:
    """
    Verify if expected URLs actually exist in Solr index.

    Args:
        expected_urls: List of expected URLs from pattern
        solr_url: Solr server URL
        collection: Solr collection name

    Returns:
        Dictionary with:
        - total_expected (int): Number of expected URLs
        - found_in_index (int): How many are actually in Solr
        - missing_urls (List[str]): URLs not found in index
        - found_urls (List[str]): URLs found in index
    """
    found_urls = []
    missing_urls = []

    for url in expected_urls:
        # Extract document ID from URL
        # Expected format: https://access.redhat.com/solutions/123456
        # Solr ID format: /solutions/123456/index.html
        doc_id = url.replace("https://access.redhat.com", "")

        # Try both with and without /index.html suffix
        possible_ids = [
            f"{doc_id}/index.html",
            f"{doc_id}",
            f"{doc_id}/index.html".replace("//", "/")
        ]

        found = False
        for test_id in possible_ids:
            # Query Solr for this specific ID
            query_url = f"{solr_url}/{collection}/select"
            params = {
                "q": f'id:"{test_id}"',
                "rows": 1,
                "fl": "id",
                "wt": "json"
            }

            try:
                response = httpx.get(query_url, params=params, timeout=10)
                data = response.json()

                if data.get("response", {}).get("numFound", 0) > 0:
                    found = True
                    found_urls.append(url)
                    break
            except Exception as e:
                continue

        if not found:
            missing_urls.append(url)

    return {
        "total_expected": len(expected_urls),
        "found_in_index": len(found_urls),
        "missing_urls": missing_urls,
        "found_urls": found_urls,
        "coverage": len(found_urls) / len(expected_urls) if expected_urls else 0.0
    }


# ============================================================================
# PATTERN LOADING
# ============================================================================

def load_pattern(pattern_name: str) -> List[Dict]:
    """
    Load pattern YAML file.

    Args:
        pattern_name: Pattern name (e.g., "BOOTLOADER_UEFI_FIRMWARE")

    Returns:
        List of conversation turns with queries and expected URLs
    """
    pattern_file = Path("okp_mcp_agent/config/patterns") / f"{pattern_name}.yaml"

    if not pattern_file.exists():
        raise FileNotFoundError(f"Pattern file not found: {pattern_file}")

    with open(pattern_file) as f:
        pattern_data = yaml.safe_load(f)

    # Extract turns
    turns = []
    for conversation in pattern_data:
        for turn in conversation.get("turns", []):
            turns.append({
                "query": turn["query"],
                "expected_urls": turn.get("expected_urls", []),
                "conversation_id": conversation.get("conversation_group_id", "unknown")
            })

    return turns


# ============================================================================
# COMPARISON & OUTPUT
# ============================================================================

def compare_approaches(
    pattern_name: str,
    simple_agent: SimpleSolrAgent,
    rag_agent: RAGSolrAgent,
    okp_mcp_cache_dir: Optional[Path] = None,
    solr_url: str = "http://localhost:8983/solr",
    collection: str = "portal"
) -> Dict[str, List[FeedbackSearchResult]]:
    """
    Compare all three approaches on a pattern.

    Args:
        pattern_name: Pattern to evaluate
        simple_agent: SimpleSolrAgent instance
        rag_agent: RAGSolrAgent instance
        okp_mcp_cache_dir: Directory with okp-mcp cache (optional)
        solr_url: Solr URL for ground truth verification
        collection: Solr collection name

    Returns:
        Dictionary mapping approach name to list of results
    """
    turns = load_pattern(pattern_name)

    results = {
        "simple": [],
        "rag": [],
        "okp-mcp": []
    }

    print(f"\n{'='*80}")
    print(f"COMPARING APPROACHES: {pattern_name}")
    print(f"{'='*80}")
    print(f"Total queries: {len(turns)}\n")

    # Verify ground truth coverage
    print("Verifying ground truth URLs in Solr index...")
    all_expected_urls = []
    for turn in turns:
        all_expected_urls.extend(turn["expected_urls"])

    ground_truth = verify_ground_truth(all_expected_urls, solr_url, collection)
    print(f"  Total expected URLs: {ground_truth['total_expected']}")
    print(f"  Found in index: {ground_truth['found_in_index']} ({ground_truth['coverage']:.1%})")
    if ground_truth['missing_urls']:
        print(f"  Missing from index: {len(ground_truth['missing_urls'])}")
        for url in ground_truth['missing_urls'][:3]:
            print(f"    - {url}")
        if len(ground_truth['missing_urls']) > 3:
            print(f"    ... and {len(ground_truth['missing_urls']) - 3} more")
    print()

    for i, turn in enumerate(turns, 1):
        query = turn["query"]
        expected_urls = turn["expected_urls"]
        conv_id = turn["conversation_id"]

        print(f"\n[{i}/{len(turns)}] {conv_id}")
        print(f"Query: {query[:80]}...")
        print(f"Expected URLs: {len(expected_urls)}")

        # Simple + feedback
        print("\n  Simple agent + feedback...")
        simple_result = search_with_feedback(
            query=query,
            expected_urls=expected_urls,
            agent=simple_agent,
            agent_type="simple"
        )
        results["simple"].append(simple_result)
        print(f"    Iterations: {simple_result.iterations}, URL F1: {simple_result.final_score:.3f}, Content: {simple_result.final_content_relevance:.3f}, Success: {simple_result.success}")

        # RAG + feedback
        print("  RAG agent + feedback...")
        rag_result = search_with_feedback(
            query=query,
            expected_urls=expected_urls,
            agent=rag_agent,
            agent_type="rag"
        )
        results["rag"].append(rag_result)
        print(f"    Iterations: {rag_result.iterations}, URL F1: {rag_result.final_score:.3f}, Content: {rag_result.final_content_relevance:.3f}, Success: {rag_result.success}")

        # okp-mcp cached
        if okp_mcp_cache_dir:
            print("  okp-mcp (cached)...")
            okp_result = load_okp_mcp_cached_results(
                query=query,
                expected_urls=expected_urls,
                cache_dir=okp_mcp_cache_dir
            )
            results["okp-mcp"].append(okp_result)
            print(f"    Score: {okp_result.final_score:.3f}, Success: {okp_result.success}")

    return results


def print_summary(results: Dict[str, List[FeedbackSearchResult]]):
    """Print summary statistics for all approaches."""
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")

    for approach_name, approach_results in results.items():
        if not approach_results:
            continue

        avg_url_score = sum(r.final_score for r in approach_results) / len(approach_results)
        avg_content_score = sum(r.final_content_relevance for r in approach_results) / len(approach_results)
        avg_iterations = sum(r.iterations for r in approach_results) / len(approach_results)
        success_count = sum(1 for r in approach_results if r.success)
        success_rate = success_count / len(approach_results) if approach_results else 0

        print(f"{approach_name.upper()}")
        print(f"  URL F1 Score: {avg_url_score:.3f}")
        print(f"  Content Relevance: {avg_content_score:.3f}")
        print(f"  Average Iterations: {avg_iterations:.1f}")
        print(f"  Success Rate (URL): {success_rate:.1%} ({success_count}/{len(approach_results)})")
        print()


def print_iteration_details(results: Dict[str, List[FeedbackSearchResult]]):
    """Print detailed iteration-by-iteration breakdown."""
    print(f"\n{'='*80}")
    print("ITERATION DETAILS")
    print(f"{'='*80}\n")

    for approach_name, approach_results in results.items():
        if not approach_results or approach_name == "okp-mcp":
            continue  # Skip okp-mcp (no iterations) and empty results

        print(f"\n{approach_name.upper()} AGENT")
        print("-" * 80)

        for i, result in enumerate(approach_results, 1):
            print(f"\n[{i}] {result.query[:60]}...")
            print(f"    Final: URL F1={result.final_score:.3f}, Content Rel={result.final_content_relevance:.3f}, Success={result.success}")

            for iter_data in result.iteration_history:
                print(f"    Iter {iter_data['iteration']}: URL F1={iter_data['score']:.3f}, Content={iter_data.get('content_relevance', 0.0):.3f}, URLs={len(iter_data['urls'])}")
                if iter_data['adjustment']:
                    print(f"      → Adjustment: {iter_data['adjustment']}")
                if iter_data['issues']:
                    print(f"      → Issues: {', '.join(iter_data['issues'][:2])}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compare okp-mcp with Simple/RAG agents using feedback loops"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="BOOTLOADER_UEFI_FIRMWARE",
        help="Pattern to evaluate (default: BOOTLOADER_UEFI_FIRMWARE)"
    )
    parser.add_argument(
        "--okp-mcp-cache",
        type=Path,
        help="Path to okp-mcp cache directory (optional)"
    )
    parser.add_argument(
        "--solr-url",
        type=str,
        default="http://localhost:8983/solr",
        help="Solr URL (default: http://localhost:8983/solr)"
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="portal",
        help="Solr collection name (default: portal)"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum feedback iterations (default: 3)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="Success threshold for URL validation (default: 0.7)"
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Show detailed iteration-by-iteration breakdown"
    )

    args = parser.parse_args()

    print("Initializing agents...")

    # Initialize Simple agent
    simple_agent = SimpleSolrAgent(
        solr_url=args.solr_url,
        collection=args.collection
    )

    # Initialize RAG agent
    rag_agent = RAGSolrAgent(
        solr_url=args.solr_url,
        collection=args.collection
    )

    # Run comparison
    results = compare_approaches(
        pattern_name=args.pattern,
        simple_agent=simple_agent,
        rag_agent=rag_agent,
        okp_mcp_cache_dir=args.okp_mcp_cache,
        solr_url=args.solr_url,
        collection=args.collection
    )

    # Print results
    print_summary(results)

    if args.details:
        print_iteration_details(results)

    print(f"\n{'='*80}")
    print("DONE")
    print(f"{'='*80}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

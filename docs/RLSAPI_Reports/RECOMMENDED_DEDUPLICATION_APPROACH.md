# Recommended Deduplication Implementation for okp-mcp

## Multi-Stage Deduplication Strategy

### Stage 1: Per-Backend Chunk Deduplication (BEFORE RRF)

**File:** `src/okp_mcp/rag/tools.py`
**Function:** `_run_fused_search()`
**When:** After each backend returns, before RRF merge

```python
async def _run_fused_search(
    query: str,
    cleaned: str,
    *,
    app: AppContext,
    max_results: int,
    product: str,
) -> RagResponse:
    """Run fused search with per-backend deduplication before RRF merge."""

    # Execute searches in parallel (existing code)
    hybrid_coro = hybrid_search(cleaned, client=app.http_client, ...)
    portal_coro = portal_search(cleaned, client=app.http_client, ...)

    if app.embedder is not None:
        semantic_coro = semantic_text_search(query, embedder=app.embedder, ...)
        hybrid_result, semantic_result, portal_result = await asyncio.gather(
            hybrid_coro, semantic_coro, portal_coro, return_exceptions=True
        )
    else:
        hybrid_result, portal_result = await asyncio.gather(
            hybrid_coro, portal_coro, return_exceptions=True
        )
        semantic_result = None

    # Error handling (existing code)
    if isinstance(hybrid_result, Exception):
        raise hybrid_result

    # ========================================================================
    # NEW: Deduplicate each backend BEFORE RRF to reduce input size
    # ========================================================================

    # Deduplicate hybrid results (removes duplicate chunks from same parent)
    hybrid_deduped = deduplicate_chunks(
        cast(RagResponse, hybrid_result).docs,
        min_tokens=30
    )[:max_results]  # Take top N after deduplication

    # Deduplicate semantic results (if available)
    semantic_deduped = []
    if isinstance(semantic_result, Exception):
        logger.warning("Semantic search failed, excluding from fusion", exc_info=semantic_result)
    elif semantic_result is not None:
        semantic_deduped = deduplicate_chunks(
            cast(RagResponse, semantic_result).docs,
            min_tokens=30
        )[:max_results]

    # Deduplicate portal results
    portal_deduped = []
    if isinstance(portal_result, Exception):
        logger.warning("Portal search failed, excluding from fusion", exc_info=portal_result)
    else:
        portal_rag = portal_highlights_to_rag_results(cast(PortalResponse, portal_result))
        if portal_rag.docs:
            portal_deduped = deduplicate_chunks(
                portal_rag.docs,
                min_tokens=30
            )[:max_results]

    # RRF with cleaner inputs (max_results × num_backends instead of max_results × 3 × num_backends)
    rag_results = [
        RagResponse(num_found=len(hybrid_deduped), docs=hybrid_deduped)
    ]
    if semantic_deduped:
        rag_results.append(RagResponse(num_found=len(semantic_deduped), docs=semantic_deduped))
    if portal_deduped:
        rag_results.append(RagResponse(num_found=len(portal_deduped), docs=portal_deduped))

    return reciprocal_rank_fusion(*rag_results)
```

**Impact:**
- Reduces RRF input from ~90 docs → ~30 docs (10 × 3 backends)
- Each backend contributes its top unique chunks, not redundant ones
- RRF scores are more meaningful (cross-backend consensus, not within-backend duplication)

---

### Stage 2: Semantic Similarity Deduplication (AFTER RRF)

**File:** `src/okp_mcp/rag/formatting.py` (new function)
**When:** After RRF merge, before context expansion

```python
"""Semantic similarity-based deduplication for near-identical content."""

from difflib import SequenceMatcher
from typing import TypeVar

from .models import RagDocument

T = TypeVar('T', bound=RagDocument)


def _compute_similarity(text1: str, text2: str) -> float:
    """Compute text similarity using SequenceMatcher (0.0 to 1.0).

    For production, consider using embeddings-based similarity:
    - cosine_similarity(embed(text1), embed(text2))

    SequenceMatcher is fast and dependency-free for MVP.
    """
    return SequenceMatcher(None, text1, text2).ratio()


def deduplicate_by_similarity(
    docs: list[T],
    *,
    threshold: float = 0.85,
    compare_field: str = "chunk",
) -> list[T]:
    """Remove near-duplicate documents based on content similarity.

    Compares documents pairwise and removes the lower-ranked document
    when similarity exceeds threshold. Preserves input rank order.

    Args:
        docs: List of RagDocument chunks, ordered by relevance (e.g., RRF score).
        threshold: Similarity threshold (0.0-1.0). Documents with similarity
            above this are considered duplicates. Default 0.85 (85% similar).
        compare_field: Field name to compare (default "chunk"). Use "title"
            to deduplicate by title similarity instead.

    Returns:
        Deduplicated list preserving original rank order.

    Example:
        Input (after RRF):
        1. RHEL 10 autofs guide (chunk: "To configure autofs, edit /etc/auto.master...")
        2. RHEL 9 autofs guide (chunk: "To configure autofs, edit /etc/auto.master...")
        3. RHEL 10 NFS guide (chunk: "Mount NFS shares with mount -t nfs...")

        Output (threshold=0.85):
        1. RHEL 10 autofs guide (kept - highest rank)
        3. RHEL 10 NFS guide (kept - dissimilar to #1)

        Removed:
        2. RHEL 9 autofs guide (85%+ similar to #1, lower rank)
    """
    if not docs or threshold >= 1.0:
        return docs

    if threshold < 0.0:
        raise ValueError(f"threshold must be >= 0.0, got {threshold}")

    keep_indices: set[int] = set(range(len(docs)))

    # Compare each pair, remove lower-ranked doc if similarity > threshold
    for i in range(len(docs)):
        if i not in keep_indices:
            continue  # Already removed

        text_i = getattr(docs[i], compare_field, "") or ""
        if not text_i.strip():
            continue

        for j in range(i + 1, len(docs)):
            if j not in keep_indices:
                continue  # Already removed

            text_j = getattr(docs[j], compare_field, "") or ""
            if not text_j.strip():
                continue

            similarity = _compute_similarity(text_i, text_j)
            if similarity > threshold:
                # Remove lower-ranked document (j, since i < j)
                keep_indices.discard(j)

    return [docs[i] for i in sorted(keep_indices)]
```

**Usage in `tools.py:search_rag()`:**

```python
@mcp.tool(tags={"rag"})
async def search_rag(
    ctx: Context,
    query: str,
    product: str = "",
    max_results: int = 10,
) -> str:
    """Search Red Hat documentation with multi-stage deduplication."""

    if not query or not query.strip():
        return "Please provide a search query."

    max_results = max(1, min(max_results, 20))
    logger.info("search_rag: query=%r product=%r max_results=%d", query, product, max_results)

    try:
        app = get_app_context(ctx)
        cleaned = clean_rag_query(query)

        # Stage 1: Per-backend dedup happens inside _run_fused_search
        # Returns ~30 docs (10 per backend) after RRF merge
        response = await _run_fused_search(
            query,
            cleaned,
            app=app,
            max_results=max_results,  # No longer multiply by 3!
            product=product
        )

        if not response.docs:
            return f"No results found for: {query}"

        # Stage 2: Remove near-duplicate content (RHEL 9 vs 10 same guide, etc.)
        similarity_deduped = deduplicate_by_similarity(
            response.docs,
            threshold=0.85
        )[:max_results]

        # Stage 3: Expand contexts (may fetch surrounding chunks)
        expanded = await expand_chunks(
            similarity_deduped,
            client=app.http_client,
            solr_url=app.rag_solr_url
        )

        # Format and return
        return _assemble_rag_output(expanded, query, app.max_response_chars)

    except httpx.TimeoutException:
        logger.warning("search_rag timed out for query: %r", query)
        return "The search timed out. Please try again with a simpler query."
    except (httpx.HTTPError, ValueError):
        logger.error("search_rag failed for query: %r", query, exc_info=True)
        return "No results found. The knowledge base may be temporarily unavailable."
```

---

### Stage 3: Smart Context Expansion (Prevent Re-introducing Duplicates)

**File:** `src/okp_mcp/rag/context.py`
**Function:** `expand_chunks()` (modify existing)

**Current behavior:** Fetches surrounding chunks for ALL deduplicated chunks, which can re-introduce duplicates if two chunks from the same parent ended up in different backend results.

**Improved behavior:** Only expand fragmentary chunks (< 500 tokens), leave complete chunks as-is.

```python
async def expand_chunks(
    chunks: list[RagDocument],
    *,
    client: httpx.AsyncClient,
    solr_url: str,
    min_tokens_for_expansion: int = 500,  # NEW parameter
) -> list[RagDocument]:
    """Expand context for fragmentary chunks by fetching surrounding content.

    Only expands chunks with fewer than min_tokens_for_expansion tokens.
    Complete chunks (>= min_tokens_for_expansion) are returned as-is to
    avoid re-introducing redundancy.

    Args:
        chunks: Deduplicated RagDocument list.
        client: Shared AsyncClient instance.
        solr_url: Base Solr URL.
        min_tokens_for_expansion: Minimum tokens to skip expansion (default 500).
            Chunks with >= this many tokens are considered "complete".

    Returns:
        List with fragmentary chunks expanded, complete chunks unchanged.
    """
    if not chunks:
        return []

    needs_expansion: list[RagDocument] = []
    complete_chunks: list[RagDocument] = []

    for chunk in chunks:
        # Determine if chunk is fragmentary or complete
        num_tokens = chunk.num_tokens or 0
        if num_tokens < min_tokens_for_expansion:
            needs_expansion.append(chunk)
        else:
            complete_chunks.append(chunk)

    # Fetch parent documents for fragmentary chunks
    if needs_expansion:
        parent_ids = [c.parent_id for c in needs_expansion if c.parent_id]
        if parent_ids:
            # ... existing logic to fetch parent docs via Solr ...
            # Merge surrounding chunks into fragmentary ones
            expanded = _merge_with_parents(needs_expansion, parent_docs)
        else:
            expanded = needs_expansion
    else:
        expanded = []

    # Combine expanded fragmentary chunks with complete chunks
    # Preserve original rank order
    result = []
    for chunk in chunks:
        if chunk.num_tokens and chunk.num_tokens >= min_tokens_for_expansion:
            result.append(chunk)  # Complete chunk, unchanged
        else:
            # Find expanded version
            expanded_chunk = next(
                (e for e in expanded if e.doc_id == chunk.doc_id),
                chunk  # Fallback if expansion failed
            )
            result.append(expanded_chunk)

    return result
```

---

## Summary: Where Should Deduplication Happen?

### Multi-Stage Pipeline (Recommended)

```
User Query (max_results=10)
    ↓
Clean Query
    ↓
[Hybrid Search: 10] + [Semantic Search: 10] + [Portal Search: 10] = 30 total
    ↓
Stage 1: Per-Backend Deduplication
    deduplicate_chunks() on each backend separately
    → 10 + 10 + 10 = 30 unique chunks (reduced from 30 + 30 + 30 = 90)
    ↓
RRF Merge
    → ~20-25 docs (some cross-backend duplicates removed by RRF)
    ↓
Stage 2: Semantic Similarity Deduplication
    deduplicate_by_similarity(threshold=0.85)
    → ~10-15 docs (near-duplicates from different sources removed)
    ↓
Slice to max_results
    → 10 docs
    ↓
Stage 3: Smart Context Expansion
    Only expand fragmentary chunks (< 500 tokens)
    Complete chunks stay as-is
    → 10 docs (no re-introduced duplicates)
    ↓
Format & Return
```

### Why This Order?

**Stage 1 (BEFORE RRF):**
- Removes obvious duplicates early (same parent_id)
- Reduces RRF input size by 3x (90 → 30)
- Makes RRF scores more meaningful

**Stage 2 (AFTER RRF):**
- RRF has already merged cross-backend duplicates
- Now catch near-duplicates that RRF missed (different parent_id but similar content)
- Examples: RHEL 9 vs RHEL 10 versions of same guide

**Stage 3 (SMART EXPANSION):**
- Only expand when necessary (fragmentary chunks)
- Prevents re-introducing duplicates via context expansion
- Complete chunks are more useful than expanded fragmentary ones anyway

---

## Alternative: Single-Pass Deduplication (NOT Recommended)

**Option:** Only deduplicate after RRF, skip per-backend dedup

```python
# After RRF merge (~60 docs)
deduped = deduplicate_chunks(response.docs)  # ~40 docs
similarity_deduped = deduplicate_by_similarity(deduped)  # ~20 docs
final = similarity_deduped[:max_results]  # 10 docs
```

**Why NOT recommended:**
- Carries 90 docs through RRF (slow, high memory)
- RRF scores are inflated by within-backend duplicates
- More expensive to deduplicate 60 docs than 3 × 10 docs separately

---

## Configuration Parameters

Add these to `src/okp_mcp/config.py`:

```python
# Deduplication settings
SIMILARITY_THRESHOLD: float = 0.85  # 85% similar = duplicate
MIN_TOKENS_FOR_EXPANSION: int = 500  # Don't expand complete chunks
PER_BACKEND_MAX_RESULTS: int = 10  # Results per backend before RRF

# Override via environment variables
SIMILARITY_THRESHOLD = float(os.getenv("OKP_MCP_SIMILARITY_THRESHOLD", "0.85"))
MIN_TOKENS_FOR_EXPANSION = int(os.getenv("OKP_MCP_MIN_TOKENS_FOR_EXPANSION", "500"))
```

---

## Testing the Multi-Stage Approach

### Benchmark Queries (Before/After)

| Query | Before: Contexts | After: Contexts | Near-Dups Before | Near-Dups After |
|-------|------------------|-----------------|-------------------|-----------------|
| DHCP server setup | 49 | 10-12 | 705 pairs | < 5 pairs |
| Kerberos CIFS mount | 80 | 10-12 | Unknown (high) | < 5 pairs |
| rpm-ostree status | 13 | 8-10 | Unknown | < 3 pairs |

### Expected Improvements

| Metric | Current | After Stage 1 | After Stage 2 | After Stage 3 |
|--------|---------|---------------|---------------|---------------|
| RRF input size | 90 docs | 30 docs | N/A | N/A |
| Post-RRF size | ~60 docs | ~20-25 docs | ~10-15 docs | N/A |
| Final output | 10 docs | 10 docs | 10 docs | 10 docs |
| Near-duplicates | 60% of pairs | 20% of pairs | < 5% of pairs | < 5% of pairs |
| Context precision | 37.3% | 45-50% | 60-70% | 65-75% |

---

## Implementation Order

1. **Phase 1 (Quick Win):** Implement Stage 1 (per-backend dedup before RRF)
   - Modify `_run_fused_search()` only
   - No new dependencies
   - Immediate 3x reduction in RRF input size

2. **Phase 2 (High Impact):** Add Stage 2 (semantic similarity dedup)
   - Add `deduplicate_by_similarity()` to `formatting.py`
   - Use in `search_rag()` after RRF
   - Eliminates RHEL 9 vs 10 duplicate content

3. **Phase 3 (Polish):** Improve Stage 3 (smart expansion)
   - Modify `expand_chunks()` to skip complete chunks
   - Prevents re-introducing duplicates
   - Better response quality

---

## Risk Mitigation

**Concern:** Too aggressive deduplication might remove useful diversity

**Mitigation:**
- Make `similarity_threshold` configurable (0.85 is conservative)
- Test with 0.85, 0.90, 0.95 to find optimal balance
- Log removed docs (debug mode) to verify they're truly redundant
- Add metrics: `docs_removed_per_stage` to monitor effectiveness

**Concern:** Semantic similarity is slow for large doc sets

**Mitigation:**
- Only runs on post-RRF set (~20-30 docs), not 90 docs
- `SequenceMatcher` is fast for short texts (< 2000 chars)
- For embeddings-based similarity, use cached embeddings from semantic search
- Set `max_results=20` cap to bound worst-case pairwise comparisons

---

## Conclusion

**Deduplication should happen in 3 stages:**

1. **Per-Backend Chunk Dedup** (BEFORE RRF) - File: `tools.py`
2. **Semantic Similarity Dedup** (AFTER RRF) - File: `formatting.py` + `tools.py`
3. **Smart Context Expansion** (SELECTIVE) - File: `context.py`

This multi-stage approach is **optimal** because:
- ✅ Reduces data volume early (Stage 1)
- ✅ Catches near-duplicates that share-parent dedup misses (Stage 2)
- ✅ Prevents re-introducing duplicates via expansion (Stage 3)
- ✅ Each stage has a specific purpose and operates on the right data size
- ✅ Progressive refinement (coarse → fine) is more efficient than single-pass

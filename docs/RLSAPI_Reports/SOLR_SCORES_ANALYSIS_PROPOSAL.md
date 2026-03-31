# Why Solr Scores Should Be Returned with Context Metadata

**Current State:** Solr scores exist but are NOT exposed to evaluation
**Proposal:** Add score metadata to enable diagnostic analysis

---

## Current Situation: Scores Exist But Are Lost

### Where Scores Exist

**1. Solr returns scores** in response:
```json
{
  "response": {
    "numFound": 50,
    "docs": [
      {
        "doc_id": "rhel10-managing-filesystems-chunk-5",
        "title": "Installing Kea DHCP Server",
        "chunk": "Kea is the DHCP server in RHEL 10...",
        "score": 0.95  // ← SOLR SCORE EXISTS HERE
      }
    ]
  }
}
```

**2. okp-mcp requests scores** from Solr:
```python
# src/okp_mcp/rag/common.py line 13-14
RAG_FL = (
    "doc_id,parent_id,title,chunk,headings,online_source_url,"
    "product,product_version,chunk_index,num_tokens,documentKind,source_path,score"  # ← Requested
)
```

**3. okp-mcp models include scores**:
```python
# src/okp_mcp/rag/models.py line 34
class RagDocument(BaseModel):
    doc_id: str | None = None
    title: str | None = None
    chunk: str | None = None
    score: float | None = None  # ← EXISTS IN MODEL
    rrf_score: float | None = None  # ← RRF SCORE ALSO AVAILABLE
```

### Where Scores Are Lost

**1. Not included in formatted output**:
```python
# src/okp_mcp/rag/formatting.py lines 77-116
def format_rag_result(doc: RagDocument) -> str:
    """Format a RagDocument chunk as a markdown result block."""
    lines: list[str] = []
    lines.append(f"**{doc.title}**" if doc.title else "**Untitled**")
    if doc.headings:
        lines.append(f"Section: {doc.headings}")
    if doc.product:
        lines.append(f"Product: {product_str}")
    if doc.online_source_url:
        lines.append(f"URL: {doc.online_source_url}")
    if doc.chunk:
        lines.append(doc.chunk)

    # ❌ SCORE NOT INCLUDED!
    # ❌ RRF_SCORE NOT INCLUDED!

    return "\n".join(lines)
```

**2. Evaluation framework only receives text**:
```python
# src/lightspeed_evaluation/core/api/client.py lines 310-315
if (result["type"]) == "mcp_call":
    content = result["content"].split("---")
    response_data["rag_chunks"] = [
        {"content": x} for x in content  # ❌ Only content, no metadata
    ]
```

**3. TurnData model only supports string contexts**:
```python
# src/lightspeed_evaluation/core/models/data.py line 54-56
contexts: Optional[list[str]] = Field(  # ❌ list[str], not list[dict]
    default=None, min_length=1, description="Contexts"
)
```

---

## Why This Matters: Diagnostic Use Cases

### Use Case 1: Identifying Scoring Mismatches

**Scenario:** High Solr score but low context_recall

**What this tells you:**
- Solr thinks the document is highly relevant (good keyword match, title match, etc.)
- But the document doesn't contain the information needed to answer (verified by LLM judge)
- **Root cause:** Solr's ranking criteria (BM25, field boosts) are not aligned with actual answer quality

**Example from failing questions:**

| Question | Doc Title | Solr Score | Context Recall | Issue |
|----------|-----------|------------|----------------|-------|
| "What kernel version does RHEL 10 use?" | "RHEL Life Cycle Policy" | **0.95** | **0.0** | Lifecycle doc matches "RHEL 10" but has no kernel info |
| "How to set up Kea?" | "RHEL Container Compatibility Matrix" | **0.88** | **0.0** | Matches "RHEL" frequently but unrelated to Kea |
| "DHCP migration RHEL 9→10" | "DHCP Server Life Cycle" | **0.82** | **0.0** | Matches keywords but no migration guide |

**Diagnostic insight:** If we see high Solr scores with low context_recall repeatedly, it means:
- Solr's field boosts are wrong (lifecycle docs shouldn't rank so high)
- Need version filtering (lifecycle docs mention all RHEL versions)
- Need document type filtering (policy docs ≠ technical docs)

---

### Use Case 2: Identifying Good Docs Buried in Results

**Scenario:** Low Solr score but high context_recall

**What this tells you:**
- Document contains the answer (LLM found it useful)
- But Solr ranked it low (poor keyword match, buried in body text, etc.)
- **Root cause:** Solr's ranking is missing signals (need semantic search, better field weighting)

**Example:**

| Question | Doc Title | Solr Score | Rank | Context Recall | Issue |
|----------|-----------|------------|------|----------------|-------|
| "Install Kea DHCP" | "Infrastructure Services" | **0.35** | **#47** | **1.0** | Title doesn't say "Kea" explicitly, buried in results |
| "Python changes RHEL 9→10" | "Considerations in Adopting RHEL 10" | **0.28** | **#62** | **0.9** | Migration guide, but generic title ranks low |

**Diagnostic insight:** If we see low Solr scores with high context_recall:
- Boost installation guides, migration docs, "Considerations in Adopting" docs
- Use semantic search (vector similarity can find these even with poor keyword match)
- Improve title/heading extraction (these docs have generic titles)

---

### Use Case 3: RRF Score vs Individual Backend Scores

**Scenario:** Compare RRF merged score vs individual backend scores

**What we can track:**
```python
class RagDocument(BaseModel):
    score: float | None = None       # Original Solr score (from hybrid/semantic/portal)
    rrf_score: float | None = None   # After RRF merge
```

**Analysis:**
- Did RRF improve ranking? (correct doc's RRF score > original score)
- Are all 3 backends ranking the same docs? (high score in all 3 → strong consensus)
- Is one backend dominating? (portal score 0.9, hybrid score 0.1 → portal-only result)

**Example:**

| Doc | Hybrid Score | Semantic Score | Portal Score | RRF Score | Consensus? |
|-----|--------------|----------------|--------------|-----------|------------|
| "Installing Kea" | 0.95 | 0.88 | 0.92 | **0.91** | ✅ All agree |
| "Life Cycle Policy" | 0.82 | 0.05 | 0.78 | **0.55** | ❌ Semantic disagrees |

**Diagnostic insight:**
- High consensus (all backends agree) → confident ranking
- Low consensus (only 1 backend ranks high) → consider de-ranking
- Semantic score << lexical score → semantic search found it's not actually relevant

---

### Use Case 4: Score Distribution Analysis

**Scenario:** Understand score ranges and thresholds

**Questions we can answer:**
- What's the typical score range for relevant docs? (e.g., 0.7-1.0)
- What's the score distribution for irrelevant docs? (e.g., 0.1-0.4)
- Is there a clear separation? (relevant: 0.8+, irrelevant: 0.3-)
- Or are scores overlapping? (relevant: 0.5-0.9, irrelevant: 0.4-0.8)

**Example analysis:**

```
Context Recall 1.0 (useful docs):
  - Solr scores: [0.95, 0.88, 0.82, 0.75, 0.68]
  - Mean: 0.82, Min: 0.68, Max: 0.95

Context Recall 0.0 (useless docs):
  - Solr scores: [0.91, 0.84, 0.77, 0.65, 0.58]
  - Mean: 0.75, Min: 0.58, Max: 0.91

Problem: Scores overlap! (0.68-0.95 useful vs 0.58-0.91 useless)
```

**Diagnostic insight:** If score distributions overlap heavily:
- Solr scoring is not discriminative enough
- Need to add filtering (version, doc type) before scoring
- Need to re-weight fields (de-boost lifecycle docs)

---

### Use Case 5: Temporal Validity Scoring

**Scenario:** Check if deprecation boost is working

**Remember from solr.py:**
```python
_EXTRACTION_BOOST_KEYWORDS = frozenset([
    "deprecated", "removed", "no longer", "unsupported"
])

if any(kw in para_lower for kw in _EXTRACTION_BOOST_KEYWORDS):
    multiplier *= 2.0  # 2× boost for deprecation keywords
```

**With scores, we can verify:**
- Do paragraphs with "deprecated" have higher scores?
- Is the 2× multiplier sufficient? (should it be 3× or 5×?)
- Are deprecation notices ranking in top 3? Or still buried at position 10?

**Example:**

| Paragraph | Contains "deprecated"? | Base BM25 | Boosted Score | Rank |
|-----------|------------------------|-----------|---------------|------|
| "ISC DHCP was deprecated in RHEL 10" | ✅ Yes | 0.45 | **0.90** | **#1** |
| "DHCP server configuration requires..." | ❌ No | 0.75 | 0.75 | #2 |
| "Install DHCP with dnf install kea" | ❌ No | 0.68 | 0.68 | #3 |

**Diagnostic insight:** Deprecation boost is working (rank #1). If it wasn't, we'd see it at rank #5 despite being critical info.

---

### Use Case 6: Version Filtering Effectiveness

**Scenario:** After adding version filtering, measure impact

**Before filtering (RHEL 10 query):**

| Doc | Version | Solr Score | Context Recall | Rank |
|-----|---------|------------|----------------|------|
| RHEL 10 Release Notes | 10 | 0.95 | 1.0 | #1 |
| RHEL Life Cycle | 5-10 | 0.92 | 0.0 | #2 ← Wrong doc, high score! |
| RHEL 9 Docs | 9 | 0.88 | 0.3 | #3 |
| RHEL 10 Install Guide | 10 | 0.85 | 0.9 | #4 |

**After version filtering (`fq: version:(10 OR 9)`):**

| Doc | Version | Solr Score | Context Recall | Rank |
|-----|---------|------------|----------------|------|
| RHEL 10 Release Notes | 10 | 0.95 | 1.0 | #1 |
| RHEL 9 Docs | 9 | 0.88 | 0.3 | #2 |
| RHEL 10 Install Guide | 10 | 0.85 | 0.9 | #3 |
| (RHEL Life Cycle excluded) | - | - | - | - |

**Metrics improvement:**
- Mean context_recall: 0.43 → **0.73** (+70%!)
- Mean Solr score for context_recall=1.0 docs: 0.90 (unchanged, but now top-ranked)

**Diagnostic insight:** Version filtering didn't change scores, but removed high-scoring junk. This proves the problem is **inclusion of wrong docs**, not **scoring of right docs**.

---

## How to Implement: 3-Step Plan

### Step 1: Add Metadata Support to Contexts

**File:** `src/lightspeed_evaluation/core/models/data.py`

**Change line 54-56:**
```python
# Current
contexts: Optional[list[str]] = Field(
    default=None, min_length=1, description="Contexts"
)

# New (backward compatible)
contexts: Optional[Union[list[str], list[dict[str, Any]]]] = Field(
    default=None,
    min_length=1,
    description="Contexts (strings for backward compatibility, or dicts with metadata)"
)
```

**This allows:**
```python
# Old format (still works)
contexts = [
    "**Installing Kea**\nKea is the DHCP server...",
    "**RHEL 10 Features**\nNew features include..."
]

# New format (with metadata)
contexts = [
    {
        "content": "**Installing Kea**\nKea is the DHCP server...",
        "metadata": {
            "solr_score": 0.95,
            "rrf_score": 0.91,
            "doc_id": "rhel10-kea-install-chunk-3",
            "parent_id": "rhel10-considerations-adopting",
            "product_version": "10",
            "rank": 1
        }
    },
    {
        "content": "**RHEL 10 Features**\nNew features include...",
        "metadata": {
            "solr_score": 0.82,
            "rrf_score": 0.78,
            "doc_id": "rhel10-release-notes-chunk-15",
            "product_version": "10",
            "rank": 2
        }
    }
]
```

---

### Step 2: Include Scores in okp-mcp Formatted Output

**File:** `src/okp_mcp/rag/formatting.py`

**Add new function:**
```python
def format_rag_result_with_metadata(doc: RagDocument, rank: int | None = None) -> dict[str, Any]:
    """Format a RagDocument with content and metadata.

    Returns:
        {
            "content": "formatted markdown string",
            "metadata": {
                "solr_score": 0.95,
                "rrf_score": 0.91,
                "doc_id": "...",
                "parent_id": "...",
                "product_version": "10",
                "rank": 1
            }
        }
    """
    # Format content (same as before)
    content = format_rag_result(doc)

    # Add metadata
    metadata = {
        "doc_id": doc.doc_id,
        "parent_id": doc.parent_id,
        "product_version": doc.product_version,
        "documentKind": doc.documentKind,
        "source_path": doc.source_path,
    }

    # Scores
    if doc.score is not None:
        metadata["solr_score"] = doc.score
    if doc.rrf_score is not None:
        metadata["rrf_score"] = doc.rrf_score
    if rank is not None:
        metadata["rank"] = rank

    return {
        "content": content,
        "metadata": metadata
    }
```

**File:** `src/okp_mcp/rag/tools.py`

**Modify `_assemble_rag_output()`:**
```python
def _assemble_rag_output(
    docs: list[RagDocument],
    query: str,
    max_chars: int,
    include_metadata: bool = False  # NEW PARAMETER
) -> str | dict:
    """Assemble RAG results into formatted output.

    Args:
        docs: Deduplicated and expanded RagDocument chunks.
        query: Original search query.
        max_chars: Character limit.
        include_metadata: If True, return dict with metadata. If False, return string (backward compatible).

    Returns:
        If include_metadata=False: formatted string (backward compatible)
        If include_metadata=True: {"formatted": "...", "chunks": [{content, metadata}, ...]}
    """

    if not include_metadata:
        # Original behavior (backward compatible)
        formatted_docs = [format_rag_result(doc) for doc in docs]
        output = "\n\n---\n\n".join(formatted_docs)
        if len(output) > max_chars:
            output = output[:max_chars] + "\n\n[Output truncated]"
        return output

    # New behavior (with metadata)
    formatted_docs_with_metadata = [
        format_rag_result_with_metadata(doc, rank=i+1)
        for i, doc in enumerate(docs)
    ]

    # Extract content for formatted string
    formatted_string = "\n\n---\n\n".join(
        item["content"] for item in formatted_docs_with_metadata
    )
    if len(formatted_string) > max_chars:
        formatted_string = formatted_string[:max_chars] + "\n\n[Output truncated]"

    return {
        "formatted": formatted_string,
        "chunks": formatted_docs_with_metadata
    }
```

**Add environment variable:**
```python
# src/okp_mcp/config.py
class ServerConfig(BaseSettings):
    # ... existing fields ...

    include_context_metadata: bool = Field(
        default=False,
        description="Include score and metadata with RAG contexts (for evaluation/debugging)"
    )
```

---

### Step 3: Parse Metadata in Evaluation Framework

**File:** `src/lightspeed_evaluation/core/api/client.py`

**Modify lines 310-315:**
```python
if (result["type"]) == "mcp_call":
    # Check if response includes metadata
    if isinstance(result["content"], dict) and "chunks" in result["content"]:
        # New format with metadata
        response_data["rag_chunks"] = result["content"]["chunks"]
        # Also store formatted string for display
        response_data["rag_formatted"] = result["content"]["formatted"]
    else:
        # Old format (backward compatible)
        content = result["content"].split("---")
        response_data["rag_chunks"] = [
            {"content": x} for x in content
        ]
```

---

## Analysis Scripts to Run

### Script 1: Score vs Context Recall Correlation

```python
import pandas as pd
import matplotlib.pyplot as plt

# Load evaluation results
df = pd.read_csv("evaluation_detailed.csv")

# Extract Solr scores from contexts (if metadata available)
def extract_scores(contexts_json):
    contexts = json.loads(contexts_json)
    return [ctx.get("metadata", {}).get("solr_score") for ctx in contexts if "metadata" in ctx]

df["solr_scores"] = df["contexts"].apply(extract_scores)

# Get context_recall scores
recall_df = df[df["metric_identifier"] == "ragas:context_recall"]

# Plot: Average Solr score vs Context Recall
plt.scatter(recall_df["score"], recall_df["solr_scores"].apply(lambda x: sum(x)/len(x) if x else 0))
plt.xlabel("Context Recall (LLM Judge)")
plt.ylabel("Average Solr Score")
plt.title("Solr Score vs Context Recall Correlation")
plt.savefig("solr_score_vs_recall.png")

# Find mismatches
high_solr_low_recall = recall_df[
    (recall_df["solr_scores"].apply(lambda x: max(x) if x else 0) > 0.8) &
    (recall_df["score"] < 0.2)
]

print("High Solr Score but Low Context Recall:")
print(high_solr_low_recall[["conversation_group_id", "query", "solr_scores", "score"]])
```

---

### Script 2: Rank vs Usefulness

```python
# For each question, check if useful docs (context_recall=1.0) are at top ranks

def analyze_ranking_quality(eval_results):
    """Check if high-quality docs are ranked at top."""

    for question_id, group in eval_results.groupby("conversation_group_id"):
        # Get context_recall for this question
        recall_row = group[group["metric_identifier"] == "ragas:context_recall"].iloc[0]

        # Extract ranks of contexts
        contexts = json.loads(recall_row["contexts"])

        # LLM-judged useful contexts (would need ground truth annotations)
        # For now, assume all contexts with high score are useful

        useful_ranks = [ctx["metadata"]["rank"] for ctx in contexts if ctx["metadata"]["solr_score"] > 0.8]

        # Calculate MRR (Mean Reciprocal Rank) for useful docs
        if useful_ranks:
            mrr = 1.0 / min(useful_ranks)  # Best rank
            print(f"{question_id}: Best useful doc at rank {min(useful_ranks)} (MRR: {mrr:.3f})")
```

---

### Script 3: Score Distribution by Context Quality

```python
import seaborn as sns

# Separate scores by context quality
high_recall_scores = []  # Contexts from questions with context_recall > 0.7
low_recall_scores = []   # Contexts from questions with context_recall < 0.3

for _, row in recall_df.iterrows():
    if row["score"] > 0.7:
        high_recall_scores.extend(row["solr_scores"])
    elif row["score"] < 0.3:
        low_recall_scores.extend(row["solr_scores"])

# Plot distributions
plt.figure(figsize=(10, 6))
plt.hist(high_recall_scores, bins=20, alpha=0.5, label="High Context Recall (>0.7)", color="green")
plt.hist(low_recall_scores, bins=20, alpha=0.5, label="Low Context Recall (<0.3)", color="red")
plt.xlabel("Solr Score")
plt.ylabel("Frequency")
plt.title("Solr Score Distribution by Context Quality")
plt.legend()
plt.savefig("score_distribution_by_quality.png")

# Calculate overlap
print(f"High recall scores: mean={sum(high_recall_scores)/len(high_recall_scores):.3f}")
print(f"Low recall scores: mean={sum(low_recall_scores)/len(low_recall_scores):.3f}")
```

---

## Expected Insights from Score Analysis

### 1. Quantify Lifecycle Doc Problem

**Current hypothesis:** Lifecycle docs have high Solr scores but low usefulness.

**Test with scores:**
```python
lifecycle_docs = df[df["contexts"].str.contains("life*cycle", case=False, regex=True)]
lifecycle_scores = lifecycle_docs["solr_scores"].explode()
lifecycle_recall = lifecycle_docs["context_recall_score"]

print(f"Lifecycle docs: Avg Solr score = {lifecycle_scores.mean():.3f}")
print(f"Lifecycle docs: Avg context recall = {lifecycle_recall.mean():.3f}")

# Expected result:
# Lifecycle docs: Avg Solr score = 0.85 (HIGH!)
# Lifecycle docs: Avg context recall = 0.08 (LOW!)
```

**Conclusion:** Quantifies the problem. We can measure improvement after de-boosting.

---

### 2. Validate Version Filtering

**Test:** Compare score distributions before/after filtering.

```python
# Before filtering (RHEL 10 queries)
rhel10_queries_before = df_before[df_before["query"].str.contains("RHEL 10")]
mean_score_before = rhel10_queries_before["solr_scores"].explode().mean()

# After filtering
rhel10_queries_after = df_after[df_after["query"].str.contains("RHEL 10")]
mean_score_after = rhel10_queries_after["solr_scores"].explode().mean()

# If filtering works, mean score should be SIMILAR
# (filtering removes docs, doesn't change scoring)
# But mean context_recall should be HIGHER
```

---

### 3. Measure RRF Effectiveness

**Test:** Does RRF improve ranking vs single backend?

```python
# Compare top doc from each backend vs RRF result
for question_id, row in results.iterrows():
    contexts = json.loads(row["contexts"])

    # RRF picked this as #1
    rrf_top = contexts[0]

    # What was the score from each backend?
    print(f"RRF top doc: solr_score={rrf_top['metadata']['solr_score']}, rrf_score={rrf_top['metadata']['rrf_score']}")

    # Did RRF improve the ranking?
    if rrf_top["metadata"]["rrf_score"] > rrf_top["metadata"]["solr_score"]:
        print("  RRF boosted this doc (multi-backend consensus)")
    else:
        print("  Single backend dominated")
```

---

## Recommended Next Steps

1. **Implement Step 1** (add metadata support to evaluation framework) ← Non-breaking change
2. **Implement Step 2** (expose scores from okp-mcp) ← Requires MCP_INCLUDE_CONTEXT_METADATA env var
3. **Run one evaluation with metadata enabled** ← Compare most recent run with metadata
4. **Analyze score vs context_recall correlation** ← Validates hypothesis about lifecycle docs
5. **Measure score distribution overlap** ← Determines if scoring is discriminative
6. **Use insights to prioritize fixes** ← Version filtering vs de-boosting vs semantic search

---

## Summary: Why This Is Valuable

**Current state:**
- We know context_recall is low (18%)
- We know context_precision is low (37%)
- We **suspect** Solr is ranking wrong docs
- We **can't prove it** without scores

**With scores:**
- We can **prove** lifecycle docs have high scores but low usefulness
- We can **measure** if version filtering helps (context_recall improves but scores stay similar)
- We can **validate** that deprecation boost is working (2× multiplier enough?)
- We can **compare** RRF vs individual backends (is fusion helping?)
- We can **identify** good docs buried in results (low score but high recall → boost these doc types)

**Bottom line:** Scores are the missing link between Solr's ranking and LLM's judgment. Without them, we're flying blind.

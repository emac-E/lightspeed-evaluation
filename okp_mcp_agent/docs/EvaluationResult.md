# EvaluationResult Class Reference

## Overview

`EvaluationResult` is the **data container for evaluation metrics** from a single ticket evaluation run. It aggregates retrieval metrics, answer quality metrics, RAG usage tracking, and provides intelligent problem classification.

**Location:** `scripts/okp_mcp_agent.py`

**Purpose:** Store metrics and classify problem type (retrieval vs answer quality)

---

## When You'll Interact With EvaluationResult

| Scenario | Need EvaluationResult? |
|----------|------------------------|
| **Reading diagnosis results** | ✅ Yes - returned by `diagnose()` |
| **Checking problem type** | ✅ Yes - use `is_retrieval_problem` |
| **Analyzing metrics** | ✅ Yes - access metric fields |
| **Iteration comparisons** | ✅ Yes - compare metrics over time |
| **Writing evaluation configs** | ❌ No - use YAML structure |
| **Running evaluations** | ❌ No - use `OkpMcpAgent.diagnose()` |

**For analyzing ticket evaluation results: This is the primary data class.**

---

## Class Definition

```python
@dataclass
class EvaluationResult:
    """Results from a single evaluation run."""
```

**Type:** `dataclass` (immutable-ish, use `replace()` to modify)

**Created by:** `OkpMcpAgent.parse_results()`

---

## Fields

### Core Identification

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `ticket_id` | `str` | ✅ Yes | RSPEED ticket identifier | `"RSPEED-2482"` |
| `query` | `str` | ❌ No | User question from CSV | `"How to install Kea DHCP?"` |

### Retrieval Metrics

Available in both retrieval-only and full evaluation modes.

| Field | Type | Description | Range | Threshold |
|-------|------|-------------|-------|-----------|
| `url_f1` | `float` | F1 score for expected URL retrieval | 0.0-1.0 | 0.7 |
| `mrr` | `float` | Mean Reciprocal Rank | 0.0-1.0 | 0.5 |
| `context_relevance` | `float` | Ragas: Are retrieved docs relevant? | 0.0-1.0 | 0.7 |
| `context_precision` | `float` | Ragas: Precision of retrieved context | 0.0-1.0 | 0.7 |

**Note:** `url_f1` can be unreliable (see debugging tips). Prioritize `context_relevance` for retrieval quality.

### Answer Quality Metrics

Only populated in full evaluation mode (using `/v1/infer` API).

| Field | Type | Description | Range | Threshold |
|-------|------|-------------|-------|-----------|
| `keywords_score` | `float` | Custom: Are required keywords present? | 0.0-1.0 | 0.7 |
| `answer_correctness` | `float` | Custom: LLM judge vs expected answer | 0.0-1.0 | 0.75 |
| `faithfulness` | `float` | Ragas: Is answer grounded in context? | 0.0-1.0 | 0.7 |
| `response_relevancy` | `float` | Ragas: Does answer address question? | 0.0-1.0 | 0.8 |
| `forbidden_claims_score` | `float` | Custom: Avoids known-incorrect claims? | 0.0-1.0 | 1.0 |

### RAG Usage Tracking

| Field | Type | Description |
|-------|------|-------------|
| `tool_calls` | `str` | Raw tool_calls JSON from CSV |
| `contexts` | `str` | Raw contexts from CSV |
| `rag_used` | `bool` | Was RAG/search tool called? |
| `docs_retrieved` | `bool` | Were any documents retrieved? |

### Ground Truth / Expected Values

From test config YAML.

| Field | Type | Description |
|-------|------|-------------|
| `response` | `str` | Actual LLM answer |
| `expected_response` | `str` | What answer should say |
| `expected_keywords` | `list` | Required keywords (all must be present) |
| `expected_urls` | `list` | Expected document URLs |
| `forbidden_claims` | `list` | Known-incorrect claims to avoid |

### Retrieved Values

Extracted from tool_calls and contexts.

| Field | Type | Description |
|-------|------|-------------|
| `retrieved_urls` | `list` | URLs actually retrieved |
| `retrieved_doc_titles` | `list` | Titles of retrieved documents |

### Evaluation Metadata

| Field | Type | Description |
|-------|------|-------------|
| `num_runs` | `int` | Number of runs averaged (for stability) |
| `high_variance_metrics` | `list` | Metrics with >15% variance (instability) |
| `solr_check` | `dict` | Solr document existence check results |
| `url_overlap_with_previous` | `float` | Jaccard similarity with previous iteration (0-1) |

---

## Properties (Problem Classification)

### is_retrieval_problem

Determine if this is a retrieval problem based on metrics.

```python
@property
def is_retrieval_problem(self) -> bool:
    """Determine if this is a retrieval problem.
    
    IMPORTANT: Prioritizes RAGAS context metrics over URL F1.
    URL F1 is unreliable (can be 0.00 even with correct answer).
    
    Returns:
        True if retrieval metrics are below thresholds
    """
```

**Logic:**

1. **PRIMARY**: Check RAGAS context metrics (most reliable)
   ```python
   if context_relevance < 0.7:
       return True  # Retrieval problem
   ```

2. **SECONDARY**: Check MRR if available
   ```python
   if mrr < 0.5:
       return True  # Retrieval problem
   ```

3. **TERTIARY**: Only check URL F1 if context metrics unavailable
   ```python
   if url_f1 < 0.7 and context_relevance is None:
       return True  # Retrieval problem
   ```

**Usage:**

```python
if result.is_retrieval_problem:
    print("Fix retrieval (boost queries, Solr tuning)")
```

---

### is_answer_problem

Determine if this is an answer quality problem.

```python
@property
def is_answer_problem(self) -> bool:
    """Determine if this is an answer quality problem.
    
    Returns:
        True if retrieval is good but keywords are missing
    """
```

**Logic:**

```python
good_retrieval = url_f1 >= 0.7
poor_keywords = keywords_score < 0.7

return good_retrieval and poor_keywords
```

**Usage:**

```python
if result.is_answer_problem:
    print("Fix answer (prompt changes, LLM tuning)")
```

---

### is_answer_good_enough

Check if answer quality is good regardless of retrieval.

```python
@property
def is_answer_good_enough(self) -> bool:
    """Check if answer quality is good regardless of retrieval.
    
    This allows the loop to end early if the answer is correct even if
    we didn't retrieve the "expected" URLs (e.g., LLM used general
    knowledge, or retrieved docs were fine despite not matching expected URLs).
    
    Uses answer_correctness if available, otherwise falls back to keywords.
    
    IMPORTANT: Also verifies answer is grounded in RAG (not hallucinated).
    
    Returns:
        True if answer is good and grounded
    """
```

**Logic:**

```python
# 1. Check answer correctness (primary signal)
if answer_correctness >= 0.8:
    good_answer = True
elif keywords_score >= 0.9:
    good_answer = True  # Fallback: Very high keywords
elif context_relevance >= 0.9 and context_precision >= 0.8:
    good_answer = True  # Fallback: Very high context metrics
else:
    good_answer = False

# 2. Check keywords (required facts present)
good_keywords = keywords_score is None or keywords_score >= 0.7

# 3. Check forbidden claims (no regression)
no_forbidden_claims = (
    forbidden_claims_score is None or
    forbidden_claims_score >= 0.9
)

# 4. GROUNDING CHECK (verify not hallucinated)
is_grounded = (
    rag_used and
    context_relevance >= 0.7 and
    faithfulness >= 0.7
)

return good_answer and good_keywords and no_forbidden_claims and is_grounded
```

**Usage:**

```python
if result.is_answer_good_enough:
    print("✅ Ticket is already good, no fix needed")
```

**Why Grounding Matters:**

Prevents accepting hallucinated answers:
- ✅ Answer looks correct, uses RAG, grounded in context → GOOD
- ❌ Answer looks correct, but RAG not used → HALLUCINATION
- ❌ Answer looks correct, but low faithfulness → MAKING THINGS UP

---

### has_metrics

Check if any metrics were successfully parsed.

```python
@property
def has_metrics(self) -> bool:
    """Check if any metrics were successfully parsed.
    
    Returns:
        True if at least one metric is available
    """
```

**Usage:**

```python
if not result.has_metrics:
    print("⚠️  No metrics found, evaluation may have failed")
```

---

### is_retrieval_only_mode

Detect if this was retrieval-only mode (no answer metrics).

```python
@property
def is_retrieval_only_mode(self) -> bool:
    """Detect if this was retrieval-only mode.
    
    Returns:
        True if has retrieval metrics but no answer metrics
    """
```

**Logic:**

```python
has_retrieval = url_f1 is not None or context_relevance is not None
has_answer = any([
    keywords_score is not None,
    faithfulness is not None,
    answer_correctness is not None,
])
return has_retrieval and not has_answer
```

**Usage:**

```python
if result.is_retrieval_only_mode:
    print("Retrieval-only mode detected, no answer quality metrics")
```

---

## Methods

### summary()

Human-readable summary of metrics.

```python
def summary(self) -> str:
    """Human-readable summary of metrics.
    
    Returns:
        Multi-line string with formatted metrics
    """
```

**Usage:**

```python
result = agent.diagnose("RSPEED-2482")
print(result.summary())
```

**Output:**

```
Ticket: RSPEED-2482
  📊 Metrics averaged across 5 runs for stability
  RAG Status: ✅ Used, 3 docs retrieved
  URL F1: 0.67
  MRR: 0.50
  Context Relevance: 0.85
  Context Precision: 0.78
  Keywords: 0.60
  Faithfulness: 0.92
  Answer Correctness: 0.73
  Response Relevancy: 0.88
  Forbidden Claims: 1.00
```

---

### num_docs_retrieved()

Count how many documents were retrieved.

```python
def num_docs_retrieved(self) -> int:
    """Count how many documents were retrieved.
    
    Returns:
        Number of unique documents (URLs) retrieved
    """
```

**Usage:**

```python
if result.num_docs_retrieved() == 0:
    print("⚠️  No documents retrieved, RAG may be broken")
```

---

## Common Patterns

### Pattern 1: Problem Classification

```python
result = agent.diagnose("RSPEED-2482")

if result.is_answer_good_enough:
    print("✅ Already good enough, no fix needed")
elif result.is_retrieval_problem:
    print("🔍 Fix retrieval (Solr boost queries)")
    # Route to fast_retrieval_loop()
elif result.is_answer_problem:
    print("💬 Fix answer (prompt changes)")
    # Route to LLM advisor for prompt suggestions
else:
    print("❓ Unclear problem, needs manual investigation")
```

### Pattern 2: Metric Comparison Over Iterations

```python
baseline = agent.diagnose("RSPEED-2482")

# After making changes
current = agent.diagnose("RSPEED-2482")

# Check improvement
if current.url_f1 > baseline.url_f1 + 0.05:
    print(f"✅ Significant improvement: {baseline.url_f1:.2f} → {current.url_f1:.2f}")
else:
    print(f"⚠️  No improvement: {baseline.url_f1:.2f} → {current.url_f1:.2f}")
```

### Pattern 3: Stability Check

```python
# Run 5 times to check for variance
result = agent.diagnose("RSPEED-2482", runs=5)

if result.high_variance_metrics:
    print(f"⚠️  Unstable metrics: {result.high_variance_metrics}")
    print("   See docs/VARIANCE_SOLUTIONS.md for root cause analysis")
else:
    print("✅ Stable results across 5 runs")
```

### Pattern 4: RAG Usage Validation

```python
result = agent.diagnose("RSPEED-2482")

if not result.rag_used:
    print("❌ RAG not used, LLM used general knowledge only")
    print("   This is usually wrong for RHEL documentation questions")
elif not result.docs_retrieved:
    print("❌ RAG used but NO documents retrieved")
    print("   Solr may be down or query is malformed")
elif result.num_docs_retrieved() < 3:
    print(f"⚠️  Only {result.num_docs_retrieved()} docs retrieved")
    print("   May need to improve query or boost configuration")
else:
    print(f"✅ RAG working, {result.num_docs_retrieved()} docs retrieved")
```

---

## Creating EvaluationResult Instances

### Via OkpMcpAgent.parse_results()

**Recommended approach:**

```python
# After running evaluation
output_dir = agent.get_latest_output_dir("full")
result = agent.parse_results(output_dir, "RSPEED-2482")
```

### Manual Construction (Testing)

```python
from scripts.okp_mcp_agent import EvaluationResult

# Create fake result for testing
test_result = EvaluationResult(
    ticket_id="TEST-123",
    query="Test query",
    url_f1=0.85,
    context_relevance=0.90,
    keywords_score=0.95,
    answer_correctness=0.88,
    rag_used=True,
    docs_retrieved=True,
)

assert test_result.is_answer_good_enough
```

---

## Debugging Tips

### Problem: All Metrics Are None

**Symptom:** `result.has_metrics == False`

**Possible Causes:**
1. Evaluation failed to run
2. Wrong output directory
3. CSV parsing error

**Check:**
```python
print(f"Output dir: {output_dir}")
print(f"CSV exists: {(output_dir / 'evaluation_results.csv').exists()}")

# Check CSV contents
import pandas as pd
df = pd.read_csv(output_dir / "evaluation_results.csv")
print(df[df['conversation_group_id'] == ticket_id])
```

### Problem: URL F1 is 0.0 but Answer is Correct

**Symptom:** `url_f1 == 0.0` but `answer_correctness >= 0.8`

**Explanation:** URL F1 is unreliable. The LLM may have:
- Retrieved different but equally valid documentation
- Used general knowledge (if grounded in RAG, this can still be good)
- Retrieved docs without URLs in expected_urls list

**Solution:** Prioritize `context_relevance` and `answer_correctness` over `url_f1`.

```python
if result.answer_correctness >= 0.8 and result.context_relevance >= 0.7:
    print("✅ Answer is good even though URL F1 is low")
    print("   This is acceptable - docs were relevant")
```

### Problem: High Variance in Metrics

**Symptom:** `len(result.high_variance_metrics) > 0`

**Meaning:** Metrics vary significantly across runs (>15% variance).

**Common Causes:**
1. Bad ground truth (vague expected_response)
2. Non-deterministic retrieval (URL ordering varies)
3. Prompt sensitivity (small input changes → big output changes)
4. Environmental issues (Solr index state, LLM API issues)

**Solution:** See `docs/VARIANCE_SOLUTIONS.md` for diagnostic steps.

```python
if result.high_variance_metrics:
    print(f"⚠️  Unstable: {result.high_variance_metrics}")
    print("   Run diagnostics from docs/VARIANCE_SOLUTIONS.md")
```

### Problem: RAG Used But No Documents Retrieved

**Symptom:** `rag_used == True` but `docs_retrieved == False`

**Possible Causes:**
1. Solr is down
2. Solr query returned 0 results
3. Query is malformed

**Check:**
```python
if result.rag_used and not result.docs_retrieved:
    # Check Solr health
    import requests
    try:
        r = requests.get("http://localhost:8983/solr/portal/admin/ping")
        print(f"Solr health: {r.status_code}")
    except:
        print("❌ Solr is down")
    
    # Check actual Solr query
    inspection = agent.inspect_solr_query(result.query)
    print(f"Solr query: {inspection}")
```

---

## Metrics Interpretation Guide

### Retrieval Metrics

| Metric | Good | Acceptable | Poor | What It Means |
|--------|------|------------|------|---------------|
| `url_f1` | ≥0.7 | 0.5-0.7 | <0.5 | How well expected URLs were retrieved |
| `mrr` | ≥0.5 | 0.3-0.5 | <0.3 | Rank of first expected URL (1/rank) |
| `context_relevance` | ≥0.8 | 0.6-0.8 | <0.6 | Are retrieved docs relevant to question? |
| `context_precision` | ≥0.8 | 0.6-0.8 | <0.6 | % of retrieved docs that are useful |

**Note:** `context_relevance` is the **most reliable** retrieval metric. Prioritize it over `url_f1`.

### Answer Quality Metrics

| Metric | Good | Acceptable | Poor | What It Means |
|--------|------|------------|------|---------------|
| `answer_correctness` | ≥0.8 | 0.6-0.8 | <0.6 | LLM judge: Does answer match expected? |
| `keywords_score` | ≥0.9 | 0.7-0.9 | <0.7 | Are all required keywords present? |
| `faithfulness` | ≥0.8 | 0.6-0.8 | <0.6 | Is answer grounded in context? |
| `response_relevancy` | ≥0.8 | 0.6-0.8 | <0.6 | Does answer address the question? |
| `forbidden_claims_score` | 1.0 | 0.8-1.0 | <0.8 | Avoids known-incorrect claims? |

**Critical Combinations:**
- ✅ High `faithfulness` + High `context_relevance` = Grounded, relevant answer
- ❌ High `answer_correctness` + Low `faithfulness` = Hallucination
- ❌ High `context_relevance` + Low `answer_correctness` = Retrieved good docs but LLM didn't use them

---

## Field Initialization Defaults

```python
@dataclass
class EvaluationResult:
    # Required
    ticket_id: str
    
    # All metrics default to None
    query: Optional[str] = None
    url_f1: Optional[float] = None
    mrr: Optional[float] = None
    # ... etc
    
    # RAG tracking defaults to False
    rag_used: bool = False
    docs_retrieved: bool = False
    
    # Lists default to empty
    expected_keywords: Optional[list] = field(default_factory=list)
    expected_urls: Optional[list] = field(default_factory=list)
    # ... etc
    
    # Metadata defaults
    num_runs: int = 1
    high_variance_metrics: List[str] = field(default_factory=list)
```

---

## Related Classes

- **OkpMcpAgent**: Creates and uses `EvaluationResult` (see `OkpMcpAgent.md`)
- **MetricThresholds**: Threshold configuration for classification
- **APIResponse**: Raw API response (different from eval results)
- **TurnData**: Evaluation framework's internal data model

---

## Summary

**EvaluationResult in a Nutshell:**
- 📊 Container for evaluation metrics
- 🔍 Intelligent problem classification (retrieval vs answer)
- ✅ Grounding validation (prevents hallucination)
- 📈 Stability tracking (variance detection)
- 🎯 Prioritizes RAGAS context metrics over URL F1

**When You Care:**
- ✅ Reading diagnosis results from `diagnose()`
- ✅ Classifying problem type
- ✅ Comparing metrics over iterations
- ✅ Checking stability across runs
- ❌ Running evaluations (use `OkpMcpAgent`)
- ❌ Writing configs (use YAML)

**Key Takeaway:** `EvaluationResult` is the **metrics container** with intelligent classification. Use `.is_retrieval_problem`, `.is_answer_problem`, and `.is_answer_good_enough` to route fixes. Always check `.rag_used` and `.faithfulness` to prevent hallucination.

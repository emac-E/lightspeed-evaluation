# OkpMcpLLMAdvisor Class Reference

## Overview

`OkpMcpLLMAdvisor` is the **AI-powered suggestion engine** that uses Claude Agent SDK to analyze evaluation metrics and suggest code changes. It provides intelligent routing between tiered models (Haiku for classification, Sonnet for fixes, Opus for hard problems) to optimize costs and quality.

**Location:** `scripts/okp_mcp_llm_advisor.py`

**Purpose:** Generate targeted Solr config and prompt suggestions based on evaluation metrics

---

## When You'll Interact With OkpMcpLLMAdvisor

| Scenario | Need OkpMcpLLMAdvisor? |
|----------|------------------------|
| **Getting AI-powered fix suggestions** | ✅ Yes - for Solr and prompt changes |
| **Analyzing complex retrieval problems** | ✅ Yes - explains root causes |
| **Tiered model routing** | ✅ Yes - cost optimization |
| **Manual Solr tuning** | ❌ No - direct edits faster |
| **Running evaluations** | ❌ No - use EvaluationPipeline |
| **Diagnosing tickets** | ❌ No - use OkpMcpAgent |

**For AI-powered code suggestions: This is the primary class.**

---

## Class Definition

```python
class OkpMcpLLMAdvisor:
    """LLM-powered advisor for okp-mcp boost query suggestions.
    
    Uses Claude Agent SDK to analyze metrics and suggest code changes.
    Supports tiered model routing to optimize costs.
    """
```

**Dependencies:**
- `claude_agent_sdk` - For calling Claude with structured output
- Vertex AI credentials - For Claude API access

---

## Constructor

```python
def __init__(
    self,
    model: str = "claude-sonnet-4-6",
    okp_mcp_root: Optional[Path] = None,
    use_tiered_models: bool = True,
    simple_model: str = "claude-haiku-4-5-20251001",
    complex_model: str = "claude-opus-4-6",
):
    """Initialize LLM advisor.
    
    Args:
        model: Default model for suggestions
        okp_mcp_root: Path to okp-mcp repo (for reading config)
        use_tiered_models: Enable tiered model routing
        simple_model: Model for simple classification tasks
        complex_model: Model for complex problems
    """
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | `"claude-sonnet-4-6"` | Default model for fixes |
| `okp_mcp_root` | `Path` | `None` | Path to okp-mcp repo |
| `use_tiered_models` | `bool` | `True` | Enable smart routing |
| `simple_model` | `str` | `"claude-haiku-4-5-20251001"` | For classification |
| `complex_model` | `str` | `"claude-opus-4-6"` | For hard problems |

### Initialization Example

```python
from pathlib import Path
from scripts.okp_mcp_llm_advisor import OkpMcpLLMAdvisor

# Standard setup with tiered routing
advisor = OkpMcpLLMAdvisor(
    model="claude-sonnet-4-6",
    okp_mcp_root=Path.cwd().parent / "okp-mcp",
    use_tiered_models=True,
)

# Single model (no routing)
advisor = OkpMcpLLMAdvisor(
    model="claude-sonnet-4-6",
    use_tiered_models=False,
)

# Custom tier configuration
advisor = OkpMcpLLMAdvisor(
    model="claude-sonnet-4-6",
    use_tiered_models=True,
    simple_model="claude-haiku-4-5-20251001",  # Classification only
    complex_model="claude-opus-4-6",            # Escalation for hard problems
)
```

---

## Core Methods

### suggest_boost_query_changes()

Get AI-powered Solr configuration suggestions.

```python
async def suggest_boost_query_changes(
    self,
    metrics: MetricSummary
) -> SolrConfigSuggestion:
    """Suggest Solr eDismax config changes based on metrics.
    
    Args:
        metrics: Complete metric summary with diagnostics
        
    Returns:
        SolrConfigSuggestion with specific code change
    """
```

**Alias:** `suggest_solr_config_changes()` (same method, newer name)

**Usage:**

```python
from scripts.okp_mcp_llm_advisor import MetricSummary

# Prepare metrics
metrics = MetricSummary(
    ticket_id="RSPEED-2482",
    query="What DHCP server in RHEL 10?",
    url_f1=0.33,
    mrr=0.25,
    context_relevance=0.45,
    answer_correctness=0.60,
    rag_used=True,
    docs_retrieved=True,
    num_docs=5,
    expected_urls=["https://access.redhat.com/articles/kea-dhcp"],
    retrieved_urls=["https://access.redhat.com/articles/general-networking"],
    solr_explain={...},  # Solr scoring details
    solr_config_snapshot={...},  # Current config
)

# Get suggestion (async)
suggestion = await advisor.suggest_boost_query_changes(metrics)

# Apply suggestion
print(f"Reasoning: {suggestion.reasoning}")
print(f"Change: {suggestion.suggested_change}")
print(f"Code: {suggestion.code_snippet}")
print(f"Expected: {suggestion.expected_improvement}")
print(f"Confidence: {suggestion.confidence}")
```

**Example Output:**

```python
SolrConfigSuggestion(
    reasoning="Expected doc has 'kea' in title, but title boost is only 4.0. "
              "Retrieved docs have 'networking' in main_content. Need to increase "
              "title weight to prioritize title matches.",
    file_path="src/okp_mcp/solr.py",
    suggested_change="Increase title boost from 4.0 to 6.0",
    code_snippet='"qf": "title^6.0 main_content^2.0",',
    expected_improvement="URL F1 should increase from 0.33 to >0.7. "
                        "Expected doc should rank in top 3.",
    confidence="high"
)
```

**Tiered Routing:**
1. **Haiku** classifies problem complexity
2. **Sonnet** handles medium complexity (default)
3. **Opus** escalates for hard problems (if enabled)

---

### suggest_prompt_changes()

Get AI-powered system prompt suggestions.

```python
async def suggest_prompt_changes(
    self,
    metrics: MetricSummary
) -> PromptSuggestion:
    """Suggest system prompt modifications for answer quality.
    
    Args:
        metrics: Complete metric summary (must include response and expected_response)
        
    Returns:
        PromptSuggestion with specific prompt modification
    """
```

**Usage:**

```python
# Prepare metrics (answer problem)
metrics = MetricSummary(
    ticket_id="RSPEED-2482",
    query="What DHCP server in RHEL 10?",
    url_f1=0.85,  # Good retrieval
    context_relevance=0.90,  # Relevant docs retrieved
    answer_correctness=0.50,  # Poor answer quality!
    keywords_score=0.40,  # Missing keywords
    rag_used=True,
    docs_retrieved=True,
    num_docs=5,
    response="RHEL 10 supports DHCP...",  # Actual answer (vague)
    expected_response="Kea is the DHCP server in RHEL 10. ISC DHCP was removed.",
    expected_keywords=[["kea"], ["removed", "deprecated"]],
)

# Get prompt suggestion
suggestion = await advisor.suggest_prompt_changes(metrics)

print(f"Reasoning: {suggestion.reasoning}")
print(f"Change: {suggestion.suggested_change}")
print(f"Expected: {suggestion.expected_improvement}")
```

**Example Output:**

```python
PromptSuggestion(
    reasoning="Answer is vague ('supports DHCP') and missing required keywords "
              "'kea' and 'removed'. Retrieved context contains these terms. "
              "LLM is not using the provided documentation.",
    suggested_change="Add instruction: 'When describing DHCP in RHEL 10, "
                    "explicitly mention Kea as the replacement for ISC DHCP. "
                    "If a feature was removed, state this clearly.'",
    expected_improvement="keywords_score should increase from 0.40 to >0.8. "
                        "answer_correctness should reach >0.75.",
    confidence="medium"
)
```

---

### classify_problem_complexity()

Classify problem complexity for model routing.

```python
async def classify_problem_complexity(
    self,
    metrics: MetricSummary
) -> str:
    """Classify problem complexity using Haiku (fast, cheap).
    
    Args:
        metrics: Metric summary
        
    Returns:
        "simple", "medium", or "complex"
    """
```

**Usage:**

```python
complexity = await advisor.classify_problem_complexity(metrics)

if complexity == "simple":
    print("✅ Simple problem - use Haiku or manual fix")
elif complexity == "medium":
    print("⚙️  Medium problem - use Sonnet")
elif complexity == "complex":
    print("🔥 Complex problem - use Opus")
```

**Classification Logic:**

```
Simple:
- Single metric below threshold
- Clear root cause (e.g., wrong field boost)
- No iteration history

Medium:
- Multiple metrics below threshold
- Unclear root cause
- 1-2 previous failed attempts

Complex:
- All metrics poor
- Multiple failed fix attempts (3+)
- Contradictory signals (good retrieval, poor answer)
- High variance (unstable metrics)
```

**Cost Implications:**

| Complexity | Model | Cost/Request | Use Case |
|------------|-------|--------------|----------|
| Simple | Haiku | ~$0.0001 | Classification only |
| Medium | Sonnet | ~$0.01 | Most fixes |
| Complex | Opus | ~$0.10 | Escalation |

---

## Helper Classes

### SolrConfigSuggestion

Structured Solr configuration change.

```python
class SolrConfigSuggestion(BaseModel):
    """Structured suggestion for Solr eDismax configuration changes."""
    
    reasoning: str                # Why this change is needed
    file_path: str                # File to edit (usually "src/okp_mcp/solr.py")
    suggested_change: str         # Human-readable description
    code_snippet: str             # Exact Python code after change (REQUIRED)
    expected_improvement: str     # What metrics should improve
    confidence: str               # "high", "medium", or "low"
```

**Field Descriptions:**

| Field | Description | Example |
|-------|-------------|---------|
| `reasoning` | Why change is needed (based on metrics/explain) | `"Expected docs have 'uefi' in title, but title weight is low"` |
| `file_path` | Path to edit | `"src/okp_mcp/solr.py"` |
| `suggested_change` | Human-readable change | `"Increase title boost from 4.0 to 6.0"` |
| `code_snippet` | **Exact code after change** | `'"qf": "title^6.0 main_content^2.0",'` |
| `expected_improvement` | Predicted metric changes | `"URL F1 should increase from 0.2 to >0.5"` |
| `confidence` | LLM's confidence | `"high"` |

**Common Change Types:**

1. **Field Weights (qf)**
   ```python
   code_snippet = '"qf": "title^6.0 main_content^2.0",'
   ```

2. **Phrase Boosts (pf/pf2/pf3)**
   ```python
   code_snippet = '"pf": "title^12.0",'
   ```

3. **Minimum Match (mm)**
   ```python
   code_snippet = '"mm": "2<-1 5<60%",'
   ```

4. **Boost Multiplier**
   ```python
   code_snippet = 'multiplier *= 3.0  # boost compatibility queries'
   ```

5. **Boost Keywords List**
   ```python
   code_snippet = '_EXTRACTION_BOOST_KEYWORDS = ["compatibility", "matrix", "support"]'
   ```

---

### PromptSuggestion

Structured system prompt modification.

```python
class PromptSuggestion(BaseModel):
    """Structured suggestion for system prompt modifications."""
    
    reasoning: str                # Why prompt changes are needed
    suggested_change: str         # Specific prompt modification
    expected_improvement: str     # What metrics should improve
    confidence: str               # "high", "medium", or "low"
```

**Common Prompt Issues:**

| Issue | Suggested Change |
|-------|------------------|
| LLM ignoring context | `"ONLY use provided documentation"` |
| Keywords missing | `"Include specific terms: X, Y, Z"` |
| Wrong tone/format | Add output formatting instructions |
| Hallucination | `"Do not make assumptions beyond docs"` |
| Not grounded | `"Quote directly from provided context"` |

---

### MetricSummary

Comprehensive metrics package for LLM analysis.

```python
@dataclass
class MetricSummary:
    """Comprehensive evaluation metrics package for LLM-powered analysis."""
    
    # Core identification
    ticket_id: str
    query: str
    
    # Retrieval metrics
    url_f1: Optional[float]
    mrr: Optional[float]
    context_relevance: Optional[float]
    context_precision: Optional[float]
    
    # Answer quality metrics
    keywords_score: Optional[float]
    forbidden_claims_score: Optional[float]
    faithfulness: Optional[float]
    answer_correctness: Optional[float]
    response_relevancy: Optional[float]
    
    # RAG usage
    rag_used: bool
    docs_retrieved: bool
    num_docs: int
    
    # Ground truth
    response: Optional[str] = None
    expected_response: Optional[str] = None
    expected_keywords: Optional[list] = None
    expected_urls: Optional[list] = None
    forbidden_claims: Optional[list] = None
    retrieved_urls: Optional[list] = None
    contexts: Optional[str] = None
    
    # Diagnostics
    iteration_history: Optional[list] = None
    solr_explain: Optional[dict] = None
    solr_config_summary: Optional[str] = None
    solr_config_snapshot: Optional[dict] = None
    ranking_analysis: Optional[dict] = None
```

**Creating MetricSummary from EvaluationResult:**

```python
from scripts.okp_mcp_agent import EvaluationResult
from scripts.okp_mcp_llm_advisor import MetricSummary

def to_metric_summary(result: EvaluationResult) -> MetricSummary:
    """Convert EvaluationResult to MetricSummary."""
    return MetricSummary(
        ticket_id=result.ticket_id,
        query=result.query or "",
        url_f1=result.url_f1,
        mrr=result.mrr,
        context_relevance=result.context_relevance,
        context_precision=result.context_precision,
        keywords_score=result.keywords_score,
        forbidden_claims_score=result.forbidden_claims_score,
        faithfulness=result.faithfulness,
        answer_correctness=result.answer_correctness,
        response_relevancy=result.response_relevancy,
        rag_used=result.rag_used,
        docs_retrieved=result.docs_retrieved,
        num_docs=result.num_docs_retrieved(),
        response=result.response,
        expected_response=result.expected_response,
        expected_keywords=result.expected_keywords,
        expected_urls=result.expected_urls,
        forbidden_claims=result.forbidden_claims,
        retrieved_urls=result.retrieved_urls,
        contexts=result.contexts,
        solr_check=result.solr_check,
    )
```

---

## Usage Patterns

### Pattern 1: Get Solr Suggestion

```python
import asyncio
from scripts.okp_mcp_agent import OkpMcpAgent
from scripts.okp_mcp_llm_advisor import OkpMcpLLMAdvisor, MetricSummary

async def main():
    # Setup
    agent = OkpMcpAgent(...)
    advisor = OkpMcpLLMAdvisor(okp_mcp_root=agent.okp_mcp_root)
    
    # Diagnose
    result = agent.diagnose("RSPEED-2482")
    
    if result.is_retrieval_problem:
        # Convert to MetricSummary
        metrics = to_metric_summary(result)
        
        # Add Solr diagnostics
        metrics.solr_explain = agent.solr_analyzer.get_explain_output(
            result.query, num_docs=20
        )
        metrics.solr_config_snapshot = agent.extract_solr_config_snapshot(
            result.ticket_id
        )
        
        # Get AI suggestion
        suggestion = await advisor.suggest_boost_query_changes(metrics)
        
        # Apply suggestion
        print(f"\n💡 AI Suggestion:")
        print(f"   {suggestion.suggested_change}")
        print(f"   Confidence: {suggestion.confidence}")
        print(f"\n📝 Code:")
        print(f"   {suggestion.code_snippet}")
        
        # Manual or automated application
        agent.apply_code_change(suggestion)

asyncio.run(main())
```

### Pattern 2: Tiered Model Routing

```python
async def suggest_with_routing(advisor: OkpMcpLLMAdvisor, metrics: MetricSummary):
    """Get suggestion with smart model routing."""
    
    # Classify complexity (Haiku - fast, cheap)
    complexity = await advisor.classify_problem_complexity(metrics)
    print(f"Complexity: {complexity}")
    
    if complexity == "simple":
        print("⚡ Simple problem - using manual heuristics")
        # Use rule-based fix instead of LLM
        return None
    
    elif complexity == "medium":
        print("⚙️  Medium problem - using Sonnet")
        advisor.model = "claude-sonnet-4-6"
        
    elif complexity == "complex":
        print("🔥 Complex problem - escalating to Opus")
        advisor.model = "claude-opus-4-6"
    
    # Get suggestion with appropriate model
    suggestion = await advisor.suggest_boost_query_changes(metrics)
    return suggestion
```

### Pattern 3: Iterative Improvement with History

```python
async def iterative_fix(advisor, ticket_id, max_iterations=5):
    """Iterative fix with history tracking."""
    
    iteration_history = []
    
    for i in range(max_iterations):
        # Diagnose
        result = agent.diagnose(ticket_id)
        
        # Build metrics with history
        metrics = to_metric_summary(result)
        metrics.iteration_history = iteration_history
        
        # Get suggestion
        suggestion = await advisor.suggest_boost_query_changes(metrics)
        
        # Apply and track
        agent.apply_code_change(suggestion)
        iteration_history.append({
            "iteration": i + 1,
            "metrics": {
                "url_f1": result.url_f1,
                "context_relevance": result.context_relevance,
            },
            "change": suggestion.suggested_change,
        })
        
        # Check if fixed
        if result.is_answer_good_enough:
            print(f"✅ Fixed in {i+1} iterations")
            break
```

---

## Environment Requirements

### Required Environment Variables

```bash
# For Claude advisor
export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id

# Authenticate with gcloud
gcloud auth application-default login
```

### Check Availability

```python
from scripts.okp_mcp_llm_advisor import LLM_ADVISOR_AVAILABLE

if LLM_ADVISOR_AVAILABLE:
    print("✅ LLM advisor available")
else:
    print("❌ LLM advisor not available")
    print("   Set ANTHROPIC_VERTEX_PROJECT_ID and run gcloud auth")
```

---

## Performance & Costs

### Model Comparison

| Model | Speed | Cost/Request | Use Case |
|-------|-------|--------------|----------|
| Haiku 4.5 | 1-2s | ~$0.0001 | Classification only |
| Sonnet 4.6 | 3-5s | ~$0.01 | Default fixes |
| Opus 4.6 | 10-15s | ~$0.10 | Hard problems |

### Cost Optimization Strategies

1. **Enable Tiered Routing**
   ```python
   advisor = OkpMcpLLMAdvisor(use_tiered_models=True)
   # Saves ~90% on classification vs using Sonnet
   ```

2. **Use Simple Model for Easy Problems**
   ```python
   complexity = await advisor.classify_problem_complexity(metrics)
   if complexity == "simple":
       # Skip LLM, use rule-based fix
       return manual_fix(metrics)
   ```

3. **Cache Suggestions**
   ```python
   # Reuse suggestions for similar problems
   cache_key = f"{metrics.query}_{metrics.url_f1}"
   if cache_key in suggestion_cache:
       return suggestion_cache[cache_key]
   ```

---

## Debugging Tips

### Problem: ImportError on claude_agent_sdk

**Symptom:** `ImportError: No module named 'claude_agent_sdk'`

**Fix:**
```bash
pip install claude-agent-sdk
# or
uv add claude-agent-sdk
```

---

### Problem: Vertex AI Authentication Failure

**Symptom:** `google.auth.exceptions.DefaultCredentialsError`

**Check:**
```bash
echo $ANTHROPIC_VERTEX_PROJECT_ID
gcloud auth application-default print-access-token
```

**Fix:**
```bash
export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id
gcloud auth application-default login
```

---

### Problem: Suggestion Code Snippet Is Wrong

**Symptom:** Applying suggestion causes syntax errors

**Possible Causes:**
1. LLM generated incomplete code
2. Context was too long, truncated
3. Wrong file_path returned

**Debug:**
```python
print(f"File: {suggestion.file_path}")
print(f"Code: {suggestion.code_snippet}")
print(f"Confidence: {suggestion.confidence}")

if suggestion.confidence == "low":
    print("⚠️  Low confidence, manual review recommended")
```

---

### Problem: Suggestions Don't Improve Metrics

**Symptom:** Applied suggestion, but metrics don't improve

**Possible Causes:**
1. LLM misunderstood the problem
2. Solr explain not provided (missing root cause)
3. Iteration history not passed (repeating same mistake)

**Debug:**
```python
# Ensure Solr diagnostics are provided
if not metrics.solr_explain:
    print("⚠️  Missing Solr explain output")
    metrics.solr_explain = agent.solr_analyzer.get_explain_output(
        metrics.query, num_docs=20
    )

# Ensure iteration history is passed
if not metrics.iteration_history:
    print("⚠️  No iteration history - LLM can't learn from past")
```

---

## Related Classes

- **OkpMcpAgent**: Uses advisor for suggestions (see `OkpMcpAgent.md`)
- **EvaluationResult**: Source of metrics (see `EvaluationResult.md`)
- **SolrConfigAnalyzer**: Provides Solr explain output
- **SolrConfigSuggestion**: Solr change suggestion (Pydantic model)
- **PromptSuggestion**: Prompt change suggestion (Pydantic model)
- **MetricSummary**: Metrics package (dataclass)

---

## Summary

**OkpMcpLLMAdvisor in a Nutshell:**
- 🤖 AI-powered Solr and prompt suggestions
- 🎯 Tiered model routing (Haiku → Sonnet → Opus)
- 📊 Analyzes metrics + Solr explain output
- 💡 Returns structured code changes
- 💰 Cost-optimized ($0.0001 - $0.10/request)

**When You Care:**
- ✅ Getting AI-powered fix suggestions
- ✅ Analyzing complex retrieval problems
- ✅ Optimizing LLM costs with tiering
- ❌ Manual Solr tuning (direct edits faster)
- ❌ Running evaluations (use EvaluationPipeline)

**Key Takeaway:** `OkpMcpLLMAdvisor` is the **AI brain** for autonomous ticket fixes. Use `suggest_boost_query_changes()` for Solr issues and `suggest_prompt_changes()` for answer quality. Enable `use_tiered_models=True` to optimize costs.

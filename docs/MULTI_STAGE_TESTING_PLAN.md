# Multi-Stage Testing Architecture - Implementation Plan

## Overview

Implement a **dual-mode, multi-stage autonomous testing workflow** for okp-mcp RSPEED ticket fixing.

## Two Testing Modes

### Mode 1: Retrieval-Only (Fast - ~30 seconds)
**Purpose:** Debug boost queries for document retrieval
**Endpoint:** `http://localhost:8001` (okp-mcp MCP server directly)
**Config:** `system_mcp_direct.yaml`
**Metrics Available:**
- `custom:url_retrieval_eval` (URL F1, MRR)
- `ragas:context_relevance`
- `ragas:context_precision_without_reference`

**Use For:** Fast iteration on boost query tuning

### Mode 2: Full Pipeline (Complete - ~3-5 minutes)
**Purpose:** Validate complete RAG pipeline including answer quality
**Endpoint:** `/v1/infer` (full lightspeed-stack)
**Config:** `system.yaml`
**Metrics Available:** ALL metrics including:

**Retrieval Metrics:**
- `custom:url_retrieval_eval` (URL F1, MRR)
- `ragas:context_relevance`
- `ragas:context_precision_without_reference`

**Answer Quality Metrics (NEW - add these):**
- `ragas:faithfulness` - Answer grounded in retrieved context
- `custom:answer_correctness` - Semantic similarity to expected answer
- `ragas:response_relevancy` - Answer addresses the question
- `custom:keywords_eval` - Required keywords present
- `custom:forbidden_claims_eval` - No hallucinations

**Use For:** Complete validation before merging

## Three-Stage Testing Workflow

```
┌──────────────────────────────────────────────────────────┐
│ STAGE 1: Fix Individual Ticket (Iterative)              │
│ Config: functional_tests_full.yaml (20 questions)       │
│ Focus: Single ticket (e.g., RSPEED-2482)                │
│                                                          │
│ Sub-stages:                                              │
│  1a. Full eval (mode 2) → Diagnose problem type         │
│  1b. If retrieval problem:                               │
│      - Fast iteration (mode 1): Tune boost queries       │
│      - Loop: Edit → Restart → Test (30 sec/iter)        │
│      - Exit when: URL F1 > 0.7                          │
│  1c. Full validation (mode 2): Check answer quality     │
│      - Must pass: Faithfulness, Answer Correctness,     │
│                   Response Relevancy, Keywords           │
│                                                          │
│ LLM Advisor Role:                                        │
│  - Suggest boost query changes (retrieval issues)       │
│  - Suggest prompt changes (answer issues)               │
│  - Use NEW metrics for better insights                  │
│                                                          │
│ Exit Criteria:                                           │
│  ✅ URL F1 > 0.7                                        │
│  ✅ Faithfulness > 0.8                                  │
│  ✅ Answer Correctness > 0.75                           │
│  ✅ Response Relevancy > 0.8                            │
│  ✅ Keywords = 1.0                                      │
│  ✅ Forbidden Claims = 1.0                              │
└──────────────┬───────────────────────────────────────────┘
               │ PASSES ✅
               ▼
┌──────────────────────────────────────────────────────────┐
│ STAGE 2: Regression Validation (Broad Coverage)         │
│ Config: CLA_tests.yaml (96 questions)                   │
│ Mode: Full pipeline (mode 2)                            │
│                                                          │
│ Purpose: Ensure fix didn't break other functionality    │
│                                                          │
│ Checks:                                                  │
│  - Pass rate doesn't drop                               │
│  - No new failures introduced                           │
│  - Mean scores across all metrics stable or improved    │
│                                                          │
│ Exit Criteria:                                           │
│  ✅ Pass rate >= baseline                              │
│  ✅ No regressions (score drops > 0.05)                │
│  ✅ Target ticket still passing                        │
└──────────────┬───────────────────────────────────────────┘
               │ PASSES ✅
               ▼
┌──────────────────────────────────────────────────────────┐
│ STAGE 3: Negative Test Validation (Future)              │
│ Config: negative_tests.yaml                             │
│ Mode: Full pipeline (mode 2)                            │
│                                                          │
│ Purpose: Ensure system rejects bad/unsafe queries       │
│                                                          │
│ Exit Criteria:                                           │
│  ✅ System properly rejects invalid queries            │
│  ✅ No false positives on edge cases                   │
└──────────────────────────────────────────────────────────┘
```

## Code Changes Required

### 1. Update `okp_mcp_llm_advisor.py`

Add three new metrics to `MetricSummary`:

```python
@dataclass
class MetricSummary:
    # ... existing fields ...

    # Add these:
    faithfulness: Optional[float] = None
    answer_correctness: Optional[float] = None
    response_relevancy: Optional[float] = None
```

Update `to_prompt_context()` method:

```python
def to_prompt_context(self) -> str:
    # ... existing code ...

    # Add after "Answer Metrics:" section:
    if self.faithfulness is not None:
        lines.append(f"  - Faithfulness: {self.faithfulness:.2f} (threshold: 0.8)")
    if self.answer_correctness is not None:
        lines.append(f"  - Answer Correctness: {self.answer_correctness:.2f} (threshold: 0.75)")
    if self.response_relevancy is not None:
        lines.append(f"  - Response Relevancy: {self.response_relevancy:.2f} (threshold: 0.8)")
```

Update system prompts for both agents to mention these metrics.

### 2. Update `okp_mcp_agent.py`

#### 2a. Update EvaluationResult (DONE ✅)

```python
@dataclass
class EvaluationResult:
    # Added three new metrics
    faithfulness: Optional[float] = None
    answer_correctness: Optional[float] = None
    response_relevancy: Optional[float] = None
```

#### 2b. Update parse_results() (DONE ✅)

```python
elif metric == "ragas:faithfulness":
    result.faithfulness = score
elif metric == "custom:answer_correctness":
    result.answer_correctness = score
elif metric == "ragas:response_relevancy":
    result.response_relevancy = score
```

#### 2c. Update MetricSummary conversion (TODO)

In `_get_llm_boost_suggestion()` and `_get_llm_prompt_suggestion()`:

```python
metrics = MetricSummary(
    # ... existing fields ...
    faithfulness=result.faithfulness,
    answer_correctness=result.answer_correctness,
    response_relevancy=result.response_relevancy,
)
```

#### 2d. Add multi-stage validation (TODO)

```python
def fix_ticket_multi_stage(
    self,
    ticket_id: str,
    max_retrieval_iterations: int = 10,
    validate_cla_tests: bool = True,
):
    """Multi-stage ticket fixing with validation.

    Stage 1: Fix individual ticket
      1a. Diagnose (full mode)
      1b. If retrieval problem: Fast iteration (retrieval-only mode)
      1c. Validate answer quality (full mode)

    Stage 2: Validate regressions (CLA_tests.yaml)

    Stage 3 (future): Negative tests
    """

    # Stage 1a: Diagnose
    result = self.diagnose(ticket_id, use_existing=False)

    if result.is_retrieval_problem:
        # Stage 1b: Fast retrieval iteration
        for i in range(max_retrieval_iterations):
            # Get LLM suggestion
            # Apply changes (manual or automated)
            # Restart okp-mcp
            # Run retrieval-only eval (fast ~30 sec)
            result = self.run_retrieval_eval_and_parse(ticket_id)

            if result.url_f1 > 0.7:
                break

    # Stage 1c: Full validation
    result = self.diagnose(ticket_id, use_existing=False)

    if not result.passes_all_thresholds():
        print("❌ Answer quality issues remain")
        return False

    # Stage 2: CLA test validation
    if validate_cla_tests:
        print("\n" + "=" * 80)
        print("STAGE 2: Regression Validation (CLA_tests.yaml)")
        print("=" * 80)

        baseline = self.get_baseline_results("CLA_tests.yaml")
        current = self.run_full_eval_and_parse("CLA_tests.yaml")

        regressions = self.find_regressions(baseline, current)

        if regressions:
            print("⚠️  Regressions detected:")
            for ticket, delta in regressions.items():
                print(f"  {ticket}: {delta:.2f}")
            return False

    print("\n✅ All stages passed!")
    return True
```

### 3. Update Test Configs

#### 3a. Add metrics to `functional_tests_full.yaml`

```yaml
turn_metrics:
  - custom:url_retrieval_eval
  - ragas:context_relevance
  - ragas:context_precision_without_reference
  - ragas:faithfulness              # NEW
  - custom:answer_correctness       # NEW
  - ragas:response_relevancy        # NEW
  - custom:keywords_eval
  - custom:forbidden_claims_eval
```

#### 3b. Ensure `jira_incorrect_answers.yaml` has `expected_response`

This file already has `expected_response` fields which are used by `custom:answer_correctness`.

### 4. Testing Strategy

**Development/Testing:**
1. Use retrieval-only mode for rapid boost query iteration
2. Use full mode for final validation

**CI/Production:**
1. Always use full mode for complete validation
2. Run both functional and CLA tests

## Implementation Timeline

### Today (Completed ✅)
- [x] LLM advisor integrated into agent
- [x] Tested with retrieval and answer problems
- [x] Added new metrics to EvaluationResult
- [x] Added parsing for new metrics

### Tomorrow (To Do)
1. **Move to okp-mcp repo**
   - Create `okp-mcp/tools/autonomous_agent/`
   - Move scripts
   - Add requirements.txt
   - Update docs

2. **Complete metric integration**
   - Update MetricSummary in llm_advisor.py
   - Update metric conversion in agent.py
   - Test with CLA_tests.yaml

3. **Implement multi-stage workflow**
   - Add `fix_ticket_multi_stage()` method
   - Add CLA validation logic
   - Add regression detection

4. **Test and merge**
   - Test complete workflow with RSPEED-2482
   - Validate no regressions in CLA tests
   - Create PR
   - Merge

## Metrics Correlation Insights

Based on your correlation analysis (from `analysis_output/`):

**Independent signals (low correlation = unique insights):**
- `ragas:faithfulness` - Different from keywords; catches when LLM adds unsupported info
- `custom:answer_correctness` - Semantic comparison to expected answer (LLM judge)
- `ragas:response_relevancy` - Catches when answer is correct but doesn't address question

**Why these three:**
1. **Faithfulness**: Prevents hallucination (answer must be in retrieved docs)
2. **Answer Correctness**: Validates against known good answers (critical for jira_incorrect_answers.yaml)
3. **Response Relevancy**: Ensures answer actually addresses the user's question

## Benefits

1. **Fast iteration**: Retrieval-only mode for rapid boost query tuning (~30 sec)
2. **Complete validation**: Full mode ensures answer quality before merge
3. **Multi-stage safety**: CLA tests catch regressions before production
4. **Better insights**: Three new metrics provide independent signals
5. **Efficient RAG**: Optimize both retrieval AND answer quality
6. **Happy customers**: Good docs retrieved + good answers generated

## References

- Retrieval-only config: `config/system_mcp_direct.yaml`
- Full config: `config/system.yaml`
- Functional tests: `config/okp_mcp_test_suites/functional_tests_full.yaml`
- CLA tests: `config/CLA_tests.yaml`
- Expected answers: `config/jira_incorrect_answers.yaml`
- Correlation analysis: `analysis_output/evaluation_*_correlation_*.csv`

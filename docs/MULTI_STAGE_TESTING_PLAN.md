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

## Iteration Strategy & Safety Mechanisms

### Overview

The agent uses **tiered iteration budgets** with **model escalation** to prevent infinite loops and ensure efficient problem solving.

### Two Separate Iteration Budgets

```python
# Primary ticket fix
PRIMARY_FIX_MAX_ITERATIONS = 5      # Max attempts to fix original RSPEED ticket
REGRESSION_FIX_MAX_ITERATIONS = 3   # Max attempts per individual regression

# Model escalation
ESCALATION_THRESHOLD = 2            # Failed attempts before escalating to better model
PLATEAU_THRESHOLD = 2               # Iterations without improvement = plateau
MIN_IMPROVEMENT_THRESHOLD = 0.05    # Metric must improve by at least 0.05
```

**Key Principle:** Primary fixes and regression fixes have **separate counters**. Fixing regressions does NOT count against the primary fix budget.

### Model Escalation Path

```
Iteration 1-2: Sonnet (medium complexity)
    ↓ (if no improvement after 2 attempts)
Iteration 3-4: Opus (complex cases)
    ↓ (if no improvement after 2 attempts)
Iteration 5:   Escalate to HUMAN
```

### Complete Feedback Loop (Primary Fix)

```
Iteration 1: (Model: Sonnet)
  1. diagnose(ticket_id) → URL F1 = 0.33 (RETRIEVAL PROBLEM)
  2. get_llm_suggestion(model="sonnet") → "Boost documentKind:solution to 4.0"
  3. apply_code_change() → Edit src/okp_mcp/portal.py
  4. restart_okp_mcp() → Restart service
  5. re_evaluate(ticket_id) → Run evaluation again
  6. check_improvement() → URL F1 = 0.55 (improved 0.33 → 0.55, but < 0.7)
  7. attempts_at_current_model = 1, continue...

Iteration 2: (Model: Sonnet)
  5. re_evaluate() → URL F1 = 0.54 (NOT improved: 0.55 → 0.54)
  6. check_improvement() → NO IMPROVEMENT
  7. attempts_at_current_model = 2 → ESCALATE MODEL!

Iteration 3: (Model: Opus - escalated!)
  2. get_llm_suggestion(model="opus") → "Add product:RHEL filter + boost to 6.0"
  3. apply_code_change()
  4. restart_okp_mcp()
  5. re_evaluate() → URL F1 = 0.85
  6. check_improvement() → PASSED! (0.85 > 0.7 threshold)
  ✅ PRIMARY TICKET FIXED in 3 iterations!
```

### Regression Handling (New Iteration Budget)

After primary fix passes, run CLA tests to detect regressions:

```
Stage 2: Run CLA_tests.yaml
  Result: 2 regressions detected
    - RSPEED-1234: Keywords dropped 0.8 → 0.6
    - RSPEED-5678: URL F1 dropped 0.9 → 0.65

Fix Regression 1: RSPEED-1234 (COUNTER RESETS TO 0)
  Max 3 attempts, start with Sonnet again

  Attempt 1: Try fix with Sonnet → Keywords = 0.7 (improved but < 0.8)
  Attempt 2: Try fix with Sonnet → Keywords = 0.69 (no improvement) → ESCALATE
  Attempt 3: Try fix with Opus → Keywords = 0.85 (FIXED!)
  ✅ Regression 1 fixed

Fix Regression 2: RSPEED-5678 (COUNTER RESETS TO 0 AGAIN)
  Max 3 attempts, start with Sonnet

  Attempt 1-3: All fail to improve URL F1
  ❌ Could not fix regression after 3 attempts
  🔄 REVERT primary fix commit
  🚨 ESCALATE TO HUMAN
```

### Safety Mechanisms

#### 1. Plateau Detection

```python
def detected_plateau(metric_history: List[float]) -> bool:
    """Detect if metrics stopped improving for N consecutive iterations."""
    if len(metric_history) < PLATEAU_THRESHOLD:
        return False

    # Check last N iterations
    last_n = metric_history[-PLATEAU_THRESHOLD:]
    best_in_last_n = max(last_n)

    # If best metric in last N attempts equals N attempts ago → plateau
    return best_in_last_n == last_n[0]
```

**Action:** If plateau detected → escalate to better model or human

#### 2. Model Escalation

```python
def escalate_model(current_model: str, attempts_at_current: int) -> Optional[str]:
    """Escalate to better model after failed attempts."""
    if attempts_at_current < ESCALATION_THRESHOLD:
        return current_model  # Stay at current level

    # Escalation path: Sonnet → Opus → Human
    if current_model == "sonnet":
        return "opus"
    elif current_model == "opus":
        return None  # Escalate to human

    return current_model
```

#### 3. Improvement Check

```python
def metrics_improved(new: EvaluationResult, old: EvaluationResult) -> bool:
    """Check if metrics improved (for the specific problem type)."""
    if old is None:
        return True  # First iteration

    # For retrieval problems, check retrieval metrics
    if new.is_retrieval_problem:
        improvement = max(
            new.url_f1 - old.url_f1,
            new.mrr - old.mrr,
            new.context_relevance - old.context_relevance
        )
        return improvement >= MIN_IMPROVEMENT_THRESHOLD

    # For answer problems, check answer metrics
    elif new.is_answer_problem:
        improvement = max(
            (new.keywords_score or 0) - (old.keywords_score or 0),
            (new.answer_correctness or 0) - (old.answer_correctness or 0),
            (new.faithfulness or 0) - (old.faithfulness or 0)
        )
        return improvement >= MIN_IMPROVEMENT_THRESHOLD

    return False
```

**Key:** Improvement must be >= 0.05 to count (prevents tiny fluctuations from resetting escalation)

#### 4. Regression Revert Policy

```python
def handle_regressions(primary_fix_commit: str, regressions: List[str]) -> bool:
    """Try to fix regressions, revert if can't fix."""
    for regression_ticket in regressions:
        fixed = fix_ticket_with_budget(
            ticket_id=regression_ticket,
            max_iterations=REGRESSION_FIX_MAX_ITERATIONS,
            starting_model="sonnet",  # Reset to Sonnet for each regression
            context="regression"
        )

        if not fixed:
            print(f"❌ Could not fix regression {regression_ticket}")
            print(f"🔄 Reverting primary fix commit {primary_fix_commit}")
            run_command(["git", "revert", primary_fix_commit], cwd=okp_mcp_root)
            print("🚨 ESCALATING TO HUMAN - regression cannot be fixed")
            return False

    return True  # All regressions fixed
```

**Critical:** If ANY regression cannot be fixed → revert entire primary fix → escalate to human

### Exit Conditions Summary

**Primary Fix Stops When:**
- ✅ **Success:** All metrics pass thresholds
- ⏱️ **Max iterations:** 5 attempts exhausted → Escalate to human
- ⏸️ **Plateau:** No improvement for 2 consecutive iterations → Escalate to human
- 🔄 **Model exhausted:** Opus failed after 2 attempts → Escalate to human

**Regression Fix Stops When (per regression):**
- ✅ **Success:** Regression fixed within 3 attempts → Continue to next regression
- ❌ **Failed:** 3 attempts exhausted → **REVERT primary fix** → Escalate to human

**Why Revert on Regression Failure:**
- Primary fix improved target ticket BUT broke other functionality
- Cannot ship a change that causes regressions
- Better to revert and let human solve the complex tradeoff

### Model Configuration

```python
TIER_MODELS = {
    "simple": "claude-haiku-4-5@20251001",      # Classification only (not for fixes)
    "medium": "claude-sonnet-4-5@20250929",     # Default for all fixes
    "complex": "claude-opus-4-5@20250929",      # Escalation for hard problems
}
```

### Cost Optimization

**Estimated costs per primary fix (5 iteration budget):**
- Classification (Haiku): ~$0.0001 × 1 = $0.0001
- Iteration 1-2 (Sonnet): ~$0.01 × 2 = $0.02
- Iteration 3-5 (Opus): ~$0.03 × 3 = $0.09
- **Max cost per ticket: ~$0.11** (if all 5 iterations used)
- **Typical cost: ~$0.02-$0.04** (most tickets fixed in 2-3 iterations)

**Why tiered routing matters:**
- Starting with Opus: $0.03 × 5 = $0.15 per ticket (36% more expensive)
- Haiku for everything: Cannot solve complex problems reliably

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

#### 2c. Update MetricSummary conversion (DONE ✅)

In `_get_llm_boost_suggestion()` and `_get_llm_prompt_suggestion()`:

```python
metrics = MetricSummary(
    # ... existing fields ...
    faithfulness=result.faithfulness,
    answer_correctness=result.answer_correctness,
    response_relevancy=result.response_relevancy,
)
```

#### 2d. Add iteration constants (TODO)

```python
# Add to top of okp_mcp_agent.py
PRIMARY_FIX_MAX_ITERATIONS = 5
REGRESSION_FIX_MAX_ITERATIONS = 3
ESCALATION_THRESHOLD = 2
PLATEAU_THRESHOLD = 2
MIN_IMPROVEMENT_THRESHOLD = 0.05

TIER_MODELS = {
    "simple": "claude-haiku-4-5@20251001",
    "medium": "claude-sonnet-4-5@20250929",
    "complex": "claude-opus-4-5@20250929",
}
```

#### 2e. Add code editing method (TODO)

```python
def apply_code_change(self, suggestion: BoostQuerySuggestion) -> bool:
    """Apply LLM-suggested code change to okp-mcp files.

    Args:
        suggestion: Structured suggestion with file path and change

    Returns:
        True if change applied successfully
    """
    file_path = self.okp_mcp_root / suggestion.file_path

    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return False

    # TODO: Implement actual code editing
    # Options:
    #  1. Use AST manipulation for Python files
    #  2. Use regex for simple replacements
    #  3. Let Claude Code edit the file (safer, gets approval)

    print(f"📝 Would apply change to: {file_path}")
    print(f"   Change: {suggestion.suggested_change}")

    if self.interactive:
        confirm = input("Apply this change? (y/n): ")
        if confirm.lower() != 'y':
            return False

    # Apply change here...
    return True
```

#### 2f. Add improvement checking (TODO)

```python
def metrics_improved(self, new: EvaluationResult, old: EvaluationResult) -> bool:
    """Check if metrics improved significantly."""
    if old is None:
        return True

    # For retrieval problems
    if new.is_retrieval_problem:
        improvement = max(
            (new.url_f1 or 0) - (old.url_f1 or 0),
            (new.mrr or 0) - (old.mrr or 0),
            (new.context_relevance or 0) - (old.context_relevance or 0)
        )
        return improvement >= MIN_IMPROVEMENT_THRESHOLD

    # For answer problems
    elif new.is_answer_problem:
        improvement = max(
            (new.keywords_score or 0) - (old.keywords_score or 0),
            (new.answer_correctness or 0) - (old.answer_correctness or 0),
            (new.faithfulness or 0) - (old.faithfulness or 0)
        )
        return improvement >= MIN_IMPROVEMENT_THRESHOLD

    return False

def detected_plateau(self, metric_history: List[float]) -> bool:
    """Detect if metrics plateaued."""
    if len(metric_history) < PLATEAU_THRESHOLD:
        return False

    last_n = metric_history[-PLATEAU_THRESHOLD:]
    return max(last_n) == last_n[0]

def escalate_model(self, current_model: str, attempts: int) -> Optional[str]:
    """Escalate to better model after failed attempts."""
    if attempts < ESCALATION_THRESHOLD:
        return current_model

    if current_model == "medium":
        return "complex"
    elif current_model == "complex":
        return None  # Escalate to human

    return current_model
```

#### 2g. Add iteration loop (TODO - CRITICAL)

```python
def fix_ticket_with_iteration(
    self,
    ticket_id: str,
    max_iterations: int = PRIMARY_FIX_MAX_ITERATIONS,
    starting_model: str = "medium",
    context: str = "primary"
) -> bool:
    """Fix a ticket with automatic iteration and model escalation.

    Args:
        ticket_id: RSPEED ticket ID
        max_iterations: Max attempts (5 for primary, 3 for regressions)
        starting_model: Starting model tier (medium or complex)
        context: "primary" or "regression" (for logging)

    Returns:
        True if ticket fixed (all thresholds passed)
    """
    print(f"\n{'='*80}")
    print(f"FIXING {context.upper()}: {ticket_id}")
    print(f"{'='*80}")

    # Initial diagnosis
    previous_result = self.diagnose(ticket_id, use_existing=False)

    if not (previous_result.is_retrieval_problem or previous_result.is_answer_problem):
        print("✅ Already passing, nothing to fix")
        return True

    # Track metrics for plateau detection
    metric_history = []
    current_model = starting_model
    attempts_at_current_model = 0

    for iteration in range(1, max_iterations + 1):
        print(f"\n--- Iteration {iteration}/{max_iterations} (Model: {current_model}) ---")

        # Get LLM suggestion
        if previous_result.is_retrieval_problem:
            suggestion = self._get_llm_boost_suggestion_object(
                previous_result,
                model=TIER_MODELS[current_model]
            )
        else:
            suggestion = self._get_llm_prompt_suggestion_object(
                previous_result,
                model=TIER_MODELS[current_model]
            )

        # Apply code change
        if not self.apply_code_change(suggestion):
            print("❌ Change not applied, stopping")
            return False

        # Restart service
        self.restart_okp_mcp()

        # Re-evaluate
        current_result = self.diagnose(ticket_id, use_existing=False)

        # Track primary metric
        if current_result.is_retrieval_problem:
            metric_history.append(current_result.url_f1 or 0)
        else:
            metric_history.append(current_result.answer_correctness or 0)

        # Check if fixed
        if current_result.passes_all_thresholds():
            print(f"✅ FIXED in {iteration} iterations!")
            return True

        # Check if improved
        improved = self.metrics_improved(current_result, previous_result)

        if improved:
            print(f"📈 Metrics improved! Continuing...")
            attempts_at_current_model = 0  # Reset escalation counter
        else:
            print(f"📉 No improvement")
            attempts_at_current_model += 1

        # Check for plateau
        if self.detected_plateau(metric_history):
            print(f"⏸️  Plateau detected (no improvement for {PLATEAU_THRESHOLD} iterations)")
            attempts_at_current_model = ESCALATION_THRESHOLD  # Force escalation

        # Escalate model if needed
        new_model = self.escalate_model(current_model, attempts_at_current_model)
        if new_model is None:
            print("🚨 All models exhausted, escalating to HUMAN")
            return False
        elif new_model != current_model:
            print(f"🔼 Escalating from {current_model} to {new_model}")
            current_model = new_model
            attempts_at_current_model = 0

        previous_result = current_result

    print(f"⏱️  Max iterations ({max_iterations}) reached")
    return False

def fix_ticket_multi_stage(
    self,
    ticket_id: str,
    validate_cla_tests: bool = True,
):
    """Multi-stage ticket fixing: Primary fix → CLA validation → Regression fixes.

    Stage 1: Fix primary ticket with iteration loop
    Stage 2: Validate against CLA tests
    Stage 3: Fix any regressions (with separate iteration budgets)
    """
    print(f"\n{'='*80}")
    print(f"MULTI-STAGE FIX: {ticket_id}")
    print(f"{'='*80}")

    # Stage 1: Fix primary ticket
    primary_fixed = self.fix_ticket_with_iteration(
        ticket_id=ticket_id,
        max_iterations=PRIMARY_FIX_MAX_ITERATIONS,
        context="primary"
    )

    if not primary_fixed:
        print("❌ Could not fix primary ticket")
        return False

    # Capture commit for potential revert
    primary_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=self.okp_mcp_root,
        text=True
    ).strip()

    # Stage 2: Validate CLA tests
    if not validate_cla_tests:
        print("✅ Primary ticket fixed (CLA validation skipped)")
        return True

    print(f"\n{'='*80}")
    print("STAGE 2: CLA Regression Validation")
    print(f"{'='*80}")

    baseline = self.load_baseline_metrics()  # TODO: implement
    current = self.run_cla_tests_and_parse()  # TODO: implement
    regressions = self.find_regressions(baseline, current)  # TODO: implement

    if not regressions:
        print("✅ No regressions detected!")
        return True

    # Stage 3: Fix regressions
    print(f"\n⚠️  {len(regressions)} regressions detected:")
    for reg_ticket, delta in regressions.items():
        print(f"  - {reg_ticket}: {delta:.2f}")

    for reg_ticket in regressions.keys():
        print(f"\n{'='*80}")
        print(f"Fixing Regression: {reg_ticket}")
        print(f"{'='*80}")

        fixed = self.fix_ticket_with_iteration(
            ticket_id=reg_ticket,
            max_iterations=REGRESSION_FIX_MAX_ITERATIONS,
            starting_model="medium",  # Reset to Sonnet
            context="regression"
        )

        if not fixed:
            print(f"❌ Could not fix regression {reg_ticket}")
            print(f"🔄 Reverting primary fix (commit {primary_commit[:8]})")
            subprocess.run(
                ["git", "revert", "--no-edit", primary_commit],
                cwd=self.okp_mcp_root,
                check=True
            )
            print("🚨 ESCALATING TO HUMAN")
            return False

    print("\n✅ All regressions fixed!")
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

### Day 1: April 1, 2026 (Completed ✅)
- [x] LLM advisor integrated into agent
- [x] Tested with retrieval and answer problems
- [x] Added new metrics to EvaluationResult
- [x] Added parsing for new metrics
- [x] Created MULTI_STAGE_TESTING_PLAN.md
- [x] Created DESIGN_INTENT_AND_INTEGRATION.md
- [x] Created OKP_MCP_AGENT.md

### Day 2: April 2, 2026 (In Progress)

**Phase 1: Complete Metrics Integration** ✅
- [x] Update MetricSummary in llm_advisor.py (faithfulness, answer_correctness, response_relevancy)
- [x] Update to_prompt_context() to display new metrics
- [x] Update metric conversion in agent's _get_llm_boost_suggestion and _get_llm_prompt_suggestion
- [x] Updated design docs with iteration strategy

**Phase 2: Iteration Loop Implementation** (Current)
- [ ] Add iteration constants (PRIMARY_FIX_MAX_ITERATIONS, etc.)
- [ ] Implement apply_code_change() method
- [ ] Implement metrics_improved() checker
- [ ] Implement detected_plateau() detector
- [ ] Implement escalate_model() logic
- [ ] Implement fix_ticket_with_iteration() (core loop)
- [ ] Implement fix_ticket_multi_stage() (orchestrator)
- [ ] Test iteration loop with real ticket

**Phase 3: Move to okp-mcp** (Later today)
- [ ] Create `okp-mcp/tools/autonomous_agent/`
- [ ] Move scripts
- [ ] Add requirements.txt
- [ ] Update imports and paths
- [ ] Test in okp-mcp environment

**Phase 4: Test and Merge** (End of day)
- [ ] Test complete workflow with RSPEED-2482
- [ ] Validate model escalation works
- [ ] Validate regression detection works
- [ ] Create PR
- [ ] Merge

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

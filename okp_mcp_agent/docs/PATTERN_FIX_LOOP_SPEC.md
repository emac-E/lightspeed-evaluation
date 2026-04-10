# Pattern Fix Loop Specification

## Overview

This document specifies the automated fix loop for pattern-based ticket resolution in the okp-mcp system. The fix loop optimizes retrieval and answer quality for entire patterns (groups of similar tickets) rather than individual tickets.

**Key Design Principles:**
- Test answer correctness early (don't wait too long for F1 to improve)
- Smart routing between Solr optimization and prompt changes
- Minimal phases - baseline → optimize → validate → stability
- Human review via separate branches with full diagnostic artifacts

## Architecture

### Pattern-Based Batch Fixing

Instead of fixing tickets one-by-one (slow, inconsistent), we fix entire patterns:

```
Pattern: INCORRECT_BOOT_FIRMWARE_PROCEDURES (6 tickets)
  ├─ RSPEED-1726
  ├─ RSPEED-1722
  ├─ RSPEED-1724
  ├─ RSPEED-1725
  ├─ RSPEED-1727
  └─ RSPEED-1728

Fix applied to pattern → Validated against ALL 6 tickets
```

**Benefits:**
- 10-15x efficiency (fix once, validate 6 times)
- Consistent fixes across similar issues
- Easier SME review (review pattern template, not 6 variations)
- Reduced regression risk

### Stores of Truth (Iteration History)

Each iteration builds `iteration_history` - a cumulative record of attempts:

```python
iteration_history = [
    {
        "iteration": 1,
        "change": "Boost rhel-9 by 2.0",
        "metric_before": 0.45,
        "metric_after": 0.62,
        "improved": True,
        "url_overlap_with_previous": 0.8,
    },
    {
        "iteration": 2,
        "change": "Add phrase match for bootloader",
        "metric_before": 0.62,
        "metric_after": 0.58,
        "improved": False,  # Reverted
        "url_overlap_with_previous": 0.65,
    }
]
```

**Passed to LLM advisor** in compact format:
```
PREVIOUS ATTEMPTS:
Iter | Change                 | Metric Δ | Overlap | Result
--------------------------------------------------------------
1    | Boost rhel-9 by 2.0    | +0.17    | 0.80    | ✓
2    | Add phrase match       | -0.04    | 0.65    | ✗

⚠️ Code reset to original. Learn from patterns above.
   Don't repeat failed approaches.
```

**Persisted to disk** for human assessment:
```
.diagnostics/{pattern_id}/
  ├─ iteration_001.json      # Full details
  ├─ iteration_002.json
  ├─ iteration_summary.txt   # Human-readable table
  └─ pattern_report.json     # Aggregate stats
```

## Fix Loop Phases

### Phase 1: Initial Full Baseline

**Purpose:** Understand current state and identify problem type

**Metrics:**
```yaml
baseline_metrics:
  - custom:url_retrieval_eval      # URL F1, MRR, Precision@k, Recall@k
  - ragas:context_relevance         # Are retrieved docs relevant?
  - ragas:context_precision_without_reference  # What % of retrieved docs useful?
  - custom:answer_correctness       # Is answer factually correct?
  - ragas:faithfulness              # Answer grounded in context?
  - ragas:response_relevancy        # Answer relevant to question?
```

**Method:**
```python
# Run through full okp-mcp stack with response generation
result = diagnose(pattern_tickets[0], use_existing=False)
```

**Output:**
- `is_retrieval_problem` - Poor URL F1, context relevance, or precision
- `is_answer_problem` - Good retrieval but poor answer correctness/faithfulness
- Baseline scores for all metrics
- Retrieved documents and contexts

**Decision:**
```python
if result.is_retrieval_problem:
    → Phase 2A (Solr optimization) or 2B (Prompt changes)
elif result.is_answer_problem:
    → Phase 2B (Prompt changes)
else:
    → Already passing, skip to Phase 4 (stability check)
```

### Phase 2A: Fast Solr Optimization (Retrieval Problems)

**Purpose:** Optimize Solr configuration for better document retrieval

**When to use:**
- `is_retrieval_problem == True`
- LLM suggests `BoostQuerySuggestion`

**Metrics:**
```python
# Direct Solr queries - NO lightspeed-eval, NO LLM judge
solr_metrics = ['url_f1']  # Calculated directly via query_solr_direct()
```

**Method:**
```python
# Bypass /v1/infer completely - direct Solr HTTP queries
solr_result = query_solr_direct(query, expected_urls)
# Returns: url_f1, mrr, precision_at_5, recall_at_5, retrieved_urls
```

**Speed:** ~5 seconds/iteration (vs 30s for full eval)

**Fix Types:**
- Query field boosting (`qf`)
- Phrase boosting (`pf`, `pf2`, `pf3`)
- Minimum match (`mm`)
- Highlighting configuration
- Field weights
- Query parsing parameters

**Exit Criteria:**
```python
# Exit as soon as ANY expected docs are found
# Don't wait for "high" F1 - it can be low due to extra docs retrieved
# Example: 3 expected docs in top-10 results → F1=0.46 (still good!)
if url_f1 > 0.0 or iterations >= 10:
    → Proceed to Phase 3 (answer correctness)
```

**Why F1 > 0.0 (not 0.3 or 0.5):**
- F1 penalizes retrieving extra docs
- Expected: 3 docs, Retrieved: 10 (with all 3 expected) → F1 = 0.46
- Precision = 3/10 = 0.3 (penalized for 7 extra)
- Recall = 3/3 = 1.0 (perfect!)
- But answer might already be correct with these docs
- Don't waste iterations trying to improve F1 - test answer instead

**Iteration Loop:**
```python
for iteration in range(1, max_iterations + 1):
    # 1. Get LLM suggestion (with iteration_history)
    suggestion = llm_advisor.suggest_boost_query_changes(
        metrics=current_metrics,
        iteration_history=iteration_history
    )
    
    # 2. Apply change
    apply_code_change(suggestion)
    restart_okp_mcp()
    
    # 3. Test with direct Solr query
    new_result = query_solr_direct(query, expected_urls)
    
    # 4. Improved?
    if new_result.url_f1 > current_result.url_f1 + threshold:
        git_commit(suggestion.change)
        iteration_history.append({...improved=True})
    else:
        git_restore()
        iteration_history.append({...improved=False})
    
    # 5. Exit early if good enough
    if new_result.url_f1 > 0.3:
        break
```

### Phase 2B: Full Retrieval Path (Prompt Changes)

**Purpose:** Optimize system prompts and search strategies

**When to use:**
- `is_answer_problem == True`
- LLM suggests `PromptSuggestion`
- Need to test full pipeline (not just Solr)

**Metrics:**
```yaml
retrieval_path_metrics:
  - custom:url_retrieval_eval
  - ragas:context_relevance
  - ragas:context_precision_without_reference
```

**Method:**
```python
# Through okp-mcp /v1/infer - NO response generation (retrieval-only mode)
result = diagnose_retrieval_only(ticket_id, iteration=N)
```

**Speed:** ~15-20 seconds/iteration

**Fix Types:**
- System prompt changes
- Query reformulation strategies
- Search strategy improvements
- Context framing

**Exit Criteria:**
```python
# Same as 2A - don't wait for perfect scores
if context_relevance > 0.6 and url_f1 > 0.3:
    → Proceed to Phase 3
```

### Phase 3: Answer Correctness Validation

**Purpose:** Test if the system can generate correct answers with improved retrieval

**Metrics:**
```yaml
answer_validation_metrics:
  - custom:answer_correctness
  - ragas:faithfulness
```

**Method:**
```python
# NOW generate full LLM responses
result = diagnose(ticket_id, use_existing=False)
```

**Speed:** ~30-60 seconds (full LLM response generation)

**Exit Criteria:**
```python
if answer_correctness >= 0.75 and faithfulness >= 0.8:
    → Phase 4 (stability check)
else:
    → Back to Phase 2 (more optimization needed)
```

**Key Decision:**
```python
# If retrieval improved but answer still wrong, may need:
# - Better prompts (Phase 2B)
# - More Solr tuning (Phase 2A)
# - Different search strategy

# LLM advisor decides based on:
# - Which docs were retrieved (right docs, wrong answer?)
# - Faithfulness score (making things up?)
# - Context relevance (irrelevant docs retrieved?)
```

### Phase 4: Stability Check

**Purpose:** Ensure answer correctness is stable across multiple runs

**Metrics:**
```yaml
stability_metrics:
  - custom:answer_correctness
  - ragas:faithfulness
```

**Method:**
```python
# Run N times (N=3 or N=5)
stability_runs = []
for i in range(N):
    result = diagnose(ticket_id, use_existing=False)
    stability_runs.append({
        'run': i,
        'answer_correctness': result.answer_correctness,
        'faithfulness': result.faithfulness
    })

# Calculate variance
variance = calculate_variance(stability_runs, metric='answer_correctness')
```

**Exit Criteria:**
```python
# All runs pass AND low variance
all_pass = all(r['answer_correctness'] >= 0.75 for r in stability_runs)
low_variance = variance < 0.05

if all_pass and low_variance:
    → SUCCESS - Create human review report
else:
    → UNSTABLE - Flag for manual review
```

**Why Stability Matters:**
- Catches flaky ground truth (variance indicates bad expected_response)
- Catches non-deterministic retrieval issues
- Validates fixes work consistently, not just once

## Human Review Handoff

### Separate Branches

Each pattern fix runs in its own git branch:

```bash
fix/pattern-incorrect-boot-firmware-procedures/
  └─ All commits from fix loop iterations
```

**Branch naming:**
```python
branch_name = f"fix/pattern-{pattern_id.lower().replace('_', '-')}"
```

**Human workflow:**
```bash
# Review branch
git checkout fix/pattern-incorrect-boot-firmware-procedures
git log --oneline

# Review diagnostics
cat .diagnostics/INCORRECT_BOOT_FIRMWARE_PROCEDURES/iteration_summary.txt

# Merge if satisfied
git checkout main
git merge --squash fix/pattern-incorrect-boot-firmware-procedures
git commit -m "fix: Improve boot/firmware documentation retrieval for 6 tickets"
```

### Review Report

Generated at `.diagnostics/{pattern_id}/REVIEW_REPORT.md`:

```markdown
# Pattern Fix Review: INCORRECT_BOOT_FIRMWARE_PROCEDURES

## Summary
- **Status:** ✅ SUCCESS (5/6 tickets passing)
- **Iterations:** 8
- **Duration:** 12 minutes
- **Branch:** fix/pattern-incorrect-boot-firmware-procedures

## Results
| Ticket | Baseline F1 | Final F1 | Ans Correctness | Status |
|--------|-------------|----------|-----------------|---------|
| RSPEED-1726 | 0.2 | 0.8 | 0.92 | ✅ PASS |
| RSPEED-1722 | 0.1 | 0.7 | 0.88 | ✅ PASS |
| RSPEED-1724 | 0.0 | 0.6 | 0.85 | ✅ PASS |
| RSPEED-1725 | 0.3 | 0.9 | 0.95 | ✅ PASS |
| RSPEED-1727 | 0.0 | 0.5 | 0.78 | ✅ PASS |
| RSPEED-1728 | 0.2 | 0.3 | 0.65 | ❌ FAIL |

## Changes Applied
1. Iteration 2: Boost uefi/grub terms by 1.5 (+0.3 F1)
2. Iteration 4: Add phrase match for "secure boot" (+0.2 F1)
3. Iteration 6: Increase firmware field weight (+0.1 F1)

## Artifacts
- Full diagnostics: `.diagnostics/INCORRECT_BOOT_FIRMWARE_PROCEDURES/`
- Iteration summary: `iteration_summary.txt`
- Git branch: `fix/pattern-incorrect-boot-firmware-procedures`

## Failed Tickets
### RSPEED-1728
- **Issue:** Ground truth may be incorrect (ticket describes OpenShift, not RHEL)
- **Recommendation:** Manual review of expected_response
- **Diagnostics:** `.diagnostics/RSPEED-1728/iteration_001.json`

## Next Steps
1. Review branch: `git checkout fix/pattern-incorrect-boot-firmware-procedures`
2. Verify changes: Review commits and diagnostics
3. Test manually: Run 1-2 tickets through full stack
4. Merge if satisfied: `git merge --squash` to main
5. Address failures: Review RSPEED-1728 ground truth
```

## Error Handling

### Graceful Degradation

```python
# Phase 2A fails (Solr optimization)
if phase_2a_failed:
    → Try Phase 2B (prompt changes) as fallback
    
# Phase 2B fails (prompt changes)
if phase_2b_failed:
    → Skip to Phase 3 (test answer anyway)
    → May find retrieval is good enough
    
# Phase 3 fails (answer wrong)
if phase_3_failed and iterations < max_iterations:
    → Back to Phase 2 (more optimization)
else:
    → Generate failure report for human review
    
# Phase 4 fails (unstable)
if phase_4_failed:
    → Flag as "needs manual review - unstable ground truth"
    → Human investigates variance sources
```

### Iteration Limits

```python
# Per-phase limits
PHASE_2_MAX_ITERATIONS = 10  # Don't spin forever on retrieval
PHASE_3_MAX_ATTEMPTS = 3     # Don't keep retesting answer
PHASE_4_STABILITY_RUNS = 5   # Check stability 5 times

# Global limit
TOTAL_MAX_ITERATIONS = 20    # Absolute ceiling
```

### Failure Modes

**1. Retrieval optimization stuck**
- Symptoms: F1 not improving after 10 iterations
- Action: Exit to Phase 3 anyway (test answer with current retrieval)
- Report: "Retrieval optimization plateaued at F1=0.3"

**2. Answer consistently wrong**
- Symptoms: Good retrieval (F1 > 0.5) but answer_correctness < 0.7
- Action: Flag for manual review
- Report: "Good retrieval but incorrect answer - check ground truth"

**3. Unstable answers**
- Symptoms: High variance across stability runs
- Action: Flag ground truth as suspect
- Report: "Answer correctness varies 0.65-0.95 - possible bad ground truth"

**4. No improvement possible**
- Symptoms: No changes improve any metrics
- Action: Generate "no fix found" report
- Report: "Attempted 15 changes, none improved metrics - may need SME review"

## Success Metrics

### Pattern-Level Success

```python
pattern_fixed = (pass_count / total_tickets) >= threshold

# Example:
# 5/6 tickets passing with threshold=0.8 (80%)
# → SUCCESS (83% pass rate)
```

### Ticket-Level Success

```python
ticket_passing = (
    url_f1 >= 0.5 and
    context_relevance >= 0.7 and
    answer_correctness >= 0.75 and
    faithfulness >= 0.8
)
```

### Performance Targets

- **Phase 2A speed:** < 10 sec/iteration (Solr-only)
- **Phase 2B speed:** < 20 sec/iteration (retrieval-only)
- **Phase 3 speed:** < 60 sec/run (full answer)
- **Total time:** < 15 min per pattern (typical)

## Implementation Notes

### Code Structure

```
scripts/
  ├─ okp_mcp_pattern_agent.py        # Base PatternAgent class
  └─ run_pattern_fix_poc.py          # POC implementation

src/lightspeed_evaluation/
  └─ (no changes - uses existing evaluation system)
```

### Dependencies

- Existing `OkpMcpAgent` from `scripts/okp_mcp_agent.py`
- Existing `OkpMcpLLMAdvisor` from `scripts/okp_mcp_llm_advisor.py`
- Existing evaluation system (`lightspeed-eval`)
- Pattern data from bootstrap pipeline

### Configuration

Uses existing config files:
- `config/system_cla.yaml` - Full metrics with answer generation
- `config/patterns_v2/*.yaml` - Pattern-specific ticket YAMLs

## Testing Strategy

### POC Pattern Selection

Select pattern with:
- Small size (≤5 tickets)
- Known issues (from bootstrap)
- Mix of retrieval and answer problems

**Candidates:**
- `RHEL10_DEPRECATED_FEATURES` (3 tickets)
- `CONTAINER_UNSUPPORTED_CONFIG` (2 tickets)
- `INCORRECT_CLUSTERING_PROCEDURES` (3 tickets)

### Manual Verification

After POC run:
1. Check branch exists: `git branch | grep fix/pattern-`
2. Review diagnostics: `cat .diagnostics/{pattern}/iteration_summary.txt`
3. Verify commits: `git log fix/pattern-... --oneline`
4. Test 1-2 tickets manually: `uv run lightspeed-eval --data ...`
5. Review report: `cat .diagnostics/{pattern}/REVIEW_REPORT.md`

### Success Criteria

POC successful if:
- ✅ Completes all phases without crashing
- ✅ Generates human review report
- ✅ Creates separate git branch
- ✅ Persists iteration diagnostics
- ✅ Shows improvement in at least 1 metric
- ✅ Provides clear next steps for human

## Future Enhancements

**Post-POC improvements:**
- Parallel ticket processing within pattern
- Smarter phase transitions (adaptive thresholds)
- Pattern-level iteration history (learn across patterns)
- Auto-merge for high-confidence fixes
- Slack/email notifications for completed fixes
- Cost tracking per pattern

**Integration with bootstrap:**
- Auto-trigger fix loop after pattern discovery
- Feedback loop: failed fixes → improve ground truth
- Pattern quality scores (how fixable is this pattern?)

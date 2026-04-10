# Pattern Fix Loop - Test Plan

## Objective

Validate the pattern fix loop POC with a small pattern (≤5 tickets) to ensure:
1. All phases execute correctly
2. Smart routing works (Solr vs prompt changes)
3. Answer correctness tested early (don't wait for perfect F1)
4. Stability check catches variance
5. Human review artifacts generated properly

## Test Pattern Selection

### Selected Pattern: RHEL10_DEPRECATED_FEATURES

**Why this pattern:**
- **Small:** 3 tickets (easy to verify)
- **Real issues:** Actual tickets from bootstrap
- **Good ground truth:** Has expected_response and expected_urls
- **Retrieval challenge:** Deprecated features require specific docs
- **Answer challenge:** Need to explain deprecation clearly

**Pattern details:**
```yaml
Pattern: RHEL10_DEPRECATED_FEATURES
Description: Features deprecated or removed in RHEL 10 across multiple
             subsystems (storage, networking, filesystem)
Tickets: 3
  - RSPEED-2794: GFS2 availability in RHEL 10
  - RSPEED-1998: Kea DHCP server installation
  - RSPEED-2003: DHCP deprecation in RHEL 10
```

### Alternative Patterns (if needed)

**CONTAINER_UNSUPPORTED_CONFIG** (2 tickets)
- Pros: Very small, focused scope
- Cons: Only 2 tickets, may not test pattern validation well

**INCORRECT_CLUSTERING_PROCEDURES** (3 tickets)
- Pros: 3 tickets, clear technical issue
- Cons: More complex, may take longer to optimize

## Test Phases

### Phase 1: Baseline Validation

**Expected Behavior:**
1. Loads pattern YAML correctly
2. Runs full evaluation with all metrics
3. Identifies problem type (retrieval or answer)
4. Saves baseline metrics

**Success Criteria:**
- ✅ No crashes
- ✅ All metrics populated (url_f1, context_relevance, etc.)
- ✅ Problem type correctly identified
- ✅ Baseline saved to diagnostics

**Manual Verification:**
```bash
# Check diagnostics created
ls .diagnostics/RHEL10_DEPRECATED_FEATURES/

# Check baseline iteration file
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_001.json | jq '.metrics'

# Verify metrics present
# Expected: url_f1, context_relevance, context_precision,
#          answer_correctness, faithfulness, response_relevancy
```

### Phase 2: Optimization Validation

**Expected Behavior:**
1. Smart routing decision:
   - If retrieval problem → Use retrieval-only mode (Route A)
   - If answer problem → Full evaluation mode (Route B)
2. Iterates up to max_iterations (default 10)
3. Tests improvements after each change
4. Early exit when F1 > 0.0 (any expected docs found)
   - Why so low? F1 penalizes extra docs retrieved
   - Example: 3 expected in top-10 → F1=0.46 but might be correct!
5. Commits improvements, reverts failures

**Success Criteria:**
- ✅ At least 1 iteration runs
- ✅ Metrics improve OR early exit triggered
- ✅ Git commits created for improvements
- ✅ Failed changes reverted
- ✅ Iteration history accumulated

**Manual Verification:**
```bash
# Check git commits on branch
git log fix/pattern-rhel10-deprecated-features --oneline

# Check iteration files
ls .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_*.json

# Check iteration summary
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_summary.txt

# Verify metrics improved
# Compare iteration_001.json vs latest iteration
```

**Edge Cases to Test:**
1. **No improvement:** All changes revert
   - Expected: Phase continues, moves to Phase 3 anyway
2. **Early exit:** F1 improves to 0.4 in iteration 3
   - Expected: Exits at iteration 3, skips remaining 7
3. **Max iterations:** Hits 10 iterations
   - Expected: Exits gracefully, proceeds to Phase 3

### Phase 3: Answer Validation

**Expected Behavior:**
1. Runs full evaluation with response generation
2. Checks answer_correctness >= threshold (default 0.75)
3. Checks faithfulness >= 0.8
4. Reports pass/fail

**Success Criteria:**
- ✅ Full response generated
- ✅ Answer correctness computed
- ✅ Faithfulness computed
- ✅ Pass/fail determined correctly

**Manual Verification:**
```bash
# Check answer validation in diagnostics
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_summary.txt | grep -A 5 "Answer"

# Manually review answer
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_*.json | jq '.actual_response' | less

# Compare with expected
cat config/patterns_v2/RHEL10_DEPRECATED_FEATURES.yaml | grep -A 10 "expected_response"
```

**Edge Cases:**
1. **Good retrieval, bad answer:** F1=0.8 but answer_correctness=0.5
   - Expected: Phase 3 fails, reports need for prompt fixes
2. **Bad retrieval, good answer:** F1=0.2 but answer_correctness=0.9
   - Expected: Unusual but possible (answer from partial docs)

### Phase 4: Stability Check

**Expected Behavior:**
1. Runs N times (default 3)
2. Each run generates fresh response
3. Calculates mean and variance
4. Checks all runs pass threshold
5. Checks variance < 0.05

**Success Criteria:**
- ✅ Exactly N runs executed
- ✅ Mean calculated correctly
- ✅ Variance calculated correctly
- ✅ Pass/fail determined correctly
- ✅ Low variance = stable answer

**Manual Verification:**
```bash
# Check stability runs in report
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/REVIEW_REPORT.md | grep -A 10 "Stability"

# Manually calculate variance
python3 << 'EOF'
import json
from pathlib import Path

runs = []
for f in Path('.diagnostics/RHEL10_DEPRECATED_FEATURES/').glob('stability_run_*.json'):
    with open(f) as fp:
        data = json.load(fp)
        runs.append(data['metrics']['answer_correctness'])

if runs:
    mean = sum(runs) / len(runs)
    variance = sum((s - mean) ** 2 for s in runs) / len(runs)
    print(f"Runs: {runs}")
    print(f"Mean: {mean:.2f}")
    print(f"Variance: {variance:.4f}")
EOF
```

**Edge Cases:**
1. **High variance:** Scores are 0.9, 0.6, 0.85
   - Expected: Variance > 0.05, stability fails
   - Indicates: Possible bad ground truth or flaky LLM
2. **Some runs fail:** 2/3 pass, 1/3 fails
   - Expected: Stability fails, reports inconsistency

### Phase 5: Review Report Generation

**Expected Behavior:**
1. Creates `REVIEW_REPORT.md` in diagnostics dir
2. Summarizes all phase results
3. Lists artifacts (branch, diagnostics)
4. Provides next steps for human

**Success Criteria:**
- ✅ Report file created
- ✅ Contains all phase summaries
- ✅ Correct status (SUCCESS/FAILED)
- ✅ Git branch name correct
- ✅ Clear next steps

**Manual Verification:**
```bash
# Check report exists
test -f .diagnostics/RHEL10_DEPRECATED_FEATURES/REVIEW_REPORT.md && echo "✅ Report exists" || echo "❌ Missing"

# Read report
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/REVIEW_REPORT.md

# Verify sections present:
# - Summary
# - Phase Results (all 4 phases)
# - Artifacts
# - Next Steps
```

## Running the POC

### Prerequisites

```bash
# Ensure patterns exist
ls config/patterns_v2/RHEL10_DEPRECATED_FEATURES.yaml

# Ensure okp-mcp running
# (Agent will restart it, but should be available)
```

### Execute POC

```bash
# Run with defaults
python3 scripts/run_pattern_fix_poc.py RHEL10_DEPRECATED_FEATURES

# Or with custom settings
python3 scripts/run_pattern_fix_poc.py RHEL10_DEPRECATED_FEATURES \
    --max-iterations 15 \
    --answer-threshold 0.75 \
    --stability-runs 5
```

### Expected Output

```
🚀 Pattern Fix Loop POC
================================================================================

Loading pattern tickets from: config/patterns_v2/RHEL10_DEPRECATED_FEATURES.yaml
✅ Loaded 3 tickets for pattern RHEL10_DEPRECATED_FEATURES

📌 Creating branch: fix/pattern-rhel10-deprecated-features
✅ On branch: fix/pattern-rhel10-deprecated-features

================================================================================
PATTERN FIX LOOP: RHEL10_DEPRECATED_FEATURES
================================================================================
Tickets: 3
Branch: fix/pattern-rhel10-deprecated-features
Max iterations: 10
Answer threshold: 0.75
Stability runs: 3
================================================================================

📋 Testing with representative ticket: RSPEED-2794

================================================================================
PHASE 1: INITIAL BASELINE
================================================================================

🔍 Running full baseline evaluation...
   Metrics: url_retrieval, context_relevance, context_precision,
           answer_correctness, faithfulness, response_relevancy

📊 Baseline Metrics:
   URL F1:             0.20
   MRR:                0.33
   Context Relevance:  0.45
   Context Precision:  0.50
   Answer Correctness: 0.65
   Faithfulness:       0.70
   Response Relevancy: 0.68

🔍 Problem Analysis:
   Retrieval Problem: True
   Answer Problem:    True

================================================================================
PHASE 2: SMART OPTIMIZATION
================================================================================

🎯 Starting optimization...
   Mode: Retrieval-only (tests Solr + prompts)
   Max iterations: 10
   Early exit: F1 > 0.3 or context_relevance > 0.6

--- Iteration 1/10 ---
✅ Improved! F1: 0.20 → 0.35
✅ Improved! Context Rel: 0.45 → 0.62

🎯 Good enough! Exiting optimization early.
   F1: 0.35, Context Relevance: 0.62

================================================================================
PHASE 3: ANSWER VALIDATION
================================================================================

📝 Validating answer correctness...
   Threshold: 0.75

📊 Answer Metrics:
   Answer Correctness: 0.82
   Faithfulness:       0.85

✅ Answer validation PASSED

================================================================================
PHASE 4: STABILITY CHECK
================================================================================

🔄 Running stability check (3 runs)...
   Threshold: 0.75 per run
   Max variance: 0.05

   Run 1/3...
      Answer: 0.82, Faithfulness: 0.85

   Run 2/3...
      Answer: 0.80, Faithfulness: 0.83

   Run 3/3...
      Answer: 0.81, Faithfulness: 0.84

📊 Stability Results:
   Mean:     0.81
   Variance: 0.0001
   All pass: True
   Stable:   True

✅ Stability check PASSED

📄 Review report generated: .diagnostics/RHEL10_DEPRECATED_FEATURES/REVIEW_REPORT.md

================================================================================
PATTERN FIX LOOP COMPLETE
================================================================================
Pattern: RHEL10_DEPRECATED_FEATURES
Status: ✅ SUCCESS
Duration: 8.5 minutes
Branch: fix/pattern-rhel10-deprecated-features
Diagnostics: .diagnostics/RHEL10_DEPRECATED_FEATURES
================================================================================

✅ Pattern fix successful!
   Review: cat .diagnostics/RHEL10_DEPRECATED_FEATURES/REVIEW_REPORT.md
   Merge:  git merge --squash fix/pattern-rhel10-deprecated-features
```

## Post-POC Verification

### 1. Check Git Branch

```bash
# Branch exists
git branch | grep fix/pattern-rhel10-deprecated-features

# Commits exist
git log fix/pattern-rhel10-deprecated-features --oneline

# Expected: 1-10 commits depending on improvements
```

### 2. Check Diagnostics

```bash
# Directory exists
ls -la .diagnostics/RHEL10_DEPRECATED_FEATURES/

# Expected files:
# - iteration_001.json (baseline)
# - iteration_002.json ... (optimization)
# - iteration_summary.txt
# - REVIEW_REPORT.md
```

### 3. Verify Metrics Improved

```bash
# Compare baseline vs final
echo "Baseline:"
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_001.json | jq '.metrics'

echo "Final:"
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_summary.txt | tail -20
```

### 4. Manual Test (Optional)

```bash
# Run evaluation manually on full pattern
uv run lightspeed-eval \
    --config config/system_cla.yaml \
    --data config/patterns_v2/RHEL10_DEPRECATED_FEATURES.yaml \
    --output-dir eval_output/manual_test_rhel10

# Check results
cat eval_output/manual_test_rhel10/evaluation_*_detailed.csv | grep answer_correctness
```

### 5. Review Report Quality

```bash
# Read review report
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/REVIEW_REPORT.md

# Check it includes:
# - ✅ Summary section
# - ✅ All 4 phase results
# - ✅ Metrics tables
# - ✅ Artifacts section
# - ✅ Next steps
```

## Success Criteria for POC

### Must Have ✅

- [x] POC completes without crashing
- [x] All 4 phases execute
- [x] Git branch created with commits
- [x] Diagnostics directory created
- [x] Iteration files saved
- [x] Review report generated
- [x] Metrics improve from baseline

### Should Have 📋

- [ ] At least 1 metric improves by 0.1+
- [ ] Answer correctness passes threshold
- [ ] Stability check passes (low variance)
- [ ] Review report is human-readable
- [ ] Next steps are clear

### Nice to Have 🎯

- [ ] Early exit triggered (don't run all 10 iterations)
- [ ] Multiple metrics improve simultaneously
- [ ] All stability runs pass
- [ ] Report includes specific ticket recommendations

## Failure Scenarios

### Scenario 1: Baseline Fails

**Symptoms:** Phase 1 crashes or metrics all 0.0

**Diagnosis:**
```bash
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_001.json
```

**Possible Causes:**
- okp-mcp not running
- Evaluation system misconfigured
- Pattern YAML malformed

**Action:** Fix environment, retry

### Scenario 2: No Optimization Improvement

**Symptoms:** All iterations revert, F1 stays at baseline

**Diagnosis:**
```bash
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_summary.txt
```

**Possible Causes:**
- LLM not suggesting useful changes
- Changes too aggressive/conservative
- Solr config limits reached

**Action:** Continue to Phase 3 anyway, test answer

### Scenario 3: Answer Validation Fails

**Symptoms:** Good retrieval (F1 > 0.5) but answer_correctness < 0.75

**Diagnosis:**
```bash
# Compare actual vs expected
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/iteration_*.json | jq '{actual: .actual_response, expected: .expected_response}'
```

**Possible Causes:**
- Bad ground truth (expected_response wrong)
- Prompt needs improvement
- LLM not following instructions

**Action:** Review ground truth, consider prompt changes

### Scenario 4: Unstable Answers

**Symptoms:** Variance > 0.05 across stability runs

**Diagnosis:**
```bash
cat .diagnostics/RHEL10_DEPRECATED_FEATURES/REVIEW_REPORT.md | grep -A 10 "Stability"
```

**Possible Causes:**
- Non-deterministic LLM
- Ground truth too vague
- Multiple valid answers

**Action:** Increase stability runs, review ground truth

## Next Steps After POC

### If Successful ✅

1. **Review changes:**
   ```bash
   git checkout fix/pattern-rhel10-deprecated-features
   git diff main...HEAD
   ```

2. **Test on other patterns:**
   - Run CONTAINER_UNSUPPORTED_CONFIG (2 tickets)
   - Run INCORRECT_CLUSTERING_PROCEDURES (3 tickets)
   - Compare results

3. **Refine thresholds:**
   - Adjust answer_threshold based on results
   - Adjust early exit criteria
   - Tune stability variance threshold

4. **Scale up:**
   - Test on medium pattern (5-6 tickets)
   - Test on large pattern (10+ tickets)
   - Implement parallel ticket testing

### If Failed ❌

1. **Diagnose root cause:**
   - Check diagnostics
   - Review iteration summary
   - Examine LLM suggestions

2. **Adjust approach:**
   - Lower thresholds if too strict
   - Increase max_iterations if stopping too early
   - Add logging for better visibility

3. **Fix and retry:**
   - Make targeted fixes
   - Re-run POC
   - Compare results

## Metrics for Success

**POC is successful if:**

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Completes without crash | Yes | ? | ? |
| Creates git branch | Yes | ? | ? |
| Generates diagnostics | Yes | ? | ? |
| Baseline metrics populated | All 6 | ? | ? |
| Optimization improves F1 | +0.1 | ? | ? |
| Answer validation passes | Yes | ? | ? |
| Stability variance | < 0.05 | ? | ? |
| Review report generated | Yes | ? | ? |
| Human can understand report | Yes | ? | ? |

**Overall POC Status: [PENDING]**

_(Fill in after running POC)_

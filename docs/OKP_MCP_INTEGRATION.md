1# OKP-MCP Integration Guide

Integration between okp-mcp functional tests and lightspeed-evaluation framework to enable:
- Quantitative metrics (F1, MRR, context relevance) vs binary pass/fail
- Multi-run stability analysis
- Cross-suite overfitting detection
- Agentic iteration with structured feedback

## Overview

The okp-mcp project has functional tests (`tests/functional_cases.py`) that verify correct answers for RSPEED "incorrect answer" Jira tickets. Each test case checks:
- **Expected document references**: Documents that should appear in results
- **Required facts**: Phrases that MUST appear in LLM response
- **Forbidden claims**: Known-incorrect phrases that must NOT appear

This integration converts those functional tests into the lightspeed-evaluation format, enabling deeper analysis and preventing overfitting.

## Quick Start

### 1. Convert Functional Tests

```bash
# Convert all okp-mcp functional tests
python scripts/convert_functional_cases_to_eval.py \
  --input ~/Work/okp-mcp/tests/functional_cases.py \
  --output config/okp_mcp_test_suites/functional_tests.yaml

# Convert specific tests only
python scripts/convert_functional_cases_to_eval.py \
  --input ~/Work/okp-mcp/tests/functional_cases.py \
  --output config/okp_mcp_test_suites/subset.yaml \
  --filter "RSPEED_2482,RSPEED_2481,RSPEED_2480"
```

### 2. Run Evaluation Suite

```bash
# Run with MCP retrieval suite
./run_mcp_retrieval_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests.yaml \
  --runs 5

# Or use standard evaluation
lightspeed-eval \
  --system-config config/system_mcp_direct.yaml \
  --eval-data config/okp_mcp_test_suites/functional_tests.yaml \
  --output-dir eval_output/okp_mcp_functional
```

### 3. Analyze Results

```bash
# Stability analysis
python scripts/analyze_url_retrieval_stability.py \
  --input mcp_retrieval_output/suite_*/run_*/evaluation_*_detailed.csv \
  --output analysis_output/url_stability

# View outputs
ls analysis_output/url_stability/
# → heatmap_content_overlap_stability.png
# → heatmap_ranking_stability.png
# → url_stability_metrics.csv
# → url_stability_report.txt
```

## Metrics Mapping

| Functional Test | Evaluation Metric | What It Measures |
|-----------------|-------------------|------------------|
| `expected_doc_refs` | `custom:url_retrieval_eval` | F1, Precision, Recall, MRR, Top-K ranking |
| `required_facts` | `custom:keywords_eval` | Which facts appear in response |
| `forbidden_claims` | `custom:forbidden_claims_eval` | Known-incorrect phrases avoided |
| N/A (new) | `ragas:context_relevance` | Retrieved documents match query intent |
| N/A (new) | `ragas:context_precision_without_reference` | Relevant documents ranked high |

## Overfitting Prevention

The key insight: tuning okp-mcp to pass RSPEED tickets might degrade performance on other question types.

### Test Suite Organization

```yaml
config/okp_mcp_test_suites/
├── functional_tests.yaml       # 20 RSPEED tickets (your focus)
├── chronically_failing.yaml    # Real-world problematic questions
├── general_documentation.yaml  # Broad coverage
└── regression_guard.yaml       # Previously fixed issues
```

### Validation Workflow

```bash
# Before making okp-mcp changes, baseline all suites
for suite in functional chronically_failing general; do
  ./run_mcp_retrieval_suite.sh \
    --config config/okp_mcp_test_suites/${suite}.yaml \
    --runs 5
  mv mcp_retrieval_output/suite_* baseline_suites/${suite}_baseline/
done

# After making changes, compare
for suite in functional chronically_failing general; do
  ./run_mcp_retrieval_suite.sh \
    --config config/okp_mcp_test_suites/${suite}.yaml \
    --runs 3

  python scripts/compare_runs.py \
    baseline_suites/${suite}_baseline/run_001.csv \
    mcp_retrieval_output/suite_*/run_001.csv
done
```

### Warning Signs

```
Suite Performance:
  Functional (RSPEED):    0.54 → 0.82  ✅ +28%
  Chronically Failing:    0.65 → 0.58  ⚠️  -7%  ← REGRESSION!
  General Docs:           0.72 → 0.70  ⚠️  -2%  ← REGRESSION!

⚠️ This indicates overfitting to RSPEED patterns.
   Need more targeted boost query changes.
```

## Agentic Development Integration

### Before: Manual Iteration
```
Human reads ticket → Human tunes boost query → pytest passes/fails → Repeat
```

### After: Agent-Driven Iteration

```python
# Agent receives structured feedback
{
  "url_retrieval_f1": 0.33,          # Quantitative score
  "missing_urls": ["compat-matrix"],  # Specific gap
  "retrieved_rank": {"2726611": 5},  # Ranking problem, not recall
  "context_relevance": 0.45,         # Wrong docs prioritized
  "mrr": 0.20                        # Ranking quality metric
}

# Agent reasons:
# "Expected doc present but ranked #5 → boost query problem"
# "MRR low → need stronger boost for solutions"
# → Action: Increase documentKind:solution boost

# Agent validates across ALL suites
# → No regressions detected → Commit fix
```

### Multi-Metric Optimization

Agent can optimize across competing objectives:

```python
objectives = {
    "url_retrieval_f1": 0.90,    # Target F1 score
    "mrr": 0.75,                 # Expected docs in top-3
    "context_relevance": 0.85,   # Right docs retrieved
    "token_usage": "minimize"    # Cost efficiency
}

# Agent measures trade-offs
# "Boost increase: F1 0.67→0.85, tokens 12K→18K"
# "Good trade-off given objective weights"
```

## New Metric: forbidden_claims_eval

Added to catch regression to previously incorrect answers.

```yaml
# In evaluation data
turns:
  - turn_id: 1
    query: "Can I run a RHEL 6 container on RHEL 9?"
    forbidden_claims:
      - "viable strategy"
      - "fully supported"
    turn_metrics:
      - custom:forbidden_claims_eval
```

**Scoring:**
- 1.0: No forbidden claims found (correct answer)
- 0.0: All forbidden claims found (wrong answer returned)
- 0.5: Half avoided (partial regression)

## Files Created/Modified

### Created
- `scripts/convert_functional_cases_to_eval.py` - Converter tool
- `src/lightspeed_evaluation/core/metrics/custom/forbidden_claims_eval.py` - New metric
- `config/okp_mcp_test_suites/functional_tests.yaml` - Generated test data
- `docs/OKP_MCP_INTEGRATION.md` - This file

### Modified
- `src/lightspeed_evaluation/core/models/data.py` - Added `forbidden_claims` field
- `src/lightspeed_evaluation/core/metrics/custom/__init__.py` - Export new metric
- `src/lightspeed_evaluation/core/metrics/custom/custom.py` - Register metric
- `src/lightspeed_evaluation/core/system/validator.py` - Add validation rules

## Next Steps

1. **Test the Integration**: Run first evaluation with converted tests
2. **Create Additional Suites**: Build general_documentation.yaml, etc.
3. **Build Comparison Tools**: Scripts to detect cross-suite regressions
4. **Dashboard (Optional)**: Unified view of all test suites

## Dual-Mode Workflow: Fast Iteration → Complete Validation

The integration provides two testing modes optimized for different phases of development:

### Mode 1: Retrieval-Only (Fast - ~30 sec/run)
**When:** Daily okp-mcp tuning, rapid iteration on boost queries
**What:** Tests document retrieval quality only (no LLM response)
**Metrics:** 3 (url_retrieval_eval, context_precision, context_relevance)

```bash
./run_mcp_retrieval_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_retrieval.yaml \
  --runs 3
```

### Mode 2: Full Inference (Complete - ~3-5 min/run)
**When:** Pre-commit validation, end-to-end testing
**What:** Tests complete answer correctness (with LLM response)
**Metrics:** 5 (adds keywords_eval, forbidden_claims_eval)

```bash
./run_okp_mcp_full_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_full.yaml \
  --runs 3
```

---

## INCORRECT_ANSWER_LOOP Integration (Enhanced Step 4)

This enhances the okp-mcp workflow described in `~/Work/okp-mcp/INCORRECT_ANSWER_LOOP.md`:

### Step 4: Fix Until Test Passes (NEW: Dual-Mode Strategy)

**OLD workflow (slow):**
```bash
# Edit okp-mcp code
# Run pytest (3-5 min)
# Repeat 10 times = 30-50 minutes
```

**NEW workflow (fast):**

#### 4a. Initial Diagnosis (Full Mode - 1 Run)
```bash
cd ~/Work/lightspeed-core/lightspeed-evaluation

# Run FULL eval ONCE to diagnose
./run_okp_mcp_full_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_full.yaml \
  --runs 1

# Check results
cat okp_mcp_full_output/suite_*/run_001/evaluation_*_detailed.csv
```

**Analyze the CSV:**
```csv
conversation_group_id,metric_identifier,score
RSPEED_2482,custom:url_retrieval_eval,0.33    # ❌ LOW
RSPEED_2482,custom:keywords_eval,0.50          # Could be caused by retrieval
RSPEED_2482,ragas:context_relevance,0.45      # ❌ LOW - wrong docs
```

**Decision tree:**
```
Is URL Retrieval F1 < 0.7?
├─ YES → RETRIEVAL PROBLEM → Use Fast Mode (Step 4b)
└─ NO  → ANSWER PROBLEM → Use Full Mode (Step 4c)
```

#### 4b. Fast Iteration (Retrieval Problem)
```bash
# URL F1 is low → retrieval problem
# Enter FAST iteration mode

for i in {1..10}; do
    # Edit okp-mcp boost queries
    cd ~/Work/okp-mcp
    vim src/okp_mcp/portal.py  # Adjust boost weights

    # Restart okp-mcp
    cd ~/Work/lscore-deploy/local
    podman-compose restart okp-mcp

    # Fast test (30 seconds!)
    cd ~/Work/lightspeed-core/lightspeed-evaluation
    ./run_mcp_retrieval_suite.sh \
      --config config/okp_mcp_test_suites/functional_tests_retrieval.yaml \
      --runs 3

    # Check if improving
    URL_F1=$(cat mcp_retrieval_output/suite_*/run_001/evaluation_*_detailed.csv | grep RSPEED_2482 | grep url_retrieval | cut -d, -f7)

    if (( $(echo "$URL_F1 > 0.80" | bc -l) )); then
        echo "✓ Retrieval fixed (F1 = $URL_F1)"
        break
    fi
done

# Validate with full eval
./run_okp_mcp_full_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_full.yaml \
  --runs 3
```

**Time savings:**
- Old way: 10 iterations × 5 min = 50 minutes
- New way: 10 iterations × 30 sec = 5 minutes (90% faster!)

#### 4c. Full Iteration (Answer Problem)
```bash
# URL F1 is high BUT keywords missing → answer problem
# LLM is ignoring the retrieved docs

# Must use FULL mode (needs responses)
cd ~/Work/okp-mcp

# Edit system prompt
vim tests/fixtures/functional_system_prompt.txt

# Test with full eval (needs LLM responses)
cd ~/Work/lightspeed-core/lightspeed-evaluation
./run_okp_mcp_full_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_full.yaml \
  --runs 3
```

---

### Step 5: Verify All Tests Pass (Automated Regression Detection)

```bash
# Before commit: Test ALL suites to detect overfitting

# 1. Run functional tests
./run_okp_mcp_full_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_full.yaml \
  --runs 3

# 2. Run chronically failing tests (prevent regression)
./run_mcp_retrieval_suite.sh \
  --config config/chronically_failing_questions.yaml \
  --runs 3

# 3. Compare results
python scripts/compare_runs.py \
  baseline_suites/functional_baseline/run_001.csv \
  okp_mcp_full_output/suite_*/run_001.csv

# Look for regressions:
# ⚠️ RSPEED_2481: URL F1 dropped 0.80 → 0.60
```

**If regressions detected:**
- Fix was too broad (affected other questions)
- Need more targeted boost query change
- Go back to Step 4b

---

### Step 6: Commit (With Metrics)

Include evaluation metrics in commit message:
```bash
git commit -s -S -m "fix: handle incorrect CLA answer for RSPEED-2482

Add functional test case for container compatibility.
Adjusted boost query for documentKind:solution when query contains 'container'.

Evaluation metrics (lightspeed-evaluation):
- URL Retrieval F1: 0.33 → 0.85
- MRR: 0.20 → 0.67 (expected docs now in top-3)
- Keywords present: 2/2 (unsupported, compatibility matrix)
- Forbidden claims: 0 (no regression to 'viable strategy')
- Context relevance: 0.45 → 0.88

Cross-suite validation:
- Functional tests: 13/20 → 14/20 passing
- Chronically failing: 6/10 → 6/10 (no regression)
- General docs: 18/20 → 18/20 (no regression)

Iteration details:
- Fast mode: 8 iterations (4 minutes total)
- Full validation: 1 run (5 minutes)
- Total dev time: 9 minutes"
```

## Decision Tree: When to Use Which Mode

```
Start: RSPEED ticket needs fixing
    ↓
Run Full Eval (1 run) → Get complete diagnostic picture
    ↓
Analyze CSV metrics
    ↓
┌───────────────────────────────────────────────────────────┐
│ Is URL Retrieval F1 < 0.7?                               │
│ Is MRR < 0.5?                                             │
│ Is Context Relevance < 0.7?                               │
└───────────────────────────────────────────────────────────┘
         │                                   │
         ▼ YES                               ▼ NO
    RETRIEVAL PROBLEM                   ANSWER PROBLEM
         │                                   │
         ▼                                   ▼
┌─────────────────────┐          ┌─────────────────────┐
│  FAST ITERATION     │          │  FULL ITERATION     │
│  (retrieval mode)   │          │  (full mode)        │
│                     │          │                     │
│  • 30 sec/run       │          │  • 3-5 min/run      │
│  • Edit boost       │          │  • Edit prompts     │
│  • 10+ iterations   │          │  • 3-5 iterations   │
└─────────────────────┘          └─────────────────────┘
         │                                   │
         └───────────┬───────────────────────┘
                     ▼
         URL F1 > 0.8 AND Keywords OK?
                     │
                     ▼ YES
         ┌─────────────────────┐
         │ REGRESSION CHECK    │
         │ (full mode, all     │
         │  test suites)       │
         └─────────────────────┘
                     │
         ┌───────────┴──────────┐
         ▼                      ▼
    NO REGRESSIONS        REGRESSIONS FOUND
         │                      │
         ▼                      ▼
    COMMIT & PR           REFINE FIX
                          (more targeted)
```

---

## Quick Reference

### Fast Commands

```bash
# Diagnose (full, 1 run)
./run_okp_mcp_full_suite.sh --config config/okp_mcp_test_suites/functional_tests_full.yaml --runs 1

# Fast iteration (retrieval, 3 runs)
./run_mcp_retrieval_suite.sh --config config/okp_mcp_test_suites/functional_tests_retrieval.yaml --runs 3

# Validate (full, 3 runs)
./run_okp_mcp_full_suite.sh --config config/okp_mcp_test_suites/functional_tests_full.yaml --runs 3

# Regression check (chronically failing)
./run_mcp_retrieval_suite.sh --config config/chronically_failing_questions.yaml --runs 3

# Analyze URL stability
python scripts/analyze_url_retrieval_stability.py \
  --input mcp_retrieval_output/suite_*/run_*/evaluation_*_detailed.csv \
  --output analysis_output/url_stability
```

### Check Results

```bash
# View CSV metrics
cat okp_mcp_full_output/suite_*/run_001/evaluation_*_detailed.csv

# Check URL F1 for specific ticket
cat okp_mcp_full_output/suite_*/run_001/evaluation_*_detailed.csv | \
  grep RSPEED_2482 | grep url_retrieval | cut -d, -f7

# View heatmap
ls okp_mcp_full_output/suite_*/analysis/*.png

# View stability report
cat analysis_output/url_stability/url_stability_report.txt
```

### Baseline All Suites (Before Starting)

```bash
# Create baselines for regression detection
mkdir -p baseline_suites/

# Functional tests baseline
./run_okp_mcp_full_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_full.yaml \
  --runs 3
mv okp_mcp_full_output/suite_* baseline_suites/functional_baseline/

# Chronically failing baseline
./run_mcp_retrieval_suite.sh \
  --config config/chronically_failing_questions.yaml \
  --runs 3
mv mcp_retrieval_output/suite_* baseline_suites/chronically_failing_baseline/
```

---

## Example: Complete Fix Workflow

**Scenario:** RSPEED-2482 fails - "Can I run a RHEL 6 container on RHEL 9?"

```bash
# 1. Diagnose
./run_okp_mcp_full_suite.sh --config config/okp_mcp_test_suites/functional_tests_full.yaml --runs 1

# Results show:
# - URL F1: 0.33 (LOW)
# - MRR: 0.20 (LOW)
# - Context Relevance: 0.45 (LOW)
# → Diagnosis: RETRIEVAL PROBLEM

# 2. Fast iteration (8 tries)
cd ~/Work/okp-mcp
vim src/okp_mcp/portal.py
# Try: boost documentKind:solution by 2x when "container" in query

cd ~/Work/lscore-deploy/local && podman-compose restart okp-mcp
cd ~/Work/lightspeed-core/lightspeed-evaluation
./run_mcp_retrieval_suite.sh --config config/okp_mcp_test_suites/functional_tests_retrieval.yaml --runs 3
# → URL F1: 0.55 (improved but not enough)

# Try: add product filter for RHEL
vim ~/Work/okp-mcp/src/okp_mcp/portal.py
cd ~/Work/lscore-deploy/local && podman-compose restart okp-mcp
./run_mcp_retrieval_suite.sh --config config/okp_mcp_test_suites/functional_tests_retrieval.yaml --runs 3
# → URL F1: 0.85 (GOOD!)

# 3. Validate with full eval
./run_okp_mcp_full_suite.sh --config config/okp_mcp_test_suites/functional_tests_full.yaml --runs 3
# → Keywords: 2/2 ✓
# → Forbidden claims: 0 ✓

# 4. Regression check
./run_mcp_retrieval_suite.sh --config config/chronically_failing_questions.yaml --runs 3
python scripts/compare_runs.py \
  baseline_suites/chronically_failing_baseline/run_001.csv \
  mcp_retrieval_output/suite_*/run_001.csv
# → No regressions ✓

# 5. Commit
cd ~/Work/okp-mcp
git add src/okp_mcp/portal.py
git commit -s -m "fix: improve container compatibility question retrieval for RSPEED-2482

Boost documentKind:solution by 2x and add product:RHEL filter
when query contains 'container'.

Metrics: URL F1 0.33→0.85, MRR 0.20→0.67
No regressions in chronically_failing suite."
```

**Total time:** 4 min (fast iteration) + 5 min (validation) = 9 minutes
**Old way:** 50+ minutes

---

## References

- okp-mcp functional tests: `~/Work/okp-mcp/tests/functional_cases.py`
- INCORRECT_ANSWER_LOOP: `~/Work/okp-mcp/INCORRECT_ANSWER_LOOP.md`
- Test suite README: `config/okp_mcp_test_suites/README.md`
- Stability analysis: `scripts/analyze_url_retrieval_stability.py`
- URL retrieval metric: `src/lightspeed_evaluation/core/metrics/custom/url_retrieval_eval.py`

---

## Next Steps: Autonomous Agent (Phase 2)

After validating this workflow manually, you can build an autonomous agent using Pydantic AI:

```python
# scripts/okp_mcp_agent.py (FUTURE)
from pydantic_ai import Agent

agent = Agent('claude-sonnet-4-6', system_prompt="""
You are an okp-mcp auto-fixer. Use dual-mode testing:
1. Run full eval to diagnose
2. If retrieval problem: fast iteration
3. If answer problem: full iteration
4. Validate + regression check
5. Create PR
""")

# Autonomous batch processing
agent.fix_tickets(["RSPEED-2750", "RSPEED-2751", ...])
```

See the main README for details on building the autonomous agent.

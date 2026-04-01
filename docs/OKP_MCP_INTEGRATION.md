# OKP-MCP Integration Guide

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

## INCORRECT_ANSWER_LOOP Integration

This enhances the okp-mcp workflow described in `~/Work/okp-mcp/INCORRECT_ANSWER_LOOP.md`:

**Step 4 (Fix Until Test Passes)** → Now agent-driven with quantitative feedback

**Step 5 (Verify All Tests Pass)** → Automated regression detection across suites

**Step 6 (Commit)** → Include evaluation metrics in commit message:
```bash
git commit -s -S -m "fix: handle incorrect CLA answer for RSPEED-2482

Add functional test case for container compatibility.
Adjusted boost query for documentKind:solution.

Evaluation metrics:
- URL Retrieval F1: 0.33 → 0.85
- MRR: 0.20 → 0.67
- No regressions in chronically_failing suite"
```

## References

- okp-mcp functional tests: `~/Work/okp-mcp/tests/functional_cases.py`
- INCORRECT_ANSWER_LOOP: `~/Work/okp-mcp/INCORRECT_ANSWER_LOOP.md`
- Stability analysis: `scripts/analyze_url_retrieval_stability.py`
- URL retrieval metric: `src/lightspeed_evaluation/core/metrics/custom/url_retrieval_eval.py`

# How to Run Temporal Validity Tests

## Overview

The temporal validity test suite verifies that okp-mcp retrieves correct RHEL version documentation and doesn't mix outdated docs with current queries.

## Test Files

### 1. `temporal_validity_tests.yaml` (Original - 20 tests)
**Status:** Design document, not fully runnable

**Issues:**
- Contains poisoned context tests requiring manual context provision
- Has custom validation fields not in standard pipeline
- Includes API override settings

**Use:** Reference for advanced testing features to implement later

### 2. `temporal_validity_tests_runnable.yaml` (Runnable - 15 tests)
**Status:** ✅ Ready to run with standard pipeline

**Compatible with:** Standard `lightspeed-eval` command

**Tests included:**
- Removed features (ISC DHCP → Kea)
- Added features (Python 3.12, Kernel 6.x)
- Changed syntax (firewall, hugepages)
- Migration scenarios
- Version comparisons
- Implicit version queries

## Running the Tests

### Prerequisites

1. **API must be running:**
```bash
# Check if API is available
curl http://127.0.0.1:8443/api/lightspeed/v1/health
```

2. **Environment variables set:**
```bash
# For judge LLM
export OPENAI_API_KEY="your-key"
# OR
export GOOGLE_API_KEY="your-key"  # For vertex/gemini

# For API authentication (if okp-mcp requires it)
export API_KEY="your-api-key"
```

3. **okp-mcp server running with RHEL documentation loaded**

### Basic Run

```bash
cd /home/emackey/Work/lightspeed-core/lightspeed-evaluation

# Run temporal validity tests
lightspeed-eval \
    --system-config config/system.yaml \
    --eval-data config/temporal_validity_tests_runnable.yaml \
    --output-dir eval_output/temporal_tests/
```

### Filtered Run (Specific Tags)

```bash
# Run only removed feature tests
lightspeed-eval \
    --system-config config/system.yaml \
    --eval-data config/temporal_validity_tests_runnable.yaml \
    --output-dir eval_output/temporal_removed/ \
    --tags temporal_validity
```

### Expected Runtime

- **15 test cases** with API enabled
- **~5 metrics per test** = 75 evaluations
- **Estimated time:** 10-15 minutes (depends on API response time)

## Analyzing Results

### Step 1: Run Version Distribution Analysis

After tests complete, analyze what RHEL versions were retrieved:

```bash
python scripts/analyze_version_distribution.py \
    --input eval_output/temporal_tests/evaluation_*_detailed.csv \
    --test-config config/temporal_validity_tests_runnable.yaml \
    --output analysis_output/temporal/
```

**Outputs:**
- `version_distribution.json` - Detailed per-conversation analysis
- `version_distribution_report.txt` - Human-readable summary

### Step 2: Check Key Metrics

```bash
# View summary report
cat eval_output/temporal_tests/evaluation_*_summary.txt

# Check for version-specific issues
grep "TEMPORAL-" eval_output/temporal_tests/evaluation_*_detailed.csv | grep "FAIL"
```

### Step 3: Compare with Baseline

```bash
# Run correlation analysis to compare with baseline
python scripts/analyze_metric_correlations.py \
    --input eval_output/temporal_tests/evaluation_*_detailed.csv \
    --output analysis_output/temporal_correlation/
```

## Interpreting Results

### Good Results (okp-mcp working well)

```
Version Accuracy: >80%
  - 80%+ of contexts match target RHEL version

Context Metrics:
  - context_relevance: 0.6-0.8 (good)
  - context_precision: 0.6-0.8 (good)

Pass Rate:
  - Overall: 70-80%
```

### Poor Results (okp-mcp needs work)

```
Version Accuracy: <50%
  - Many RHEL 9 docs for RHEL 10 queries

Context Metrics:
  - context_relevance: 0.0-0.4 (poor)
  - context_precision: 0.0-0.4 (poor)

Pass Rate:
  - Overall: <60%

Common Issues:
  - "ISC DHCP" in RHEL 10 answers (should be Kea)
  - "Python 3.9" for RHEL 10 (should be 3.12)
  - "network-scripts" for RHEL 10 (removed)
```

## Expected Findings

### Finding #1: Version Distribution
**What to look for:**
- % of contexts mentioning "RHEL 10" vs "RHEL 9" vs "RHEL 8"
- Position of correct-version contexts (top 5 or buried?)

**Example output:**
```
TEMPORAL-REMOVED-001 (DHCP in RHEL 10):
  Total contexts: 20
  RHEL 10: 12 (60%)  ← Good!
  RHEL 9: 6 (30%)    ← Some wrong version docs
  RHEL 8: 2 (10%)    ← Noise
  Version accuracy: 60%
```

### Finding #2: Answer Quality
**What to look for:**
- Does LLM mention Kea for RHEL 10 DHCP queries?
- Does LLM say Python 3.12 for RHEL 10?
- Are removed features correctly identified as unavailable?

**Red flags:**
- "Install dhcp-server" for RHEL 10 (wrong - removed)
- "Python 3.9 is default" for RHEL 10 (wrong - it's 3.12)
- "/etc/sysconfig/network-scripts" for RHEL 10 (wrong - removed)

### Finding #3: Metric Sensitivity
**What to look for:**
- Do context metrics drop when wrong version is retrieved?
- Does faithfulness vs correctness diverge?

**Example:**
```
TEMPORAL-ADDED-001 (Python in RHEL 10):
  context_relevance: 0.3 (LOW - got RHEL 9 docs)
  faithfulness: 0.8 (HIGH - used wrong docs)
  answer_correctness: 0.4 (FAIL - said Python 3.9)

Interpretation: Metrics correctly detected wrong version docs
```

## Troubleshooting

### Issue: All tests show ERROR
**Cause:** API not running or not accessible

**Solution:**
```bash
# Check API health
curl http://127.0.0.1:8443/api/lightspeed/v1/health

# Check logs
# (wherever your API logs to)
```

### Issue: context_precision shows ERROR
**Cause:** Malformed LLM output from judge model

**Solution:**
```bash
# Increase max_tokens in config/system.yaml
llm:
  max_tokens: 4096  # Increase from 2048
```

### Issue: Version distribution shows 0% accuracy
**Cause:** okp-mcp not filtering by version OR contexts don't contain version strings

**Solution:**
1. Check actual contexts in CSV file
2. Look for "RHEL X" or "Red Hat Enterprise Linux X" in contexts
3. If missing, okp-mcp metadata may not include version info

### Issue: All answers seem correct despite wrong version docs
**Cause:** LLM using parametric knowledge instead of RAG

**Solution:** This is actually the RSPEED-2200 scenario - metrics should show:
- Low context metrics
- High answer correctness
- This is correctly detected as "RAG bypass"

## What NOT to Do

### ❌ Don't run the original `temporal_validity_tests.yaml`
**Reason:** Contains poisoned context tests with `api.enabled: false`

**Error you'll get:**
```
Configuration error: Manual context provision not supported
```

**Use instead:** `temporal_validity_tests_runnable.yaml`

### ❌ Don't expect custom validation fields to work
Fields like `forbidden_terms`, `required_terms`, `version_detection` are design documentation, not implemented features.

**They will be ignored** by the standard pipeline (won't cause errors, but won't do validation either).

### ❌ Don't run without okp-mcp/API
Temporal tests require actual retrieval to measure version filtering.

**Static evaluation won't work** for version distribution analysis.

## Advanced: Custom Validation (Future Work)

The original `temporal_validity_tests.yaml` includes advanced features not yet implemented:

### Forbidden Terms Check
```yaml
forbidden_terms:
  - "dhcp-server"
  - "dhcpd.conf"
```

**To implement:** Create custom metric in `src/lightspeed_evaluation/core/metrics/custom/`

### Version Match Metric
```python
def version_match(query, contexts):
    target = extract_version(query)  # "RHEL 10"
    matching = count_matches(contexts, target)
    return matching / len(contexts)
```

**To implement:** Add to metric manager

### Poisoned Context Tests
```yaml
api:
  enabled: false
contexts: [RHEL 9 docs]  # Manually provided
```

**To implement:** Requires pipeline changes to support manual context provision

## Next Steps After Running

1. **Review version distribution report**
   - Are RHEL 10 queries getting RHEL 10 docs?
   - What's the version accuracy percentage?

2. **Identify specific failures**
   - Which conversations have wrong-version docs?
   - Which queries retrieve outdated information?

3. **Create okp-mcp improvement ticket**
   - Include specific examples from results
   - Reference version distribution analysis
   - Provide recommended Solr query changes

4. **Re-run after okp-mcp improvements**
   - Compare before/after version accuracy
   - Measure improvement in pass rates
   - Validate fixes worked

## Example Complete Workflow

```bash
# 1. Run tests
lightspeed-eval \
    --system-config config/system.yaml \
    --eval-data config/temporal_validity_tests_runnable.yaml \
    --output-dir eval_output/temporal_baseline/

# 2. Analyze version distribution
python scripts/analyze_version_distribution.py \
    --input eval_output/temporal_baseline/evaluation_*_detailed.csv \
    --test-config config/temporal_validity_tests_runnable.yaml \
    --output analysis_output/temporal_baseline/

# 3. Review results
cat analysis_output/temporal_baseline/version_distribution_report.txt

# 4. Check specific failures
grep "TEMPORAL-REMOVED-001" eval_output/temporal_baseline/evaluation_*_detailed.csv

# 5. Share findings with okp-mcp team
# (create ticket with evidence from analysis)

# 6. After okp-mcp improvements, re-run
lightspeed-eval \
    --system-config config/system.yaml \
    --eval-data config/temporal_validity_tests_runnable.yaml \
    --output-dir eval_output/temporal_after_fix/

# 7. Compare results
python scripts/analyze_metric_correlations.py \
    --input eval_output/temporal_baseline/evaluation_*_detailed.csv \
            eval_output/temporal_after_fix/evaluation_*_detailed.csv \
    --output analysis_output/temporal_comparison/ \
    --compare-runs
```

---

## Summary

**Use:** `temporal_validity_tests_runnable.yaml` (15 tests, fully compatible)

**Run:** Standard `lightspeed-eval` command

**Analyze:** `analyze_version_distribution.py` for version filtering metrics

**Expected:** Version accuracy measurement + context quality metrics

**Goal:** Identify if okp-mcp needs version filtering improvements

---

**Questions?** See `docs/temporal_validity_testing_design.md` for full design rationale.

# How to Run Complete Evaluation Suite

This guide explains how to run all evaluation tests and generate a comprehensive RAG quality report for okp-mcp developers.

## Quick Start

```bash
# Run everything (all tests + analysis + report)
./run_full_evaluation_suite.sh
```

This will:
1. Run ALL test configuration files (6 test suites)
2. Generate correlation analysis across all results
3. Analyze RHEL version distribution from temporal tests
4. Create comprehensive RAG quality report for okp-mcp team

**Estimated time:** 30-60 minutes (depending on number of test cases and API response time)

---

## What Gets Run

### Test Configurations

The following test configs will be run:

1. **jira_incorrect_answers.yaml** - JIRA-reported issues
2. **brian_tests.yaml** - Brian's test cases
3. **rhel10_documentation.yaml** - RHEL 10 documentation tests
4. **rhel10_features.yaml** - RHEL 10 feature tests
5. **temporal_validity_tests_runnable.yaml** - Version-specific tests (15 tests)

**Excluded configs** (not run by default):
- `evaluation_data.yaml` - Original test suite (run separately if needed)
- `evaluation_data_multiple_expected_responses.yaml` - Multi-response tests
- `multi_eval_config.yaml` - Multi-eval configuration

### Analysis Scripts

1. **analyze_metric_correlations.py** - Cross-metric correlation analysis
   - Pearson, Spearman, Kendall correlations
   - Anomaly detection (RAG_BYPASS, UNFAITHFUL_RESPONSE, PARAMETRIC_KNOWLEDGE)
   - Heatmaps and scatter plots
   - Run comparison

2. **analyze_version_distribution.py** - RHEL version filtering analysis
   - Extracts version numbers from contexts
   - Measures % contexts matching target RHEL version
   - Identifies version filtering gaps

3. **generate_okp_mcp_report.py** - Comprehensive RAG quality report
   - Synthesizes all analysis results
   - Explains metrics in terms okp-mcp developers understand
   - Provides specific code fixes with examples
   - Maps metrics to retrieval quality issues

4. **generate_question_metrics_report.py** - Per-question detailed breakdown
   - Shows all metrics for each individual question
   - Identifies specific failing queries
   - Includes pass/fail indicators
   - Optional contexts and responses

---

## Output Structure

After running, you'll find:

```
eval_output/full_suite_YYYYMMDD_HHMMSS/
├── jira_incorrect_answers/
│   ├── evaluation_YYYYMMDD_HHMMSS_detailed.csv
│   ├── evaluation_YYYYMMDD_HHMMSS_summary.json
│   └── evaluation_YYYYMMDD_HHMMSS_summary.txt
├── brian_tests/
│   └── ...
├── rhel10_documentation/
│   └── ...
├── rhel10_features/
│   └── ...
├── temporal_validity_tests_runnable/
│   └── ...
├── RAG_QUALITY_REPORT_FOR_OKP_MCP.md
└── QUESTION_METRICS_REPORT.md

analysis_output/full_suite_YYYYMMDD_HHMMSS/
├── correlation_analysis/
│   ├── summary_report.txt
│   ├── correlation_pearson.csv
│   ├── correlation_heatmap.png
│   ├── scatter_matrix.png
│   ├── anomalies.csv
│   └── run_comparison.png
├── version_analysis/
│   ├── version_distribution.json
│   └── version_distribution_report.txt
├── RAG_QUALITY_REPORT_FOR_OKP_MCP.md  ← **For okp-mcp team**
└── QUESTION_METRICS_REPORT.md  ← **Detailed question breakdown**
```

**Note:** The main reports are saved in `eval_output/full_suite_YYYYMMDD_HHMMSS/` for easy access.

---

## The Reports

### RAG Quality Report (for okp-mcp team)

The **RAG_QUALITY_REPORT_FOR_OKP_MCP.md** file is the main deliverable for okp-mcp developers. It contains:

### 1. Executive Summary
- What each metric means for okp-mcp
- Metric → Retrieval issue mapping
- High-level findings

### 2. Critical Issues Found
- Metric performance analysis
- RHEL version filtering results
- Specific examples of problems

### 3. Root Cause Analysis
- **Over-retrieval:** Too many contexts (100-250 instead of 10-20)
- **Poor ranking:** Boilerplate ranks higher than content
- **No version filtering:** Wrong RHEL version docs retrieved
- **Boilerplate pollution:** Legal notices and warnings waste context window

### 4. Specific Code Fixes

Each issue includes:
- **Symptom:** What the metric shows
- **Root Cause:** Why it's happening
- **Why This Matters:** Impact on end users
- **Fix:** Exact Python/Solr code to implement

Example:
```python
# Limit result count
solr_params = {
    'rows': 10,  # Instead of unlimited
}
```

### 5. Action Plan

Phased approach:
- **Week 1:** Quick wins (limit results, boost content)
- **Week 2:** Version filtering
- **Week 3-4:** Content quality improvements

### 6. Success Metrics

Before/after targets for each metric.

### 7. Metric Explanations

Detailed explanation of what each metric means with examples.

---

### Question Metrics Report (detailed breakdown)

The **QUESTION_METRICS_REPORT.md** file shows every question with its individual metric scores. It's useful for:

**When to use this report:**
- Debugging specific failing tests
- Identifying which question types have issues
- Deep-diving into metric discrepancies
- Sharing specific examples with teams

**What it contains:**

For each question:
- **Query text** - The actual question asked
- **All metric scores** - With pass/fail indicators (✅ ❌)
- **Threshold comparison** - Easy to see why tests failed
- **Expected response** - What the correct answer should be
- **Token usage** - API and judge LLM token counts

Example:
```markdown
### turn1

**Query:** How to install DHCP server in RHEL 10?

**Metrics:**
| Metric | Score | Threshold | Result | Reason |
|--------|-------|-----------|--------|--------|
| ragas:context_precision | 0.032 ❌ | 0.70 | FAIL | Only 3.2% relevant |
| ragas:faithfulness | 1.000 ✅ | 0.80 | PASS | Supported by contexts |
```

**Summary sections:**
- Pass rates by metric across all questions
- Questions with most failures (top 10 worst performers)

**Advanced usage:**
```bash
# Include actual responses in report
python scripts/generate_question_metrics_report.py \
    --input eval_output/*/evaluation_*_detailed.csv \
    --output custom_report.md \
    --include-responses

# Include retrieved contexts (warning: makes report very long)
python scripts/generate_question_metrics_report.py \
    --input eval_output/*/evaluation_*_detailed.csv \
    --output custom_report.md \
    --include-contexts --include-responses
```

---

## Prerequisites

### 1. API Running

```bash
# Check if API is available
curl http://127.0.0.1:8443/api/lightspeed/v1/health
```

### 2. Environment Variables

```bash
# For judge LLM (required)
export OPENAI_API_KEY="your-key"
# OR
export GOOGLE_API_KEY="your-key"  # For vertex/gemini

# For API authentication (if needed)
export API_KEY="your-api-key"
```

### 3. okp-mcp Server

Ensure okp-mcp is running with RHEL documentation loaded.

---

## Running Individual Components

### Run Excluded Test Configs

If you want to run the excluded configs separately:

```bash
# Run evaluation_data.yaml
lightspeed-eval \
    --system-config config/system.yaml \
    --eval-data config/evaluation_data.yaml \
    --output-dir eval_output/evaluation_data_only/

# Run multiple expected responses tests
lightspeed-eval \
    --system-config config/system.yaml \
    --eval-data config/evaluation_data_multiple_expected_responses.yaml \
    --output-dir eval_output/multi_response_only/
```

### Run Just One Test Config

```bash
lightspeed-eval \
    --system-config config/system.yaml \
    --eval-data config/temporal_validity_tests_runnable.yaml \
    --output-dir eval_output/temporal_only/
```

### Run Just Correlation Analysis

```bash
python scripts/analyze_metric_correlations.py \
    --input eval_output/*/evaluation_*_detailed.csv \
    --output analysis_output/correlation_only/ \
    --compare-runs
```

### Run Just Version Distribution Analysis

```bash
python scripts/analyze_version_distribution.py \
    --input eval_output/temporal_validity_tests_runnable/evaluation_*_detailed.csv \
    --test-config config/temporal_validity_tests_runnable.yaml \
    --output analysis_output/version_only/
```

### Generate Just the Report

```bash
python scripts/generate_okp_mcp_report.py \
    --output-base eval_output/full_suite_YYYYMMDD_HHMMSS \
    --correlation-analysis analysis_output/full_suite_YYYYMMDD_HHMMSS/correlation_analysis \
    --version-analysis analysis_output/full_suite_YYYYMMDD_HHMMSS/version_analysis \
    --output-file custom_report.md
```

---

## Troubleshooting

### All Tests Show ERROR

**Cause:** API not running or not accessible

**Solution:**
```bash
curl http://127.0.0.1:8443/api/lightspeed/v1/health
# Check logs for API errors
```

### context_precision Shows ERROR

**Cause:** Malformed LLM output from judge model

**Solution:**
```yaml
# In config/system.yaml
llm:
  max_tokens: 4096  # Increase from 2048
```

### Temporal Tests Fail

**Cause:** okp-mcp not returning RHEL version in contexts

**Solution:** Check that RHEL version metadata is indexed in Solr

### Script Fails Partway Through

**Partial results are OK!** The script saves each test run independently. You can:
1. Check which tests succeeded
2. Review partial analysis
3. Re-run just failed tests later

---

## Interpreting Results

### Good Results (okp-mcp Healthy)

```
context_precision: >0.6
context_relevance: >0.7
faithfulness: >0.8
answer_correctness: >0.9
Overall pass rate: >75%
```

### Poor Results (okp-mcp Needs Work)

```
context_precision: 0.2-0.4  ← Too much noise
context_relevance: 0.3-0.5  ← Poor ranking
faithfulness: 0.6-0.8       ← Marginally usable
answer_correctness: 0.8-0.9 ← LLM compensates
Overall pass rate: 50-60%   ← Below target
```

**Key insight:** If answer_correctness is high but context metrics are low, the LLM is finding signal in noise OR using parametric knowledge (not ideal for RAG).

---

## Sharing Results

### For okp-mcp Developers

Send them:
1. **RAG_QUALITY_REPORT_FOR_OKP_MCP.md** (main report)
2. `correlation_analysis/summary_report.txt` (metrics overview)
3. `correlation_analysis/anomalies.csv` (specific problem cases)
4. `version_analysis/version_distribution_report.txt` (version filtering issues)

### For Management

Key talking points from report:
- Overall pass rate (target: >75%)
- Primary issue: Over-retrieval
- Quick wins: 30-50% improvement possible
- Timeline: 3-4 weeks to implement fixes

### For Evaluation Team

Full analysis outputs:
- All CSVs for detailed investigation
- Heatmaps and scatter plots for visualization
- Anomaly list for test case refinement

---

## Next Steps After Running

1. **Read the report:** `cat analysis_output/full_suite_*/RAG_QUALITY_REPORT_FOR_OKP_MCP.md`
2. **Review visualizations:** Open `*.png` files in `correlation_analysis/`
3. **Identify worst cases:** Check `anomalies.csv` for specific problems
4. **Share with okp-mcp:** Send report + anomalies
5. **Track improvements:** Re-run after okp-mcp fixes to measure progress

---

## Advanced Usage

### Compare Multiple Runs

After okp-mcp makes improvements, run again and compare:

```bash
# First run (baseline)
./run_full_evaluation_suite.sh
# Output: eval_output/full_suite_20260323_100000

# After okp-mcp improvements
./run_full_evaluation_suite.sh
# Output: eval_output/full_suite_20260324_150000

# Compare
python scripts/analyze_metric_correlations.py \
    --input eval_output/full_suite_20260323_100000/*/evaluation_*_detailed.csv \
            eval_output/full_suite_20260324_150000/*/evaluation_*_detailed.csv \
    --output analysis_output/before_after_comparison/ \
    --compare-runs
```

### Add Custom Test Configs

Add new YAML files to `config/` directory, then edit `run_full_evaluation_suite.sh`:

```bash
TEST_CONFIGS=(
    "config/evaluation_data.yaml"
    "config/your_new_tests.yaml"  # Add here
    # ...
)
```

### Customize Report

Edit `scripts/generate_okp_mcp_report.py` to:
- Add new sections
- Include additional metrics
- Change formatting
- Add company-specific context

---

## Summary

**Single command to run everything:**
```bash
./run_full_evaluation_suite.sh
```

**Main deliverable:**
```
analysis_output/full_suite_YYYYMMDD_HHMMSS/RAG_QUALITY_REPORT_FOR_OKP_MCP.md
```

**Time required:** 30-60 minutes

**Value:** Comprehensive RAG quality analysis with specific, actionable fixes for okp-mcp team

---

**Questions?** See:
- `docs/HOW_TO_RUN_TEMPORAL_TESTS.md` - Temporal test details
- `RSPEED-2685_COMPLETION_SUMMARY.md` - Investigation background
- `scripts/README.md` - Analysis script documentation

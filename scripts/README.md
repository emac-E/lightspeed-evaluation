# Analysis Scripts Documentation

This directory contains analysis scripts for processing evaluation outputs and generating insights about RAG retrieval quality.

## Quick Start

**Run everything at once:**
```bash
# From project root
./run_full_evaluation_suite.sh
```

This runs all evaluations + all analysis scripts + generates the okp-mcp report automatically.

---

## Scripts Overview

### 1. `analyze_metric_correlations.py`

Cross-metric correlation analysis tool that validates evaluation framework health and identifies retrieval issues.

#### Features

- **Correlation Analysis**: Pearson, Spearman, and Kendall correlations
- **Anomaly Detection**: RAG_BYPASS, UNFAITHFUL_RESPONSE, PARAMETRIC_KNOWLEDGE
- **Visualization**: Heatmaps, scatter plots, run comparisons
- **Multi-Run Comparison**: Compare before/after okp-mcp improvements
- **Threshold Recommendations**: Statistical analysis of metric calibration

#### Usage

**Single evaluation run:**
```bash
python scripts/analyze_metric_correlations.py \
    --input eval_output/evaluation_20260317_142455_detailed.csv \
    --output analysis_output/single_run/
```

**Compare multiple runs:**
```bash
python scripts/analyze_metric_correlations.py \
    --input eval_output/run1/evaluation_*_detailed.csv \
            eval_output/run2/evaluation_*_detailed.csv \
    --output analysis_output/comparison/ \
    --compare-runs
```

**Analyze all runs:**
```bash
python scripts/analyze_metric_correlations.py \
    --input eval_output/*/evaluation_*_detailed.csv \
    --output analysis_output/all_runs/ \
    --compare-runs
```

#### Outputs

| File | Description |
|------|-------------|
| `summary_report.txt` | Human-readable summary with recommendations |
| `correlation_pearson.csv` | Pearson correlation matrix |
| `correlation_spearman.csv` | Spearman correlation matrix |
| `correlation_kendall.csv` | Kendall correlation matrix |
| `correlation_heatmap.png` | Visual correlation matrix |
| `scatter_matrix.png` | Pairwise scatter plots |
| `anomalies.csv` | Detected anomalous cases |
| `run_comparison.png` | Multi-run comparison (with --compare-runs) |

#### Anomaly Types

| Type | Description | Meaning |
|------|-------------|---------|
| **RAG_BYPASS** | High answer_correctness + low context_precision | LLM found signal in noise or used parametric knowledge |
| **UNFAITHFUL_RESPONSE** | High context_relevance + low faithfulness | LLM added info beyond contexts |
| **PARAMETRIC_KNOWLEDGE** | Zero context scores + correct answer | LLM bypassed RAG entirely |

---

### 2. `analyze_version_distribution.py`

Analyzes RHEL version distribution in retrieved contexts to measure okp-mcp version filtering quality.

#### Features

- Extracts RHEL version numbers from contexts (supports "RHEL 10", "Red Hat Enterprise Linux 10", etc.)
- Calculates version accuracy per conversation
- Overall statistics and trends
- JSON + text report output

#### Usage

```bash
python scripts/analyze_version_distribution.py \
    --input eval_output/temporal_tests/evaluation_*_detailed.csv \
    --test-config config/temporal_validity_tests_runnable.yaml \
    --output analysis_output/version_analysis/
```

#### Outputs

| File | Description |
|------|-------------|
| `version_distribution.json` | Detailed per-conversation analysis |
| `version_distribution_report.txt` | Human-readable summary |

#### Interpretation

**Version Accuracy Levels:**
- **>80%**: Good version filtering ✅
- **50-80%**: Needs improvement 🟡
- **<50%**: Poor version filtering, urgent fix needed ❌

**Example Report:**
```
Total conversations: 15
Conversations with version strings: 12
Average version accuracy: 62.5%

TEMPORAL-REMOVED-001 (Target: RHEL 10)
  Contexts analyzed: 200
  Version accuracy: 58% (116/200 contexts match RHEL 10)
  Issues: 42% are RHEL 9 or RHEL 8 docs
```

---

### 3. `generate_question_metrics_report.py`

Generates detailed per-question breakdown showing all metric scores for each query.

#### Features

- Shows each question with all its metric scores
- Identifies which questions perform poorly
- Includes pass/fail status with thresholds
- Optional: Include contexts and responses
- Summary statistics by metric
- Top failing questions list

#### Usage

```bash
# Basic report
python scripts/generate_question_metrics_report.py \
    --input eval_output/temporal_tests/evaluation_*_detailed.csv \
    --output analysis_output/question_report.md

# Include responses (makes report longer)
python scripts/generate_question_metrics_report.py \
    --input eval_output/*/evaluation_*_detailed.csv \
    --output analysis_output/question_report.md \
    --include-responses

# Include contexts (makes report much longer)
python scripts/generate_question_metrics_report.py \
    --input eval_output/*/evaluation_*_detailed.csv \
    --output analysis_output/question_report.md \
    --include-contexts \
    --include-responses
```

#### Output

**File:** `QUESTION_METRICS_REPORT.md`

**For each question:**
- Conversation and turn ID
- Query text
- All metric scores with pass/fail indicators (✅ ❌)
- Expected response
- Token usage (API + judge)
- Optionally: actual response and contexts

**Summary sections:**
- Pass rates by metric
- Questions with most failures

#### Example Entry

```markdown
### turn1

**Query:** How to install DHCP server in RHEL 10?

**Metrics:**

| Metric | Score | Threshold | Result | Reason |
|--------|-------|-----------|--------|--------|
| ragas:context_precision | 0.032 ❌ | 0.70 | FAIL | Only 3.2% relevant |
| ragas:faithfulness | 1.000 ✅ | 0.80 | PASS | Supported by contexts |

**Expected Response:**
```
Kea is the DHCP server in RHEL 10...
```

**Token Usage:**
- API Input: 1523
- API Output: 156
```

#### Use Cases

- **Debugging:** Deep-dive into specific failing tests
- **Pattern Analysis:** Identify question types that fail
- **Team Sharing:** Show specific examples to stakeholders
- **Metric Investigation:** Understand why metrics disagree

---

### 4. `generate_okp_mcp_report.py`

Generates comprehensive RAG quality report for okp-mcp developers, synthesizing all analysis results.

#### Features

- Explains metrics in terms okp-mcp developers understand
- Maps metrics to specific retrieval issues
- Provides code fixes with examples
- Includes actionable phased implementation plan
- Synthesizes correlation + version analysis results

#### Usage

```bash
# After running full evaluation suite
python scripts/generate_okp_mcp_report.py \
    --output-base eval_output/full_suite_20260323_100000 \
    --correlation-analysis analysis_output/full_suite_20260323_100000/correlation_analysis \
    --version-analysis analysis_output/full_suite_20260323_100000/version_analysis

# Custom output location
python scripts/generate_okp_mcp_report.py \
    --output-base eval_output/my_run \
    --correlation-analysis analysis_output/my_run/correlation \
    --output-file custom_report.md
```

#### Output

**File:** `RAG_QUALITY_REPORT_FOR_OKP_MCP.md`

**Sections:**
1. **Executive Summary** - Metric → okp-mcp impact mapping
2. **Critical Issues** - Performance analysis + version filtering
3. **Root Cause Analysis** - 4 primary issues:
   - Over-retrieval (100-250 contexts vs 10-20)
   - Poor ranking (boilerplate first)
   - No version filtering
   - Boilerplate pollution
4. **Specific Examples** - Anomalous cases
5. **Action Plan** - 3-4 week phased implementation
6. **Success Metrics** - Before/after targets
7. **Appendix** - Detailed metric explanations

**Example Fix from Report:**
```python
# Fix over-retrieval
solr_params = {
    'rows': 10,  # Instead of unlimited
    'qf': 'content^5.0 title^2.0',  # Boost content
    'bq': f'version:{target_version}^10.0',  # Boost target RHEL version
}
```

---

## Common Workflows

### Workflow 1: Complete Analysis (Recommended)

```bash
# Run everything
./run_full_evaluation_suite.sh

# Results in:
# - eval_output/full_suite_YYYYMMDD_HHMMSS/
# - analysis_output/full_suite_YYYYMMDD_HHMMSS/
# - RAG_QUALITY_REPORT_FOR_OKP_MCP.md

# Read the report
cat eval_output/full_suite_*/RAG_QUALITY_REPORT_FOR_OKP_MCP.md
```

### Workflow 2: Single Test Deep Dive

```bash
# Run one test
lightspeed-eval \
    --system-config config/system.yaml \
    --eval-data config/temporal_validity_tests_runnable.yaml \
    --output-dir eval_output/temporal_only/

# Analyze correlations
python scripts/analyze_metric_correlations.py \
    --input eval_output/temporal_only/evaluation_*_detailed.csv \
    --output analysis_output/temporal_only/

# Analyze versions
python scripts/analyze_version_distribution.py \
    --input eval_output/temporal_only/evaluation_*_detailed.csv \
    --test-config config/temporal_validity_tests_runnable.yaml \
    --output analysis_output/temporal_only/

# Review
cat analysis_output/temporal_only/summary_report.txt
cat analysis_output/temporal_only/version_distribution_report.txt
```

### Workflow 3: Before/After Comparison

```bash
# Baseline
./run_full_evaluation_suite.sh
# → eval_output/full_suite_20260323_100000

# ... okp-mcp makes improvements ...

# After improvements
./run_full_evaluation_suite.sh
# → eval_output/full_suite_20260324_150000

# Compare
python scripts/analyze_metric_correlations.py \
    --input eval_output/full_suite_20260323_100000/*/evaluation_*_detailed.csv \
            eval_output/full_suite_20260324_150000/*/evaluation_*_detailed.csv \
    --output analysis_output/before_after/ \
    --compare-runs

# Review improvement
cat analysis_output/before_after/summary_report.txt
```

---

## Understanding Outputs

### Correlation Analysis

**Expected Correlations:**
- `context_precision ↔ context_relevance`: **+0.7 to +0.9** (both measure context quality)
- `faithfulness ↔ response_relevancy`: **+0.3 to +0.5** (both measure response quality)

**Suspicious Patterns:**
- Strong negative correlations (<-0.3)
- Very weak where positive expected
- Very strong (>0.9) suggests redundancy

**Example:**
```
CORRELATION SUMMARY (Pearson)
Strongest Correlations:
  +0.784  context_precision ↔ context_relevance  ✅ Expected
  -0.262  context_relevance ↔ faithfulness  ⚠️ Suspicious
```

The negative correlation means: when contexts are relevant, faithfulness is low. This suggests retrieval is finding related docs but LLM isn't using them (possibly because they're buried in boilerplate).

### Anomalies

**Anomalies are NOT bugs!** They reveal system behavior:

- **High anomaly rate (>10%)**: Systematic retrieval issues
- **RAG_BYPASS cluster**: okp-mcp over-retrieval (LLM digs through noise)
- **PARAMETRIC_KNOWLEDGE**: LLM knows answer without docs (common for basics)

**Action:** Review `anomalies.csv` for patterns, not individual fixes.

### Version Distribution

**Per-conversation accuracy:**
- Shows which queries get wrong-version docs
- Helps prioritize okp-mcp fixes
- Example: DHCP queries consistently get RHEL 9 docs instead of RHEL 10

**Overall accuracy:**
- System health metric
- Track over time
- Expected improvement: 50% → 80% after version boost in Solr

---

## Troubleshooting

### "FileNotFoundError: No such file"

**Cause:** Evaluation didn't run or outputs in different location

**Fix:**
```bash
# Find actual outputs
find eval_output -name "evaluation_*_detailed.csv"

# Use correct path
python scripts/analyze_metric_correlations.py \
    --input eval_output/YOUR_ACTUAL_PATH/evaluation_*_detailed.csv \
    --output analysis_output/
```

### "No module named 'pandas'"

**Cause:** Missing dependencies

**Fix:**
```bash
uv sync --group dev
# or
pip install pandas numpy matplotlib seaborn scipy
```

### "ValueError: `x` and `y` must have length at least 2"

**Cause:** Evaluation run has fewer than 2 data points (conversations/turns)

**Fix:**
- Run evaluation on at least 2 test cases
- If testing single conversation, ensure it has multiple turns
- For full correlation analysis, recommend 10+ data points

**Note:** The script will now skip correlation calculations and show warnings instead of crashing.

### Empty heatmap or "insufficient data"

**Cause:** Too few data points or no variance

**Fix:**
- Run on full test suite, not single test
- Check CSV has multiple conversations
- Verify metrics have different values (not all 0 or all 1)
- Minimum 2 data points required, 10+ recommended for meaningful analysis

### Version distribution shows 0%

**Cause:** Contexts don't contain "RHEL X" strings

**Fix:**
- Check okp-mcp includes version in context metadata
- Verify Solr index has version field
- Review temporal test expected versions match reality

---

## Advanced Usage

### Filter to Specific Metrics

```bash
# Extract only context metrics
awk -F',' 'NR==1 || $3 ~ /context_precision|context_relevance/' \
    eval_output/evaluation_*_detailed.csv > filtered.csv

python scripts/analyze_metric_correlations.py \
    --input filtered.csv \
    --output analysis_output/context_only/
```

### Batch Process Multiple Runs

```bash
for run_dir in eval_output/full_suite_*/; do
    run_name=$(basename "$run_dir")
    python scripts/analyze_metric_correlations.py \
        --input "${run_dir}"/*/evaluation_*_detailed.csv \
        --output "analysis_output/${run_name}/"
done
```

### Programmatic Access

```python
from scripts.analyze_metric_correlations import CorrelationAnalyzer

analyzer = CorrelationAnalyzer()
analyzer.load_data(["eval_output/run1_detailed.csv"])
df = analyzer.analyze_run("run1")

# Access results
pearson = analyzer.correlation_results["run1"]["pearson"]
anomalies = analyzer.anomalies["run1"]
```

---

## Related Tasks

These scripts address RSPEED-2685 investigation:

- **Task #6**: Implement cross-metric correlation analysis ✅
- **Task #8**: Analyze faithfulness threshold calibration ✅
- **Task #10**: Design temporal validity tests ✅
- **Task #12**: Create okp-mcp improvement ticket ✅

---

## Dependencies

All included in `pyproject.toml`:
- pandas
- numpy
- scipy
- matplotlib
- seaborn

Install with: `uv sync --group dev`

---

## Contributing

### Add New Anomaly Type

Edit `analyze_metric_correlations.py`:
```python
# In detect_anomalies() method
if your_condition:
    new_anomaly = pivot[your_filter].copy()
    new_anomaly["anomaly_type"] = "YOUR_TYPE"
    anomalies.append(new_anomaly)
```

### Add Report Section

Edit `generate_okp_mcp_report.py`:
```python
report += f"""
### Your New Section
{your_analysis}
"""
```

---

## FAQ

**Q: How long does full suite take?**
A: 30-60 minutes for ~100 test cases

**Q: Can I run analysis without re-running evals?**
A: Yes! Scripts work on existing CSVs

**Q: What if some tests fail?**
A: Partial results are fine, scripts analyze available data

**Q: How to share with okp-mcp team?**
A: Send `RAG_QUALITY_REPORT_FOR_OKP_MCP.md` + `anomalies.csv`

**Q: How to track improvements?**
A: Run full suite periodically, use `--compare-runs`

---

**See Also:**
- `../RUN_ALL_EVALS.md` - Complete workflow guide
- `../docs/HOW_TO_RUN_TEMPORAL_TESTS.md` - Temporal testing details
- `../RSPEED-2685_COMPLETION_SUMMARY.md` - Investigation background

---

*Last updated: 2026-03-23*

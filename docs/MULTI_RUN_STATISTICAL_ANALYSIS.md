# Multi-Run Statistical Analysis and Variance Testing

**Purpose:** Establish statistical confidence in evaluation results through repeated testing and variance analysis

**Status:** Design Specification

**Estimated Effort:** 2-3 days implementation + ongoing per-run analysis

**Cost Estimate:** Variable ($5-50 per analysis depending on sample size and test suite)

---

## Table of Contents

1. [Overview](#overview)
2. [Motivation](#motivation)
3. [Statistical Background](#statistical-background)
4. [Implementation Workflow](#implementation-workflow)
5. [Sample Size Guidelines](#sample-size-guidelines)
6. [Scripts and Tools](#scripts-and-tools)
7. [Analysis Methodology](#analysis-methodology)
8. [Expected Outputs](#expected-outputs)
9. [Implementation Checklist](#implementation-checklist)
10. [Usage Examples](#usage-examples)
11. [Debugging Tips](#debugging-tips)

---

## Overview

Multi-run statistical analysis addresses the **variance problem** in LLM evaluation:

**The Problem:** A single evaluation run tells you "what happened once" but not "what typically happens"

**The Solution:** Run multiple evaluations and use statistical methods to:

1. **Quantify variance** - How much do results fluctuate?
2. **Establish confidence** - Are improvements real or luck?
3. **Detect regressions** - Did this change actually help?
4. **Set baselines** - What's our true performance?

### Key Metrics

| Metric | What It Measures | Good Value |
|--------|------------------|------------|
| **Mean** | Average performance | Depends on metric |
| **Standard Deviation** | How much results vary | Low (< 10% of mean) |
| **Confidence Interval** | Range of likely values | Narrow (< 5% width) |
| **p-value** | Statistical significance | < 0.05 (significant) |
| **Coefficient of Variation (CV)** | Relative variance | < 20% (stable) |

---

## Motivation

### Problem Statement

From recent evaluation work:
- Single run showed 40% → 60% improvement (version filtering)
- But was this real or just LLM variance?
- Pattern tightening showed 60% → 50% drop (regression or variance?)
- Need to know: **How many runs before we can trust results?**

### Questions This Answers

1. **"Is my improvement statistically significant?"**
   - Answer: "Yes, p=0.003, mean improved from 40.2% to 59.8% with 95% CI"

2. **"How many test runs do I need?"**
   - Answer: "3 for directional feedback, 10 for PR validation, 30 for baselines"

3. **"Is this metric too noisy to use?"**
   - Answer: "Yes, CV=45% means results are unreliable"

4. **"Did this code change cause a regression?"**
   - Answer: "No, difference is within expected variance (p=0.32)"

### Real Example from Our Work

**Version Filtering Impact (Without Multi-Run Analysis):**
```
Before: 40% pass rate (1 run)
After:  60% pass rate (1 run)
Conclusion: +50% improvement!
```

**Version Filtering Impact (With Multi-Run Analysis - Needed):**
```
Before: 40.2% ± 3.1% pass rate (10 runs, 95% CI: [37.1%, 43.3%])
After:  59.8% ± 2.8% pass rate (10 runs, 95% CI: [57.0%, 62.6%])
t-test: p < 0.001 (highly significant)
Conclusion: +19.6% improvement (statistically significant)
```

The second tells us the improvement is **real and reproducible**.

---

## Statistical Background

### Why LLM Evaluations Have Variance

**Sources of variance:**

1. **Response Generation Variance**
   - Even with temperature=0, LLMs have sampling variation
   - Token-level randomness accumulates
   - Model state varies between API calls

2. **Judge LLM Variance**
   - Ragas/DeepEval use LLMs to score responses
   - Judge models also have sampling variance
   - Different runs may score identically slightly differently

3. **Temporal Factors**
   - API load affects response time/quality
   - Model versions may change (provider updates)
   - Rate limiting and throttling effects

### Central Limit Theorem Application

**The Math:**
- With n ≥ 30 samples, sample mean approaches normal distribution
- With n ≥ 10 samples, can approximate with t-distribution
- With n < 10 samples, results are unreliable

**For our use case:**
- **n=3-5**: Directional signal only (development)
- **n=10-20**: Good confidence (pre-deployment)
- **n=30+**: Publication quality (baselines)

### Statistical Tests

**t-test (comparing two conditions):**
```python
from scipy import stats

baseline_scores = [40, 42, 38, 41, 39, 40, 41, 38, 42, 40]  # 10 runs
feature_scores = [58, 62, 60, 59, 61, 58, 60, 62, 59, 61]   # 10 runs

t_stat, p_value = stats.ttest_ind(baseline_scores, feature_scores)

if p_value < 0.05:
    print("✓ Statistically significant improvement")
else:
    print("✗ Not statistically significant")
```

**Interpretation:**
- **p < 0.001**: Highly significant (very confident)
- **p < 0.01**: Significant (confident)
- **p < 0.05**: Marginally significant (somewhat confident)
- **p ≥ 0.05**: Not significant (could be random)

**Confidence Intervals (uncertainty range):**
```python
import numpy as np

mean = np.mean(scores)
std = np.std(scores, ddof=1)
ci = stats.t.interval(0.95, len(scores)-1, loc=mean, scale=stats.sem(scores))

print(f"Mean: {mean:.1f}%")
print(f"95% CI: [{ci[0]:.1f}%, {ci[1]:.1f}%]")
# Example: Mean: 59.8%, 95% CI: [57.2%, 62.4%]
```

**Coefficient of Variation (relative stability):**
```python
cv = (std / mean) * 100

if cv < 10:
    print("Low variance - stable metric")
elif cv < 20:
    print("Moderate variance - acceptable")
else:
    print("High variance - unreliable metric")
```

---

## Implementation Workflow

### Phase 1: Run Collection Script

Create `scripts/run_n_evals.sh` to automate multiple runs:

```bash
#!/bin/bash
# Run N evaluations for statistical analysis

RUNS=${1:-10}
CONFIG=${2:-config/temporal_validity_tests_runnable.yaml}
OUTPUT_PREFIX="multi_run_$(date +%Y%m%d_%H%M%S)"

echo "Running $RUNS evaluations with config: $CONFIG"

for i in $(seq 1 $RUNS); do
    echo "========================================="
    echo "Run $i of $RUNS"
    echo "========================================="

    lightspeed-eval \
        --system-config config/system.yaml \
        --eval-data "$CONFIG" \
        --output-dir "eval_output/${OUTPUT_PREFIX}_run${i}"

    # Rate limiting
    if [ $i -lt $RUNS ]; then
        sleep 5
    fi
done

echo "Completed $RUNS runs in eval_output/${OUTPUT_PREFIX}_run*"
```

### Phase 2: Statistical Analysis Script

Create `scripts/analyze_multi_run.py`:

**Core functionality:**
1. Load all runs with matching prefix
2. Calculate per-metric statistics (mean, std, CI)
3. Assess variance (coefficient of variation)
4. Generate statistical reports
5. Create visualizations

**Key functions:**
```python
def load_multi_run_data(prefix: str) -> pd.DataFrame:
    """Load data from all runs with given prefix."""
    # Find all run directories
    # Combine CSVs with run_number field
    # Return combined DataFrame

def calculate_statistics(df: pd.DataFrame) -> dict:
    """Calculate statistical measures per metric."""
    # Group by metric
    # Calculate mean, std, CI, CV
    # Return statistics dictionary

def detect_variance_issues(stats: dict) -> list:
    """Identify metrics with high variance."""
    # Check CV > 20%
    # Return list of problematic metrics

def generate_report(stats: dict, output_file: Path):
    """Generate statistical analysis report."""
    # Write formatted text report
    # Include interpretations and warnings
```

### Phase 3: Comparison Script

Create `scripts/compare_multi_runs.py` to compare two sets of runs:

```python
def compare_run_sets(baseline_prefix: str, feature_prefix: str):
    """Compare two sets of multi-run data."""
    baseline_data = load_multi_run_data(baseline_prefix)
    feature_data = load_multi_run_data(feature_prefix)

    results = []
    for metric in baseline_data['metric'].unique():
        # Extract scores for this metric
        baseline_scores = baseline_data[baseline_data['metric'] == metric]['pass_rate']
        feature_scores = feature_data[feature_data['metric'] == metric]['pass_rate']

        # Statistical test
        t_stat, p_value = stats.ttest_ind(baseline_scores, feature_scores)

        # Effect size
        cohens_d = calculate_cohens_d(baseline_scores, feature_scores)

        results.append({
            'metric': metric,
            'baseline_mean': baseline_scores.mean(),
            'feature_mean': feature_scores.mean(),
            'improvement': feature_scores.mean() - baseline_scores.mean(),
            'p_value': p_value,
            'significant': p_value < 0.05,
            'effect_size': cohens_d
        })

    return pd.DataFrame(results)
```

---

## Sample Size Guidelines

### By Use Case

| Use Case | Sample Size | Confidence | When to Use |
|----------|-------------|------------|-------------|
| **Quick Iteration** | 3-5 runs | Directional only | Development, debugging |
| **Pre-PR Validation** | 10-20 runs | ~85% confidence | Before merging changes |
| **Baseline Establishment** | 30+ runs | ~95% confidence | Setting benchmarks |
| **Problem Question Analysis** | 20-30 runs | High confidence | Investigating failures |

### Sample Size Calculator

**For detecting improvements:**

```python
def required_sample_size(
    expected_improvement: float,
    variance: float,
    confidence: float = 0.95,
    power: float = 0.80
) -> int:
    """Calculate required sample size for detecting improvement.

    Args:
        expected_improvement: Expected effect size (e.g., 0.10 for 10%)
        variance: Expected standard deviation
        confidence: Confidence level (0.95 = 95%)
        power: Statistical power (0.80 = 80% chance of detecting real effect)

    Returns:
        Required sample size per group
    """
    from scipy.stats import norm

    z_alpha = norm.ppf(1 - (1 - confidence) / 2)
    z_beta = norm.ppf(power)

    n = ((z_alpha + z_beta) ** 2 * 2 * variance ** 2) / expected_improvement ** 2

    return int(np.ceil(n))

# Example: Detect 10% improvement with 5% variance
n = required_sample_size(
    expected_improvement=0.10,
    variance=0.05,
    confidence=0.95,
    power=0.80
)
print(f"Need {n} runs per condition")  # Output: Need 8 runs per condition
```

### Adaptive Sampling

Stop early if confidence interval is narrow enough:

```python
def adaptive_sampling(
    initial_runs: int = 5,
    max_runs: int = 30,
    target_ci_width: float = 5.0  # percent
) -> list:
    """Run until confidence interval is narrow enough."""
    results = []

    for run in range(max_runs):
        # Run evaluation
        result = run_single_evaluation()
        results.append(result)

        if len(results) >= initial_runs:
            mean = np.mean(results)
            ci = stats.t.interval(
                0.95,
                len(results)-1,
                loc=mean,
                scale=stats.sem(results)
            )
            ci_width = ci[1] - ci[0]

            if ci_width < target_ci_width:
                print(f"Stopping at {len(results)} runs (CI width: {ci_width:.2f})")
                break

    return results
```

---

## Scripts and Tools

### Directory Structure

```
scripts/
├── run_n_evals.sh              # Run N evaluations
├── analyze_multi_run.py        # Statistical analysis
├── compare_multi_runs.py       # Compare baseline vs feature
├── plot_variance_trends.py     # Visualize variance over runs
└── adaptive_sampler.py         # Auto-stop when confident
```

### Run N Evaluations Script

**Location:** `scripts/run_n_evals.sh`

**Features:**
- Configurable number of runs
- Any test configuration
- Auto-naming with timestamp
- Rate limiting between runs
- Progress tracking

**Usage:**
```bash
# Run 10 temporal tests
./scripts/run_n_evals.sh 10 config/temporal_validity_tests_runnable.yaml

# Run 3 quick iterations
./scripts/run_n_evals.sh 3 config/brian_tests.yaml

# Run 30 for baseline
./scripts/run_n_evals.sh 30 config/full_suite.yaml
```

### Statistical Analysis Script

**Location:** `scripts/analyze_multi_run.py`

**Features:**
- Auto-detects run prefix
- Calculates comprehensive statistics
- Identifies variance issues
- Generates formatted reports
- Creates visualizations

**Usage:**
```bash
# Analyze runs with prefix
python scripts/analyze_multi_run.py multi_run_20260327_120000

# Output:
#   - eval_output/multi_run_20260327_120000_statistics.txt
#   - eval_output/multi_run_20260327_120000_statistics.json
#   - analysis_output/multi_run_20260327_120000/*.png
```

### Comparison Script

**Location:** `scripts/compare_multi_runs.py`

**Features:**
- Compares two run sets statistically
- t-tests for each metric
- Effect size calculations
- Significance indicators
- Regression detection

**Usage:**
```bash
# Compare baseline vs feature
python scripts/compare_multi_runs.py \
    baseline_prefix \
    feature_prefix \
    --output comparison_report.txt
```

### Visualization Script

**Location:** `scripts/plot_variance_trends.py`

**Features:**
- Box plots of score distribution
- Convergence plots (CI width over runs)
- Metric stability comparison
- Per-question variance analysis

**Usage:**
```bash
python scripts/plot_variance_trends.py multi_run_20260327_120000
```

---

## Analysis Methodology

### Per-Metric Analysis

For each metric, calculate:

1. **Descriptive Statistics**
   - Mean (average performance)
   - Median (middle value)
   - Standard deviation (spread)
   - Min/Max (range)
   - 25th/75th percentiles (quartiles)

2. **Confidence Intervals**
   - 95% CI using t-distribution
   - Interpretation: "95% confident true mean is in this range"

3. **Variance Assessment**
   - Coefficient of variation (CV)
   - Classification: Low (<10%), Moderate (10-20%), High (>20%)

4. **Sample Statistics**
   - Number of runs
   - Number of questions evaluated
   - Pass rate distribution

### Comparison Analysis

When comparing baseline vs feature:

1. **Hypothesis Testing**
   - Null hypothesis: No difference between groups
   - Alternative: Feature is different from baseline
   - Use two-sample t-test
   - Report p-value

2. **Effect Size**
   - Cohen's d: Standardized difference
   - Interpretation:
     - Small: d = 0.2
     - Medium: d = 0.5
     - Large: d = 0.8

3. **Practical Significance**
   - Statistical significance (p < 0.05)
   - Practical significance (improvement > threshold)
   - Both are needed!

### Variance Issue Detection

Automatically flag metrics with:

1. **High CV** (> 20%)
   - Metric is too noisy
   - Need more runs or different metric

2. **Wide Confidence Intervals** (> 10% of mean)
   - Uncertain about true performance
   - Need more data

3. **Bimodal Distributions**
   - Two distinct performance modes
   - Investigate why (data quality? question types?)

---

## Expected Outputs

### Statistical Summary Report

**Format:** Plain text with tables

**Example:**
```
================================================================================
MULTI-RUN STATISTICAL ANALYSIS
================================================================================

Run Set: multi_run_20260327_120000
Total Runs: 10
Date Range: 2026-03-27 12:00:00 to 2026-03-27 13:30:00

================================================================================
PER-METRIC STATISTICS
================================================================================

custom:answer_correctness:
  Mean:        76.4%
  Std Dev:     2.8%
  95% CI:      [74.6%, 78.2%]
  CV:          3.7% (Low variance - stable)
  Range:       [72.1%, 80.0%]
  Sample Size: 10 runs, 14 questions

ragas:context_precision_without_reference:
  Mean:        38.6%
  Std Dev:     8.2%
  95% CI:      [32.7%, 44.5%]
  CV:          21.2% (High variance - unstable!)
  Range:       [28.6%, 50.0%]
  Sample Size: 10 runs, 14 questions
  ⚠️  WARNING: High variance detected

ragas:faithfulness:
  Mean:        41.4%
  Std Dev:     4.1%
  95% CI:      [38.5%, 44.3%]
  CV:          9.9% (Moderate variance)
  Range:       [35.7%, 50.0%]
  Sample Size: 10 runs, 14 questions

================================================================================
VARIANCE ISSUES
================================================================================

Metrics with CV > 20% (unreliable):
  - ragas:context_precision_without_reference (CV=21.2%)

Recommendation: These metrics may need:
  - More runs (20-30) to stabilize
  - Investigation into why variance is high
  - Different evaluation approach

================================================================================
RECOMMENDATIONS
================================================================================

✅ Low variance metrics (safe to use):
  - custom:answer_correctness (CV=3.7%)
  - ragas:response_relevancy (CV=5.2%)

⚠️  Moderate variance metrics (use with caution):
  - ragas:faithfulness (CV=9.9%)

❌ High variance metrics (needs investigation):
  - ragas:context_precision_without_reference (CV=21.2%)

For high variance metrics, consider:
  1. Increasing sample size to 20-30 runs
  2. Analyzing question-level variance
  3. Checking for data quality issues
  4. Using alternative metrics
```

### Comparison Report

**Format:** Side-by-side comparison with significance

**Example:**
```
================================================================================
STATISTICAL COMPARISON: Baseline vs Version Filtering
================================================================================

Baseline:  multi_run_baseline_20260327_090000 (10 runs)
Feature:   multi_run_version_filter_20260327_120000 (10 runs)

================================================================================
RESULTS BY METRIC
================================================================================

custom:answer_correctness:
  Baseline:    64.3% ± 2.1% (95% CI: [62.2%, 66.4%])
  Feature:     76.4% ± 2.8% (95% CI: [74.6%, 78.2%])
  Improvement: +12.1 percentage points
  t-test:      p = 0.002 ✓✓ (highly significant)
  Effect size: d = 1.2 (very large effect)
  Verdict:     ✅ SIGNIFICANT IMPROVEMENT

ragas:context_relevance:
  Baseline:    25.0% ± 3.5% (95% CI: [21.5%, 28.5%])
  Feature:     50.0% ± 4.2% (95% CI: [45.8%, 54.2%])
  Improvement: +25.0 percentage points
  t-test:      p < 0.001 ✓✓✓ (highly significant)
  Effect size: d = 2.1 (very large effect)
  Verdict:     ✅ SIGNIFICANT IMPROVEMENT

ragas:faithfulness:
  Baseline:    54.4% ± 5.1% (95% CI: [49.3%, 59.5%])
  Feature:     41.4% ± 4.1% (95% CI: [38.5%, 44.3%])
  Improvement: -13.0 percentage points
  t-test:      p = 0.041 ✓ (marginally significant)
  Effect size: d = 0.7 (medium effect)
  Verdict:     ⚠️  POSSIBLE REGRESSION (investigate!)

ragas:response_relevancy:
  Baseline:    85.2% ± 3.2% (95% CI: [82.0%, 88.4%])
  Feature:     92.9% ± 2.5% (95% CI: [90.4%, 95.4%])
  Improvement: +7.7 percentage points
  t-test:      p = 0.018 ✓ (significant)
  Effect size: d = 0.8 (large effect)
  Verdict:     ✅ SIGNIFICANT IMPROVEMENT

================================================================================
OVERALL ASSESSMENT
================================================================================

Significant Improvements: 3 metrics
  ✅ custom:answer_correctness (+12.1%, p=0.002)
  ✅ ragas:context_relevance (+25.0%, p<0.001)
  ✅ ragas:response_relevancy (+7.7%, p=0.018)

Regressions: 1 metric
  ⚠️  ragas:faithfulness (-13.0%, p=0.041)

No Significant Change: 0 metrics

================================================================================
RECOMMENDATION
================================================================================

Version filtering shows SIGNIFICANT IMPROVEMENTS in 3 out of 4 metrics.

However, investigate faithfulness regression:
  - 13.0 percentage point drop
  - p=0.041 (marginally significant)
  - Could be:
    * Real issue with version filtering
    * Natural variance (borderline p-value)
    * Interaction with other factors

Suggested action:
  1. Run 10 more evaluations of both conditions
  2. Verify faithfulness regression is real
  3. If confirmed, investigate root cause
  4. Otherwise, proceed with deployment
```

### Visualization Outputs

1. **Box Plots** (`box_plots_by_metric.png`)
   - Show distribution for each metric
   - Identify outliers
   - Compare across runs

2. **Convergence Plots** (`confidence_interval_convergence.png`)
   - CI width vs number of runs
   - Shows when to stop collecting data

3. **Variance Comparison** (`variance_by_metric.png`)
   - Bar chart of CV per metric
   - Identifies stable vs unstable metrics

4. **Time Series** (`scores_over_runs.png`)
   - Score trend across sequential runs
   - Detect systematic drift

---

## Implementation Checklist

### Phase 1: Basic Scripts (Week 1)

- [ ] Create `scripts/run_n_evals.sh`
  - [ ] Parse arguments (num_runs, config)
  - [ ] Loop through evaluations
  - [ ] Create numbered output directories
  - [ ] Add rate limiting
  - [ ] Test with 3 runs

- [ ] Create `scripts/analyze_multi_run.py`
  - [ ] Load multi-run data by prefix
  - [ ] Calculate per-metric statistics
  - [ ] Calculate confidence intervals
  - [ ] Generate text report
  - [ ] Test with sample data

### Phase 2: Comparison Tools (Week 1)

- [ ] Create `scripts/compare_multi_runs.py`
  - [ ] Load two run sets
  - [ ] Perform t-tests per metric
  - [ ] Calculate effect sizes
  - [ ] Generate comparison report
  - [ ] Add significance indicators

- [ ] Add to documentation
  - [ ] Update BEST_PRACTICES_TESTING.md
  - [ ] Add examples to README
  - [ ] Document interpretation guide

### Phase 3: Visualizations (Week 2)

- [ ] Create `scripts/plot_variance_trends.py`
  - [ ] Box plots by metric
  - [ ] Convergence plots
  - [ ] Variance comparison
  - [ ] Time series

- [ ] Integrate into `run_full_evaluation_suite.sh`
  - [ ] Add `--multi-run N` flag
  - [ ] Auto-run statistical analysis
  - [ ] Generate all reports

### Phase 4: Advanced Features (Week 2)

- [ ] Implement adaptive sampling
  - [ ] Auto-stop when CI narrow
  - [ ] Progress updates
  - [ ] Cost tracking

- [ ] Add variance issue detection
  - [ ] Auto-flag high CV metrics
  - [ ] Suggest remediation
  - [ ] Question-level analysis

### Phase 5: Integration (Ongoing)

- [ ] Add to CI/CD pipeline
  - [ ] Nightly multi-run baselines
  - [ ] PR validation with 10 runs
  - [ ] Regression detection

- [ ] Create dashboard
  - [ ] Track variance over time
  - [ ] Monitor metric stability
  - [ ] Alert on regressions

---

## Usage Examples

### Example 1: Quick Development Iteration

```bash
# Make code change
vim src/okp_mcp/tools.py

# Quick test with 3 runs
./scripts/run_n_evals.sh 3 config/temporal_validity_tests_runnable.yaml

# Analyze
python scripts/analyze_multi_run.py multi_run_20260327_140000

# Check if improvement is directional
# If yes, continue. If no, revert.
```

### Example 2: Pre-PR Validation

```bash
# Baseline (main branch)
git checkout main
./scripts/run_n_evals.sh 10 config/temporal_validity_tests_runnable.yaml
# Output: multi_run_baseline_20260327_140000

# Feature (your branch)
git checkout feature/version-filtering
./scripts/run_n_evals.sh 10 config/temporal_validity_tests_runnable.yaml
# Output: multi_run_feature_20260327_150000

# Compare
python scripts/compare_multi_runs.py \
    multi_run_baseline_20260327_140000 \
    multi_run_feature_20260327_150000

# If p < 0.05 and improvement > 5%, create PR
```

### Example 3: Monthly Baseline Establishment

```bash
# First of each month
./scripts/run_n_evals.sh 30 config/full_suite.yaml

# Analyze and save as baseline
python scripts/analyze_multi_run.py multi_run_20260401_090000 \
    --save-baseline baselines/april_2026.json

# Track drift over time
python scripts/compare_baselines.py \
    baselines/march_2026.json \
    baselines/april_2026.json
```

### Example 4: Investigating High Variance

```bash
# Metric shows high variance
# Run focused analysis on specific questions

python scripts/analyze_question_variance.py \
    multi_run_20260327_120000 \
    --metric ragas:context_precision_without_reference

# Output shows which questions vary most
# Investigate those questions specifically
```

---

## Debugging Tips

### Common Issues

**Issue:** "No runs found with prefix"
- **Check:** Directory naming matches expected pattern
- **Fix:** Ensure `run_n_evals.sh` creates `multi_run_PREFIX_runN` directories

**Issue:** "Insufficient data for statistics"
- **Check:** Need at least 3 runs for basic stats
- **Fix:** Run more evaluations

**Issue:** "High variance detected in all metrics"
- **Check:** May indicate evaluation environment issues
- **Fix:**
  - Check cache settings
  - Verify API stability
  - Test with deterministic metrics first

**Issue:** "Conflicting significance results"
- **Check:** p-value significant but effect size small
- **Fix:** Both matter - need practical AND statistical significance

### Validation

**Test with synthetic data:**

```python
# Create test data with known properties
import numpy as np

# Baseline: mean=50, std=5
baseline = np.random.normal(50, 5, 10)

# Feature: mean=60, std=5 (true 10-point improvement)
feature = np.random.normal(60, 5, 10)

# Run comparison
# Should detect significant improvement
```

**Check calculations manually:**

```python
# For one metric
scores = [40, 42, 38, 41, 39, 40, 41, 38, 42, 40]

import numpy as np
from scipy import stats

print(f"Mean: {np.mean(scores)}")
print(f"Std: {np.std(scores, ddof=1)}")
print(f"CV: {(np.std(scores, ddof=1) / np.mean(scores)) * 100}%")

ci = stats.t.interval(0.95, len(scores)-1, loc=np.mean(scores), scale=stats.sem(scores))
print(f"95% CI: {ci}")
```

### Performance Optimization

**For large-scale analysis:**

1. **Parallel processing:**
   ```bash
   # Run evaluations in parallel (if resources allow)
   for i in {1..10}; do
       lightspeed-eval ... &
   done
   wait
   ```

2. **Incremental analysis:**
   ```python
   # Don't reload all data each time
   # Cache intermediate results
   ```

3. **Sampling:**
   ```python
   # For quick checks, sample subset of questions
   # Full analysis on subset, detailed on interesting cases
   ```

---

## Future Enhancements

1. **Bayesian Analysis**
   - Prior distributions from historical data
   - Posterior updates with new runs
   - Better for small sample sizes

2. **Sequential Testing**
   - Stop as soon as significant
   - Reduces unnecessary runs
   - Adaptive significance thresholds

3. **Multi-Level Modeling**
   - Account for question-level variation
   - Model random effects
   - Better variance decomposition

4. **Anomaly Detection**
   - Flag unusual runs
   - Detect data quality issues
   - Auto-exclude outliers with justification

5. **Cost-Aware Sampling**
   - Optimize sample size for budget
   - Focus runs on uncertain metrics
   - Skip stable metrics after few runs

---

## References

- Central Limit Theorem: https://en.wikipedia.org/wiki/Central_limit_theorem
- Student's t-test: https://en.wikipedia.org/wiki/Student%27s_t-test
- Cohen's d: https://en.wikipedia.org/wiki/Effect_size#Cohen's_d
- Statistical Power: https://en.wikipedia.org/wiki/Power_of_a_test
- Multiple Comparisons Problem: https://en.wikipedia.org/wiki/Multiple_comparisons_problem

---

## Appendix: Statistical Formulas

### Mean
```
μ = (Σ xᵢ) / n
```

### Standard Deviation
```
σ = √[(Σ(xᵢ - μ)²) / (n - 1)]
```

### Coefficient of Variation
```
CV = (σ / μ) × 100%
```

### Confidence Interval (t-distribution)
```
CI = μ ± t(α/2, n-1) × (σ / √n)
```

### t-statistic (two-sample)
```
t = (μ₁ - μ₂) / √[(σ₁²/n₁) + (σ₂²/n₂)]
```

### Cohen's d
```
d = (μ₁ - μ₂) / σpooled

where σpooled = √[((n₁-1)σ₁² + (n₂-1)σ₂²) / (n₁ + n₂ - 2)]
```

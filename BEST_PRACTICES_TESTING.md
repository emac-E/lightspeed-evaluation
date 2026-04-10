# Best Practices for Evaluation Testing

## Table of Contents
- [Statistical Significance in LLM Evaluation](#statistical-significance-in-llm-evaluation)
- [Recommended Sample Sizes](#recommended-sample-sizes)
- [Practical Testing Workflow](#practical-testing-workflow)
- [Statistical Analysis](#statistical-analysis)
- [Automated Testing Scripts](#automated-testing-scripts)
- [Cost vs Confidence Tradeoffs](#cost-vs-confidence-tradeoffs)

---

## Statistical Significance in LLM Evaluation

### The Problem: Single-Run Variance

LLM evaluations have inherent variance due to:

1. **Response generation variance**
   - Even with `temperature=0`, sampling introduces variation
   - Model state varies between API calls
   - Token-level randomness in generation

2. **Judge LLM variance**
   - Ragas/DeepEval metrics use LLMs to evaluate responses
   - Judge models also have sampling variance
   - Different runs may score identical responses differently

3. **Temporal factors**
   - API load affects response time and potentially quality
   - Model versions may change (provider updates)
   - Rate limiting and throttling effects

**Key Insight:** A single evaluation run tells you "what happened once" but not "what typically happens."

### Why Multiple Runs Matter

Consider this scenario:
```
Single run shows: 40% → 60% pass rate (appears to be +50% improvement)

But with 10 runs:
  Before: 35-45% (mean: 40%, std: 3.2%)
  After:  55-65% (mean: 60%, std: 3.5%)

Conclusion: Improvement is REAL and CONSISTENT
```

vs.

```
Single run shows: 40% → 60% pass rate (appears to be +50% improvement)

But with 10 runs:
  Before: 38-42% (mean: 40%, std: 1.2%)
  After:  38-62% (mean: 50%, std: 8.5%)

Conclusion: High variance, improvement is UNSTABLE
```

---

## Recommended Sample Sizes

### Quick Reference Table

| Use Case | Sample Size | Confidence Level | When to Use |
|----------|-------------|------------------|-------------|
| **Quick Iteration** | 3-5 runs | Directional only | Development, debugging |
| **Pre-PR Validation** | 10-20 runs | ~80-90% confidence | Before merging changes |
| **Benchmark/Baseline** | 30+ runs | ~95% confidence | Establishing ground truth |
| **Problem Questions** | 20-30 runs | High confidence | Investigating failures |

### 1. Quick Iteration/Development (3-5 runs)

**Purpose:** Fast feedback during development

**When to use:**
- Testing if a change helps at all
- Debugging specific failures
- Rapid prototyping
- Sanity checks after code changes

**Limitations:**
- Directional signal only
- Cannot detect small improvements
- High chance of false positives/negatives

**Example:**
```bash
# Quick test of version filtering change
for i in {1..3}; do
  uv run lightspeed-eval run config/temporal_validity_tests_runnable.yaml
done
```

**Interpret results as:**
- "This seems to help" or "This seems to hurt"
- NOT: "This improves by exactly 15.3%"

### 2. Pre-Deployment Validation (10-20 runs)

**Purpose:** Validate improvements before merging

**When to use:**
- Before creating or merging a PR
- Comparing two approaches (A/B testing)
- Detecting regressions
- Measuring moderate effect sizes

**Statistical power:**
- Can detect improvements of ~10% with 80% confidence
- Provides reasonable estimates of mean and variance
- Good balance of cost vs confidence

**Example:**
```bash
# Validate version filtering improvement
for i in {1..10}; do
  uv run lightspeed-eval run config/temporal_validity_tests_runnable.yaml
  sleep 5  # Rate limiting
done
```

**Interpret results as:**
- Calculate mean ± standard deviation
- If std_dev > mean/2, collect more samples
- Use t-test for statistical significance (p < 0.05)

### 3. Benchmark/Baseline Establishment (30+ runs)

**Purpose:** Establish ground truth performance

**When to use:**
- Setting initial baseline metrics
- Major system architecture changes
- Publishing results or reports
- Monthly/quarterly benchmarks

**Statistical power:**
- ~95% confidence intervals
- Can detect small effect sizes (~5%)
- Normal distribution assumptions valid (Central Limit Theorem)

**Example:**
```bash
# Establish monthly baseline
for i in {1..30}; do
  uv run lightspeed-eval run config/full_suite.yaml
  sleep 10
done
```

**Interpret results as:**
- Calculate 95% confidence intervals
- Track metric drift over time
- Use as reference for all future comparisons

### 4. Problem Question Analysis (20-30 runs)

**Purpose:** Deep investigation of poorly performing questions

**When to use:**
- Question fails inconsistently
- Debugging specific failure modes
- Understanding variance patterns

**Example:**
```bash
# Focus on specific problematic questions
for i in {1..20}; do
  uv run lightspeed-eval run config/temporal_validity_tests_runnable.yaml \
    --filter "TEMPORAL-REMOVED-001"
done
```

---

## Practical Testing Workflow

### Phase 1: Development (Current State)

**Goal:** Fast iteration and debugging

**Approach:**
- Run **3 times** per code change
- Look for consistent direction, not exact numbers
- Quick feedback loop (< 30 minutes)

**Workflow:**
```bash
# Make code change
vim src/okp_mcp/tools.py

# Build and deploy
podman build -t localhost/okp-mcp:dev .
# ... deploy to test environment ...

# Run 3 evals
for i in {1..3}; do
  uv run lightspeed-eval run config/temporal_validity_tests_runnable.yaml
done

# Quick analysis
python scripts/analyze_test_failures.py
```

**Decision criteria:**
- All 3 runs show improvement → Continue developing
- Mixed results → Investigate variance
- All 3 runs worse → Revert change

### Phase 2: Pre-PR Validation

**Goal:** Confirm improvement is real and consistent

**Approach:**
- Run **10 times** before creating PR
- Calculate statistical significance
- Ensure improvement is consistent across runs

**Workflow:**
```bash
# After feature is complete
./scripts/run_n_evals.sh 10 config/temporal_validity_tests_runnable.yaml

# Analyze with statistics
python scripts/analyze_statistical_significance.py
```

**Decision criteria:**
- p-value < 0.05 AND improvement > 5% → Create PR
- p-value > 0.05 OR high variance → Investigate further
- Worse performance → Debug or abandon

### Phase 3: Monthly Benchmark

**Goal:** Track long-term trends and establish baseline

**Approach:**
- Run **30 times** once per month
- Establish confidence intervals
- Monitor for metric drift

**Workflow:**
```bash
# First day of month
./scripts/run_n_evals.sh 30 config/full_suite.yaml

# Generate baseline report
python scripts/generate_baseline_report.py

# Track over time
python scripts/plot_baseline_trends.py
```

**Outputs:**
- Baseline metrics with 95% confidence intervals
- Trend analysis over months
- Detection of degradation

---

## Statistical Analysis

### Understanding Variance

**Low Variance (Good):**
```
Run 1: 58%
Run 2: 60%
Run 3: 59%
Mean: 59%, Std Dev: 0.8%

→ System is STABLE, results are REPRODUCIBLE
```

**High Variance (Problem):**
```
Run 1: 45%
Run 2: 68%
Run 3: 52%
Mean: 55%, Std Dev: 9.7%

→ System is UNSTABLE, need to investigate WHY
```

### Calculating Statistical Significance

**Simple t-test approach:**

```python
from scipy import stats

baseline_scores = [40, 42, 38, 41, 39, 40, 41, 38, 42, 40]  # 10 runs
feature_scores = [58, 62, 60, 59, 61, 58, 60, 62, 59, 61]   # 10 runs

# Two-sample t-test
t_statistic, p_value = stats.ttest_ind(baseline_scores, feature_scores)

if p_value < 0.05:
    print("✓ STATISTICALLY SIGNIFICANT improvement")
    print(f"  Baseline: {np.mean(baseline_scores):.1f}% ± {np.std(baseline_scores):.1f}%")
    print(f"  Feature:  {np.mean(feature_scores):.1f}% ± {np.std(feature_scores):.1f}%")
    print(f"  p-value: {p_value:.4f}")
else:
    print("✗ Not statistically significant")
    print(f"  p-value: {p_value:.4f} (need < 0.05)")
```

### Interpreting p-values

| p-value | Interpretation | Action |
|---------|----------------|--------|
| < 0.001 | Highly significant | Very confident in result |
| < 0.01 | Significant | Confident in result |
| < 0.05 | Marginally significant | Reasonably confident |
| < 0.10 | Trend | Suggestive but not conclusive |
| ≥ 0.10 | Not significant | Could be random chance |

### Effect Size

**Don't just look at p-values, also measure effect size:**

```python
# Cohen's d (standardized effect size)
def cohens_d(group1, group2):
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_std = np.sqrt(((n1-1)*var1 + (n2-1)*var2) / (n1+n2-2))
    return (np.mean(group1) - np.mean(group2)) / pooled_std

d = cohens_d(baseline_scores, feature_scores)

# Interpretation:
# |d| < 0.2  : Small effect
# |d| < 0.5  : Medium effect
# |d| < 0.8  : Large effect
# |d| ≥ 0.8  : Very large effect
```

---

## Automated Testing Scripts

### Script 1: Run N Evaluations

Create `scripts/run_n_evals.sh`:

```bash
#!/bin/bash
# Run multiple evaluation runs for statistical analysis

RUNS=${1:-10}
CONFIG=${2:-config/temporal_validity_tests_runnable.yaml}
OUTPUT_PREFIX="multi_run_$(date +%Y%m%d_%H%M%S)"

echo "Running $RUNS evaluations with config: $CONFIG"
echo "Output prefix: $OUTPUT_PREFIX"

for i in $(seq 1 $RUNS); do
  echo ""
  echo "========================================="
  echo "Run $i of $RUNS"
  echo "========================================="

  uv run lightspeed-eval run $CONFIG

  # Move to numbered directory
  LATEST=$(ls -td eval_output/full_suite_* | head -1)
  TARGET="eval_output/${OUTPUT_PREFIX}_run${i}"
  mv "$LATEST" "$TARGET"
  echo "Saved to: $TARGET"

  # Rate limiting
  if [ $i -lt $RUNS ]; then
    echo "Waiting 5 seconds before next run..."
    sleep 5
  fi
done

echo ""
echo "========================================="
echo "Completed $RUNS runs"
echo "========================================="
echo "Output directories: eval_output/${OUTPUT_PREFIX}_run*"
echo ""
echo "Next steps:"
echo "  1. Analyze results: python scripts/analyze_multi_run.py $OUTPUT_PREFIX"
echo "  2. View statistics: cat eval_output/${OUTPUT_PREFIX}_statistics.txt"
```

Make executable:
```bash
chmod +x scripts/run_n_evals.sh
```

### Script 2: Analyze Multiple Runs

Create `scripts/analyze_multi_run.py`:

```python
#!/usr/bin/env python3
"""Analyze results from multiple evaluation runs for statistical significance."""

import argparse
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from scipy import stats

def load_multi_run_data(prefix: str) -> pd.DataFrame:
    """Load data from all runs with given prefix."""
    base_dir = Path("eval_output")
    run_dirs = sorted(base_dir.glob(f"{prefix}_run*"))

    if not run_dirs:
        print(f"No runs found with prefix: {prefix}")
        return pd.DataFrame()

    all_data = []
    for run_dir in run_dirs:
        csv_files = list(run_dir.glob("*/evaluation_*_detailed.csv"))
        for csv_file in csv_files:
            df = pd.read_csv(csv_file)
            run_num = int(run_dir.name.split("_run")[-1])
            df["run_number"] = run_num
            df["run_dir"] = run_dir.name
            all_data.append(df)

    return pd.concat(all_data, ignore_index=True)

def calculate_pass_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate pass rates per run per metric."""
    results = []

    for run in sorted(df["run_number"].unique()):
        run_data = df[df["run_number"] == run]

        for metric in run_data["metric_identifier"].unique():
            metric_data = run_data[run_data["metric_identifier"] == metric]
            total = len(metric_data[metric_data["result"].notna()])
            passed = len(metric_data[metric_data["result"] == "PASS"])
            pass_rate = (passed / total * 100) if total > 0 else 0

            results.append({
                "run": run,
                "metric": metric,
                "total": total,
                "passed": passed,
                "pass_rate": pass_rate,
            })

    return pd.DataFrame(results)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", help="Output prefix from run_n_evals.sh")
    args = parser.parse_args()

    print(f"Analyzing multi-run data: {args.prefix}")
    print("=" * 80)

    df = load_multi_run_data(args.prefix)
    if df.empty:
        return 1

    pass_rates = calculate_pass_rates(df)

    print(f"\nAnalyzing {len(df['run_number'].unique())} runs")
    print(f"Metrics evaluated: {len(pass_rates['metric'].unique())}")
    print("\n" + "=" * 80)
    print("STATISTICAL SUMMARY BY METRIC")
    print("=" * 80)

    for metric in sorted(pass_rates["metric"].unique()):
        metric_data = pass_rates[pass_rates["metric"] == metric]
        rates = metric_data["pass_rate"].values

        mean = np.mean(rates)
        std = np.std(rates, ddof=1)
        min_val = np.min(rates)
        max_val = np.max(rates)

        # Calculate 95% confidence interval
        ci = stats.t.interval(0.95, len(rates)-1, loc=mean, scale=stats.sem(rates))

        print(f"\n{metric}:")
        print(f"  Mean:        {mean:.1f}%")
        print(f"  Std Dev:     {std:.1f}%")
        print(f"  95% CI:      [{ci[0]:.1f}%, {ci[1]:.1f}%]")
        print(f"  Range:       [{min_val:.1f}%, {max_val:.1f}%]")
        print(f"  Runs:        {len(rates)}")

        # Variance assessment
        cv = (std / mean * 100) if mean > 0 else 0
        if cv > 20:
            print(f"  ⚠️  HIGH VARIANCE (CV={cv:.1f}%) - results unstable")
        elif cv > 10:
            print(f"  ⚠️  Moderate variance (CV={cv:.1f}%)")
        else:
            print(f"  ✓  Low variance (CV={cv:.1f}%) - results stable")

    # Save summary
    output_file = Path("eval_output") / f"{args.prefix}_statistics.txt"
    with open(output_file, "w") as f:
        for metric in sorted(pass_rates["metric"].unique()):
            metric_data = pass_rates[pass_rates["metric"] == metric]
            rates = metric_data["pass_rate"].values
            f.write(f"{metric}: {np.mean(rates):.1f}% ± {np.std(rates, ddof=1):.1f}%\n")

    print(f"\n✓ Summary saved to: {output_file}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
```

Make executable:
```bash
chmod +x scripts/analyze_multi_run.py
```

### Usage Example

```bash
# Run 10 evaluations
./scripts/run_n_evals.sh 10 config/temporal_validity_tests_runnable.yaml

# Analyze results
python scripts/analyze_multi_run.py multi_run_20260327_120000

# Compare two sets of runs (baseline vs feature)
python scripts/compare_multi_runs.py baseline_prefix feature_prefix
```

---

## Cost vs Confidence Tradeoffs

### Time and Resource Costs

**Typical evaluation times:**
- Full suite: ~30 minutes
- Temporal tests only: ~5 minutes
- Single question: ~30 seconds

**Cost breakdown:**

| Sample Size | Time (full suite) | Time (temporal only) | LLM API Costs* |
|-------------|------------------|---------------------|----------------|
| 1 run | 30 min | 5 min | $0.50 |
| 3 runs | 90 min | 15 min | $1.50 |
| 10 runs | 5 hours | 50 min | $5.00 |
| 30 runs | 15 hours | 2.5 hours | $15.00 |

*Approximate costs, varies by model and usage

### Optimization Strategies

#### 1. Stratified Sampling

Instead of running everything multiple times:

```bash
# Strategy: Focus runs where variance matters most

# Full suite baseline: 3 runs
./scripts/run_n_evals.sh 3 config/full_suite.yaml

# Temporal tests (what you changed): 10 runs
./scripts/run_n_evals.sh 10 config/temporal_validity_tests_runnable.yaml

# Worst questions only: 20 runs
./scripts/run_n_evals.sh 20 config/problem_questions.yaml
```

**Benefit:** Get high confidence on key metrics without 30x cost

#### 2. Progressive Testing

```bash
# Step 1: Quick check (3 runs)
./scripts/run_n_evals.sh 3 config/temporal_validity_tests_runnable.yaml
python scripts/analyze_multi_run.py latest_prefix

# If promising, continue to Step 2
# Step 2: Validation (7 more runs = 10 total)
./scripts/run_n_evals.sh 7 config/temporal_validity_tests_runnable.yaml
python scripts/analyze_multi_run.py latest_prefix

# If still good, continue to Step 3
# Step 3: Final confirmation (10 more runs = 20 total)
./scripts/run_n_evals.sh 10 config/temporal_validity_tests_runnable.yaml
```

**Benefit:** Stop early if change doesn't help, saving cost

#### 3. Variance-Adaptive Sampling

```python
# Auto-determine sample size based on observed variance
def adaptive_sampling(initial_runs=5, max_runs=30, target_ci_width=5.0):
    """Keep running until confidence interval is narrow enough."""
    results = []

    for run in range(max_runs):
        # Run evaluation
        result = run_evaluation()
        results.append(result)

        if len(results) >= initial_runs:
            mean = np.mean(results)
            ci = stats.t.interval(0.95, len(results)-1,
                                loc=mean, scale=stats.sem(results))
            ci_width = ci[1] - ci[0]

            if ci_width < target_ci_width:
                print(f"Stopping at {len(results)} runs (CI width: {ci_width:.2f})")
                break

    return results
```

---

## Recommendations Summary

### For Your Current Workflow

Based on your scenario with okp-mcp version filtering:

**During Active Development:**
- **3 runs** per code change
- Focus on temporal tests only (5 min each)
- Total time: ~15 minutes per iteration
- Confidence: Directional only

**Before Creating PR:**
- **10 runs** of temporal tests
- Statistical analysis with t-test
- Total time: ~50 minutes
- Confidence: ~85% (good enough to merge)

**Monthly Baseline:**
- **30 runs** of full suite
- Comprehensive statistics
- Total time: ~15 hours (run overnight/weekend)
- Confidence: ~95% (publication quality)

**For Specific Problem Questions:**
- **20 runs** focused on failing questions
- Deep dive into variance patterns
- Understand failure modes

### Decision Framework

```
Is this change ready to merge?

1. Run 10 evaluations
2. Calculate: mean improvement and p-value
3. Decision tree:

   If p < 0.05 AND improvement > 5%:
     → MERGE (statistically significant improvement)

   If p < 0.05 AND improvement < 5%:
     → CONSIDER (significant but small)

   If p > 0.05 AND std_dev < mean/4:
     → INVESTIGATE (low variance but not significant - need more runs?)

   If p > 0.05 AND std_dev > mean/2:
     → DEBUG (high variance - system unstable)

   Otherwise:
     → REJECT (not improving or too unstable)
```

### Key Takeaways

1. **Never trust a single run** for important decisions
2. **3 runs minimum** for any change validation
3. **10 runs standard** for PR validation
4. **30 runs** for establishing baselines
5. **Always report variance** alongside mean
6. **Check p-values** for statistical significance
7. **High variance** means you need to investigate WHY, not just run more tests

---

## References and Further Reading

- Central Limit Theorem: https://en.wikipedia.org/wiki/Central_limit_theorem
- Statistical Power Analysis: https://www.statmethods.net/stats/power.html
- Cohen's d Effect Size: https://en.wikipedia.org/wiki/Effect_size#Cohen's_d
- Multiple Hypothesis Testing: https://en.wikipedia.org/wiki/Multiple_comparisons_problem

---

## Appendix: Your Specific Case Study

### Version Filtering Impact Analysis

**What we observed (single run each):**
- Before: 28/70 passed (40%)
- After: 42/70 passed (60%)
- Improvement: +20 percentage points (+50% relative)

**Was this real or lucky?**

With only 1 run each, we **cannot be certain**. Here's why:

If the true pass rate is actually 50% for both (no real change), there's a ~8% chance of seeing a 20-point swing by random chance alone.

**What you should do next:**

```bash
# Run 10 times with version filtering
cd ~/Work/lightspeed-core/lightspeed-evaluation
./scripts/run_n_evals.sh 10 config/temporal_validity_tests_runnable.yaml
python scripts/analyze_multi_run.py multi_run_VERSION_FILTER

# Compare to baseline (run 10 times without version filtering)
# Switch back to main branch, deploy old version
./scripts/run_n_evals.sh 10 config/temporal_validity_tests_runnable.yaml
python scripts/analyze_multi_run.py multi_run_BASELINE

# Statistical comparison
python scripts/compare_multi_runs.py multi_run_BASELINE multi_run_VERSION_FILTER
```

**Expected outcome if improvement is real:**

```
Baseline:  40% ± 3% (95% CI: [37%, 43%])
Filter:    60% ± 3% (95% CI: [57%, 63%])
t-test:    p < 0.001 (highly significant)
Cohen's d: 2.1 (very large effect)

Conclusion: ✓ Version filtering provides CONSISTENT +20% improvement
```

**Or if it was just luck:**

```
Baseline:  48% ± 8% (95% CI: [40%, 56%])
Filter:    52% ± 9% (95% CI: [43%, 61%])
t-test:    p = 0.35 (not significant)
Cohen's d: 0.4 (small effect)

Conclusion: ✗ No consistent improvement, original result was variance
```

This is why **multiple runs matter** for confident decision-making.

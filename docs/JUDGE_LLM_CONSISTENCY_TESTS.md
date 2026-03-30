# Judge LLM Consistency Comparison Tests

This guide explains how to implement and run judge LLM consistency tests to quantify non-determinism in evaluation metrics.

---

## The Problem

LLM-based metrics (ragas, deepeval) use an **LLM judge** to evaluate responses. Different judges may:
- Give different scores for the same input
- Have different error rates (malformed outputs)
- Show different variance across runs
- Disagree on what constitutes "good" vs "bad"

**This test suite measures how much we can trust these scores.**

---

## The Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. TEST DESIGN                                                  │
└─────────────────────────────────────────────────────────────────┘

Select Representative Test Cases
────────────────────────────────
- 10-20 diverse questions
- Mix of PASS/FAIL/ERROR cases
- Include edge cases (RAG_BYPASS, malformed output triggers)
- Cover all metric types

Define Judge LLMs to Test
─────────────────────────
- gemini-2.5-flash (current default)
- gpt-4o (OpenAI best)
- claude-3.5-sonnet (Anthropic best)
- gemini-1.5-pro (Google alternative)

       │
       │ Configuration
       ▼

┌─────────────────────────────────────────────────────────────────┐
│ 2. CONFIGURATION                                                │
└─────────────────────────────────────────────────────────────────┘

config/judge_comparison_test.yaml
──────────────────────────────────
judges:
  - model: gemini/gemini-2.5-flash
    name: gemini-2.5-flash
    temperature: 0.0
    runs: 3  # Repeat 3 times for variance

  - model: openai/gpt-4o
    name: gpt-4o
    temperature: 0.0
    runs: 3

test_cases:
  - conversation_group_id: CONSISTENCY-TEST-001
    # ...existing test case...

metrics_to_test:
  - ragas:faithfulness
  - ragas:context_relevance
  - ragas:context_precision_without_reference
  - custom:answer_correctness

       │
       │ Execution
       ▼

┌─────────────────────────────────────────────────────────────────┐
│ 3. TEST EXECUTION                                               │
└─────────────────────────────────────────────────────────────────┘

scripts/run_judge_consistency_test.py
─────────────────────────────────────
For each judge:
  For run in [1, 2, 3]:
    # Create temporary system.yaml with this judge
    temp_config = modify_llm_config(
        system_config,
        llm_model=judge.model,
        temperature=judge.temperature
    )

    # Run evaluation
    results = run_evaluation(
        system_config=temp_config,
        eval_data=test_cases,
        output_dir=f"judge_comparison/{judge.name}/run_{run}/"
    )

    # Track execution time, costs, errors
    metrics[judge.name][run] = extract_metrics(results)

       │
       │ Analysis
       ▼

┌─────────────────────────────────────────────────────────────────┐
│ 4. STATISTICAL ANALYSIS                                         │
└─────────────────────────────────────────────────────────────────┘

scripts/analyze_judge_consistency.py
────────────────────────────────────
1. Score Variance Analysis
   - Mean, StdDev, Coefficient of Variation
   - Within-judge variance (3 runs same judge)
   - Between-judge variance (different judges)

2. Inter-Judge Agreement
   - Cohen's Kappa (categorical: PASS/FAIL/ERROR)
   - Pearson correlation (continuous: scores)
   - Fleiss' Kappa (all judges together)

3. Error Rate Comparison
   - Malformed output frequency
   - Execution failures
   - Timeout rates

4. Cost & Performance
   - Execution time per metric
   - Token usage
   - API costs

       │
       │ Visualization
       ▼

┌─────────────────────────────────────────────────────────────────┐
│ 5. REPORT GENERATION                                            │
└─────────────────────────────────────────────────────────────────┘

Output Files:
─────────────
analysis_output/judge_consistency/
├── judge_comparison_summary.md          # Executive summary
├── score_variance_by_metric.csv         # Variance tables
├── inter_judge_agreement.csv            # Kappa/correlation
├── error_rates.csv                      # Error frequencies
├── cost_performance.csv                 # Time/cost data
└── visualizations/
    ├── score_distributions.png          # Box plots
    ├── agreement_heatmap.png            # Inter-judge agreement
    ├── variance_comparison.png          # Error bars
    └── run_consistency.png              # Same judge variance
```

---

## Step-by-Step Implementation

### Step 1: Create Test Configuration

**File:** `config/judge_consistency_test.yaml`

```yaml
# Judge LLM Consistency Test Configuration

description: >
  Tests different LLM judges to measure score variance, inter-judge agreement,
  and error rates across metrics.

# Define which judges to test
judges:
  - name: gemini-2.5-flash
    model: gemini/gemini-2.5-flash
    temperature: 0.0
    max_tokens: 4096
    runs: 3

  - name: gpt-4o
    model: openai/gpt-4o
    temperature: 0.0
    max_tokens: 4096
    runs: 3

  - name: claude-3.5-sonnet
    model: anthropic/claude-3.5-sonnet-20241022
    temperature: 0.0
    max_tokens: 4096
    runs: 3

  - name: gemini-1.5-pro
    model: gemini/gemini-1.5-pro
    temperature: 0.0
    max_tokens: 4096
    runs: 3

# Which metrics to evaluate
metrics_to_test:
  - ragas:faithfulness
  - ragas:context_relevance
  - ragas:context_precision_without_reference
  - ragas:response_relevancy
  - custom:answer_correctness

# Test cases - select diverse representative samples
test_cases:
  # Include from existing test suites
  - include: config/jira_incorrect_answers.yaml
    filter:
      conversation_group_ids:
        - RSPEED-1930  # Known malformed output case
        - RSPEED-2200  # Known RAG bypass case
        - RSPEED-2124  # Missing contexts case

  - include: config/rhel10_features.yaml
    filter:
      tags:
        - rag_bypass
        - high_precision

  # Or define new test cases
  - conversation_group_id: CONSISTENCY-BASELINE-001
    description: "Simple baseline test"
    tag: baseline
    turns:
      - turn_id: turn1
        query: "How to install DHCP in RHEL 10?"
        response: null
        contexts: null
        expected_response: "Install Kea DHCP using dnf install kea..."
        turn_metrics:
          - ragas:faithfulness
          - ragas:context_relevance
          - custom:answer_correctness
```

---

### Step 2: Create Test Runner Script

**File:** `scripts/run_judge_consistency_test.py`

```python
#!/usr/bin/env python3
"""
Run judge LLM consistency comparison tests.

This script:
1. Loads test configuration
2. For each judge LLM:
   - Runs evaluation multiple times (for variance)
   - Captures results, errors, timing
3. Saves results for analysis
"""

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from lightspeed_evaluation.core.models.system import SystemConfig
from lightspeed_evaluation.pipeline.evaluation.pipeline import EvaluationPipeline


class JudgeConsistencyTester:
    """Runs consistency tests across multiple judge LLMs."""

    def __init__(self, config_path: Path):
        """Initialize with test configuration."""
        with open(config_path) as f:
            self.test_config = yaml.safe_load(f)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_base = Path(f"judge_consistency_{self.timestamp}")
        self.output_base.mkdir(exist_ok=True)

    def run_all_tests(self):
        """Run tests for all judges."""
        results = {}

        for judge in self.test_config["judges"]:
            print(f"\n{'='*80}")
            print(f"Testing Judge: {judge['name']}")
            print(f"{'='*80}\n")

            judge_results = self._test_judge(judge)
            results[judge["name"]] = judge_results

        # Save combined results
        self._save_results(results)

        print(f"\n✅ All tests complete! Results in: {self.output_base}")

    def _test_judge(self, judge: dict[str, Any]) -> dict[str, Any]:
        """Run multiple evaluation runs for a single judge."""
        runs = []

        for run_num in range(1, judge["runs"] + 1):
            print(f"  Run {run_num}/{judge['runs']}...")

            # Create temporary config with this judge
            temp_config = self._create_judge_config(judge)

            # Run evaluation
            run_result = self._run_evaluation(
                temp_config,
                output_dir=self.output_base / judge["name"] / f"run_{run_num}"
            )

            runs.append(run_result)

        return {
            "judge": judge,
            "runs": runs,
            "summary": self._summarize_runs(runs),
        }

    def _create_judge_config(self, judge: dict[str, Any]) -> Path:
        """Create temporary system.yaml with specified judge LLM."""
        # Load base system config
        base_config = SystemConfig.from_yaml("config/system.yaml")

        # Modify LLM settings
        config_dict = base_config.model_dump()
        config_dict["llm"]["model"] = judge["model"]
        config_dict["llm"]["temperature"] = judge["temperature"]
        config_dict["llm"]["max_tokens"] = judge["max_tokens"]

        # Write to temp file
        temp_dir = tempfile.mkdtemp()
        temp_config = Path(temp_dir) / "system.yaml"
        with open(temp_config, "w") as f:
            yaml.dump(config_dict, f)

        return temp_config

    def _run_evaluation(self, system_config: Path, output_dir: Path) -> dict[str, Any]:
        """Run single evaluation and capture results."""
        import time
        start_time = time.time()

        try:
            # Load test cases
            test_cases = self._load_test_cases()

            # Run evaluation
            pipeline = EvaluationPipeline(
                system_config=str(system_config),
                eval_data_config=test_cases,
                output_dir=str(output_dir),
            )

            pipeline.run()

            # Extract results
            results = self._extract_results(output_dir)

            return {
                "status": "success",
                "execution_time": time.time() - start_time,
                "results": results,
            }

        except Exception as e:
            return {
                "status": "error",
                "execution_time": time.time() - start_time,
                "error": str(e),
            }

    def _load_test_cases(self) -> str:
        """Load and filter test cases based on config."""
        # Implementation depends on your test case format
        # Could merge multiple test files, filter by IDs, etc.
        return "config/judge_consistency_test.yaml"

    def _extract_results(self, output_dir: Path) -> dict[str, Any]:
        """Extract metrics from evaluation output."""
        import pandas as pd

        # Load detailed CSV
        csv_file = list(output_dir.glob("*_detailed.csv"))[0]
        df = pd.read_csv(csv_file)

        # Extract by metric
        results = {}
        for metric in self.test_config["metrics_to_test"]:
            metric_df = df[df["metric_identifier"] == metric]

            results[metric] = {
                "scores": metric_df["score"].tolist(),
                "results": metric_df["result"].tolist(),
                "errors": metric_df[metric_df["result"] == "ERROR"].shape[0],
                "mean_score": metric_df["score"].mean(),
                "std_score": metric_df["score"].std(),
            }

        return results

    def _summarize_runs(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        """Calculate summary statistics across runs."""
        import numpy as np

        # Collect scores by metric across all runs
        metric_scores = {}

        for run in runs:
            if run["status"] != "success":
                continue

            for metric, data in run["results"].items():
                if metric not in metric_scores:
                    metric_scores[metric] = []
                metric_scores[metric].extend(data["scores"])

        # Calculate statistics
        summary = {}
        for metric, scores in metric_scores.items():
            scores = [s for s in scores if s is not None]  # Filter None
            if scores:
                summary[metric] = {
                    "mean": float(np.mean(scores)),
                    "std": float(np.std(scores)),
                    "cv": float(np.std(scores) / np.mean(scores)) if np.mean(scores) != 0 else 0,
                    "min": float(np.min(scores)),
                    "max": float(np.max(scores)),
                }

        return summary

    def _save_results(self, results: dict[str, Any]):
        """Save results to JSON file."""
        output_file = self.output_base / "judge_comparison_results.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    tester = JudgeConsistencyTester(Path("config/judge_consistency_test.yaml"))
    tester.run_all_tests()
```

**Usage:**
```bash
python scripts/run_judge_consistency_test.py
```

---

### Step 3: Create Analysis Script

**File:** `scripts/analyze_judge_consistency.py`

```python
#!/usr/bin/env python3
"""
Analyze judge consistency test results.

Generates:
- Score variance tables
- Inter-judge agreement (Cohen's Kappa, correlations)
- Error rate comparison
- Cost/performance analysis
- Visualizations
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import cohen_kappa_score
import matplotlib.pyplot as plt
import seaborn as sns


class JudgeConsistencyAnalyzer:
    """Analyzes judge consistency test results."""

    def __init__(self, results_file: Path):
        """Load results from JSON."""
        with open(results_file) as f:
            self.results = json.load(f)

        self.output_dir = results_file.parent / "analysis"
        self.output_dir.mkdir(exist_ok=True)

    def run_all_analyses(self):
        """Run all analyses and generate reports."""
        print("Analyzing judge consistency results...")

        # 1. Score variance
        variance_df = self.analyze_score_variance()
        variance_df.to_csv(self.output_dir / "score_variance.csv")

        # 2. Inter-judge agreement
        agreement_df = self.analyze_inter_judge_agreement()
        agreement_df.to_csv(self.output_dir / "inter_judge_agreement.csv")

        # 3. Error rates
        error_df = self.analyze_error_rates()
        error_df.to_csv(self.output_dir / "error_rates.csv")

        # 4. Cost/performance
        perf_df = self.analyze_performance()
        perf_df.to_csv(self.output_dir / "cost_performance.csv")

        # 5. Visualizations
        self.create_visualizations()

        # 6. Summary report
        self.generate_summary_report()

        print(f"✅ Analysis complete! Results in: {self.output_dir}")

    def analyze_score_variance(self) -> pd.DataFrame:
        """Calculate score variance within and between judges."""
        rows = []

        for judge_name, judge_data in self.results.items():
            summary = judge_data["summary"]

            for metric, stats_data in summary.items():
                rows.append({
                    "judge": judge_name,
                    "metric": metric,
                    "mean": stats_data["mean"],
                    "std": stats_data["std"],
                    "cv": stats_data["cv"],  # Coefficient of variation
                    "min": stats_data["min"],
                    "max": stats_data["max"],
                })

        return pd.DataFrame(rows)

    def analyze_inter_judge_agreement(self) -> pd.DataFrame:
        """Calculate agreement between different judges."""
        # Collect all scores by metric and test case
        metrics = list(self.results[list(self.results.keys())[0]]["summary"].keys())

        rows = []
        for metric in metrics:
            # Get scores from each judge for this metric
            judge_scores = {}
            for judge_name, judge_data in self.results.items():
                # Combine scores from all runs
                all_scores = []
                for run in judge_data["runs"]:
                    if run["status"] == "success":
                        all_scores.extend(run["results"][metric]["scores"])
                judge_scores[judge_name] = all_scores

            # Calculate pairwise correlations
            judge_names = list(judge_scores.keys())
            for i, judge1 in enumerate(judge_names):
                for judge2 in judge_names[i+1:]:
                    scores1 = [s for s in judge_scores[judge1] if s is not None]
                    scores2 = [s for s in judge_scores[judge2] if s is not None]

                    # Ensure same length
                    min_len = min(len(scores1), len(scores2))
                    scores1 = scores1[:min_len]
                    scores2 = scores2[:min_len]

                    if len(scores1) > 1:
                        corr, p_value = stats.pearsonr(scores1, scores2)

                        # Also calculate Kappa for PASS/FAIL
                        results1 = ["PASS" if s >= 0.7 else "FAIL" for s in scores1]
                        results2 = ["PASS" if s >= 0.7 else "FAIL" for s in scores2]
                        kappa = cohen_kappa_score(results1, results2)

                        rows.append({
                            "metric": metric,
                            "judge1": judge1,
                            "judge2": judge2,
                            "pearson_r": corr,
                            "p_value": p_value,
                            "cohen_kappa": kappa,
                        })

        return pd.DataFrame(rows)

    def analyze_error_rates(self) -> pd.DataFrame:
        """Calculate error rates for each judge."""
        rows = []

        for judge_name, judge_data in self.results.items():
            for run in judge_data["runs"]:
                if run["status"] != "success":
                    continue

                for metric, metric_data in run["results"].items():
                    total = len(metric_data["results"])
                    errors = metric_data["errors"]

                    rows.append({
                        "judge": judge_name,
                        "metric": metric,
                        "total_evaluations": total,
                        "errors": errors,
                        "error_rate": errors / total if total > 0 else 0,
                    })

        # Aggregate by judge and metric
        df = pd.DataFrame(rows)
        return df.groupby(["judge", "metric"]).agg({
            "total_evaluations": "sum",
            "errors": "sum",
            "error_rate": "mean",
        }).reset_index()

    def analyze_performance(self) -> pd.DataFrame:
        """Analyze execution time and cost."""
        rows = []

        for judge_name, judge_data in self.results.items():
            times = []
            for run in judge_data["runs"]:
                if run["status"] == "success":
                    times.append(run["execution_time"])

            if times:
                rows.append({
                    "judge": judge_name,
                    "mean_execution_time": np.mean(times),
                    "std_execution_time": np.std(times),
                    "total_runs": len(times),
                })

        return pd.DataFrame(rows)

    def create_visualizations(self):
        """Create analysis visualizations."""
        viz_dir = self.output_dir / "visualizations"
        viz_dir.mkdir(exist_ok=True)

        # 1. Score distributions box plot
        self._plot_score_distributions(viz_dir / "score_distributions.png")

        # 2. Agreement heatmap
        self._plot_agreement_heatmap(viz_dir / "agreement_heatmap.png")

        # 3. Error rate comparison
        self._plot_error_rates(viz_dir / "error_rates.png")

    def _plot_score_distributions(self, output_path: Path):
        """Box plot of score distributions by judge and metric."""
        # Prepare data
        data = []
        for judge_name, judge_data in self.results.items():
            for metric in judge_data["summary"].keys():
                for run in judge_data["runs"]:
                    if run["status"] == "success":
                        scores = run["results"][metric]["scores"]
                        for score in scores:
                            if score is not None:
                                data.append({
                                    "Judge": judge_name,
                                    "Metric": metric,
                                    "Score": score,
                                })

        df = pd.DataFrame(data)

        # Create plot
        metrics = df["Metric"].unique()
        fig, axes = plt.subplots(len(metrics), 1, figsize=(12, 4 * len(metrics)))
        if len(metrics) == 1:
            axes = [axes]

        for i, metric in enumerate(metrics):
            metric_df = df[df["Metric"] == metric]
            sns.boxplot(data=metric_df, x="Judge", y="Score", ax=axes[i])
            axes[i].set_title(f"{metric} Score Distribution")
            axes[i].axhline(y=0.7, color='r', linestyle='--', label='Threshold')
            axes[i].legend()

        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()

    def _plot_agreement_heatmap(self, output_path: Path):
        """Heatmap of inter-judge agreement."""
        agreement_df = pd.read_csv(self.output_dir / "inter_judge_agreement.csv")

        # Pivot for heatmap (use Cohen's Kappa)
        judges = sorted(set(agreement_df["judge1"].unique()) | set(agreement_df["judge2"].unique()))

        for metric in agreement_df["metric"].unique():
            metric_df = agreement_df[agreement_df["metric"] == metric]

            # Build matrix
            matrix = np.eye(len(judges))  # Diagonal = 1 (perfect agreement with self)
            for _, row in metric_df.iterrows():
                i = judges.index(row["judge1"])
                j = judges.index(row["judge2"])
                matrix[i, j] = row["cohen_kappa"]
                matrix[j, i] = row["cohen_kappa"]

            # Plot
            plt.figure(figsize=(10, 8))
            sns.heatmap(
                matrix,
                xticklabels=judges,
                yticklabels=judges,
                annot=True,
                fmt=".3f",
                cmap="RdYlGn",
                vmin=0,
                vmax=1,
                center=0.5,
            )
            plt.title(f"Inter-Judge Agreement: {metric}\n(Cohen's Kappa)")
            plt.tight_layout()
            plt.savefig(
                output_path.parent / f"agreement_{metric.replace(':', '_')}.png",
                dpi=300,
                bbox_inches='tight'
            )
            plt.close()

    def _plot_error_rates(self, output_path: Path):
        """Bar plot of error rates by judge."""
        error_df = pd.read_csv(self.output_dir / "error_rates.csv")

        # Create plot
        fig, ax = plt.subplots(figsize=(12, 6))

        # Pivot for grouped bar chart
        pivot_df = error_df.pivot(index="judge", columns="metric", values="error_rate")
        pivot_df.plot(kind="bar", ax=ax)

        ax.set_ylabel("Error Rate")
        ax.set_title("Error Rates by Judge and Metric")
        ax.legend(title="Metric", bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()

    def generate_summary_report(self):
        """Generate markdown summary report."""
        report = []
        report.append("# Judge LLM Consistency Analysis Report\n")
        report.append(f"**Generated:** {pd.Timestamp.now()}\n")
        report.append("---\n")

        # Executive Summary
        report.append("## Executive Summary\n")

        # Find best judge
        variance_df = pd.read_csv(self.output_dir / "score_variance.csv")
        error_df = pd.read_csv(self.output_dir / "error_rates.csv")

        # Lowest average CV
        avg_cv = variance_df.groupby("judge")["cv"].mean().sort_values()
        report.append(f"**Most Consistent (lowest variance):** {avg_cv.index[0]} (CV: {avg_cv.iloc[0]:.3f})\n")

        # Lowest error rate
        avg_error = error_df.groupby("judge")["error_rate"].mean().sort_values()
        report.append(f"**Lowest Error Rate:** {avg_error.index[0]} ({avg_error.iloc[0]:.1%})\n")

        report.append("\n---\n")

        # Score Variance
        report.append("## Score Variance Analysis\n")
        report.append("\n")
        report.append(variance_df.to_markdown(index=False))
        report.append("\n\n---\n")

        # Inter-Judge Agreement
        report.append("## Inter-Judge Agreement\n")
        agreement_df = pd.read_csv(self.output_dir / "inter_judge_agreement.csv")
        report.append("\n")
        report.append(agreement_df.to_markdown(index=False))
        report.append("\n\n---\n")

        # Error Rates
        report.append("## Error Rates\n")
        report.append("\n")
        report.append(error_df.to_markdown(index=False))
        report.append("\n\n---\n")

        # Recommendations
        report.append("## Recommendations\n")
        report.append(f"1. **Primary Judge:** {avg_error.index[0]} (lowest error rate)\n")
        report.append(f"2. **Backup Judge:** {avg_cv.index[0]} (most consistent)\n")
        report.append(f"3. **Threshold Calibration:** Review thresholds for metrics with high variance\n")

        # Write report
        with open(self.output_dir / "summary_report.md", "w") as f:
            f.write("".join(report))


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python analyze_judge_consistency.py <results.json>")
        sys.exit(1)

    analyzer = JudgeConsistencyAnalyzer(Path(sys.argv[1]))
    analyzer.run_all_analyses()
```

**Usage:**
```bash
python scripts/analyze_judge_consistency.py judge_consistency_20260324_123456/judge_comparison_results.json
```

---

## Expected Output

### Directory Structure

```
judge_consistency_20260324_123456/
├── judge_comparison_results.json        # Raw results
├── gemini-2.5-flash/
│   ├── run_1/
│   │   ├── evaluation_*_detailed.csv
│   │   └── evaluation_*_summary.json
│   ├── run_2/
│   └── run_3/
├── gpt-4o/
│   ├── run_1/
│   ├── run_2/
│   └── run_3/
├── claude-3.5-sonnet/
│   ├── run_1/
│   ├── run_2/
│   └── run_3/
└── analysis/
    ├── summary_report.md
    ├── score_variance.csv
    ├── inter_judge_agreement.csv
    ├── error_rates.csv
    ├── cost_performance.csv
    └── visualizations/
        ├── score_distributions.png
        ├── agreement_faithfulness.png
        ├── agreement_context_relevance.png
        └── error_rates.png
```

### Sample Results

**score_variance.csv:**
```csv
judge,metric,mean,std,cv,min,max
gemini-2.5-flash,ragas:faithfulness,0.747,0.152,0.203,0.0,1.0
gpt-4o,ragas:faithfulness,0.820,0.098,0.119,0.5,1.0
claude-3.5-sonnet,ragas:faithfulness,0.777,0.121,0.156,0.3,1.0
```

**Interpretation:**
- **gpt-4o** has lowest CV (0.119) = most consistent
- **gpt-4o** has highest mean (0.820) = most generous scorer
- **gemini-2.5-flash** has highest CV (0.203) = most variable

**inter_judge_agreement.csv:**
```csv
metric,judge1,judge2,pearson_r,p_value,cohen_kappa
ragas:faithfulness,gemini-2.5-flash,gpt-4o,0.785,0.001,0.623
ragas:faithfulness,gemini-2.5-flash,claude-3.5-sonnet,0.812,0.000,0.701
ragas:faithfulness,gpt-4o,claude-3.5-sonnet,0.891,0.000,0.789
```

**Interpretation:**
- **High correlation** (r > 0.78) = judges mostly agree on scores
- **Moderate Kappa** (0.6-0.8) = some disagreement on PASS/FAIL boundary
- **gpt-4o & claude-3.5-sonnet** most aligned (r=0.891)

**error_rates.csv:**
```csv
judge,metric,total_evaluations,errors,error_rate
gemini-2.5-flash,ragas:faithfulness,30,4,0.133
gpt-4o,ragas:faithfulness,30,1,0.033
claude-3.5-sonnet,ragas:faithfulness,30,2,0.067
```

**Interpretation:**
- **gpt-4o** has lowest error rate (3.3%)
- **gemini-2.5-flash** has highest (13.3%) - matches our earlier finding!

---

## Debugging Tips

### 1. Test with Single Judge First

```bash
# Modify config to test one judge only
judges:
  - name: gemini-2.5-flash
    model: gemini/gemini-2.5-flash
    runs: 1  # Just 1 run for testing

python scripts/run_judge_consistency_test.py
```

### 2. Use Small Test Set

Start with 3-5 test cases to verify workflow before running full suite.

### 3. Check API Keys

All judge models require valid API keys:
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."
```

### 4. Monitor Costs

Track token usage and costs:
```python
# Add to run_evaluation method
print(f"Tokens used: {results['api_input_tokens']} + {results['api_output_tokens']}")
print(f"Estimated cost: ${calculate_cost(judge['model'], tokens)}")
```

---

## Success Criteria

After running the test, you should be able to answer:

✅ **Can we trust our metric scores?**
- If CV < 10% → Yes, scores are stable
- If CV > 20% → No, too much variance

✅ **Do different judges agree?**
- If Kappa > 0.7 → Yes, strong agreement
- If Kappa < 0.4 → No, different judges have different standards

✅ **Which judge is best?**
- Lowest error rate
- Lowest variance
- Best agreement with others
- Reasonable cost/performance

✅ **Should we adjust thresholds?**
- If all judges score lower → Threshold too strict
- If high inter-judge variance → Metric definition unclear

---

## Summary Checklist

Implementing judge consistency tests:

- [ ] Create `config/judge_consistency_test.yaml`
- [ ] Select 10-20 diverse test cases
- [ ] Define 3-4 judge LLMs to compare
- [ ] Create `scripts/run_judge_consistency_test.py`
- [ ] Create `scripts/analyze_judge_consistency.py`
- [ ] Install analysis dependencies (`pip install scipy sklearn seaborn`)
- [ ] Set up API keys for all judges
- [ ] Run test with 1 judge first (verify)
- [ ] Run full test suite (3+ judges, 3 runs each)
- [ ] Generate analysis and visualizations
- [ ] Review summary report
- [ ] Make recommendations (best judge, threshold adjustments)

**Estimated Time:**
- Setup: 2-3 hours
- Test execution: 4-6 hours (depends on test case count)
- Analysis: 1-2 hours
- **Total: 1 working day**

**Estimated Cost:**
- Depends on test case count and judges
- Example: 20 cases × 3 judges × 3 runs = 180 evaluations
- With 5 metrics each = 900 metric evaluations
- Cost range: $20-100 (mostly gpt-4o/claude costs)

---

## Benefits

After implementing this test suite, you'll have:

1. ✅ **Quantified non-determinism** - Know exactly how much variance to expect
2. ✅ **Best judge selection** - Data-driven choice of evaluation LLM
3. ✅ **Confidence intervals** - Can report scores ± uncertainty
4. ✅ **Threshold validation** - Know if current thresholds are appropriate
5. ✅ **Metric reliability** - Identify which metrics are stable vs noisy

**Long-term value:**
- Run periodically to track judge model improvements
- Detect if new model versions change scoring behavior
- Justify evaluation methodology with statistical evidence

---

**Questions?** See existing evaluation scripts in `scripts/` for examples!

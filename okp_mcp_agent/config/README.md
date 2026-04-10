# Scripts Directory

Utility scripts for LightSpeed Evaluation Framework. Organized by functional category.

## Table of Contents

- [Quick Start](#quick-start)
- [JIRA Ticket Processing (Multi-Agent)](#jira-ticket-processing-multi-agent)
- [OKP-MCP Agent & Automation](#okp-mcp-agent--automation)
- [Evaluation Analysis](#evaluation-analysis)
- [Cost & Resource Management](#cost--resource-management)
- [Reporting & Visualization](#reporting--visualization)
- [Test Configuration & Conversion](#test-configuration--conversion)
- [Regression Testing](#regression-testing)
- [Common Workflows](#common-workflows)

---

## Quick Start

**Run complete evaluation suite:**
```bash
# From project root
./run_full_evaluation_suite.sh
```

This runs all evaluations + all analysis scripts + generates the okp-mcp report automatically.

**Process JIRA tickets end-to-end:**
```bash
# Extract tickets with multi-agent verification
python scripts/extract_jira_tickets.py

# Discover patterns
python scripts/discover_ticket_patterns.py

# Fix tickets using patterns
python scripts/okp_mcp_agent.py fix RSPEED-2482 --max-iterations 10
```

---

## JIRA Ticket Processing (Multi-Agent)

Scripts for fetching and processing JIRA tickets using multi-agent collaboration (Linux Expert + Solr Expert).

### `extract_jira_tickets.py`

**Stage 1: Fetch & Extract** - Main extraction workflow using multi-agent verification.

```bash
# Default: append new tickets to existing YAML
python scripts/extract_jira_tickets.py

# Force rebuild everything
python scripts/extract_jira_tickets.py --force-rebuild

# Process specific tickets
python scripts/extract_jira_tickets.py --tickets RSPEED-2482,RSPEED-2511

# Custom JQL query
python scripts/extract_jira_tickets.py --jql "project = RSPEED AND status = Open"

# Force re-extract specific tickets (even if already processed)
python scripts/extract_jira_tickets.py --tickets RSPEED-2482 --force-reextract
```

**Features:**
- Incremental append mode (default) - only processes new tickets
- Multi-agent verification (Linux Expert ↔ Solr Expert)
- Search intelligence logging for workflow optimization
- Default JQL for `cla-incorrect-answer` tickets

**Output:** `config/extracted_tickets.yaml`

**Tests:** `tests/agents/test_jira_extraction.py`

---

### `discover_ticket_patterns.py`

**Stage 2: Pattern Discovery** - Identifies common patterns across extracted tickets.

```bash
# Default: discover patterns in extracted_tickets.yaml
python scripts/discover_ticket_patterns.py

# Custom input/output
python scripts/discover_ticket_patterns.py \
  --input config/extracted_tickets_20260407.yaml \
  --output-tagged config/tickets_with_patterns.yaml \
  --output-report patterns_report.json

# Require at least 5 tickets per pattern
python scripts/discover_ticket_patterns.py --min-pattern-size 5
```

**Features:**
- Groups tickets by problem type, components, RHEL versions
- Clusters similar tickets (≥3 by default)
- Tags tickets with pattern_id
- Generates pattern reports for batch fixing

**Outputs:**
- Tagged YAML with pattern_id annotations
- JSON pattern report

**Use Case:** Process 15 similar tickets as 1 pattern (15x efficiency)

---

### `multi_agent_jira_extractor.py`

Earlier prototype of multi-agent extraction.

**Status:** Legacy - use `extract_jira_tickets.py` instead

---

### `fetch_jira_open_tickets.py`

Fetch open JIRA tickets using Claude Agent SDK + JIRA MCP.

```bash
python scripts/fetch_jira_open_tickets.py
```

**Features:**
- Uses JIRA MCP for ticket access
- Intelligent query/answer extraction
- Generates test configs compatible with `system_okp_mcp_agent.yaml`

**Use Case:** Quick fetch of open tickets without multi-agent verification

---

### `fetch_jira_tickets_direct.py`

Fetch JIRA tickets via REST API (no Claude SDK dependency).

```bash
python scripts/fetch_jira_tickets_direct.py
```

**Features:**
- Direct REST API calls for reliability
- No MCP or SDK dependencies
- Fast ticket fetching

**Use Case:** When MCP/SDK unavailable or for simple bulk fetches

---

## OKP-MCP Agent & Automation

Scripts for autonomous ticket fixing and Solr diagnostics.

### `okp_mcp_agent.py`

**Autonomous agent for okp-mcp RSPEED ticket fixing.**

Automates the INCORRECT_ANSWER_LOOP workflow:
1. **Diagnose** - Run full evaluation to identify problem type
2. **Analyze** - Determine if retrieval or answer quality issue
3. **Iterate** - Make targeted changes (boost queries or prompts)
4. **Validate** - Check for regressions across all test suites
5. **Commit** - Create commit with detailed metrics

```bash
# Diagnose a single ticket (runs new evaluation)
python scripts/okp_mcp_agent.py diagnose RSPEED-2482

# Diagnose using existing results (fast, no re-run)
python scripts/okp_mcp_agent.py diagnose RSPEED-2482 --use-existing

# Auto-fix with iterations
python scripts/okp_mcp_agent.py fix RSPEED-2482 --max-iterations 10

# Validate across all suites
python scripts/okp_mcp_agent.py validate
```

**Workflow:**
- Identifies retrieval vs answer quality issues
- Suggests targeted boost query or prompt changes
- Validates against regression test suites
- Creates detailed commit messages with metrics

---

### `okp_mcp_llm_advisor.py`

**LLM-powered advisor for boost query suggestions.**

Uses Claude Agent SDK to analyze metrics and suggest code changes.

**Features:**
- Tiered model routing (Haiku/Sonnet/Opus) to optimize costs
- Analyzes evaluation metrics to suggest improvements
- Generates boost query code snippets
- Integration with `okp_mcp_agent.py`

**Use Case:** AI-powered suggestions for fixing retrieval issues

---

### `okp_solr_checker.py`

**Solr document checker for diagnostics.**

Validates that expected documents exist in Solr index.

```bash
python scripts/okp_solr_checker.py
```

**Features:**
- Checks if expected URLs exist in Solr
- Suggests alternative URLs when documents missing
- Helps debug retrieval failures

**Use Case:** Diagnose why test configs fail (missing docs)

---

### `okp_solr_config_analyzer.py`

**Solr configuration analyzer and explain output parser.**

Diagnoses why Solr ranks documents incorrectly.

```bash
python scripts/okp_solr_config_analyzer.py
```

**Features:**
- Parses current Solr config from `okp-mcp/src/okp_mcp/solr.py`
- Fetches Solr explain output to see scoring details
- Analyzes which parameters need tuning (qf, pf, boost values)

**Use Case:** Debug ranking issues and optimize Solr config

---

## Evaluation Analysis

Scripts for analyzing evaluation results and metrics.

### `analyze_metric_correlations.py`

**Cross-Metric Correlation Analysis.**

```bash
# Single evaluation run
python scripts/analyze_metric_correlations.py \
    --input eval_output/evaluation_20260317_142455_detailed.csv \
    --output analysis_output/single_run/

# Compare multiple runs
python scripts/analyze_metric_correlations.py \
    --input eval_output/run1/evaluation_*_detailed.csv \
            eval_output/run2/evaluation_*_detailed.csv \
    --output analysis_output/comparison/ \
    --compare-runs
```

**Analyzes:**
- Correlations between different Ragas metrics
- Validates that metrics measure what they claim
- Identifies redundant metrics
- Detects anomalies where metrics disagree

**Outputs:**
| File | Description |
|------|-------------|
| `summary_report.txt` | Human-readable summary with recommendations |
| `correlation_pearson.csv` | Pearson correlation matrix |
| `correlation_heatmap.png` | Visual correlation matrix |
| `anomalies.csv` | Detected anomalous cases |

**Anomaly Types:**
- **RAG_BYPASS**: High answer_correctness + low context_precision (LLM found signal in noise)
- **UNFAITHFUL_RESPONSE**: High context_relevance + low faithfulness (LLM added info)
- **PARAMETRIC_KNOWLEDGE**: Zero context scores + correct answer (LLM bypassed RAG)

**Use Case:** Understand which metrics provide unique signal

---

### `analyze_test_failures.py`

**Analyze test failures and regressions.**

```bash
python scripts/analyze_test_failures.py evaluation_outputs/run_20260407/
```

**Features:**
- Loads detailed CSV files from run directories
- Identifies failing tests
- Tracks regressions between runs

**Use Case:** Prioritize which failures to fix first

---

### `analyze_token_correlations.py`

**Analyze correlation between token usage and metric scores.**

```bash
python scripts/analyze_token_correlations.py \
  evaluation_outputs/okp_mcp_20260407_101520/ragas_metrics/evaluation_ragas_metrics_detailed.csv
```

**Explores:**
- Do larger contexts (more input tokens) lead to better scores?
- Does response length correlate with correctness?
- Optimal token ranges for different metrics

**Use Case:** Optimize context window vs cost tradeoff

---

### `analyze_url_retrieval_stability.py`

**Analyze URL retrieval stability across multiple runs.**

```bash
python scripts/analyze_url_retrieval_stability.py \
  evaluation_outputs/run1/ \
  evaluation_outputs/run2/ \
  evaluation_outputs/run3/
```

**Measures:**
- Content overlap stability - Do we get the same documents back?
- Ranking stability - Do documents appear in consistent positions?
- Expected URL tracking - Where do expected URLs rank?

**Use Case:** Measure RAG retrieval consistency

---

### `analyze_version_distribution.py`

**Analyze RHEL version distribution in retrieved contexts.**

```bash
python scripts/analyze_version_distribution.py \
    --input eval_output/temporal_tests/evaluation_*_detailed.csv \
    --test-config config/temporal_validity_tests_runnable.yaml \
    --output analysis_output/version_analysis/
```

**Measures:**
- Percentage of contexts matching target RHEL version
- Version distribution across all retrieved contexts
- Temporal accuracy by conversation

**Interpretation:**
- **>80%**: Good version filtering ✅
- **50-80%**: Needs improvement 🟡
- **<50%**: Poor version filtering, urgent fix needed ❌

**Use Case:** Validate version-specific retrieval (e.g., RHEL 9 queries get RHEL 9 docs)

---

## Cost & Resource Management

Scripts for tracking token usage and costs.

### `calculate_cost_estimate.py`

**Calculate cost estimates for evaluation runs.**

```bash
python scripts/calculate_cost_estimate.py \
  evaluation_outputs/okp_mcp_20260407_101520/ragas_metrics/evaluation_ragas_metrics_detailed.csv
```

**Provides:**
- Token usage statistics (input/output/total)
- Cost estimates for different LLM providers
- Per-question cost breakdown

**Use Case:** Budget forecasting for large evaluation runs

---

### `calculate_cost_estimate_multi.py`

**Calculate costs for runs with multiple CSV files.**

```bash
python scripts/calculate_cost_estimate_multi.py \
  evaluation_outputs/okp_mcp_20260407_101520/
```

**Features:**
- Finds all detailed CSV files in directory
- Aggregates token usage across all test suites
- Total cost across multiple evaluations

**Use Case:** Cost tracking for multi-suite runs

---

### `show_cost.py`

**Simple cost calculator - show cost of last run.**

```bash
python scripts/show_cost.py
```

**Features:**
- Zero-argument convenience script
- Shows cost of most recent evaluation
- Quick cost visibility

**Use Case:** Quick check after running eval

---

## Reporting & Visualization

Scripts for generating reports and plots.

### `generate_okp_mcp_report.py`

**Generate comprehensive RAG quality report for okp-mcp developers.**

```bash
python scripts/generate_okp_mcp_report.py \
    --output-base eval_output/full_suite_20260323_100000 \
    --correlation-analysis analysis_output/full_suite_20260323_100000/correlation_analysis \
    --version-analysis analysis_output/full_suite_20260323_100000/version_analysis
```

**Output File:** `RAG_QUALITY_REPORT_FOR_OKP_MCP.md`

**Sections:**
1. **Executive Summary** - Metric → okp-mcp impact mapping
2. **Critical Issues** - Performance analysis + version filtering
3. **Root Cause Analysis** - Over-retrieval, poor ranking, no version filtering, boilerplate pollution
4. **Specific Examples** - Anomalous cases
5. **Action Plan** - 3-4 week phased implementation
6. **Success Metrics** - Before/after targets
7. **Appendix** - Detailed metric explanations

**Features:**
- Data-driven report explaining retrieval quality issues
- Actual examples with metrics
- Actionable recommendations with code fixes

**Use Case:** Share evaluation insights with okp-mcp team

---

### `generate_question_metrics_report.py`

**Generate detailed per-question metrics report.**

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
```

**Shows:**
- Each question with all metric scores
- Easy identification of poorly performing questions
- Metric comparison across question types
- Pass rates by metric
- Questions with most failures

**Use Cases:**
- **Debugging:** Deep-dive into specific failing tests
- **Pattern Analysis:** Identify question types that fail
- **Team Sharing:** Show specific examples to stakeholders

---

### `plot_scores_over_time.py`

**Plot evaluation scores over time - time series analysis.**

```bash
python scripts/plot_scores_over_time.py evaluation_outputs/
```

**Features:**
- Finds all evaluation run directories
- Loads detailed CSV files from all runs
- Creates time-series plots showing score changes

**Use Case:** Track improvement trends over multiple iterations

---

### `plot_stability.py`

**Generate heatmaps for MCP retrieval suite stability.**

```bash
python scripts/plot_stability.py evaluation_outputs/mcp_retrieval_suite/
```

**Generates:**
- Average Score Heatmap (green=high, red=low)
- Stability Heatmap (white=stable, orange=unstable)

**Use Case:** Visualize retrieval consistency across runs

---

## Test Configuration & Conversion

Scripts for managing test configs and formats.

### `convert_functional_cases_to_eval.py`

**Convert okp-mcp functional test cases to evaluation YAML.**

```bash
python scripts/convert_functional_cases_to_eval.py
```

**Features:**
- Reads FunctionalCase definitions from okp-mcp test suite
- Converts to lightspeed-evaluation YAML format
- Enables quantitative metrics vs binary pass/fail
- Multi-run stability analysis

**Use Case:** Leverage existing okp-mcp tests in evaluation framework

---

### `generate_jira_issues_for_failures.py`

**Generate JIRA issue proposals for RAG failures.**

```bash
python scripts/generate_jira_issues_for_failures.py \
  evaluation_outputs/okp_mcp_20260407_101520/
```

**Features:**
- Categorizes context retrieval failures
- Identifies boilerplate/irrelevant content
- Generates JIRA issue templates

**Use Case:** Auto-create tickets for systematic failures

---

### `extract_contexts_for_question.py`

**Extract and display contexts for a specific question.**

```bash
python scripts/extract_contexts_for_question.py \
  evaluation_outputs/okp_mcp_20260407_101520/ragas_metrics/evaluation_ragas_metrics_detailed.csv \
  "How do I install RHEL 9?"
```

**Features:**
- Shows retrieved contexts for debugging
- Displays relevance scores
- Helps diagnose retrieval issues

**Use Case:** Debug why specific question fails

---

### `compare_error_resolution.py`

**Compare error resolution between two evaluation runs.**

```bash
python scripts/compare_error_resolution.py \
  evaluation_outputs/run_before/ \
  evaluation_outputs/run_after/
```

**Features:**
- Tracks which questions had errors
- Shows whether errors were resolved
- Progress tracking on fixing failures

**Use Case:** Measure fix effectiveness between iterations

---

## Regression Testing

Scripts for running repeated evaluations and tracking regressions.

### `run_cla_regression.py`

**Run CLA regression testing with heatmap analysis.**

```bash
# Run 10 evaluations and generate heatmaps
python scripts/run_cla_regression.py --runs 10

# Use specific config
python scripts/run_cla_regression.py --config config/system_cla_production.yaml
```

**Features:**
- Runs lightspeed-eval N times with CLA test configs
- Saves each run to timestamped directories (under CLA_REGRESSION)
- Automatically generates heatmaps showing score changes
- Tracks score stability and regressions

**Use Case:** Ensure changes don't regress existing functionality

---

## Common Workflows

### Complete JIRA Ticket Processing

```bash
# Stage 1: Extract tickets with multi-agent verification
python scripts/extract_jira_tickets.py

# Stage 2: Discover patterns
python scripts/discover_ticket_patterns.py

# Review patterns
cat patterns_report.json | jq '.patterns'

# Stage 3: Fix tickets using patterns
python scripts/okp_mcp_agent.py fix RSPEED-2482 --max-iterations 10
```

### Complete Evaluation Analysis

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

### Single Test Deep Dive

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

### Before/After Comparison

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

### Debugging Retrieval Issues

```bash
# Check if expected docs exist in Solr
python scripts/okp_solr_checker.py

# Analyze Solr config and ranking
python scripts/okp_solr_config_analyzer.py

# Extract contexts for specific question
python scripts/extract_contexts_for_question.py \
  evaluation_outputs/latest/ragas_metrics/evaluation_ragas_metrics_detailed.csv \
  "How do I install RHEL 9?"

# Measure retrieval stability
python scripts/analyze_url_retrieval_stability.py \
  evaluation_outputs/run1/ \
  evaluation_outputs/run2/ \
  evaluation_outputs/run3/
```

---

## Environment Requirements

Most scripts require:
- Python 3.11+
- Dependencies from `pyproject.toml`
- `.env` file with credentials (see main README.md)

### Required Environment Variables

**For JIRA scripts:**
- JIRA token in secret-tool: `secret-tool store --label="JIRA API Token" application jira`

**For LLM-powered scripts:**
- `ANTHROPIC_VERTEX_PROJECT_ID` - For Claude Agent SDK
- `GOOGLE_APPLICATION_CREDENTIALS` - For Vertex AI ADC

**For evaluation scripts:**
- `OPENAI_API_KEY` - For LLM evaluation metrics
- `API_KEY` - For okp-mcp API access (if testing live API)

See main [README.md](../README.md) for complete environment setup.

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

## Contributing

When adding new scripts:
1. Include comprehensive docstring at top of file
2. Add usage examples in docstring
3. Update this README.md with script description
4. Add tests if script has complex logic (see `tests/agents/test_jira_extraction.py`)
5. Follow code quality standards (black, pylint, pydocstyle)

Run quality checks:
```bash
make black-format
make pre-commit
make test
```

---

## Dependencies

All included in `pyproject.toml`:
- pandas
- numpy
- scipy
- matplotlib
- seaborn
- requests
- pyyaml
- pydantic

Install with: `uv sync --group dev`

---

## Related Documentation

- [../RUN_ALL_EVALS.md](../RUN_ALL_EVALS.md) - Complete workflow guide
- [../docs/HOW_TO_RUN_TEMPORAL_TESTS.md](../docs/HOW_TO_RUN_TEMPORAL_TESTS.md) - Temporal testing details
- [../README.md](../README.md) - Main project documentation
- [../AGENTS.md](../AGENTS.md) - AI agent guidelines

---

*Last updated: 2026-04-07*

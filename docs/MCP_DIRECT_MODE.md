# MCP Direct Mode - Testing Retrieval Quality

This document explains how to use MCP Direct mode to test retrieval quality without generating LLM responses.

## Overview

MCP Direct mode queries the okp-mcp MCP server directly (http://localhost:8001) to retrieve contexts, bypassing the full `/v1/infer` endpoint. This is useful for:

- **Testing retrieval improvements** (lifecycle de-boost, better ranking, etc.)
- **Evaluating URL retrieval** (which docs are being fetched)
- **Fast iteration** (no LLM calls = faster + cheaper)
- **Building cache** for later full evaluation with LLM metrics

## What Works and What Doesn't

### ✅ Metrics That Work (No LLM Response OR Ground Truth Needed)
- `ragas:context_precision_without_reference` - Are retrieved contexts relevant?
- `ragas:context_relevance` - How relevant are contexts to the query?
- `custom:url_retrieval_eval` - F1 score of expected vs retrieved URLs

### ❌ Metrics That Don't Work

**Need LLM Response:**
- `ragas:faithfulness` - Requires LLM response
- `ragas:response_relevancy` - Requires LLM response
- `custom:answer_correctness` - Requires LLM response

**Need Ground Truth (expected_response):**
- `ragas:context_recall` - Checks if contexts contain facts from expected_response
- `ragas:context_precision_with_reference` - Uses expected_response as reference

## Quick Start

### Option 1: Run Multiple Times with Heatmap (Recommended)

```bash
cd ~/Work/lightspeed-core/lightspeed-evaluation

# Run 5 times and generate heatmap
./run_mcp_retrieval_suite.sh

# Or customize:
./run_mcp_retrieval_suite.sh --runs 10 --config config/chronically_failing_questions.yaml
```

This will:
- Run MCP direct evaluation N times (default: 5)
- Clear cache between runs for fresh retrieval
- Generate heatmap showing questions vs metrics
- Save all results to `mcp_retrieval_output/suite_TIMESTAMP/`

### Option 2: Single Run

```bash
cd ~/Work/lightspeed-core/lightspeed-evaluation

# Ensure okp-mcp is running
cd ~/Work/lscore-deploy/local
podman-compose ps okp-mcp  # Should show "healthy"

# Run single evaluation
cd ~/Work/lightspeed-core/lightspeed-evaluation
uv run python -m lightspeed_evaluation.runner \
  --system-config config/system_mcp_direct.yaml \
  --config config/chronically_failing_questions.yaml
```

### View Results

Results are saved just like normal evaluations:
- `evaluation_YYYYMMDD_HHMMSS_detailed.csv` - Detailed metrics per question
- `evaluation_YYYYMMDD_HHMMSS_summary.txt` - Summary report
- `graphs/` - Visualizations of results
- `analysis/*.png` - Heatmaps (when using run_mcp_retrieval_suite.sh)

## Configuration

### system_mcp_direct.yaml

Key settings:

```yaml
api:
  enabled: true
  mode: "mcp_direct"                       # Use MCP direct instead of /v1/infer
  mcp_url: "http://localhost:8001"         # MCP server URL
  cache_enabled: true                      # Cache contexts for later
  cache_dir: ".caches/mcp_direct_cache"

metrics_metadata:
  turn_level:
    "ragas:context_recall":
      threshold: 0.8
      default: true

    "ragas:context_precision_without_reference":
      threshold: 0.7
      default: true

    "ragas:context_relevance":
      threshold: 0.7
      default: true

    "custom:url_retrieval_eval":
      threshold: 0.7
      default: true
```

### Test Configs with expected_urls

The following configs now have `expected_urls` uncommented:
- `config/chronically_failing_questions.yaml`

Each question includes expected URLs that should be retrieved:

```yaml
- conversation_group_id: TEMPORAL-REMOVED-001
  turns:
    - turn_id: turn1
      query: "How to install and configure a DHCP server in RHEL 10?"
      expected_urls:
        - https://access.redhat.com/documentation/.../managing_networking_infrastructure_services
        - https://access.redhat.com/documentation/.../10.0_release_notes
```

## Typical Workflow: Iterating on Retrieval Quality

### 1. Baseline - Test Current Retrieval

```bash
cd ~/Work/lightspeed-core/lightspeed-evaluation

# Run 5 times to get stable baseline
./run_mcp_retrieval_suite.sh --runs 5

# View heatmap to see which questions have poor retrieval
ls mcp_retrieval_output/suite_*/analysis/*.png
```

**What to look for:**
- Low `context_precision_without_reference` (< 0.5) = retrieving irrelevant docs
- Low `context_relevance` (< 0.5) = contexts don't match query intent
- Low `url_retrieval_eval` (< 0.5) = not fetching expected documentation

### 2. Make Changes to okp-mcp

```bash
# Edit ranking/boosting in okp-mcp
cd ~/Work/okp-mcp-lifecycle-deboost
vim src/okp_mcp/tools.py

# Example changes:
# - Adjust lifecycle de-boost (^0.2)
# - Increase technical doc boost (^3.0 → ^5.0)
# - Add phrase proximity reranking
# - Adjust reRankWeight (3 → 10)

# Restart to load changes
cd ~/Work/lscore-deploy/local
podman-compose restart okp-mcp
```

### 3. Re-test After Changes

```bash
cd ~/Work/lightspeed-core/lightspeed-evaluation

# Run same number of times for fair comparison
./run_mcp_retrieval_suite.sh --runs 5

# Compare to baseline
python scripts/compare_runs.py \
  mcp_retrieval_output/suite_BASELINE/run_001.csv \
  mcp_retrieval_output/suite_IMPROVED/run_001.csv
```

### 4. Iterate Until Satisfied

Repeat steps 2-3 until metrics improve:
- **Target**: context_precision > 0.7, context_relevance > 0.7, url_retrieval > 0.7
- **Focus on**: Questions with consistently low scores across runs

### 5. (Optional) Build Cache for Full Evaluation

Once retrieval quality is good, build cache for full evaluation with LLM responses:

```bash
# Run once more to build cache
uv run python -m lightspeed_evaluation.runner \
  --system-config config/system_mcp_direct.yaml \
  --config config/chronically_failing_questions.yaml

# Then run full evaluation using cached contexts + LLM responses
uv run python -m lightspeed_evaluation.runner \
  --config config/chronically_failing_questions.yaml

# This will use cached contexts and add LLM responses
# Then run all metrics including answer_correctness
```

## Understanding Results

### URL Retrieval Metric

The `custom:url_retrieval_eval` metric calculates:
- **Precision**: % of retrieved URLs that are expected
- **Recall**: % of expected URLs that were retrieved
- **F1 Score**: Harmonic mean (the reported score)

Example output:
```
F1=0.67, Precision=0.50, Recall=1.00
Matched 2/2: access.redhat.com/.../managing_networking_infrastructure_services, ...
Extra 2 unexpected: access.redhat.com/.../considerations_in_adopting_rhel_10, ...
```

Interpretation:
- F1=0.67: Moderate success (both expected URLs found, but 2 extra)
- Precision=0.50: Half of retrieved URLs are expected
- Recall=1.00: All expected URLs were found

### Context Recall

`ragas:context_recall` checks if retrieved contexts contain the facts from `expected_response`.

Example:
- Score: 0.4 (40%)
- Means: Only 40% of facts in expected_response were found in contexts

## Comparing Runs

```bash
# Run baseline
uv run python -m lightspeed_evaluation.runner \
  --system-config config/system_mcp_direct.yaml \
  --config config/chronically_failing_questions.yaml

mv evaluation_*_detailed.csv baseline_retrieval.csv

# Make changes to okp-mcp...

# Run after changes
uv run python -m lightspeed_evaluation.runner \
  --system-config config/system_mcp_direct.yaml \
  --config config/chronically_failing_questions.yaml

mv evaluation_*_detailed.csv improved_retrieval.csv

# Compare
python scripts/compare_runs.py baseline_retrieval.csv improved_retrieval.csv
```

## Troubleshooting

### okp-mcp not responding

```bash
# Check if okp-mcp is healthy
cd ~/Work/lscore-deploy/local
podman-compose ps okp-mcp

# Check logs
podman-compose logs okp-mcp --tail=50

# Restart if needed
podman-compose restart okp-mcp
```

### Cache issues

```bash
# Clear MCP direct cache
rm -rf .caches/mcp_direct_cache/*

# Clear all caches
rm -rf .caches/*
```

### No contexts retrieved

Check okp-mcp logs for errors:
```bash
podman-compose logs okp-mcp | grep -i error
```

## Tips

1. **Add more expected_urls**: Don't penalize retrieval for fetching multiple good docs. Add 2-3 expected URLs per question.

2. **Focus on context_recall**: This metric tells you if you're retrieving the information needed to answer the question.

3. **Use url_retrieval_eval**: This shows exactly which docs are being fetched, helping debug ranking issues.

4. **Iterate quickly**: MCP direct mode is much faster than full evaluation, so you can test changes rapidly.

5. **Build cache then run full eval**: Use MCP direct to build cache, then run full evaluation with standard system.yaml to get LLM metrics too.

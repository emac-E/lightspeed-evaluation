# run_mcp_retrieval_suite.sh - Quick Reference

Run MCP direct mode evaluation N times and generate heatmap.

## Quick Start

```bash
cd ~/Work/lightspeed-core/lightspeed-evaluation

# Run 5 times (default) and generate heatmap
./run_mcp_retrieval_suite.sh

# Or customize
./run_mcp_retrieval_suite.sh --runs 10
./run_mcp_retrieval_suite.sh --runs 5 --config config/chronically_failing_questions.yaml
```

## What It Does

1. **Clears cache between runs** - Each run gets fresh retrieval results
2. **Runs N evaluations** using MCP direct mode (queries okp-mcp, no LLM responses)
3. **Generates heatmap** showing question vs metrics scores
4. **Saves all results** to `mcp_retrieval_output/suite_TIMESTAMP/`

## Metrics Evaluated

**These work WITHOUT ground truth (no expected_response needed):**
- `ragas:context_precision_without_reference` - Are contexts relevant to query?
- `ragas:context_relevance` - How relevant are contexts?
- `custom:url_retrieval_eval` - Are expected docs being retrieved? (needs expected_urls)

## Output Structure

```
mcp_retrieval_output/suite_YYYYMMDD_HHMMSS/
├── run_001/                          # First run
│   ├── evaluation_*_detailed.csv
│   ├── evaluation_*_summary.txt
│   └── graphs/
├── run_002/                          # Second run
│   └── ...
├── run_001.csv                       # Flat CSV for heatmap
├── run_002.csv
└── analysis/
    ├── heatmap_simple.png           # Question × Metrics heatmap
    └── ...
```

## Common Use Cases

### Baseline Before Changes
```bash
./run_mcp_retrieval_suite.sh --runs 5
# Save timestamp for comparison
```

### Test After okp-mcp Changes
```bash
# Make changes to okp-mcp
cd ~/Work/okp-mcp-lifecycle-deboost
# ... edit src/okp_mcp/tools.py ...
cd ~/Work/lscore-deploy/local
podman-compose restart okp-mcp

# Re-test
cd ~/Work/lightspeed-core/lightspeed-evaluation
./run_mcp_retrieval_suite.sh --runs 5
```

### Compare Results
```bash
python scripts/compare_runs.py \
  mcp_retrieval_output/suite_BASELINE/run_001.csv \
  mcp_retrieval_output/suite_IMPROVED/run_001.csv
```

## Options

```
--runs N                 Number of runs (default: 5)
--config FILE            Evaluation config (default: config/chronically_failing_questions.yaml)
--system-config FILE     System config (default: config/system_mcp_direct.yaml)
--help                   Show help
```

## Requirements

1. **okp-mcp must be running**:
   ```bash
   cd ~/Work/lscore-deploy/local
   podman-compose ps okp-mcp  # Should show "healthy"
   ```

2. **expected_urls in test config** (for url_retrieval_eval metric):
   ```yaml
   - conversation_group_id: TEST-001
     turns:
       - turn_id: turn1
         query: "Your question here"
         expected_urls:
           - https://access.redhat.com/documentation/.../doc1
           - https://access.redhat.com/documentation/.../doc2
   ```

## Interpreting Results

### Heatmap
- **Green** (> 0.7): Good retrieval
- **Yellow** (0.5-0.7): Moderate retrieval
- **Red** (< 0.5): Poor retrieval

### Focus On
- Questions with consistently low scores across multiple runs
- Metrics that fail most often (context_precision vs context_relevance vs url_retrieval)

### What Low Scores Mean

**Low context_precision_without_reference (< 0.5)**:
- Retrieving too many irrelevant documents
- Need better query understanding or filtering

**Low context_relevance (< 0.5)**:
- Retrieved docs don't match query intent
- May need better semantic matching or ranking

**Low url_retrieval_eval (< 0.5)**:
- Not retrieving expected documentation
- Could be ranking issue, missing docs, or wrong version

## Next Steps After Running

1. **View heatmap** to identify problem questions
2. **Analyze failing questions** - what docs are being retrieved instead?
3. **Adjust okp-mcp** ranking/boosting parameters
4. **Re-run suite** to verify improvements
5. **Repeat** until metrics improve

## See Also

- `MCP_DIRECT_MODE.md` - Full documentation on MCP direct mode
- `config/system_mcp_direct.yaml` - MCP direct system configuration
- `config/chronically_failing_questions.yaml` - Default test questions

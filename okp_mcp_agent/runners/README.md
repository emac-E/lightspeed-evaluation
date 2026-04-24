# Pattern Fix Loop - Proof of Concept

Automated fix loop for pattern-based JIRA ticket resolution with smart optimization routing.

## Configuration

### 1. Set up paths

**Option A: Edit config file** (recommended for stable setups)
```bash
# Copy example config
cp okp_mcp_agent/config/pattern_fix_config.yaml.example okp_mcp_agent/config/pattern_fix_config.yaml

# Edit paths to match your environment
vim okp_mcp_agent/config/pattern_fix_config.yaml
```

**Option B: Use environment variables** (recommended for flexibility)
```bash
# In your .bashrc or .zshrc:
export OKP_MCP_ROOT=/path/to/okp-mcp
export LSCORE_DEPLOY_ROOT=/path/to/lscore-deploy

# Update config to use env vars:
okp_mcp_root: ${OKP_MCP_ROOT}
lscore_deploy_root: ${LSCORE_DEPLOY_ROOT}
```

**Option C: Relative paths** (if repos are siblings)
```yaml
# If your directory structure is:
#   ~/Work/
#     lightspeed-evaluation/
#     okp-mcp/
#     lscore-deploy/
#
# Config file uses paths relative to itself:
eval_root: ../..
okp_mcp_root: ../../../../okp-mcp
lscore_deploy_root: ../../../../lscore-deploy
```

### 2. Verify configuration

```bash
python okp_mcp_agent/runners/run_pattern_fix_poc.py --help
```

If paths are incorrect, you'll get a clear error message with the missing path.

## Usage

### Basic Usage

```bash
# Run POC on a pattern (uses defaults from config)
python okp_mcp_agent/runners/run_pattern_fix_poc.py EOL_UNSUPPORTED_LEGACY_RHEL
```

### Custom Parameters

```bash
# Override config values via command line
python okp_mcp_agent/runners/run_pattern_fix_poc.py EOL_UNSUPPORTED_LEGACY_RHEL \
    --max-iterations 5 \
    --answer-threshold 0.80 \
    --stability-runs 3
```

### Use Custom Config

```bash
# Use a different config file
python okp_mcp_agent/runners/run_pattern_fix_poc.py PATTERN_ID \
    --config /path/to/custom_config.yaml
```

## Workflow Phases

### Phase 1: Initial Baseline
- Runs full evaluation with all metrics
- Determines problem type (retrieval vs answer quality)
- If already passing, exits early

### Phase 2: Smart Optimization
Routes to appropriate optimization based on problem type:

**Route A: Retrieval Optimization** (if retrieval metrics are low)
- Fast: ~15-20 sec/iteration
- Tests: Solr config changes (qf, pf, mm, highlighting)
- Mode: Retrieval-only (no response generation)
- Early exit: When any expected docs are found

**Route B: Prompt Optimization** (if answer quality is low)
- Slower: ~30-60 sec/iteration  
- Tests: System prompt changes (instructions, grounding)
- Mode: Full evaluation (with response generation)
- Early exit: When answer_correctness > 0.75

### Phase 3: Answer Validation
- Validates final answer_correctness ≥ threshold
- Must pass faithfulness ≥ 0.8
- Single run with full evaluation

### Phase 4: Stability Check
- Runs N times (default: 3) to verify consistency
- Checks variance < 0.05
- All runs must pass threshold
- High variance triggers escalation (see docs/VARIANCE_SOLUTIONS.md)

## Output

### Git Branch
```bash
fix/pattern-eol-unsupported-legacy-rhel
```

### Diagnostics Directory
```
.diagnostics/EOL_UNSUPPORTED_LEGACY_RHEL/
├── REVIEW_REPORT.md          # Human review report
├── iteration_summary.txt     # Iteration-by-iteration metrics
├── baseline_metrics.json     # Phase 1 results
├── optimization_log.txt      # Phase 2 changes
└── stability_results.json    # Phase 4 variance data
```

### Review Report
Automatically generated markdown summary:
- Overall status (✅ SUCCESS / ❌ FAILED)
- Phase-by-phase breakdown
- Final metrics and recommendations
- Next steps (merge or investigate)

## Configuration Reference

### Required Paths

| Key | Description | Example |
|-----|-------------|---------|
| `eval_root` | lightspeed-evaluation repo | `/home/user/Work/lightspeed-evaluation` |
| `okp_mcp_root` | okp-mcp repo | `/home/user/Work/okp-mcp` |
| `lscore_deploy_root` | lscore-deploy repo | `/home/user/Work/lscore-deploy` |
| `patterns_dir` | Pattern YAML directory | `okp_mcp_agent/config/patterns` |

### Optimization Parameters

| Key | Default | Description |
|-----|---------|-------------|
| `max_iterations` | 10 | Max iterations per optimization phase |
| `answer_threshold` | 0.75 | Minimum answer_correctness to pass |
| `stability_runs` | 3 | Number of runs for stability check |

### Agent Options

| Key | Default | Description |
|-----|---------|-------------|
| `interactive` | true | Ask for confirmation before changes |
| `enable_llm_advisor` | true | Use LLM for AI-powered suggestions |

## Examples

### Quick Test (2 iterations, 2 stability runs)
```bash
python okp_mcp_agent/runners/run_pattern_fix_poc.py EOL_UNSUPPORTED_LEGACY_RHEL \
    --max-iterations 2 \
    --stability-runs 2
```

### High Confidence (15 iterations, 5 stability runs)
```bash
python okp_mcp_agent/runners/run_pattern_fix_poc.py BOOTLOADER_UEFI_FIRMWARE \
    --max-iterations 15 \
    --answer-threshold 0.80 \
    --stability-runs 5
```

### Production Run (all patterns, full validation)
```bash
for pattern in okp_mcp_agent/config/patterns/*.yaml; do
    pattern_id=$(basename "$pattern" .yaml)
    python okp_mcp_agent/runners/run_pattern_fix_poc.py "$pattern_id"
done
```

## Troubleshooting

### "Config file not found"
```bash
# Create config from example:
cp okp_mcp_agent/config/pattern_fix_config.yaml.example \
   okp_mcp_agent/config/pattern_fix_config.yaml

# Edit paths:
vim okp_mcp_agent/config/pattern_fix_config.yaml
```

### "Environment variable not set"
```bash
# Check current value:
echo $OKP_MCP_ROOT

# Set it:
export OKP_MCP_ROOT=/home/user/Work/okp-mcp

# Or edit config to use absolute path instead
```

### "Required path does not exist"
```bash
# Verify paths exist:
ls -ld /path/to/okp-mcp
ls -ld /path/to/lscore-deploy

# Fix config file with correct paths
```

### "Pattern file not found"
```bash
# List available patterns:
ls okp_mcp_agent/config/patterns/

# Use exact pattern ID (case-sensitive):
python okp_mcp_agent/runners/run_pattern_fix_poc.py EOL_UNSUPPORTED_LEGACY_RHEL
```

## See Also

- [Pattern Discovery](../pattern_discovery/README.md) - How patterns are discovered
- [Variance Solutions](../../docs/VARIANCE_SOLUTIONS.md) - Debugging high variance
- [OKP-MCP Agent](../agents/README.md) - Base agent implementation

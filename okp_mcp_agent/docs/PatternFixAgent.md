# PatternFixAgent Class Reference

## Overview

`PatternFixAgent` is a **specialized subclass of OkpMcpAgent** for pattern-based batch ticket fixing. It implements the simplified fix loop with smart routing between fast Solr optimization and full retrieval path testing.

**Location:** `scripts/run_pattern_fix_poc.py`

**Purpose:** Fix groups of 6-15 similar tickets together using shared Solr optimizations

---

## When You'll Interact With PatternFixAgent

| Scenario | Need PatternFixAgent? |
|----------|----------------------|
| **Fixing batches of similar tickets** | ✅ Yes - pattern-based fixes |
| **Testing pattern fix workflow** | ✅ Yes - POC implementation |
| **Running stability checks** | ✅ Yes - multi-run variance detection |
| **Fixing single tickets** | ❌ No - use `OkpMcpAgent` |
| **Running standard evaluations** | ❌ No - use EvaluationPipeline |

**For batch pattern fixes: This is the primary class.**

---

## Class Definition

```python
class PatternFixAgent(OkpMcpAgent):
    """Fix loop agent for pattern-based ticket resolution."""
```

**Inheritance:** Extends `OkpMcpAgent`

**Inherits:** All methods from `OkpMcpAgent` (diagnosis, Solr queries, validation)

---

## Constructor

```python
def __init__(self, pattern_id: str, **kwargs):
    """Initialize pattern fix agent.
    
    Args:
        pattern_id: Pattern identifier (e.g., "RHEL10_DEPRECATED_FEATURES")
        **kwargs: Passed to OkpMcpAgent parent class
    """
```

### Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `pattern_id` | `str` | ✅ Yes | Pattern identifier from YAML filename | `"RHEL10_DEPRECATED_FEATURES"` |
| `**kwargs` | - | ❌ No | Passed to `OkpMcpAgent` | `eval_root`, `okp_mcp_root`, etc. |

### Initialization Example

```python
from pathlib import Path
from scripts.run_pattern_fix_poc import PatternFixAgent

# Create agent for specific pattern
agent = PatternFixAgent(
    pattern_id="RHEL10_DEPRECATED_FEATURES",
    eval_root=Path.cwd(),
    okp_mcp_root=Path.cwd().parent / "okp-mcp",
    lscore_deploy_root=Path.cwd().parent / "lscore-deploy",
    interactive=True,
    enable_llm_advisor=True,
)

print(f"Pattern: {agent.pattern_id}")
print(f"Branch: {agent.branch_name}")
# Output:
# Pattern: RHEL10_DEPRECATED_FEATURES
# Branch: fix/pattern-rhel10-deprecated-features
```

### Auto-Generated Attributes

```python
self.pattern_id = pattern_id  # e.g., "RHEL10_DEPRECATED_FEATURES"
self.pattern_tickets = []      # Loaded via load_pattern_tickets()
self.branch_name = f"fix/pattern-{pattern_id.lower().replace('_', '-')}"
# e.g., "fix/pattern-rhel10-deprecated-features"
```

---

## Core Methods

### load_pattern_tickets()

Load tickets for this pattern from YAML config.

```python
def load_pattern_tickets(self, patterns_dir: Path) -> None:
    """Load tickets for this pattern from YAML.
    
    Args:
        patterns_dir: Directory containing pattern YAMLs
        
    Raises:
        FileNotFoundError: Pattern file not found
        ValueError: No conversations found in file
    """
```

**Usage:**

```python
agent = PatternFixAgent("RHEL10_DEPRECATED_FEATURES", ...)

# Load tickets from pattern YAML
patterns_dir = Path("config/patterns_v2")
agent.load_pattern_tickets(patterns_dir)

print(f"Loaded {len(agent.pattern_tickets)} tickets")
# Output: Loaded 3 tickets

# Access ticket info
for ticket in agent.pattern_tickets:
    print(f"  {ticket['ticket_id']}: {ticket['query']}")
```

**Expected YAML Structure:**

```yaml
# config/patterns_v2/RHEL10_DEPRECATED_FEATURES.yaml
conversations:
  - conversation_group_id: "RSPEED-2482"
    turns:
      - query: "What DHCP server should I use in RHEL 10?"
        expected_response: "Kea is the DHCP server in RHEL 10..."
        expected_urls:
          - "https://access.redhat.com/articles/12345"
        turn_metrics:
          - "custom:url_retrieval_eval"
          - "ragas:context_relevance"
          - "custom:answer_correctness"
```

**Loaded Fields Per Ticket:**

```python
{
    'ticket_id': "RSPEED-2482",
    'query': "What DHCP server should I use in RHEL 10?",
    'expected_response': "Kea is the DHCP server...",
    'expected_urls': ["https://access.redhat.com/articles/12345"],
}
```

---

### create_pattern_branch()

Create git branch for this pattern's fixes.

```python
def create_pattern_branch(self) -> None:
    """Create git branch for this pattern's fixes.
    
    Branch naming: fix/pattern-{pattern_id_lowercase}
    
    Behavior:
        - If branch exists: Switch to it
        - If branch doesn't exist: Create and switch
    """
```

**Usage:**

```python
agent.create_pattern_branch()
# Output:
# 📌 Creating branch: fix/pattern-rhel10-deprecated-features
# ✅ On branch: fix/pattern-rhel10-deprecated-features
```

**Git Commands Run:**

```bash
# Check if branch exists
git branch --list fix/pattern-rhel10-deprecated-features

# If exists:
git checkout fix/pattern-rhel10-deprecated-features

# If doesn't exist:
git checkout -b fix/pattern-rhel10-deprecated-features
```

---

### run_fix_loop()

Run complete fix loop with all phases.

```python
def run_fix_loop(
    self,
    max_iterations: int = 15,
    answer_threshold: float = 0.75,
    stability_runs: int = 5,
) -> PatternFixResult:
    """Run complete fix loop with all phases.
    
    Args:
        max_iterations: Max iterations for optimization phases
        answer_threshold: Minimum answer_correctness to pass
        stability_runs: Number of runs for stability check
        
    Returns:
        PatternFixResult with complete status
    """
```

**Phases:**

1. **Baseline**: Establish starting metrics
2. **Phase 2A: Solr Optimization** (Fast loop)
   - Use `query_solr_direct()` for fast iteration
   - ~5 seconds per iteration
   - Exit when URL F1 plateaus or reaches threshold
3. **Phase 2B: Answer Validation** (Full loop)
   - Run full LLM evaluation on all tickets
   - Check answer_correctness across pattern
4. **Phase 3: Stability Check**
   - Run `stability_runs` times (default: 5)
   - Detect variance in metrics
   - Escalate if unstable (>= 0.05 variance)

**Usage:**

```python
agent = PatternFixAgent("RHEL10_DEPRECATED_FEATURES", ...)
agent.load_pattern_tickets(Path("config/patterns_v2"))
agent.create_pattern_branch()

# Run complete fix loop
result = agent.run_fix_loop(
    max_iterations=15,
    answer_threshold=0.75,
    stability_runs=5,
)

# Check results
if result.success:
    print(f"✅ Pattern fixed successfully")
    print(f"   Branch: {result.branch_name}")
    print(f"   Tickets tested: {result.tickets_tested}/{result.total_tickets}")
    print(f"   Duration: {result.duration_seconds:.1f}s")
else:
    print(f"❌ Pattern fix failed")
    print(f"   Reason: {result.stability.reason if result.stability else 'Unknown'}")
```

**Output:**

```
================================================================================
PATTERN FIX LOOP: RHEL10_DEPRECATED_FEATURES
================================================================================
Tickets: 3
Branch: fix/pattern-rhel10-deprecated-features
Max iterations: 15
Answer threshold: 0.75
Stability runs: 5

Phase 1: Baseline
  Ticket RSPEED-2482: URL F1=0.33, Answer=0.60
  Ticket RSPEED-2483: URL F1=0.40, Answer=0.65
  Ticket RSPEED-2484: URL F1=0.35, Answer=0.62
  Average: URL F1=0.36, Answer=0.62

Phase 2A: Solr Optimization (Fast Loop)
  Iteration 1: URL F1=0.45 (+0.09)
  Iteration 2: URL F1=0.52 (+0.07)
  Iteration 3: URL F1=0.71 (+0.19) ✅ Threshold reached
  
Phase 2B: Answer Validation (Full Loop)
  Running full evaluation on all 3 tickets...
  RSPEED-2482: Answer=0.78 ✅
  RSPEED-2483: Answer=0.82 ✅
  RSPEED-2484: Answer=0.76 ✅
  Average: 0.79 ✅ Above threshold (0.75)

Phase 3: Stability Check
  Run 1/5: Answer=0.78
  Run 2/5: Answer=0.79
  Run 3/5: Answer=0.77
  Run 4/5: Answer=0.80
  Run 5/5: Answer=0.78
  Variance: 0.012 ✅ Stable (< 0.05)

✅ Pattern fix complete!
   Diagnostics: .diagnostics/RHEL10_DEPRECATED_FEATURES/
   Review report: .diagnostics/RHEL10_DEPRECATED_FEATURES/REVIEW_REPORT.md
```

---

## Helper Classes

### PhaseResult

Result from a single fix loop phase.

```python
@dataclass
class PhaseResult:
    """Result from a fix loop phase."""
    
    phase_name: str
    success: bool
    iterations: int = 0
    final_metrics: Dict = field(default_factory=dict)
    reason: str = ""
```

**Usage:**

```python
baseline_phase = PhaseResult(
    phase_name="Baseline",
    success=True,
    iterations=0,
    final_metrics={"url_f1": 0.36, "answer_correctness": 0.62},
    reason="Baseline established"
)
```

---

### PatternFixResult

Complete result from pattern fix loop.

```python
@dataclass
class PatternFixResult:
    """Complete result from pattern fix loop."""
    
    pattern_id: str
    total_tickets: int
    tickets_tested: int
    
    # Phase results
    baseline: Optional[PhaseResult] = None
    optimization: Optional[PhaseResult] = None
    answer_validation: Optional[PhaseResult] = None
    stability: Optional[PhaseResult] = None
    
    # Overall status
    success: bool = False
    branch_name: str = ""
    diagnostics_dir: Path = Path()
    
    # Timing
    start_time: str = ""
    end_time: str = ""
    duration_seconds: float = 0.0
```

**Usage:**

```python
result = agent.run_fix_loop()

# Access phase results
if result.baseline and result.baseline.success:
    print(f"Baseline: {result.baseline.final_metrics}")

if result.optimization and result.optimization.success:
    print(f"Optimization: {result.optimization.iterations} iterations")

# Check overall success
if result.success:
    print(f"✅ Fixed in {result.duration_seconds:.1f}s")
else:
    print(f"❌ Failed: {result.stability.reason}")
```

---

## Pattern Fix Workflow

### Complete Example

```python
#!/usr/bin/env python3
"""Fix pattern RHEL10_DEPRECATED_FEATURES."""

from pathlib import Path
from scripts.run_pattern_fix_poc import PatternFixAgent

# 1. Initialize agent
agent = PatternFixAgent(
    pattern_id="RHEL10_DEPRECATED_FEATURES",
    eval_root=Path.cwd(),
    okp_mcp_root=Path.cwd().parent / "okp-mcp",
    lscore_deploy_root=Path.cwd().parent / "lscore-deploy",
)

# 2. Load pattern tickets
agent.load_pattern_tickets(Path("config/patterns_v2"))

# 3. Create git branch
agent.create_pattern_branch()

# 4. Run fix loop
result = agent.run_fix_loop(
    max_iterations=15,
    answer_threshold=0.75,
    stability_runs=5,
)

# 5. Review results
if result.success:
    print(f"\n{'='*80}")
    print(f"SUCCESS: Pattern fixed")
    print(f"{'='*80}")
    print(f"Branch: {result.branch_name}")
    print(f"Tickets: {result.tickets_tested}/{result.total_tickets}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"Diagnostics: {result.diagnostics_dir}")
    
    # Review report
    review_report = result.diagnostics_dir / "REVIEW_REPORT.md"
    if review_report.exists():
        print(f"\nReview: {review_report}")
else:
    print(f"\n{'='*80}")
    print(f"FAILED: Pattern not fixed")
    print(f"{'='*80}")
    if result.stability:
        print(f"Reason: {result.stability.reason}")
    print(f"Diagnostics: {result.diagnostics_dir}")
```

---

## Command-Line Usage

### Script: run_pattern_fix_poc.py

```bash
# Basic usage
python scripts/run_pattern_fix_poc.py RHEL10_DEPRECATED_FEATURES

# Custom parameters
python scripts/run_pattern_fix_poc.py CONTAINER_UNSUPPORTED_CONFIG \
    --max-iterations 15 \
    --answer-threshold 0.75 \
    --stability-runs 5

# Non-interactive mode
python scripts/run_pattern_fix_poc.py RHEL10_DEPRECATED_FEATURES \
    --non-interactive
```

**Arguments:**

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `pattern_id` | ✅ Yes | - | Pattern identifier (matches YAML filename) |
| `--max-iterations` | ❌ No | 15 | Max iterations for optimization |
| `--answer-threshold` | ❌ No | 0.75 | Minimum answer_correctness |
| `--stability-runs` | ❌ No | 5 | Number of stability check runs |
| `--non-interactive` | ❌ No | False | Skip confirmation prompts |

---

## Diagnostics Output

All diagnostics saved to `.diagnostics/{pattern_id}/`:

```
.diagnostics/RHEL10_DEPRECATED_FEATURES/
├── baseline_metrics.json           # Initial metrics per ticket
├── optimization_history.json       # Solr iteration history
├── answer_validation_results.json  # Full eval results per ticket
├── stability_runs.json             # Variance analysis
├── REVIEW_REPORT.md               # Human-readable summary
└── solr_config_snapshot.json      # Final Solr configuration
```

### REVIEW_REPORT.md Format

```markdown
# Pattern Fix Review: RHEL10_DEPRECATED_FEATURES

## Summary

- **Status**: ✅ Success
- **Tickets**: 3/3 tested
- **Duration**: 245.3 seconds
- **Branch**: fix/pattern-rhel10-deprecated-features

## Metrics Improvement

| Ticket | Baseline URL F1 | Final URL F1 | Baseline Answer | Final Answer |
|--------|-----------------|--------------|-----------------|--------------|
| RSPEED-2482 | 0.33 | 0.75 | 0.60 | 0.78 |
| RSPEED-2483 | 0.40 | 0.78 | 0.65 | 0.82 |
| RSPEED-2484 | 0.35 | 0.72 | 0.62 | 0.76 |

## Phase Results

### Phase 1: Baseline
- All 3 tickets evaluated
- Average URL F1: 0.36
- Average Answer Correctness: 0.62

### Phase 2A: Solr Optimization
- Iterations: 3
- Final URL F1: 0.71
- Improvement: +0.35 (+97%)

### Phase 2B: Answer Validation
- All tickets above threshold (0.75)
- Average: 0.79

### Phase 3: Stability
- Runs: 5
- Variance: 0.012 ✅ Stable

## Next Steps

1. Review changes in branch: `fix/pattern-rhel10-deprecated-features`
2. Manual QA on sample tickets
3. Merge if acceptable
```

---

## Performance Characteristics

### Phase Timing

| Phase | Tickets | Time per Ticket | Total Time |
|-------|---------|-----------------|------------|
| Baseline | 3 | ~30s | ~90s |
| Solr Optimization (10 iter) | 1 (representative) | ~5s | ~50s |
| Answer Validation | 3 | ~30s | ~90s |
| Stability Check (5 runs) | 3 | ~30s | ~450s |

**Total:** ~680 seconds (~11 minutes) for 3-ticket pattern

**Scaling:**
- 6-ticket pattern: ~15 minutes
- 15-ticket pattern: ~30 minutes

---

## Comparison: PatternFixAgent vs OkpMcpAgent

| Feature | PatternFixAgent | OkpMcpAgent |
|---------|-----------------|-------------|
| **Purpose** | Batch pattern fixes | Single ticket fixes |
| **Tickets** | 6-15 similar tickets | 1 ticket |
| **Phases** | 4 phases (baseline, optimize, validate, stability) | 2 phases (diagnose, fix) |
| **Stability** | Required (5 runs) | Optional (1 run) |
| **Branch** | Auto-creates pattern branch | No auto-branch |
| **Fast Loop** | ✅ Phase 2A | ✅ fast_retrieval_loop() |
| **Validation** | ✅ All tickets in pattern | ❌ Single ticket only |

---

## Debugging Tips

### Problem: Pattern File Not Found

**Symptom:** `FileNotFoundError: Pattern file not found`

**Check:**
```python
pattern_file = Path("config/patterns_v2") / f"{pattern_id}.yaml"
print(f"Looking for: {pattern_file}")
print(f"Exists: {pattern_file.exists()}")
```

**Fix:** Ensure pattern ID matches YAML filename exactly (case-sensitive).

---

### Problem: No Tickets Loaded

**Symptom:** `ValueError: No conversations found`

**Check:**
```python
with open(pattern_file) as f:
    content = f.read()
    print(content[:500])  # Check YAML format
```

**Fix:** Ensure YAML has `conversations:` key with list of ticket dicts.

---

### Problem: Stability Fails with High Variance

**Symptom:** Phase 3 fails, `variance >= 0.05`

**Meaning:** Metrics vary significantly across runs (unstable).

**Check:**
```python
# Read stability_runs.json
import json
with open(".diagnostics/{pattern_id}/stability_runs.json") as f:
    runs = json.load(f)
    print(f"Variance: {runs['variance']}")
    print(f"Runs: {runs['individual_runs']}")
```

**Solution:** See `docs/VARIANCE_SOLUTIONS.md` for root cause analysis.

---

## Integration with CI/CD

### Example CI Script

```bash
#!/bin/bash
# .github/workflows/pattern-fix.yml

set -e

PATTERN_ID="RHEL10_DEPRECATED_FEATURES"

# Run pattern fix
python scripts/run_pattern_fix_poc.py "$PATTERN_ID" \
    --non-interactive \
    --max-iterations 15 \
    --answer-threshold 0.75 \
    --stability-runs 5

# Check results
if [ -f ".diagnostics/$PATTERN_ID/REVIEW_REPORT.md" ]; then
    cat ".diagnostics/$PATTERN_ID/REVIEW_REPORT.md"
    
    # Create PR automatically
    gh pr create \
        --title "Fix pattern: $PATTERN_ID" \
        --body-file ".diagnostics/$PATTERN_ID/REVIEW_REPORT.md" \
        --base main \
        --head "fix/pattern-$(echo $PATTERN_ID | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
else
    echo "Pattern fix failed"
    exit 1
fi
```

---

## Related Classes

- **OkpMcpAgent**: Parent class (see `OkpMcpAgent.md`)
- **EvaluationResult**: Metrics container (see `EvaluationResult.md`)
- **OkpMcpLLMAdvisor**: LLM suggestions (see `OkpMcpLLMAdvisor.md`)
- **PhaseResult**: Phase outcome container
- **PatternFixResult**: Complete fix result

---

## Summary

**PatternFixAgent in a Nutshell:**
- 🎯 Batch fix 6-15 similar tickets together
- 📊 4-phase workflow: baseline → optimize → validate → stability
- ⚡ Fast Solr loop (~5s/iter) before full LLM eval (~30s/ticket)
- ✅ Required stability check (5 runs, <5% variance)
- 📝 Auto-generates review report
- 🌿 Auto-creates git branch

**When You Care:**
- ✅ Fixing batches of similar tickets
- ✅ Testing pattern fix workflow
- ✅ Stability validation required
- ❌ Single ticket fixes (use `OkpMcpAgent`)
- ❌ Ad-hoc evaluations (use EvaluationPipeline)

**Key Takeaway:** `PatternFixAgent` extends `OkpMcpAgent` with pattern-aware batch fixing, stability requirements, and comprehensive diagnostics. Use for production pattern fixes where stability is critical.

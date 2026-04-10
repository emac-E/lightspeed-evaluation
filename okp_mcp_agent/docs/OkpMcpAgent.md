# OkpMcpAgent Class Reference

## Overview

`OkpMcpAgent` is the **core autonomous agent** for fixing okp-mcp RSPEED tickets using the INCORRECT_ANSWER_LOOP workflow. It orchestrates the complete fix cycle: diagnosis, iteration, validation, and commits.

**Location:** `scripts/okp_mcp_agent.py`

**Purpose:** Automate ticket fixes with intelligent routing between Solr optimization (fast) and full LLM evaluation (comprehensive)

---

## When You'll Interact With OkpMcpAgent

| Scenario | Need OkpMcpAgent? |
|----------|-------------------|
| **Fixing individual RSPEED tickets** | ✅ Yes - use `diagnose()` and `fix_ticket()` |
| **Pattern-based batch fixes** | ✅ Yes - subclass as `PatternFixAgent` |
| **Debugging retrieval issues** | ✅ Yes - use `query_solr_direct()` |
| **Validating changes** | ✅ Yes - use `validate_all_suites()` |
| **Writing evaluation configs** | ❌ No - use YAML structure |
| **Running standard evaluations** | ❌ No - use EvaluationPipeline |

**For autonomous ticket fixing: This is the primary class you'll use.**

---

## Class Definition

```python
class OkpMcpAgent:
    """Autonomous agent for fixing okp-mcp RSPEED tickets."""
```

**Inheritance:** None (base class)

**Subclasses:** `PatternFixAgent` (in `run_pattern_fix_poc.py`)

---

## Constructor

```python
def __init__(
    self,
    eval_root: Path,
    okp_mcp_root: Path,
    lscore_deploy_root: Path,
    worktree_root: Optional[Path] = None,
    interactive: bool = True,
    enable_llm_advisor: bool = True,
):
    """Initialize agent with paths to key directories."""
```

### Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `eval_root` | `Path` | ✅ Yes | Path to lightspeed-evaluation repo | - |
| `okp_mcp_root` | `Path` | ✅ Yes | Path to okp-mcp repo | - |
| `lscore_deploy_root` | `Path` | ✅ Yes | Path to lscore-deploy repo | - |
| `worktree_root` | `Path` | ❌ No | Base directory for worktrees | `~/Work/okp-mcp-worktrees` |
| `interactive` | `bool` | ❌ No | Ask confirmation before changes | `True` |
| `enable_llm_advisor` | `bool` | ❌ No | Use LLM for AI suggestions | `True` |

### Initialization Example

```python
from pathlib import Path
from scripts.okp_mcp_agent import OkpMcpAgent

# Standard setup
agent = OkpMcpAgent(
    eval_root=Path("/home/user/Work/lightspeed-evaluation"),
    okp_mcp_root=Path("/home/user/Work/okp-mcp"),
    lscore_deploy_root=Path("/home/user/Work/lscore-deploy"),
)

# Non-interactive mode (for CI/automation)
agent = OkpMcpAgent(
    eval_root=Path.cwd(),
    okp_mcp_root=Path.cwd().parent / "okp-mcp",
    lscore_deploy_root=Path.cwd().parent / "lscore-deploy",
    interactive=False,
    enable_llm_advisor=False,
)
```

### Initialized Components

The constructor automatically initializes:

1. **LLM Advisor** (if `enable_llm_advisor=True` and available)
   ```python
   self.llm_advisor = OkpMcpLLMAdvisor(
       model="claude-sonnet-4-6",
       okp_mcp_root=okp_mcp_root,
       use_tiered_models=True,
   )
   ```

2. **Solr Checker** (for document validation)
   ```python
   self.solr_checker = SolrDocumentChecker()
   # Checks if Solr is accessible at http://localhost:8983/solr/portal
   ```

3. **Solr Analyzer** (for explain output and tuning)
   ```python
   self.solr_analyzer = SolrConfigAnalyzer(okp_mcp_root)
   ```

4. **Test Suite Configs**
   ```python
   self.functional_full = eval_root / "config/okp_mcp_test_suites/functional_tests_full.yaml"
   self.functional_retrieval = eval_root / "config/okp_mcp_test_suites/functional_tests_retrieval.yaml"
   ```

---

## Core Methods

### Diagnosis Methods

#### diagnose()

Run comprehensive evaluation to identify the problem type (retrieval vs answer quality).

```python
def diagnose(
    self,
    ticket_id: str,
    use_existing: bool = False,
    runs: int = 1
) -> EvaluationResult:
    """Diagnose ticket by running full evaluation.
    
    Args:
        ticket_id: RSPEED ticket ID (e.g., "RSPEED-2482")
        use_existing: Use existing results instead of re-running
        runs: Number of evaluation runs to average (for stability)
        
    Returns:
        EvaluationResult with metrics and problem classification
    """
```

**Usage:**

```python
# Diagnose with fresh evaluation
result = agent.diagnose("RSPEED-2482")

# Use existing results (fast, no re-run)
result = agent.diagnose("RSPEED-2482", use_existing=True)

# Stability check (5 runs averaged)
result = agent.diagnose("RSPEED-2482", runs=5)

# Check problem type
if result.is_retrieval_problem:
    print("Fix retrieval (boost queries)")
elif result.is_answer_problem:
    print("Fix answer (prompt changes)")
elif result.is_answer_good_enough:
    print("Already good enough, no fix needed")
```

**Output:**
- Creates evaluation config at `.diagnostics/{ticket_id}/ticket_config.yaml`
- Runs full evaluation via `run_full_eval()`
- Parses results into `EvaluationResult`
- Classifies problem type based on metrics

---

#### diagnose_retrieval_only()

Fast diagnosis using only retrieval metrics (no LLM answer evaluation).

```python
def diagnose_retrieval_only(
    self,
    ticket_id: str,
    use_existing: bool = False,
    runs: int = 3
) -> EvaluationResult:
    """Diagnose using retrieval-only mode (faster).
    
    Args:
        ticket_id: RSPEED ticket ID
        use_existing: Use existing retrieval results
        runs: Number of runs to average
        
    Returns:
        EvaluationResult with retrieval metrics only
    """
```

**Usage:**

```python
# Fast retrieval check (no LLM answer generation)
result = agent.diagnose_retrieval_only("RSPEED-2482")

# Check retrieval quality
print(f"URL F1: {result.url_f1}")
print(f"Context Relevance: {result.context_relevance}")
```

**When to Use:**
- ✅ Quick check before committing changes
- ✅ Iterating on Solr boost queries (fast loop)
- ❌ Need answer quality metrics (use `diagnose()` instead)

---

### Solr Direct Query Methods

#### query_solr_direct()

Query Solr directly and compute fast URL-based metrics without LLM. **This is the key method for fast Solr optimization loops.**

```python
def query_solr_direct(
    self,
    query: str,
    expected_urls: List[str],
    num_docs: int = 20
) -> Dict:
    """Query Solr directly and compute fast URL-based metrics (no LLM).
    
    This bypasses /v1/infer for fast iteration loops.
    
    Args:
        query: User query
        expected_urls: Expected document URLs
        num_docs: Number of docs to retrieve
        
    Returns:
        Dict with retrieved_urls and fast metrics:
        - url_f1: F1 score for URL retrieval (0.0-1.0)
        - mrr: Mean Reciprocal Rank (0.0-1.0)
        - precision_at_5: % of top 5 that are expected (0.0-1.0)
        - recall_at_5: % of expected docs in top 5 (0.0-1.0)
        - num_retrieved: Total docs retrieved
    """
```

**Usage:**

```python
# Fast Solr loop (~5 seconds per iteration)
expected = [
    "https://access.redhat.com/articles/12345",
    "https://docs.redhat.com/en-us/some-doc",
]

result = agent.query_solr_direct(
    query="How to configure Kea DHCP?",
    expected_urls=expected,
    num_docs=20
)

print(f"URL F1: {result['url_f1']:.2f}")
print(f"MRR: {result['mrr']:.2f}")
print(f"Precision@5: {result['precision_at_5']:.2f}")
print(f"Recall@5: {result['recall_at_5']:.2f}")
print(f"Retrieved {result['num_retrieved']} docs")

# Check improvement
if result['url_f1'] >= baseline['url_f1'] + 0.02:
    print("✅ Improvement detected")
```

**Performance:**
- ~5 seconds per query (vs ~30 seconds for full LLM evaluation)
- No LLM costs
- Fast feedback for Solr tuning

**Metrics Calculated:**
1. **URL F1**: Harmonic mean of precision/recall for expected URLs
2. **MRR (Mean Reciprocal Rank)**: 1/rank of first expected URL (0.0-1.0)
3. **Precision@5**: % of top 5 results that are expected
4. **Recall@5**: % of expected URLs in top 5

**Current Usage:**
As of the pattern fix POC, only `url_f1` is used in decision logic. Other metrics are displayed but not factored into improvement thresholds. See `docs/OPTIMIZATION_OPPORTUNITIES.md` for discussion on using all metrics.

---

#### inspect_solr_query()

Inspect what okp-mcp actually sent to Solr (detects query augmentation).

```python
def inspect_solr_query(self, original_query: str) -> Optional[Dict]:
    """Inspect what okp-mcp actually sent to Solr.
    
    This helps detect query augmentation (e.g., automatic addition of
    'deprecated removed' terms) that might be poisoning results.
    
    Args:
        original_query: The original user query
        
    Returns:
        Dict with 'original', 'actual', and 'injected_terms' keys,
        or None if not found
    """
```

**Usage:**

```python
# Check for query poisoning
inspection = agent.inspect_solr_query("How to install Kea?")

if inspection:
    print(f"Original: {inspection['original']}")
    print(f"Actual: {inspection['actual']}")
    
    if inspection['injected_terms']:
        print(f"⚠️  Injected terms: {inspection['injected_terms']}")
        # Example: ['deprecated', 'removed'] auto-added
```

---

### Fix Methods

#### fix_ticket()

Main fix loop with iteration and smart routing.

```python
def fix_ticket(
    self,
    ticket_id: str,
    max_iterations: int = 5,
    use_existing: bool = False,
) -> bool:
    """Fix ticket with iteration and validation.
    
    Args:
        ticket_id: RSPEED ticket ID
        max_iterations: Max fix attempts
        use_existing: Start from existing diagnosis
        
    Returns:
        True if fixed successfully
    """
```

**Usage:**

```python
# Standard fix
success = agent.fix_ticket("RSPEED-2482", max_iterations=5)

# Start from existing diagnosis (skip initial eval)
success = agent.fix_ticket("RSPEED-2482", use_existing=True)

if success:
    print("✅ Ticket fixed, changes committed")
else:
    print("❌ Fix failed, see diagnostics")
```

**Workflow:**
1. Diagnose problem type (retrieval vs answer)
2. Route to appropriate fix method:
   - Retrieval problem → `fast_retrieval_loop()` (Solr tuning)
   - Answer problem → LLM advisor for prompt changes
3. Iterate until metrics improve or max_iterations reached
4. Validate across all test suites (regression check)
5. Create commit if successful

---

#### fast_retrieval_loop()

Fast Solr optimization loop using `query_solr_direct()`.

```python
def fast_retrieval_loop(
    self,
    ticket_id: str,
    baseline: EvaluationResult,
    max_iterations: int = 10,
) -> EvaluationResult:
    """Fast Solr optimization loop with direct queries.
    
    Args:
        ticket_id: RSPEED ticket ID
        baseline: Baseline metrics to beat
        max_iterations: Max Solr tuning iterations
        
    Returns:
        Best EvaluationResult achieved
    """
```

**Usage:**

```python
# Get baseline
baseline = agent.diagnose("RSPEED-2482")

# Fast Solr tuning loop
best = agent.fast_retrieval_loop(
    ticket_id="RSPEED-2482",
    baseline=baseline,
    max_iterations=10
)

print(f"Baseline URL F1: {baseline.url_f1:.2f}")
print(f"Best URL F1: {best.url_f1:.2f}")
```

**Exit Criteria:**
- URL F1 improvement plateaus (2 iterations without improvement)
- Max iterations reached
- URL F1 >= 0.7 (good enough)

**Speed:**
- ~5 seconds per iteration
- ~50 seconds for 10 iterations (vs ~300 seconds for full LLM eval)

---

### Validation Methods

#### validate_all_suites()

Validate changes across all test suites to detect regressions.

```python
def validate_all_suites(self) -> Dict[str, List[EvaluationResult]]:
    """Validate across all test suites.
    
    Returns:
        Dict mapping suite name to list of results
    """
```

**Usage:**

```python
# After making changes, check for regressions
results = agent.validate_all_suites()

for suite_name, suite_results in results.items():
    passed = sum(1 for r in suite_results if r.is_answer_good_enough)
    total = len(suite_results)
    print(f"{suite_name}: {passed}/{total} passed")
    
    # Check for regressions
    failures = [r for r in suite_results if not r.is_answer_good_enough]
    if failures:
        print(f"⚠️  {len(failures)} regressions detected:")
        for f in failures:
            print(f"  - {f.ticket_id}: {f.summary()}")
```

**Test Suites Run:**
1. `functional_tests_full.yaml` - Full evaluation with LLM
2. `functional_tests_retrieval.yaml` - Retrieval-only (faster)

---

### Utility Methods

#### create_worktree()

Create git worktree for isolated testing.

```python
def create_worktree(
    self,
    branch_name: str,
    base_branch: str = "main"
) -> Path:
    """Create git worktree for isolated changes.
    
    Args:
        branch_name: New branch name
        base_branch: Branch to base off
        
    Returns:
        Path to worktree directory
    """
```

**Usage:**

```python
# Create isolated workspace
worktree = agent.create_worktree(
    branch_name="fix/rspeed-2482",
    base_branch="main"
)

print(f"Worktree at: {worktree}")
# Output: ~/Work/okp-mcp-worktrees/fix-rspeed-2482
```

---

#### restart_okp_mcp()

Restart okp-mcp container and verify health.

```python
def restart_okp_mcp(self, verify_healthy: bool = True):
    """Restart okp-mcp container.
    
    Args:
        verify_healthy: Wait for health check to pass
    """
```

**Usage:**

```python
# After changing Solr config
agent.restart_okp_mcp()

# Skip health check (faster, risky)
agent.restart_okp_mcp(verify_healthy=False)
```

---

#### parse_results()

Parse evaluation CSV results into `EvaluationResult`.

```python
def parse_results(
    self,
    output_dir: Path,
    ticket_id: str
) -> EvaluationResult:
    """Parse evaluation results from CSV.
    
    Args:
        output_dir: Evaluation output directory
        ticket_id: RSPEED ticket ID
        
    Returns:
        EvaluationResult with parsed metrics
    """
```

**Usage:**

```python
# Parse latest results
output_dir = agent.get_latest_output_dir("full")
result = agent.parse_results(output_dir, "RSPEED-2482")

print(result.summary())
```

---

## Helper Classes

### EvaluationResult

See `docs_draft/API_Guide/EvaluationResult.md` for detailed documentation.

Quick reference:

```python
@dataclass
class EvaluationResult:
    """Results from a single evaluation run."""
    
    ticket_id: str
    
    # Retrieval metrics
    url_f1: Optional[float] = None
    mrr: Optional[float] = None
    context_relevance: Optional[float] = None
    
    # Answer quality metrics
    keywords_score: Optional[float] = None
    answer_correctness: Optional[float] = None
    
    # Classification properties
    @property
    def is_retrieval_problem(self) -> bool: ...
    
    @property
    def is_answer_problem(self) -> bool: ...
    
    @property
    def is_answer_good_enough(self) -> bool: ...
```

---

### MetricThresholds

Configuration for problem classification.

```python
@dataclass
class MetricThresholds:
    """Thresholds for determining problem type."""
    
    url_f1_retrieval_problem: float = 0.7
    mrr_retrieval_problem: float = 0.5
    context_relevance_retrieval_problem: float = 0.7
    keywords_answer_problem: float = 0.7
    answer_correctness_good: float = 0.8
```

**Usage:**

```python
thresholds = MetricThresholds()

if result.url_f1 < thresholds.url_f1_retrieval_problem:
    print("Retrieval problem detected")
```

---

## Configuration Files

### Test Suite Configs

Located in `config/okp_mcp_test_suites/`:

1. **functional_tests_full.yaml**
   - Full LLM evaluation
   - Answer quality metrics
   - ~30 seconds per ticket
   - Used for final validation

2. **functional_tests_retrieval.yaml**
   - Retrieval-only metrics
   - No LLM answer generation
   - ~10 seconds per ticket
   - Used for fast regression checks

**Format:**

```yaml
conversations:
  - conversation_group_id: "RSPEED-2482"
    turns:
      - query: "How to install Kea DHCP?"
        expected_response: "Kea is the DHCP server in RHEL 10..."
        expected_keywords:
          - ["kea", "DHCP"]
          - ["install"]
        expected_urls:
          - "https://access.redhat.com/articles/12345"
        turn_metrics:
          - "custom:url_retrieval_eval"
          - "ragas:context_relevance"
          - "custom:answer_correctness"
```

---

## Common Workflows

### Workflow 1: Diagnose and Fix Single Ticket

```python
from pathlib import Path
from scripts.okp_mcp_agent import OkpMcpAgent

# Setup
agent = OkpMcpAgent(
    eval_root=Path.cwd(),
    okp_mcp_root=Path.cwd().parent / "okp-mcp",
    lscore_deploy_root=Path.cwd().parent / "lscore-deploy",
)

# Diagnose
result = agent.diagnose("RSPEED-2482")
print(result.summary())

# Fix
if result.is_retrieval_problem or result.is_answer_problem:
    success = agent.fix_ticket("RSPEED-2482", max_iterations=5)
    print(f"Fixed: {success}")
```

### Workflow 2: Fast Solr Tuning Loop

```python
# Get baseline
baseline = agent.diagnose_retrieval_only("RSPEED-2482")
print(f"Baseline URL F1: {baseline.url_f1:.2f}")

# Fast iteration loop
for i in range(10):
    # Make manual change to okp-mcp/src/okp_mcp/solr.py
    # (In practice, LLM advisor suggests changes)
    
    agent.restart_okp_mcp()
    
    # Fast check (5 seconds)
    current = agent.query_solr_direct(
        query=baseline.query,
        expected_urls=baseline.expected_urls,
    )
    
    print(f"Iteration {i+1}: URL F1 = {current['url_f1']:.2f}")
    
    if current['url_f1'] >= 0.7:
        print("✅ Good enough")
        break
```

### Workflow 3: Validate Changes

```python
# After making changes, check for regressions
results = agent.validate_all_suites()

all_passed = all(
    all(r.is_answer_good_enough for r in suite_results)
    for suite_results in results.values()
)

if all_passed:
    print("✅ No regressions, safe to commit")
else:
    print("❌ Regressions detected, investigate")
```

---

## Environment Requirements

### Required Environment Variables

```bash
# For Gemini evaluation LLM
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

# For Claude advisor (if enable_llm_advisor=True)
export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id
gcloud auth application-default login
```

### Check Environment

```python
if agent.check_environment():
    print("✅ Environment ready")
else:
    print("❌ Missing environment variables")
```

---

## Diagnostics Output

All diagnostics are saved to `.diagnostics/{ticket_id}/`:

```
.diagnostics/RSPEED-2482/
├── ticket_config.yaml          # Single-ticket evaluation config
├── iteration_1_diagnostics.json # Detailed metrics per iteration
├── iteration_summary.csv        # Summary table
└── solr_config_snapshot.json    # Solr config at each iteration
```

**iteration_diagnostics.json Format:**

```json
{
  "iteration": 1,
  "timestamp": "2026-04-09T10:30:00",
  "metrics": {
    "url_f1": 0.33,
    "mrr": 0.25,
    "context_relevance": 0.45,
    "answer_correctness": 0.60
  },
  "problem_type": "retrieval",
  "llm_suggestion": {
    "reasoning": "Expected docs have 'kea' in title...",
    "suggested_change": "Increase title boost from 4.0 to 6.0"
  }
}
```

---

## Performance Characteristics

| Operation | Time | Cost |
|-----------|------|------|
| `diagnose()` (1 run) | ~30s | ~$0.01 |
| `diagnose_retrieval_only()` | ~10s | ~$0.005 |
| `query_solr_direct()` | ~5s | $0 |
| `fast_retrieval_loop()` (10 iterations) | ~50s | $0 |
| `validate_all_suites()` | ~5min | ~$0.20 |

---

## Debugging Tips

### Problem: LLM Advisor Not Available

**Symptom:** `⚠️  LLM advisor not available`

**Check:**
```python
print(f"LLM advisor enabled: {agent.llm_advisor is not None}")
```

**Fix:**
```bash
export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id
gcloud auth application-default login
```

### Problem: Solr Checker Not Working

**Symptom:** `⚠️  Solr is not accessible`

**Check:**
```bash
curl http://localhost:8983/solr/portal/admin/ping
```

**Fix:**
```bash
cd lscore-deploy/local
podman-compose up -d
```

### Problem: Evaluation Results Not Found

**Symptom:** `FileNotFoundError: eval_output/...`

**Check:**
```python
output_dir = agent.get_latest_output_dir("full")
print(f"Looking for results in: {output_dir}")
```

**Fix:** Run evaluation first with `diagnose()` or check if results directory exists.

---

## Related Classes

- **PatternFixAgent**: Subclass for pattern-based batch fixes (see `PatternFixAgent.md`)
- **OkpMcpLLMAdvisor**: LLM-powered suggestion engine (see `OkpMcpLLMAdvisor.md`)
- **EvaluationResult**: Metrics container (see `EvaluationResult.md`)
- **SolrDocumentChecker**: Document validation (see `SolrDocumentChecker.md`)
- **SolrConfigAnalyzer**: Solr explain output (see `SolrConfigAnalyzer.md`)

---

## Summary

**OkpMcpAgent in a Nutshell:**
- 🤖 Autonomous agent for fixing RSPEED tickets
- 🔍 Diagnoses problems (retrieval vs answer quality)
- ⚡ Fast Solr optimization loop (~5s per iteration)
- 🔄 Iterative improvement with LLM suggestions
- ✅ Validates changes across test suites
- 📊 Tracks metrics and saves diagnostics

**When You Care:**
- ✅ Fixing individual RSPEED tickets
- ✅ Debugging retrieval issues
- ✅ Iterating on Solr boost queries
- ✅ Validating changes before commit
- ❌ Running standard evaluations (use EvaluationPipeline)
- ❌ Writing configs (use YAML)

**Key Takeaway:** `OkpMcpAgent` is the orchestrator for autonomous ticket fixes. Use `diagnose()` to identify problems, `fast_retrieval_loop()` for Solr tuning, and `validate_all_suites()` before committing.

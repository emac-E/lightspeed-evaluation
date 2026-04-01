# OKP-MCP Autonomous Agent

Autonomous agent for fixing okp-mcp RSPEED tickets using the lightspeed-evaluation framework.

## Overview

The `okp_mcp_agent.py` script automates the [INCORRECT_ANSWER_LOOP workflow](https://github.com/RedHatInsights/okp-mcp/blob/main/INCORRECT_ANSWER_LOOP.md) documented in okp-mcp:

```
┌──────────────┐
│  1. Diagnose │  Run full eval to identify problem type
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  2. Analyze  │  Determine retrieval vs answer problem
└──────┬───────┘
       │
       ├─────────────────┬─────────────────┐
       ▼                 ▼                 ▼
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ Retrieval   │   │  Answer     │   │  Already    │
│ Problem     │   │  Problem    │   │  Passing    │
└──────┬──────┘   └──────┬──────┘   └──────┬──────┘
       │                 │                 │
       ▼                 ▼                 │
┌─────────────┐   ┌─────────────┐         │
│ Fast Iter   │   │ Full Iter   │         │
│ (30 sec)    │   │ (3-5 min)   │         │
└──────┬──────┘   └──────┬──────┘         │
       │                 │                 │
       └────────┬────────┘                 │
                ▼                          │
         ┌─────────────┐                  │
         │ 3. Validate │                  │
         └──────┬──────┘                  │
                │                         │
                ▼                         │
         ┌─────────────┐                  │
         │ 4. Commit   │                  │
         └─────────────┘                  │
                                          ▼
                                    ┌─────────────┐
                                    │    Done     │
                                    └─────────────┘
```

## Quick Start

### Diagnose a Ticket

```bash
python scripts/okp_mcp_agent.py diagnose RSPEED-2482
```

**Output:**
```
================================================================================
DIAGNOSING: RSPEED-2482
================================================================================

📊 Running full evaluation (1 runs)...
$ ./run_okp_mcp_full_suite.sh --config config/okp_mcp_test_suites/functional_tests_full.yaml --runs 1

Ticket: RSPEED-2482
  URL F1: 0.33
  MRR: 0.20
  Context Relevance: 0.45
  Context Precision: 0.60
  Keywords: 0.50
  Forbidden Claims: 1.00

🔍 DIAGNOSIS: RETRIEVAL PROBLEM
   → Use fast iteration mode (retrieval-only)
   → Edit okp-mcp boost queries
```

### Auto-Fix a Ticket (TODO: Not Yet Implemented)

```bash
python scripts/okp_mcp_agent.py fix RSPEED-2482 --max-iterations 10
```

### Validate All Suites

```bash
python scripts/okp_mcp_agent.py validate
```

## Architecture

### Current Implementation (Phase 1)

The agent currently provides:

✅ **Diagnosis**: Automated problem classification
- Runs full evaluation once
- Parses CSV results
- Determines if retrieval or answer problem based on thresholds

✅ **Metric Analysis**: Decision tree for problem type
- URL F1 < 0.7 → Retrieval problem
- MRR < 0.5 → Retrieval problem
- Context Relevance < 0.7 → Retrieval problem
- URL F1 ≥ 0.7 AND Keywords < 0.7 → Answer problem

✅ **Shell Command Execution**: Automated script running
- `run_okp_mcp_full_suite.sh`
- `run_mcp_retrieval_suite.sh`
- `podman-compose restart okp-mcp`

✅ **Result Parsing**: CSV parsing and metric extraction
- Reads evaluation_*_detailed.csv
- Extracts per-ticket metrics
- Handles missing metrics gracefully

### TODO: Phase 2 Implementation

The following features are planned but not yet implemented:

❌ **Iteration Loop**: Autonomous fixing
```python
def fix_ticket_retrieval_mode(self, ticket_id: str, max_iterations: int):
    """Iterate on boost queries until URL F1 > 0.8."""
    for iteration in range(max_iterations):
        # 1. Edit okp-mcp boost queries
        self.edit_boost_queries(ticket_id)

        # 2. Restart okp-mcp
        self.restart_okp_mcp()

        # 3. Run fast retrieval eval
        result = self.run_retrieval_eval_and_parse(ticket_id)

        # 4. Check if fixed
        if result.url_f1 > 0.8:
            print(f"✅ Fixed in {iteration + 1} iterations!")
            return result

        print(f"Iteration {iteration + 1}: URL F1 = {result.url_f1:.2f}")

    print("⚠️ Max iterations reached")
```

❌ **LLM Integration**: AI-powered code editing
```python
from pydantic_ai import Agent

self.llm_agent = Agent('claude-sonnet-4-6', system_prompt="""
You are an okp-mcp boost query expert. Given evaluation metrics,
suggest specific changes to boost queries to improve document retrieval.
""")

def suggest_boost_query_changes(self, ticket_id: str, metrics: EvaluationResult):
    """Use LLM to suggest boost query improvements."""
    prompt = f"""
    Ticket: {ticket_id}
    Current metrics:
    - URL F1: {metrics.url_f1}
    - MRR: {metrics.mrr}
    - Context Relevance: {metrics.context_relevance}

    Suggest specific changes to okp-mcp boost queries to improve retrieval.
    """
    return self.llm_agent.run_sync(prompt)
```

❌ **Code Editing**: Automated file modification
```python
def edit_boost_queries(self, ticket_id: str, changes: Dict[str, Any]):
    """Apply boost query changes to okp-mcp portal.py."""
    portal_py = self.okp_mcp_root / "src/okp_mcp/portal.py"

    # Read current content
    content = portal_py.read_text()

    # Apply changes (could use AST manipulation or regex)
    modified = apply_boost_changes(content, changes)

    # Write back
    portal_py.write_text(modified)
```

❌ **Regression Testing**: Multi-suite validation
```python
def validate_no_regressions(self, baseline_dir: Path, current_dir: Path):
    """Compare current results with baseline across all suites."""
    suites = ["functional", "chronically_failing", "general_documentation"]

    for suite in suites:
        baseline = parse_suite_results(baseline_dir / suite)
        current = parse_suite_results(current_dir / suite)

        regressions = find_regressions(baseline, current, threshold=-0.05)

        if regressions:
            print(f"⚠️ Regressions detected in {suite}:")
            for ticket, delta in regressions.items():
                print(f"  {ticket}: {delta:.2f}")
            return False

    return True
```

❌ **Commit Creation**: Git automation
```python
def create_commit(self, ticket_id: str, metrics_before: EvaluationResult,
                  metrics_after: EvaluationResult):
    """Create git commit with detailed metrics."""
    message = f"""fix: improve retrieval for {ticket_id}

Adjusted boost query for documentKind:solution when query contains 'container'.

Evaluation metrics (lightspeed-evaluation):
- URL Retrieval F1: {metrics_before.url_f1:.2f} → {metrics_after.url_f1:.2f}
- MRR: {metrics_before.mrr:.2f} → {metrics_after.mrr:.2f}
- Context Relevance: {metrics_before.context_relevance:.2f} → {metrics_after.context_relevance:.2f}

No regressions detected in chronically_failing and general_documentation suites.

Iteration details:
- Fast mode: 8 iterations (4 minutes total)
- Full validation: 1 run (5 minutes)
- Total dev time: 9 minutes

Co-Authored-By: okp-mcp-agent <noreply@redhat.com>
"""

    self.run_command(["git", "add", "-A"], cwd=self.okp_mcp_root)
    self.run_command(["git", "commit", "-m", message], cwd=self.okp_mcp_root)
```

## Usage Examples

### Example 1: Diagnose Multiple Tickets

```bash
# Diagnose all functional test tickets
for ticket in RSPEED-2482 RSPEED-2481 RSPEED-2480; do
    python scripts/okp_mcp_agent.py diagnose $ticket
done
```

### Example 2: Manual Iteration Loop (Current)

Since auto-fix is not yet implemented, you can use the agent for diagnosis and iterate manually:

```bash
# 1. Diagnose
python scripts/okp_mcp_agent.py diagnose RSPEED-2482
# Output: RETRIEVAL PROBLEM → Use fast iteration mode

# 2. Edit boost queries manually
cd ~/Work/okp-mcp
vim src/okp_mcp/portal.py

# 3. Restart okp-mcp manually
cd ~/Work/lscore-deploy/local
podman-compose restart okp-mcp

# 4. Run fast eval manually
cd ~/Work/lightspeed-core/lightspeed-evaluation
./run_mcp_retrieval_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_retrieval.yaml \
  --runs 3

# 5. Check results and repeat until URL F1 > 0.8
```

### Example 3: Future Auto-Fix (Planned)

```bash
# Once LLM integration is complete:
python scripts/okp_mcp_agent.py fix RSPEED-2482 \
  --max-iterations 10 \
  --auto-commit
```

**Expected output:**
```
================================================================================
AUTO-FIX: RSPEED-2482
================================================================================

🔍 DIAGNOSIS: RETRIEVAL PROBLEM
   → Use fast iteration mode (retrieval-only)

🔄 Starting fast iteration (retrieval mode)...

Iteration 1/10:
  🤖 LLM suggests: Increase documentKind:solution boost by 2x for 'container' queries
  ✏️  Editing src/okp_mcp/portal.py...
  🔄 Restarting okp-mcp...
  ⚡ Running retrieval eval...
  📊 URL F1: 0.33 → 0.55 (improved but not enough)

Iteration 2/10:
  🤖 LLM suggests: Add product:RHEL filter
  ✏️  Editing src/okp_mcp/portal.py...
  🔄 Restarting okp-mcp...
  ⚡ Running retrieval eval...
  📊 URL F1: 0.55 → 0.85 (GOOD!)

✅ Fixed in 2 iterations!

🔍 Running regression checks...
  ✅ functional: 13/20 → 14/20 (no regressions)
  ✅ chronically_failing: 6/10 → 6/10 (no regressions)
  ✅ general_documentation: 18/20 → 18/20 (no regressions)

💾 Creating commit...
[okp-mcp abc1234] fix: improve retrieval for RSPEED-2482
 1 file changed, 5 insertions(+), 2 deletions(-)

🎉 DONE! Total time: 4 minutes
```

## Metric Thresholds

The agent uses the following thresholds to classify problems:

| Metric | Threshold | Meaning |
|--------|-----------|---------|
| URL F1 | < 0.7 | Retrieval problem |
| MRR | < 0.5 | Retrieval problem |
| Context Relevance | < 0.7 | Retrieval problem |
| Keywords | < 0.7 | Answer problem (if retrieval is good) |

You can adjust these in `okp_mcp_agent.py` by modifying the `MetricThresholds` dataclass.

## Integration with Existing Workflow

This agent complements the human-in-the-loop workflow documented in `OKP_MCP_INTEGRATION.md`:

**Phase 1 (Current)**: Human-driven with agent assistance
- Agent provides diagnosis
- Human edits boost queries
- Human runs evaluations
- Agent validates no regressions

**Phase 2 (Future)**: Agent-driven with human oversight
- Agent diagnoses
- Agent suggests changes (LLM)
- Human approves changes
- Agent applies changes
- Agent validates
- Agent creates PR
- Human reviews and merges

## Development Roadmap

### Phase 2.1: LLM Integration (Next)

**Goal**: Add AI-powered code analysis and suggestions

**Tasks**:
1. Add `pydantic-ai` dependency to pyproject.toml
2. Implement `suggest_boost_query_changes()` method
3. Implement `suggest_prompt_changes()` method
4. Add configuration for Claude model selection

**Estimated effort**: 2-3 hours

### Phase 2.2: Code Editing (After 2.1)

**Goal**: Automated file modification with safety checks

**Tasks**:
1. Implement AST-based boost query editing
2. Add backup/rollback mechanism
3. Implement dry-run mode
4. Add validation of changes before applying

**Estimated effort**: 3-4 hours

### Phase 2.3: Iteration Loop (After 2.2)

**Goal**: Fully autonomous fixing with human oversight

**Tasks**:
1. Implement retrieval iteration loop
2. Implement answer iteration loop
3. Add progress tracking
4. Add early stopping when metrics plateau

**Estimated effort**: 2-3 hours

### Phase 2.4: Regression Testing (After 2.3)

**Goal**: Multi-suite validation with baseline comparison

**Tasks**:
1. Implement baseline storage
2. Add multi-suite comparison
3. Add regression detection with thresholds
4. Generate regression reports

**Estimated effort**: 2-3 hours

### Phase 2.5: Git Automation (Final)

**Goal**: Automated commit and PR creation

**Tasks**:
1. Implement commit message generation
2. Add git hooks integration
3. Implement PR creation via `gh` CLI
4. Add PR description with metrics

**Estimated effort**: 1-2 hours

**Total estimated effort**: 10-15 hours

## Testing the Agent

```bash
# Test diagnosis (works now)
python scripts/okp_mcp_agent.py diagnose RSPEED-2482

# Test with a ticket that should pass
python scripts/okp_mcp_agent.py diagnose RSPEED-2481

# Test validation (partially implemented)
python scripts/okp_mcp_agent.py validate
```

## Troubleshooting

### Agent can't find evaluation output

**Problem**: `RuntimeError: No evaluation output found`

**Solution**: Ensure you've run at least one evaluation manually first:
```bash
./run_okp_mcp_full_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_full.yaml \
  --runs 1
```

### Agent can't parse CSV

**Problem**: `KeyError` or `ValueError` when parsing results

**Solution**: Check that the CSV has the expected columns:
```bash
head -1 okp_mcp_full_output/suite_*/run_001/evaluation_*_detailed.csv
```

### okp-mcp restart fails

**Problem**: `podman-compose: command not found`

**Solution**: Ensure lscore-deploy is set up and podman-compose is in PATH:
```bash
cd ~/Work/lscore-deploy/local
which podman-compose
```

## Contributing

When extending the agent, follow these principles:

1. **Fail-safe**: Always validate before making destructive changes
2. **Observable**: Log all actions clearly
3. **Reversible**: Implement rollback for file changes
4. **Testable**: Add dry-run modes for testing
5. **Explainable**: Generate human-readable reports

## References

- [OKP_MCP_INTEGRATION.md](OKP_MCP_INTEGRATION.md) - Dual-mode testing workflow
- [okp-mcp INCORRECT_ANSWER_LOOP.md](https://github.com/RedHatInsights/okp-mcp/blob/main/INCORRECT_ANSWER_LOOP.md) - Manual workflow this automates
- [Pydantic AI Documentation](https://ai.pydantic.dev/) - For Phase 2 LLM integration

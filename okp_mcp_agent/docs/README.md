# OKP-MCP Agent API Guide

Comprehensive API documentation for reusable classes in the okp-mcp agent work. These classes will eventually become a proper API when migrated to the `okp-mcp` project.

---

## Quick Navigation

### Core Agent Classes

| Class | Purpose | When to Use |
|-------|---------|-------------|
| **[OkpMcpAgent](OkpMcpAgent.md)** | Main autonomous agent for fixing RSPEED tickets | Single ticket diagnosis and fixes |
| **[PatternFixAgent](PatternFixAgent.md)** | Pattern-based batch ticket fixing | Fixing groups of 6-15 similar tickets |
| **[OkpMcpLLMAdvisor](OkpMcpLLMAdvisor.md)** | AI-powered suggestion engine | Getting intelligent Solr/prompt suggestions |

### Data Models

| Class | Purpose | When to Use |
|-------|---------|-------------|
| **[EvaluationResult](EvaluationResult.md)** | Evaluation metrics container | Reading diagnosis results, problem classification |
| **[APIResponse](APIResponse.md)** | Raw API response model | Building test caches, API integration |
| **[TurnData](TurnData.md)** | Evaluation framework data | Developing metrics, writing evaluations |

### Utility Classes

| Class | Purpose | Documentation |
|-------|---------|---------------|
| **SolrConfigAnalyzer** | Solr explain output and tuning | _(Coming soon)_ |
| **SolrDocumentChecker** | Solr document validation | _(Coming soon)_ |
| **MetricSummary** | Metrics package for LLM analysis | See [OkpMcpLLMAdvisor](OkpMcpLLMAdvisor.md) |

---

## Getting Started

### 1. For Single Ticket Fixes

Start with **OkpMcpAgent**:

```python
from pathlib import Path
from scripts.okp_mcp_agent import OkpMcpAgent

# Initialize agent
agent = OkpMcpAgent(
    eval_root=Path.cwd(),
    okp_mcp_root=Path.cwd().parent / "okp-mcp",
    lscore_deploy_root=Path.cwd().parent / "lscore-deploy",
)

# Diagnose ticket
result = agent.diagnose("RSPEED-2482")

# Check problem type and fix
if result.is_retrieval_problem:
    agent.fix_ticket("RSPEED-2482")
```

**Read:** [OkpMcpAgent API Guide](OkpMcpAgent.md)

---

### 2. For Pattern-Based Batch Fixes

Use **PatternFixAgent**:

```python
from scripts.run_pattern_fix_poc import PatternFixAgent

# Initialize for specific pattern
agent = PatternFixAgent(
    pattern_id="RHEL10_DEPRECATED_FEATURES",
    eval_root=Path.cwd(),
    okp_mcp_root=Path.cwd().parent / "okp-mcp",
    lscore_deploy_root=Path.cwd().parent / "lscore-deploy",
)

# Load pattern tickets and run fix loop
agent.load_pattern_tickets(Path("config/patterns_v2"))
result = agent.run_fix_loop(max_iterations=15)
```

**Read:** [PatternFixAgent API Guide](PatternFixAgent.md)

---

### 3. For AI-Powered Suggestions

Use **OkpMcpLLMAdvisor**:

```python
import asyncio
from scripts.okp_mcp_llm_advisor import OkpMcpLLMAdvisor, MetricSummary

async def main():
    # Initialize advisor
    advisor = OkpMcpLLMAdvisor(
        model="claude-sonnet-4-6",
        use_tiered_models=True,
    )
    
    # Prepare metrics
    metrics = MetricSummary(
        ticket_id="RSPEED-2482",
        query="What DHCP server in RHEL 10?",
        url_f1=0.33,
        context_relevance=0.45,
        # ... more metrics
    )
    
    # Get AI suggestion
    suggestion = await advisor.suggest_boost_query_changes(metrics)
    print(f"Suggestion: {suggestion.suggested_change}")

asyncio.run(main())
```

**Read:** [OkpMcpLLMAdvisor API Guide](OkpMcpLLMAdvisor.md)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                 OkpMcpAgent                         │
│  - diagnose()                                       │
│  - fix_ticket()                                     │
│  - query_solr_direct()                              │
│  - validate_all_suites()                            │
└──────────────┬──────────────────────────────────────┘
               │ extends
               │
               ▼
┌─────────────────────────────────────────────────────┐
│              PatternFixAgent                        │
│  - load_pattern_tickets()                           │
│  - run_fix_loop()                                   │
│  - Phase 1: Baseline                                │
│  - Phase 2A: Solr Optimization (fast)               │
│  - Phase 2B: Answer Validation (full)               │
│  - Phase 3: Stability Check                         │
└─────────────────────────────────────────────────────┘

Uses ↓

┌─────────────────────────────────────────────────────┐
│            OkpMcpLLMAdvisor                         │
│  - suggest_boost_query_changes()                    │
│  - suggest_prompt_changes()                         │
│  - classify_problem_complexity()                    │
│  - Tiered routing: Haiku → Sonnet → Opus           │
└─────────────────────────────────────────────────────┘

Produces ↓

┌─────────────────────────────────────────────────────┐
│            EvaluationResult                         │
│  - Metrics: url_f1, context_relevance, etc.         │
│  - Problem classification                           │
│  - RAG usage tracking                               │
│  - Grounding validation                             │
└─────────────────────────────────────────────────────┘
```

---

## Common Workflows

### Workflow 1: Diagnose → Classify → Fix

```python
# 1. Diagnose
result = agent.diagnose("RSPEED-2482")

# 2. Classify problem type
if result.is_answer_good_enough:
    print("✅ Already good enough")
elif result.is_retrieval_problem:
    print("🔍 Retrieval problem → Fix Solr")
elif result.is_answer_problem:
    print("💬 Answer problem → Fix prompt")

# 3. Fix
agent.fix_ticket("RSPEED-2482", max_iterations=5)
```

### Workflow 2: Fast Solr Loop

```python
# 1. Get baseline
baseline = agent.diagnose_retrieval_only("RSPEED-2482")

# 2. Fast Solr iteration (5s per iteration)
for i in range(10):
    current = agent.query_solr_direct(
        query=baseline.query,
        expected_urls=baseline.expected_urls,
    )
    
    if current['url_f1'] >= baseline['url_f1'] + 0.02:
        print(f"✅ Improvement: {current['url_f1']:.2f}")
        break

# 3. Validate with full evaluation
final = agent.diagnose("RSPEED-2482")
```

### Workflow 3: Pattern Fix with Stability

```python
# 1. Initialize pattern agent
agent = PatternFixAgent("RHEL10_DEPRECATED_FEATURES", ...)
agent.load_pattern_tickets(Path("config/patterns_v2"))

# 2. Run complete fix loop (all phases)
result = agent.run_fix_loop(
    max_iterations=15,
    stability_runs=5,
)

# 3. Check results
if result.success:
    print(f"✅ Fixed {result.tickets_tested} tickets")
    print(f"   Review: {result.diagnostics_dir}/REVIEW_REPORT.md")
```

---

## Key Concepts

### Problem Classification

**EvaluationResult** provides three classification properties:

```python
if result.is_answer_good_enough:
    # Answer is correct and grounded → Done
    pass

elif result.is_retrieval_problem:
    # Retrieval metrics poor → Fix Solr boost queries
    # Route to: fast_retrieval_loop() or suggest_boost_query_changes()
    pass

elif result.is_answer_problem:
    # Retrieval good, answer poor → Fix system prompt
    # Route to: suggest_prompt_changes()
    pass
```

**Prioritization:**
1. `context_relevance` (most reliable) > `url_f1` (unreliable)
2. `faithfulness` checks grounding (prevents hallucination)
3. `answer_correctness` is primary success metric

---

### Fast Loop vs Full Loop

| Aspect | Fast Loop | Full Loop |
|--------|-----------|-----------|
| **Method** | `query_solr_direct()` | `diagnose()` |
| **Speed** | ~5s per iteration | ~30s per iteration |
| **Metrics** | URL F1, MRR, Precision@5, Recall@5 | All metrics (retrieval + answer) |
| **Cost** | $0 (no LLM) | ~$0.01 per ticket |
| **Use Case** | Solr tuning iteration | Final validation |

**Pattern Fix Phases:**
- **Phase 2A** (Solr Optimization): Fast loop
- **Phase 2B** (Answer Validation): Full loop

---

### Tiered Model Routing

**OkpMcpLLMAdvisor** optimizes costs with model routing:

```
┌──────────────┐
│ Problem      │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────┐
│ Haiku: Classify complexity   │  ~$0.0001
└──────┬───────────────────────┘
       │
       ├─── Simple ──────────────── Manual heuristics
       │
       ├─── Medium ──────────────── Sonnet (~$0.01)
       │
       └─── Complex ─────────────── Opus (~$0.10)
```

**Enable:**
```python
advisor = OkpMcpLLMAdvisor(use_tiered_models=True)
```

---

### Stability Validation

**PatternFixAgent** requires stability check (Phase 3):

```python
# Run 5 times to detect variance
result = agent.diagnose("RSPEED-2482", runs=5)

if result.high_variance_metrics:
    print(f"⚠️  Unstable: {result.high_variance_metrics}")
    # Escalate to docs/VARIANCE_SOLUTIONS.md
else:
    print("✅ Stable results")
```

**Variance Threshold:** `>= 0.05` (5%) triggers escalation

---

## Environment Setup

### Required Environment Variables

```bash
# For Gemini evaluation LLM
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

# For Claude advisor (optional)
export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id
gcloud auth application-default login

# For API evaluation (optional)
export API_KEY=your-lightspeed-api-key
```

### Check Environment

```python
# Check agent environment
if agent.check_environment():
    print("✅ Environment ready")

# Check LLM advisor availability
from scripts.okp_mcp_llm_advisor import LLM_ADVISOR_AVAILABLE
if LLM_ADVISOR_AVAILABLE:
    print("✅ LLM advisor available")
```

---

## Performance & Costs

### Typical Pattern Fix (3 tickets)

| Phase | Duration | Cost |
|-------|----------|------|
| Baseline | ~90s | ~$0.03 |
| Solr Optimization (10 iter) | ~50s | $0 |
| Answer Validation | ~90s | ~$0.03 |
| Stability Check (5 runs) | ~450s | ~$0.15 |
| **Total** | **~11 min** | **~$0.21** |

### Single Ticket Fix

| Operation | Duration | Cost |
|-----------|----------|------|
| Diagnose (1 run) | ~30s | ~$0.01 |
| Fast Solr loop (10 iter) | ~50s | $0 |
| LLM suggestion (Sonnet) | ~5s | ~$0.01 |
| Validation | ~5 min | ~$0.20 |
| **Total** | **~6 min** | **~$0.22** |

**Cost Optimization:**
- Enable tiered routing: `-90% on classification`
- Use fast loop for Solr: `$0 vs $0.01/iter`
- Cache suggestions: Reuse for similar problems

---

## Debugging

### Common Issues

| Problem | Check | Fix |
|---------|-------|-----|
| Environment variables missing | `agent.check_environment()` | Set `GOOGLE_APPLICATION_CREDENTIALS` |
| LLM advisor not available | `LLM_ADVISOR_AVAILABLE` | Set `ANTHROPIC_VERTEX_PROJECT_ID` |
| Solr not accessible | `agent.solr_checker.is_available()` | Start containers: `podman-compose up -d` |
| No metrics found | `result.has_metrics` | Re-run evaluation |
| URL F1 is 0 but answer correct | Check `context_relevance` instead | URL F1 unreliable, use context metrics |

### Diagnostic Outputs

All diagnostics saved to `.diagnostics/{ticket_id}/`:

```
.diagnostics/RSPEED-2482/
├── ticket_config.yaml          # Single-ticket eval config
├── iteration_*_diagnostics.json # Metrics per iteration
├── iteration_summary.csv        # Summary table
└── solr_config_snapshot.json    # Solr config snapshots
```

---

## Migration Path

This API guide documents classes currently in `lightspeed-evaluation` that will migrate to `okp-mcp`:

### Current Location
```
lightspeed-evaluation/
└── scripts/
    ├── okp_mcp_agent.py           # OkpMcpAgent, EvaluationResult
    ├── run_pattern_fix_poc.py     # PatternFixAgent
    └── okp_mcp_llm_advisor.py     # OkpMcpLLMAdvisor
```

### Future Location (Target)
```
okp-mcp/
└── src/okp_mcp/
    └── agent/
        ├── __init__.py
        ├── core.py                 # OkpMcpAgent
        ├── pattern.py              # PatternFixAgent
        ├── advisor.py              # OkpMcpLLMAdvisor
        └── models.py               # EvaluationResult, etc.
```

**Timeline:** After pattern fix POC validation

---

## Contributing

### Adding New Methods to Documented Classes

When adding new methods:

1. **Add to class implementation** (e.g., `okp_mcp_agent.py`)
2. **Update API guide** (e.g., `OkpMcpAgent.md`)
   - Add method signature
   - Add usage example
   - Add to relevant workflow section
3. **Update this README** if it affects common workflows

### Creating New Class Documentation

Follow the template from existing guides:

```markdown
# ClassName Reference

## Overview
- What it does
- Where it lives
- Purpose

## When You'll Interact With It
- Table of scenarios

## Class Definition

## Methods
- Signature
- Parameters
- Usage examples

## Common Patterns

## Debugging Tips

## Related Classes

## Summary
```

---

## Related Documentation

### Design Specs
- `docs/PATTERN_FIX_LOOP_SPEC.md` - Pattern fix loop design
- `docs/VARIANCE_SOLUTIONS.md` - Stability troubleshooting
- `docs/OPTIMIZATION_OPPORTUNITIES.md` - Future improvements

### Project Docs
- `README.md` - Project overview
- `AGENTS.md` - AI agent guidelines
- `docs/` - User guides

---

## Quick Reference Card

```python
# --- SINGLE TICKET FIX ---
from scripts.okp_mcp_agent import OkpMcpAgent

agent = OkpMcpAgent(eval_root, okp_mcp_root, lscore_deploy_root)
result = agent.diagnose("RSPEED-2482")

if result.is_retrieval_problem:
    agent.fix_ticket("RSPEED-2482")

# --- PATTERN BATCH FIX ---
from scripts.run_pattern_fix_poc import PatternFixAgent

agent = PatternFixAgent("RHEL10_DEPRECATED_FEATURES", ...)
agent.load_pattern_tickets(Path("config/patterns_v2"))
result = agent.run_fix_loop(max_iterations=15)

# --- AI SUGGESTIONS ---
from scripts.okp_mcp_llm_advisor import OkpMcpLLMAdvisor

advisor = OkpMcpLLMAdvisor(use_tiered_models=True)
suggestion = await advisor.suggest_boost_query_changes(metrics)

# --- FAST SOLR LOOP ---
current = agent.query_solr_direct(query, expected_urls)
print(f"URL F1: {current['url_f1']:.2f}")

# --- PROBLEM CLASSIFICATION ---
if result.is_answer_good_enough:
    pass  # Done
elif result.is_retrieval_problem:
    pass  # Fix Solr
elif result.is_answer_problem:
    pass  # Fix prompt
```

---

**Questions? Issues?**
- File issues at: https://github.com/anthropics/claude-code/issues (for Claude Code questions)
- See project README for project-specific questions

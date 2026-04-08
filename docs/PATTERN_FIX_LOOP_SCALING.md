# Pattern Fix Loop Scaling - Multi-Agent Architecture

## Overview

This document outlines the scaling strategy for the pattern fix loop beyond the POC, focusing on **multi-agent architecture with dynamic loading** to manage context window size and enable parallelization.

**Problem:** As patterns grow larger (10-20+ tickets) and iteration history accumulates (100+ attempts), a single-agent approach leads to:
- Context window bloat (12K+ tokens)
- Slower processing (sequential only)
- Reduced agent effectiveness (too much irrelevant context)

**Solution:** Decompose into specialized agents that load only what they need, when they need it.

---

## Current POC Architecture (Phase 1)

### Single Agent with Growing Context

```python
class PatternFixAgent:
    """Single agent accumulates all context."""
    
    def run_pattern_fix(self, pattern_id):
        baseline = self.run_baseline()          # +2K tokens
        optimization = self.optimize()          # +5K tokens (iteration history grows)
        answer_check = self.validate_answer()   # +2K tokens
        stability = self.check_stability()      # +3K tokens (multiple runs)
        
        # Total: ~12K tokens in context by end
        # All phases see all data (wasteful)
```

**Characteristics:**
- ✅ Simple to implement
- ✅ Validates concept
- ✅ Works for small patterns (3-5 tickets)
- ❌ Context grows with iterations
- ❌ Sequential processing only
- ❌ Can't scale to large patterns

---

## Production Architecture (Phase 2-4)

### Phase 2: Multi-Agent Specialists (Same Pattern Size)

**Goal:** Improve iteration quality with specialized agents

```python
class PatternCoordinator:
    """Lightweight coordinator - routes to specialists."""
    
    def run_pattern_fix(self, pattern_id):
        # Load minimal metadata
        pattern_meta = self.load_pattern_metadata(pattern_id)
        # → Just: pattern_id, ticket_count, representative_ticket_id
        
        # 1. Baseline Agent (Fresh Context)
        baseline_agent = Agent(
            subagent_type="pattern-baseline",
            prompt=f"""
            Run full baseline evaluation for pattern {pattern_id}.
            Representative ticket: {pattern_meta['rep_ticket']}
            Save results to: .diagnostics/{pattern_id}/baseline.json
            """
        )
        baseline = baseline_agent.run()
        
        # 2. Route to Specialist (Fresh Context)
        specialist = self._get_specialist(baseline.problem_type)
        improvement = specialist.run()
        
        # 3. Validator (Fresh Context)
        validator = Agent(
            subagent_type="pattern-validator",
            prompt=f"""
            Validate fixes for pattern {pattern_id}.
            Read changes from: .diagnostics/{pattern_id}/changes.json
            Test representative ticket: {pattern_meta['rep_ticket']}
            """
        )
        validation = validator.run()
        
        # 4. Variance Analyzer (Fresh Context, if needed)
        if validation.has_high_variance:
            variance_agent = self._create_variance_analyzer(pattern_id)
            variance_fix = variance_agent.run()
    
    def _get_specialist(self, problem_type):
        """Route to appropriate specialist."""
        if problem_type == "RETRIEVAL":
            return Agent(
                subagent_type="solr-expert",
                prompt=self._load_solr_expert_prompt()
            )
        elif problem_type == "ANSWER":
            return Agent(
                subagent_type="prompt-expert",
                prompt=self._load_prompt_expert_prompt()
            )
```

**Specialist Agents:**

#### Solr Expert
```python
class SolrExpert(Agent):
    """Specialist for Solr configuration optimization."""
    
    def suggest_improvements(self, pattern_id):
        # Load only Solr-relevant context
        solr_config = self.read_file("okp-mcp/src/okp_mcp/solr.py")
        
        # Load only Solr-related iteration history
        past_attempts = self.load_history(
            pattern_id=pattern_id,
            filter_type="BoostQuerySuggestion"
        )
        
        # Load Solr documentation (only when needed)
        solr_docs = self.load_reference_docs("solr_edismax.md")
        
        # Make suggestion with focused context (~4K tokens)
        suggestion = self.llm.call(f"""
        Improve Solr retrieval for pattern {pattern_id}.
        
        Current config:
        {solr_config}
        
        Past Solr changes (last 5):
        {past_attempts[-5:]}
        
        Solr eDisMax reference:
        {solr_docs}
        
        Suggest next boost query change.
        """)
        
        return suggestion
```

#### Prompt Expert
```python
class PromptExpert(Agent):
    """Specialist for system prompt optimization."""
    
    def suggest_improvements(self, pattern_id):
        # Load only prompt-relevant context
        system_prompt = self.read_file("okp-mcp/src/okp_mcp/system_prompt.txt")
        
        # Load only prompt-related iteration history
        past_attempts = self.load_history(
            pattern_id=pattern_id,
            filter_type="PromptSuggestion"
        )
        
        # Load example prompts
        prompt_patterns = self.load_reference_docs("prompt_patterns.md")
        
        # Make suggestion with focused context (~4K tokens)
        suggestion = self.llm.call(f"""
        Improve system prompt for pattern {pattern_id}.
        
        Current prompt:
        {system_prompt}
        
        Past prompt changes (last 5):
        {past_attempts[-5:]}
        
        Prompt engineering patterns:
        {prompt_patterns}
        
        Suggest prompt modification.
        """)
        
        return suggestion
```

**Benefits:**
- ✅ Each agent starts with fresh context (~3-4K tokens)
- ✅ Specialists have deeper domain knowledge
- ✅ Better iteration suggestions (focused expertise)
- ✅ Still simple (no parallelization yet)
- ❌ Still sequential processing
- ❌ Still limited to small patterns

---

### Phase 3: Dynamic Loading + Parallelization (Scale to 10-15 tickets)

**Goal:** Scale to medium patterns with parallel validation

```python
class PatternCoordinator:
    """Coordinator with parallel validation."""
    
    def run_pattern_fix(self, pattern_id):
        # 1. Baseline on representative ticket (same as Phase 2)
        baseline = self._run_baseline(pattern_id)
        
        # 2. Optimization on representative ticket (same as Phase 2)
        improvement = self._run_specialist(baseline, pattern_id)
        
        # 3. Parallel validation across ALL tickets
        pattern_tickets = self.load_pattern_tickets(pattern_id)
        
        # Launch parallel validators (one per ticket)
        validators = [
            Agent(
                subagent_type="ticket-validator",
                prompt=f"""
                Validate ticket {ticket.id} with current changes.
                
                Load ticket data from: config/patterns_v2/{pattern_id}.yaml
                Load current changes from: .diagnostics/{pattern_id}/changes.json
                
                Run full evaluation and save to:
                .diagnostics/{pattern_id}/ticket_{ticket.id}_validation.json
                """,
                run_in_background=True
            )
            for ticket in pattern_tickets
        ]
        
        # Wait for all validators to complete
        validation_results = [v.get_result() for v in validators]
        
        # 4. Aggregate results (Fresh Context)
        aggregator = Agent(
            subagent_type="pattern-aggregator",
            prompt=f"""
            Aggregate validation results for pattern {pattern_id}.
            
            Read validation results from:
            .diagnostics/{pattern_id}/ticket_*_validation.json
            
            Calculate:
            - Pattern pass rate (how many tickets pass?)
            - Per-metric averages
            - Failure analysis
            
            Save to: .diagnostics/{pattern_id}/pattern_report.json
            """
        )
        
        report = aggregator.run()
        
        return report
```

**External Storage Pattern:**

```python
# Instead of passing large data in prompts
iteration_history = [...]  # Could be 100+ iterations × 500 tokens each = 50K tokens!

# Save to file
save_json(f".diagnostics/{pattern_id}/iteration_history.json", iteration_history)

# Agent loads only what it needs
agent_prompt = f"""
Read iteration history from:
.diagnostics/{pattern_id}/iteration_history.json

Focus on:
- Last 5 iterations (most recent attempts)
- Iterations where URL F1 improved by >0.1 (successful patterns)

Identify what worked and suggest next change.
"""
```

**Benefits:**
- ✅ Parallel ticket validation (10x faster for 10-ticket pattern)
- ✅ Context stays small (each agent ~3-5K tokens)
- ✅ Scales to 10-15 ticket patterns
- ✅ External storage prevents context bloat
- ❌ More complex coordination
- ❌ Need to manage file I/O carefully

**Performance Example:**
```
POC (Sequential):
  Representative baseline: 60s
  Optimization (10 iter): 200s
  Validate 10 tickets: 10 × 60s = 600s
  Total: ~14.5 minutes

Phase 3 (Parallel):
  Representative baseline: 60s
  Optimization (10 iter): 200s
  Validate 10 tickets: 60s (in parallel!)
  Total: ~5.5 minutes
```

---

### Phase 4: Cross-Pattern Learning (Scale to 20+ tickets)

**Goal:** Large patterns + learning from other patterns

```python
class CrossPatternLearner(Agent):
    """Learns from successful fixes across all patterns."""
    
    def suggest_improvement(self, pattern_id):
        # 1. Load current pattern metadata (minimal)
        current_pattern = self.load_pattern_metadata(pattern_id)
        
        # 2. Find similar patterns (by problem type)
        similar_patterns = self.find_similar_patterns(
            problem_type=current_pattern.problem_type,
            limit=3
        )
        
        # 3. Load only successful changes from similar patterns
        successful_changes = []
        for similar_id in similar_patterns:
            history = self.load_history(similar_id)
            # Only load changes that improved metrics by >0.2
            successful_changes.extend([
                change for change in history
                if change.metric_improvement > 0.2
            ])
        
        # 4. Make suggestion based on cross-pattern learning
        suggestion = self.llm.call(f"""
        Improve pattern {pattern_id}.
        Problem type: {current_pattern.problem_type}
        
        Similar patterns that were fixed successfully:
        {similar_patterns}
        
        Changes that worked for similar patterns:
        {successful_changes}
        
        Suggest a change for this pattern based on what worked elsewhere.
        """)
        
        return suggestion
```

**Pattern Knowledge Base:**

```python
# Store pattern metadata for cross-pattern learning
pattern_knowledge = {
    "INCORRECT_BOOT_FIRMWARE": {
        "problem_type": "RETRIEVAL",
        "tickets": 6,
        "successful_changes": [
            {"type": "BoostQuery", "change": "Boost uefi by 1.5", "improvement": 0.3},
            {"type": "BoostQuery", "change": "Add pf for 'secure boot'", "improvement": 0.2}
        ],
        "final_f1": 0.85,
        "iterations": 8
    },
    "RHEL10_DEPRECATED_FEATURES": {
        "problem_type": "RETRIEVAL",
        "tickets": 3,
        "successful_changes": [
            {"type": "BoostQuery", "change": "Boost rhel-10 by 2.0", "improvement": 0.4}
        ],
        "final_f1": 0.78,
        "iterations": 5
    }
}

# When fixing a new RETRIEVAL pattern, load successful changes from other RETRIEVAL patterns
```

**Benefits:**
- ✅ Learn from past successes
- ✅ Faster convergence (skip known failures)
- ✅ Works for large patterns (20+ tickets)
- ✅ Builds institutional knowledge
- ❌ Complex coordination
- ❌ Need pattern similarity detection

---

## Context Window Optimization Strategies

### 1. Incremental Loading

Load data only when needed:

```python
# Bad: Load everything upfront
all_tickets = load_all_tickets(pattern_id)  # 20 tickets × 1K tokens = 20K!
all_history = load_all_history(pattern_id)  # 100 iterations × 500 tokens = 50K!

# Good: Load incrementally
representative_ticket = load_representative_ticket(pattern_id)  # 1K tokens
recent_history = load_history(pattern_id, last_n=5)            # 2.5K tokens
```

### 2. Summarization

Compress large data:

```python
# Bad: Pass full iteration history
iteration_history = [
    {"iteration": 1, "change": "...", "before": 0.2, "after": 0.35, ...},
    {"iteration": 2, "change": "...", "before": 0.35, "after": 0.32, ...},
    # ... 100 more iterations
]  # 50K tokens

# Good: Summarize
iteration_summary = """
ITERATION SUMMARY (100 iterations):
- Successful changes (5): Boost uefi by 1.5 (+0.3), Add pf for 'secure boot' (+0.2), ...
- Failed patterns: Increasing mm too high (tried 3 times, all failed)
- Current F1: 0.85 (started at 0.2)
"""  # 500 tokens
```

### 3. External References

Store large data externally:

```python
# Agent prompt includes reference, not data
prompt = f"""
Suggest Solr improvements for pattern {pattern_id}.

Configuration file: okp-mcp/src/okp_mcp/solr.py (read with Read tool)
Iteration history: .diagnostics/{pattern_id}/history.json (read with Read tool)
Solr documentation: docs/solr_edismax_reference.md (read with Read tool)

Current metrics: {current_metrics}  # Only inline the small, critical data

Suggest next change.
"""
```

### 4. Agent Specialization

Each agent loads only its domain:

| Agent Type | Context Size | What It Loads |
|------------|--------------|---------------|
| Baseline Agent | ~3K tokens | Pattern metadata, representative ticket |
| Solr Expert | ~4K tokens | Solr config, Solr docs, Solr-related history |
| Prompt Expert | ~4K tokens | System prompt, prompt patterns, prompt-related history |
| Validator | ~2K tokens | Ticket data, expected metrics |
| Aggregator | ~3K tokens | Validation summaries (not full results) |
| Variance Analyzer | ~3K tokens | Stability run summaries, variance diagnostics |

**Total context (sequential):** ~19K tokens spread across 6 agents
**vs. POC (single agent):** ~19K tokens in one agent (approaches context limit)

---

## Implementation Roadmap

### Phase 1: POC (Current) ✅
**Timeline:** Week 1
**Pattern Size:** 3-5 tickets
**Architecture:** Single agent
**Parallelization:** None
**Goal:** Prove concept works

**Implementation:**
- ✅ Single `PatternFixAgent` class
- ✅ All phases in one agent
- ✅ Sequential processing
- ✅ Small patterns only

**Success Criteria:**
- Completes without crashing
- Shows metric improvement
- Generates review report

---

### Phase 2: Multi-Agent Specialists
**Timeline:** Weeks 2-3
**Pattern Size:** 3-5 tickets (same)
**Architecture:** Coordinator + Specialists
**Parallelization:** None
**Goal:** Improve iteration quality

**Implementation:**
- [ ] Create `PatternCoordinator` class
- [ ] Implement `SolrExpert` agent
- [ ] Implement `PromptExpert` agent
- [ ] Implement `PatternValidator` agent
- [ ] Implement `VarianceAnalyzer` agent
- [ ] External storage for iteration history

**Success Criteria:**
- Better suggestions (specialist knowledge)
- Context per agent < 5K tokens
- Same or better results than POC

---

### Phase 3: Parallel Validation + Dynamic Loading
**Timeline:** Weeks 4-5
**Pattern Size:** 10-15 tickets
**Architecture:** Coordinator + Specialists + Parallel Validators
**Parallelization:** Ticket validation
**Goal:** Scale to medium patterns

**Implementation:**
- [ ] Parallel ticket validation
- [ ] External storage pattern
- [ ] Incremental loading utilities
- [ ] Summarization for iteration history
- [ ] Pattern aggregation logic

**Success Criteria:**
- Successfully fix 10-15 ticket patterns
- 5-10x speedup from parallelization
- Context per agent < 5K tokens
- Total time < 10 minutes per pattern

---

### Phase 4: Cross-Pattern Learning
**Timeline:** Weeks 6-8
**Pattern Size:** 20+ tickets
**Architecture:** Full multi-agent with knowledge base
**Parallelization:** Ticket validation + optimization strategies
**Goal:** Scale to large patterns + learn from history

**Implementation:**
- [ ] Pattern knowledge base
- [ ] Cross-pattern similarity detection
- [ ] Successful change extraction
- [ ] Pattern metadata tracking
- [ ] Parallel optimization strategies

**Success Criteria:**
- Successfully fix 20+ ticket patterns
- Faster convergence (learn from past patterns)
- Pattern knowledge base grows over time
- Total time < 15 minutes per pattern

---

## Cost and Performance Estimates

### Phase 1 (POC)
- Pattern size: 3 tickets
- Time: ~10 minutes
- API calls: ~15 (baseline + 10 optimization + answer + 3 stability)
- Cost: ~$0.15 per pattern
- Context per agent: 3-12K tokens (grows)

### Phase 2 (Specialists)
- Pattern size: 3 tickets
- Time: ~8 minutes (better suggestions)
- API calls: ~12 (fewer iterations needed)
- Cost: ~$0.12 per pattern
- Context per agent: 3-5K tokens (stable)

### Phase 3 (Parallel)
- Pattern size: 10 tickets
- Time: ~6 minutes (parallel validation)
- API calls: ~25 (baseline + 10 optimization + 10 parallel validations + 3 stability)
- Cost: ~$0.25 per pattern
- Context per agent: 3-5K tokens (stable)

### Phase 4 (Cross-Pattern)
- Pattern size: 20 tickets
- Time: ~10 minutes (faster convergence from learning)
- API calls: ~30 (baseline + 5 optimization + 20 parallel validations + 3 stability)
- Cost: ~$0.30 per pattern
- Context per agent: 3-5K tokens (stable)

---

## References

- Pattern Fix Loop Spec: `docs/PATTERN_FIX_LOOP_SPEC.md`
- Test Plan: `docs/PATTERN_FIX_LOOP_TEST_PLAN.md`
- Variance Solutions: `docs/VARIANCE_SOLUTIONS.md`
- POC Implementation: `scripts/run_pattern_fix_poc.py`

# Optimization Opportunities & Agentic Workflow Improvements

**Created:** 2026-04-03
**Purpose:** Document performance bottlenecks, parallelization opportunities, and advanced agentic workflows for the OKP-MCP Agent

---

## Table of Contents
1. [Current Bottlenecks](#current-bottlenecks)
2. [Parallelization Opportunities](#parallelization-opportunities)
3. [Caching & Memoization](#caching--memoization)
4. [Advanced Agentic Workflows](#advanced-agentic-workflows)
5. [Infrastructure Improvements](#infrastructure-improvements)
6. [Experimentation Roadmap](#experimentation-roadmap)

---

## Current Bottlenecks

### 1. Container Restarts (⏱️ ~10-20 sec each)
**Location:** `restart_okp_mcp()` - called after every code change

```python
# Current: Sequential restart with health check
restart_okp_mcp()  # 5s sleep + health check polling
```

**Impact:**
- ~10-20 seconds per iteration
- 20 iterations = 3-6 minutes just waiting for restarts
- Blocks all other work during health check

**Optimization Ideas:**
- **Hot reload**: Patch Solr config without container restart
- **Async health checks**: Continue other work while waiting
- **Batch changes**: Apply multiple changes before restarting
- **Container pooling**: Keep multiple containers with different configs

---

### 2. Sequential Ticket Processing
**Location:** `main()` batch mode - processes tickets one at a time

```python
for ticket_id in ticket_ids:
    agent.fix_ticket_multi_stage(ticket_id)  # Blocks until complete
```

**Impact:**
- 5 tickets × 45 min/ticket = 3.75 hours sequential
- CPU/LLM idle during container restarts
- No shared learning between tickets

**Optimization Ideas:**
- **Parallel worktrees**: Each ticket gets isolated git worktree + container
- **Task queue**: Distribute tickets across multiple agents
- **Shared learnings**: Extract patterns from fixed tickets to inform remaining ones

---

### 3. Single-Threaded LLM Calls
**Location:** `_get_llm_suggestion_object()` - sequential API calls

```python
# Current: One suggestion at a time
suggestion = advisor.get_suggestion(...)  # Blocks 5-10 seconds
```

**Impact:**
- 10 iterations × 5 sec/LLM call = 50 seconds waiting for LLM
- API has rate limits, but we're not approaching them
- Could generate multiple hypotheses in parallel

**Optimization Ideas:**
- **Parallel suggestions**: Generate N suggestions simultaneously, pick best
- **Streaming**: Use streaming API to show thinking in real-time
- **Speculative execution**: Generate next suggestion while testing current
- **Batch prompts**: Ask for top 3 changes in one call

---

### 4. Full Evaluation Overhead (⏱️ ~30 sec/run)
**Location:** `diagnose()` - runs full eval every iteration

```python
# Current: Full eval with LLM judges
output_dir = self.run_full_eval(config, runs=1)  # 30 seconds
```

**Impact:**
- 30 seconds × 20 iterations = 10 minutes in evaluation
- 90% of time is LLM judging (answer_correctness, faithfulness)
- Retrieval metrics could be computed in <5 seconds

**Optimization Ideas:**
- ✅ **ALREADY IMPLEMENTED**: `fast_retrieval_loop()` - direct Solr queries
- **Incremental evaluation**: Only re-judge changed aspects
- **Parallel LLM judges**: Run all metrics concurrently
- **Cached judgments**: Reuse if context unchanged

---

### 5. Git Operations
**Location:** Various - git add, commit, restore scattered throughout

```python
# Current: Many small git commands
subprocess.run(["git", "add", file])
subprocess.run(["git", "commit", "-m", msg])
subprocess.run(["git", "restore", file])
```

**Impact:**
- Each subprocess has startup overhead
- Sequential operations (add → commit)
- Could batch or use gitpython library

**Optimization Ideas:**
- **Use gitpython**: In-process git operations (no subprocess)
- **Batch commits**: Stage multiple files, commit once
- **Git hooks optimization**: Skip unnecessary pre-commit checks in YOLO mode

---

## Parallelization Opportunities

### 1. Multi-Ticket Parallel Processing ⭐⭐⭐
**Effort:** Medium | **Impact:** High | **Complexity:** Medium

```python
# Proposed Architecture
import asyncio
from concurrent.futures import ProcessPoolExecutor

async def process_tickets_parallel(ticket_ids, max_workers=3):
    """Process multiple tickets in parallel using worktrees."""

    # Create isolated worktree per ticket
    worktrees = [create_worktree(f"fix/{tid}") for tid in ticket_ids]

    # Spin up containers per worktree
    containers = await asyncio.gather(*[
        start_container(wt) for wt in worktrees
    ])

    # Process in parallel
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = await asyncio.gather(*[
            executor.submit(fix_ticket, tid, container)
            for tid, container in zip(ticket_ids, containers)
        ])

    return results
```

**Benefits:**
- 3 tickets in parallel = 3x speedup (45min → 15min for 3 tickets)
- Each ticket gets isolated environment (no interference)
- Container restarts parallelized

**Challenges:**
- Resource usage (3 containers, 3 Solr instances if needed)
- LLM API rate limits (need backoff)
- Result merging complexity

---

### 2. Parallel Suggestion Generation ⭐⭐
**Effort:** Low | **Impact:** Medium | **Complexity:** Low

```python
async def get_parallel_suggestions(result, n=3):
    """Generate N suggestions in parallel, pick best."""

    tasks = [
        advisor.get_suggestion_async(result, temperature=0.7)
        for _ in range(n)
    ]

    suggestions = await asyncio.gather(*tasks)

    # Pick highest confidence, or combine multiple ideas
    return max(suggestions, key=lambda s: s.confidence)
```

**Benefits:**
- Higher quality suggestions (pick best of N)
- Diversity of approaches
- Only adds LLM cost, not wall time (parallel)

---

### 3. Parallel Evaluation Metrics ⭐⭐⭐
**Effort:** Medium | **Impact:** High | **Complexity:** Medium

```python
async def evaluate_parallel(response, contexts, expected):
    """Run all LLM-judged metrics in parallel."""

    tasks = {
        'answer_correctness': judge_answer_correctness(response, expected),
        'faithfulness': judge_faithfulness(response, contexts),
        'context_relevance': judge_context_relevance(contexts, query),
        'keywords': check_keywords(response, expected_keywords),
    }

    results = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results))
```

**Benefits:**
- 4 LLM judges × 5 sec = 20 sec sequential → 5 sec parallel
- 15 second savings per iteration
- 20 iterations = 5 minutes saved

---

### 4. Batch Document Discovery ⭐
**Effort:** Low | **Impact:** Low | **Complexity:** Low

```python
def bootstrap_batch(ticket_ids):
    """Discover docs for multiple tickets in one Solr query."""

    # Build combined query
    queries = [get_discovery_query(tid) for tid in ticket_ids]

    # Single large Solr query
    results = solr.search_batch(queries)

    # Distribute results back to tickets
    return distribute_results(results, ticket_ids)
```

**Benefits:**
- Reduce Solr roundtrips
- Share document cache across tickets

---

## Caching & Memoization

### 1. LLM Response Caching ⭐⭐⭐
**Effort:** Low | **Impact:** High | **Complexity:** Low

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def get_llm_judgment(prompt_hash, model):
    """Cache LLM judgments by prompt hash."""
    # If we've seen this exact prompt before, reuse result
    pass

# Usage
prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
result = get_llm_judgment(prompt_hash, "claude-sonnet-4-5")
```

**Benefits:**
- Reuse judgments across iterations if context unchanged
- Useful for regression testing (same questions)
- Massive savings in YOLO runs

**When it helps:**
- Retrieval improves but context unchanged → reuse answer_correctness
- Multiple tickets with same question
- Regression validation (CLA tests)

---

### 2. Solr Config Snapshot Caching ✅
**Status:** Already implemented
**Location:** `extract_solr_config_snapshot()`, `load_solr_config_snapshot()`

```python
# Current implementation
snapshot = self.load_solr_config_snapshot(ticket_id)  # Cached
if not snapshot:
    snapshot = self.extract_solr_config_snapshot(ticket_id)  # Generate
```

**Impact:** Saves ~500 lines of file reads per iteration

---

### 3. Evaluation Result Caching ⭐⭐
**Effort:** Low | **Impact:** Medium | **Complexity:** Low

```python
# Cache eval results by (ticket_id, git_commit_hash)
eval_cache = {
    ("RSPEED-2482", "abc123def"): EvaluationResult(...),
}

def diagnose_cached(ticket_id):
    commit = get_current_commit_hash()

    if (ticket_id, commit) in eval_cache:
        print("📦 Using cached evaluation result")
        return eval_cache[(ticket_id, commit)]

    result = diagnose(ticket_id)
    eval_cache[(ticket_id, commit)] = result
    return result
```

**Benefits:**
- Avoid re-running identical evaluations
- Useful when reverting changes (back to known state)
- Save 30 seconds per cache hit

---

## Advanced Agentic Workflows

### 1. Multi-Agent Collaboration ⭐⭐⭐
**Effort:** High | **Impact:** High | **Complexity:** High

```
┌─────────────────────────────────────────────────┐
│         Orchestrator Agent                      │
│  (Coordinates sub-agents, merges insights)      │
└──────────┬──────────────────────────────────────┘
           │
     ┌─────┴─────┬──────────┬──────────┬──────────┐
     │           │          │          │          │
┌────▼────┐ ┌───▼───┐ ┌────▼────┐ ┌──▼──┐ ┌─────▼─────┐
│Retrieval│ │Answer │ │Root     │ │Test │ │Regression │
│Optimizer│ │Expert │ │Cause    │ │Agent│ │Predictor  │
│         │ │       │ │Analyzer │ │     │ │           │
└─────────┘ └───────┘ └─────────┘ └─────┘ └───────────┘
```

**Specialized Agents:**

#### Retrieval Optimizer Agent
- **Focus:** Solr config tuning only
- **Tools:** Solr analyzer, explain output, direct queries
- **Output:** Parameter changes (qf, pf, mm, etc.)

#### Answer Quality Expert
- **Focus:** Prompt engineering, context window optimization
- **Tools:** LLM advisor, answer analysis
- **Output:** System prompt changes

#### Root Cause Analyzer
- **Focus:** Why is this failing?
- **Tools:** Solr explain, document analysis, keyword extraction
- **Output:** Diagnosis report with confidence scores

#### Test Agent
- **Focus:** Validation and regression detection
- **Tools:** Full test suite, fast eval
- **Output:** Pass/fail + regression list

#### Regression Predictor
- **Focus:** Predict what might break before applying change
- **Tools:** Change impact analysis, historical data
- **Output:** Risk score + affected tickets

**Workflow:**
1. **Orchestrator** receives ticket
2. **Root Cause Analyzer** diagnoses problem type
3. Dispatches to **Retrieval Optimizer** OR **Answer Expert** based on diagnosis
4. **Test Agent** validates proposed change
5. **Regression Predictor** checks for side effects
6. **Orchestrator** merges insights, decides whether to apply

**Benefits:**
- Specialized expertise per domain
- Parallel analysis
- Better decision making (multiple perspectives)

---

### 2. Automated Root Cause Analysis ⭐⭐⭐
**Effort:** Medium | **Impact:** High | **Complexity:** Medium

```python
class RootCauseAnalyzer:
    """Deeply analyze why retrieval is failing."""

    def analyze(self, ticket_id, query, expected_urls, retrieved_urls):
        """Multi-step analysis."""

        # Step 1: Document existence check
        missing_docs = self.check_document_existence(expected_urls)
        if missing_docs:
            return Diagnosis("MISSING_DOCS", missing_docs)

        # Step 2: Query analysis
        query_issues = self.analyze_query_problems(query, expected_urls)
        if query_issues:
            return Diagnosis("QUERY_REFORMULATION", query_issues)

        # Step 3: Solr explain analysis
        explain_data = self.get_solr_explain(query, expected_urls)
        ranking_issues = self.analyze_ranking(explain_data)

        # Step 4: Field weight analysis
        field_problems = self.analyze_field_weights(explain_data)

        # Step 5: Competing documents analysis
        competitors = self.analyze_top_docs(retrieved_urls, expected_urls)

        return Diagnosis(
            problem_type="RANKING",
            subtype=ranking_issues['type'],
            competing_docs=competitors,
            recommended_changes=ranking_issues['changes'],
            confidence=ranking_issues['confidence']
        )

    def analyze_ranking(self, explain_data):
        """Analyze Solr explain output to find ranking issues."""

        issues = []

        # Check if expected docs scored poorly
        for doc_id, explain in explain_data.items():
            # Parse BM25 components
            tf = extract_tf(explain)
            idf = extract_idf(explain)
            field_boosts = extract_field_boosts(explain)

            # Identify weak signals
            if tf < 0.5:
                issues.append({
                    'doc': doc_id,
                    'problem': 'LOW_TERM_FREQUENCY',
                    'suggestion': 'Query terms not appearing enough in doc',
                    'fix': 'Increase field weights or add phrase boosting'
                })

            if not field_boosts['title']:
                issues.append({
                    'doc': doc_id,
                    'problem': 'TITLE_NOT_MATCHING',
                    'suggestion': 'Query terms missing from title',
                    'fix': 'Reduce title boost or improve mm threshold'
                })

        return self.prioritize_issues(issues)
```

**Benefits:**
- Faster diagnosis (automated explain parsing)
- Actionable insights (specific field/boost to change)
- Learning over time (pattern recognition)

---

### 3. Regression Prediction Model ⭐⭐
**Effort:** High | **Impact:** Medium | **Complexity:** High

```python
class RegressionPredictor:
    """Predict which tickets might regress from a change."""

    def __init__(self):
        self.change_history = self.load_change_history()

    def predict_regressions(self, proposed_change):
        """Predict regression risk before applying change."""

        # Extract change features
        features = {
            'param_changed': proposed_change.param_name,
            'direction': 'increase' if proposed_change.delta > 0 else 'decrease',
            'magnitude': abs(proposed_change.delta),
            'param_type': self.classify_param(proposed_change.param_name)
        }

        # Find similar historical changes
        similar_changes = self.find_similar_changes(features)

        # Analyze historical regressions
        regression_rate = self.calculate_regression_rate(similar_changes)
        affected_tickets = self.identify_affected_tickets(similar_changes)

        return {
            'risk_score': regression_rate,
            'likely_affected': affected_tickets,
            'recommendation': self.generate_recommendation(regression_rate),
            'mitigation': self.suggest_mitigation(affected_tickets)
        }

    def suggest_mitigation(self, affected_tickets):
        """Suggest how to prevent regressions."""

        # Pre-test affected tickets before committing
        # Adjust change magnitude
        # Add compensating changes
        pass
```

**Benefits:**
- Proactive regression prevention
- Smarter change magnitude (don't overshoot)
- Prioritize validation (test risky tickets first)

---

### 4. Automated Bisection for Regressions ⭐⭐
**Effort:** Medium | **Impact:** Medium | **Complexity:** Medium

```python
async def bisect_regression(ticket_id, good_commit, bad_commit):
    """Git bisect to find commit that broke a ticket."""

    commits = get_commit_range(good_commit, bad_commit)

    # Binary search
    while len(commits) > 1:
        mid = commits[len(commits) // 2]

        # Checkout mid commit
        checkout(mid)
        restart_okp_mcp()

        # Test ticket
        result = diagnose(ticket_id)

        if result.is_passing:
            # Regression is after this commit
            commits = commits[mid:]
        else:
            # Regression is at or before this commit
            commits = commits[:mid+1]

    return commits[0]  # The breaking commit
```

**Benefits:**
- Automatic root cause for regressions
- Faster debugging
- Can revert or cherry-pick specific changes

---

### 5. Knowledge Graph Building ⭐⭐⭐
**Effort:** High | **Impact:** High | **Complexity:** High

```python
class KnowledgeGraph:
    """Build relationships between tickets, docs, and config changes."""

    def __init__(self):
        self.graph = nx.DiGraph()

    def record_fix(self, ticket_id, change, outcome):
        """Record a fix attempt in knowledge graph."""

        # Nodes
        self.graph.add_node(ticket_id, type='ticket')
        self.graph.add_node(change.param, type='config')

        # Edge: ticket → config (with outcome)
        self.graph.add_edge(
            ticket_id,
            change.param,
            change_type=change.type,
            delta=change.delta,
            outcome='improved' if outcome.improved else 'failed',
            metric_delta=outcome.metric_delta
        )

        # Document relationships
        for doc_url in outcome.retrieved_docs:
            self.graph.add_node(doc_url, type='document')
            self.graph.add_edge(ticket_id, doc_url, relation='retrieved')

    def suggest_similar_fix(self, new_ticket):
        """Suggest fix based on similar tickets."""

        # Find similar tickets by:
        # - Query similarity
        # - Expected documents overlap
        # - Problem type

        similar = self.find_similar_tickets(new_ticket)

        # Extract successful changes from similar tickets
        successful_changes = [
            self.graph[ticket][config]
            for ticket in similar
            for config in self.graph.successors(ticket)
            if self.graph[ticket][config]['outcome'] == 'improved'
        ]

        # Rank by success rate and similarity
        return self.rank_changes(successful_changes)

    def visualize_fix_patterns(self):
        """Visualize which config changes fix which ticket types."""

        # Cluster tickets by fix patterns
        # Show which parameters most frequently improve retrieval
        # Identify parameter interactions
        pass
```

**Benefits:**
- Learn from past fixes
- Transfer learning across tickets
- Identify fix patterns ("mm loosening helps RHEL version queries")
- Visual debugging (see why certain changes keep failing)

---

### 6. Continuous Learning & Improvement ⭐⭐
**Effort:** Medium | **Impact:** Medium | **Complexity:** Medium

```python
class MetaLearner:
    """Learn meta-patterns from fix history."""

    def extract_fix_patterns(self, history):
        """Extract patterns from successful fixes."""

        patterns = []

        for fix in history:
            pattern = {
                'problem_signature': self.signature(fix.problem),
                'solution_type': fix.change.type,
                'confidence': fix.outcome.metric_improvement,
            }
            patterns.append(pattern)

        # Cluster by problem signature
        clusters = self.cluster_patterns(patterns)

        # Extract rules
        rules = []
        for cluster in clusters:
            rule = self.extract_rule(cluster)
            rules.append(rule)

        return rules

    def signature(self, problem):
        """Create signature for problem type."""
        return {
            'url_f1': problem.url_f1,
            'mrr': problem.mrr,
            'query_length': len(problem.query.split()),
            'doc_missing_rate': problem.missing_docs / problem.expected_docs,
            'title_match': problem.title_matches,
        }
```

**Example Learned Rules:**
- "If URL_F1=0 and query has product names → increase title boost"
- "If MRR low but URL_F1 okay → loosen mm threshold"
- "If context_relevance poor → add phrase boosting"

---

## Infrastructure Improvements

### 1. Distributed Agent Architecture ⭐⭐⭐
**Effort:** High | **Impact:** High | **Complexity:** High

```
┌──────────────────────────────────────┐
│         Central Coordinator          │
│   (Task queue, result aggregation)   │
└────────────┬─────────────────────────┘
             │
      ┌──────┴──────┬──────────┬──────────┐
      │             │          │          │
┌─────▼─────┐ ┌────▼────┐ ┌───▼───┐ ┌───▼───┐
│Worker 1   │ │Worker 2 │ │Worker3│ │Worker4│
│Container A│ │Container│ │Container│ │Container│
│Worktree A │ │Worktree │ │Worktree│ │Worktree│
└───────────┘ └─────────┘ └───────┘ └───────┘
```

**Components:**
- **Coordinator**: Distributes tickets, merges results
- **Workers**: Independent agent processes
- **Message Queue**: Redis/RabbitMQ for task distribution
- **Shared Cache**: Redis for eval results, LLM responses

**Benefits:**
- True parallelism (4 workers = 4x throughput)
- Horizontal scaling (add more workers)
- Fault tolerance (worker fails → retry task)

---

### 2. LLM API Optimization ⭐⭐
**Effort:** Low | **Impact:** Medium | **Complexity:** Low

**Current Issues:**
- Not using streaming (wait for full response)
- No request batching
- No retry logic with backoff

**Improvements:**
```python
# Streaming for faster feedback
async for chunk in llm.stream(prompt):
    print(chunk, end='', flush=True)

# Batch requests where possible
results = await llm.batch([prompt1, prompt2, prompt3])

# Retry with exponential backoff
@retry(max_attempts=3, backoff=ExponentialBackoff())
async def call_llm(prompt):
    return await llm.complete(prompt)
```

---

### 3. Telemetry & Observability ⭐⭐
**Effort:** Medium | **Impact:** Medium | **Complexity:** Low

**Add instrumentation:**
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("fix_ticket")
def fix_ticket(ticket_id):
    span = trace.get_current_span()
    span.set_attribute("ticket_id", ticket_id)

    with tracer.start_as_current_span("diagnose"):
        result = diagnose(ticket_id)
        span.set_attribute("url_f1", result.url_f1)

    with tracer.start_as_current_span("iterate"):
        for i in range(max_iterations):
            # ...
            span.add_event(f"iteration_{i}_complete")
```

**Benefits:**
- See where time is spent (flamegraphs)
- Track success rates over time
- Identify bottlenecks in production

---

## Experimentation Roadmap

### Phase 1: Quick Wins (1-2 weeks)
**Focus:** Low effort, high impact

1. ✅ **Batch ticket processing** - Already implemented!
2. ✅ **Progress reports** - Already implemented!
3. **Parallel LLM judges** - Use asyncio for metrics
4. **LLM response caching** - Hash prompts, cache results
5. **Evaluation result caching** - Cache by git commit hash

**Expected Gains:** 30-40% speedup

---

### Phase 2: Parallelization (2-4 weeks)
**Focus:** True parallelization

1. **Multi-ticket parallel processing** - Worktrees + containers
2. **Parallel suggestion generation** - Generate N, pick best
3. **Async container management** - Non-blocking restarts
4. **Distributed worker architecture** - Task queue

**Expected Gains:** 2-4x speedup (depending on workers)

---

### Phase 3: Advanced Agents (4-8 weeks)
**Focus:** Smarter decision making

1. **Root cause analyzer agent** - Automated Solr explain analysis
2. **Regression predictor** - ML model for risk prediction
3. **Knowledge graph** - Learn from fix history
4. **Meta-learner** - Extract fix patterns

**Expected Gains:** Higher quality fixes, fewer regressions

---

### Phase 4: Production Infrastructure (8-12 weeks)
**Focus:** Scale and reliability

1. **Distributed coordinator** - Central task queue
2. **Telemetry system** - OpenTelemetry instrumentation
3. **Auto-scaling workers** - Kubernetes deployment
4. **CI/CD integration** - Automated regression detection

**Expected Gains:** 10x scale, production-grade reliability

---

## Metrics to Track

### Performance Metrics
- **Time to fix** (minutes per ticket)
- **Throughput** (tickets per hour)
- **LLM latency** (seconds per call)
- **Container restart time** (seconds)
- **Evaluation time** (seconds per run)

### Quality Metrics
- **Fix success rate** (% tickets fixed)
- **Regression rate** (% fixes causing regressions)
- **Iterations to fix** (lower is better)
- **Confidence accuracy** (LLM confidence vs actual success)

### Cost Metrics
- **LLM API cost** ($ per ticket)
- **Compute cost** ($ per hour)
- **Developer time saved** (hours)

---

## Answer-First Workflow ⭐⭐⭐ (IMPLEMENTED)

**Status:** ✅ Implemented and documented
**Effort:** Medium | **Impact:** High | **Complexity:** Medium

The most realistic workflow for customer bugs where you don't have ground truth URLs.

### What It Is

Instead of requiring known "correct" documents, this workflow:
1. Starts with just **question + expected answer** (from SME)
2. Evaluates answer quality first
3. Uses LLM to check if retrieved docs contain the answer
4. If not → **discovers** which docs actually have the answer
5. Optimizes retrieval to get those docs
6. Saves discovered URLs as regression test

### Impact

**Before (Traditional):**
- ❌ Need to know correct URLs upfront
- ❌ Can't handle new customer bugs
- ❌ Manual document discovery

**After (Answer-First):**
- ✅ Works with just question + answer
- ✅ Automatic document discovery
- ✅ Creates regression test automatically
- ✅ Perfect for customer bug workflow

### Usage

```yaml
# Just need question and answer - NO URLs!
- conversation_group_id: CUSTOMER_BUG_123
  turns:
  - query: "Is SPICE available?"
    expected_response: "SPICE is deprecated in RHEL 8.3..."
    # expected_urls: null  # Will be discovered!
```

```bash
# Auto-discover docs and fix
uv run scripts/okp_mcp_agent.py bootstrap CUSTOMER-BUG-123 --yolo
```

**Full Documentation:** [ANSWER_FIRST_WORKFLOW.md](ANSWER_FIRST_WORKFLOW.md)

---

## Conclusion

**Immediate Priorities:**
1. ✅ Batch processing (Done!)
2. ✅ Progress reports (Done!)
3. ✅ Answer-first workflow (Done!)
4. Parallel LLM judges (Easy win)
5. LLM response caching (Easy win)
6. Multi-ticket parallel processing (Big win)

**Long-term Vision:**
- Distributed multi-agent system
- Self-improving through meta-learning
- Production-scale infrastructure
- 10x faster, 10x more reliable

**Key Insight:**
Most bottlenecks are in sequential operations that could be parallelized. The architecture already supports isolation (worktrees), we just need to execute them concurrently.

The **Answer-First Workflow** removes a major barrier: you no longer need to know which documents are "correct" upfront. This makes the agent useful for real customer bugs, not just regression testing.

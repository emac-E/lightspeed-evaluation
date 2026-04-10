# Pattern-Based Batch Fixing

## Overview

Instead of fixing tickets one-by-one, fix entire patterns in batch. This is 10-15x more efficient for clustered tickets.

## Workflow

```
Bootstrap Step (Stage 1 + 2)
├── extract_jira_tickets.py        → extracted_tickets.yaml
└── discover_ticket_patterns.py    → patterns_report.json
                                    → tickets_with_patterns.yaml

Coding Agent (Pattern-Based)
└── okp_mcp_agent.py fix-pattern <PATTERN_ID>
    ├── Load all tickets in pattern
    ├── Create branch: fix/<PATTERN_ID>
    ├── Iterate:
    │   ├── Get LLM suggestion (considering ALL tickets)
    │   ├── Apply code change
    │   ├── Evaluate against ALL tickets in pattern
    │   └── Pass only if ALL (or majority) pass
    └── Stack commits on pattern branch
```

## Key Differences from Single-Ticket Mode

| Aspect | Single-Ticket | Pattern-Based |
|--------|--------------|---------------|
| Input | `RSPEED-2482` | `EOL_CONTAINER_COMPATIBILITY` |
| Branch name | `fix/rspeed-2482` | `fix/pattern-eol-container-compat` |
| Evaluation scope | 1 ticket | All tickets in pattern (e.g., 15) |
| Success criteria | Single ticket passes | All tickets pass (or >80% pass) |
| Iterations | 5 per ticket | 5 for entire pattern |
| Total iterations | 5 × 15 = 75 | 5 |
| Commits | 1 commit per ticket | Stacked commits on pattern branch |

## Implementation

### New Command: `fix-pattern`

```bash
# Fix entire pattern
python scripts/okp_mcp_agent.py fix-pattern EOL_CONTAINER_COMPATIBILITY \
    --max-iterations 10 \
    --threshold 0.80  # Pass if 80% of tickets fixed - ? is this adequate? can it do better?

# List available patterns
python scripts/okp_mcp_agent.py list-patterns

# Show pattern details
python scripts/okp_mcp_agent.py show-pattern EOL_CONTAINER_COMPATIBILITY
```

### Pattern-Based Evaluation

During each iteration:

```python
def evaluate_pattern(pattern_id: str, tickets: list[dict]) -> PatternEvaluationResult:
    """Evaluate all tickets in a pattern.
    
    Returns:
        PatternEvaluationResult with:
        - per_ticket_results: Dict[ticket_id, EvaluationResult]
        - pass_count: Number of tickets passing
        - fail_count: Number of tickets failing
        - pass_rate: Percentage passing
        - pattern_fixed: True if pass_rate >= threshold
    """
    results = {}
    for ticket in tickets:
        # Run evaluation for each ticket
        result = self.diagnose(ticket['ticket_key'], use_existing=False)
        results[ticket['ticket_key']] = result
    
    pass_count = sum(1 for r in results.values() if r.is_passing)
    pass_rate = pass_count / len(tickets)
    
    return PatternEvaluationResult(
        per_ticket_results=results,
        pass_count=pass_count,
        fail_count=len(tickets) - pass_count,
        pass_rate=pass_rate,
        pattern_fixed=pass_rate >= threshold
    )
```

### LLM Suggestion with Pattern Context

The LLM advisor receives:

```python
suggestion = llm_advisor.get_suggestion(
    pattern_id="EOL_CONTAINER_COMPATIBILITY",
    pattern_description="RHEL 6/7 containers on RHEL 9/10 hosts",
    representative_tickets=[
        {"ticket_key": "RSPEED-2482", "query": "Can I run RHEL 6 container on RHEL 9?"},
        {"ticket_key": "RSPEED-2511", "query": "Can I run RHEL 7 container on RHEL 10?"},
        {"ticket_key": "RSPEED-2520", "query": "Minimum RHEL version for containers on RHEL 9?"},
    ],
    current_metrics={
        "RSPEED-2482": {"url_f1": 0.2, "context_relevance": 0.3},
        "RSPEED-2511": {"url_f1": 0.15, "context_relevance": 0.25},
        "RSPEED-2520": {"url_f1": 0.3, "context_relevance": 0.4},
    },
    pattern_hypothesis="All tickets need container compatibility matrix URL boosted",
    solr_config_snapshot=solr_snapshot,
)
```

This gives the LLM:
- **Common pattern** across tickets
- **Generalized fix** instead of ticket-specific
- **Validation** against multiple tickets (prevents overfitting)

### Success Criteria

**Strict Mode (default):**
- ALL tickets must pass
- Use for critical patterns (security, data loss)

**Majority Mode (--threshold 0.8):**
- 80% of tickets must pass
- Use for non-critical patterns
- Acceptable for large patterns (e.g., 15 tickets)

**Example:**
```bash
# Strict: all 15 tickets must pass
python scripts/okp_mcp_agent.py fix-pattern EOL_CONTAINER_COMPATIBILITY

# Majority: 12/15 tickets must pass (80%)
python scripts/okp_mcp_agent.py fix-pattern EOL_CONTAINER_COMPATIBILITY --threshold 0.8
```

## Git Branching Strategy

### Pattern Branch Naming

```bash
# Pattern ID: EOL_CONTAINER_COMPATIBILITY
# Branch: fix/pattern-eol-container-compat
git checkout -b fix/pattern-eol-container-compat

# Multiple patterns can be fixed in parallel on different branches
git checkout -b fix/pattern-version-mismatch
git checkout -b fix/pattern-deprecated-feature
```

### Commit Stacking

Each iteration creates a commit on the pattern branch:

```
fix/pattern-eol-container-compat
├── commit 1: "agent: boost container-compatibility URL by 2.0"
│              (RSPEED-2482: 60% pass, RSPEED-2511: 40% pass, RSPEED-2520: 50% pass)
│
├── commit 2: "agent: boost container-compatibility URL by 5.0"
│              (RSPEED-2482: 80% pass, RSPEED-2511: 70% pass, RSPEED-2520: 75% pass)
│
└── commit 3: "agent: boost container-compatibility URL by 10.0 + add to qf"
               (RSPEED-2482: 100% pass, RSPEED-2511: 100% pass, RSPEED-2520: 95% pass)
               ✅ PATTERN FIXED (3/3 passing)
```

### Merge Strategy

After pattern is fixed:

```bash
# Review commits on pattern branch
git log fix/pattern-eol-container-compat

# Option 1: Merge all commits (preserves iteration history)
git checkout main
git merge fix/pattern-eol-container-compat

# Option 2: Squash to single commit (cleaner history)
git checkout main
git merge --squash fix/pattern-eol-container-compat
git commit -m "fix: EOL container compatibility pattern (15 tickets)

Fixes: RSPEED-2482, RSPEED-2511, RSPEED-2520, ...

Pattern: EOL_CONTAINER_COMPATIBILITY
- Boosted container compatibility matrix URL by 10.0
- Added container-compatibility to qf boost
- All 15 tickets now passing

Metrics (average across pattern):
- URL F1: 0.2 → 0.95
- Context Relevance: 0.3 → 0.92
"
```

## Benefits

### Efficiency
- **15x fewer iterations** for clustered tickets
- One fix validates against all tickets simultaneously
- Prevents regression within pattern

### Quality
- **Generalized fixes** instead of ticket-specific hacks
- LLM sees pattern, suggests root cause fix
- Validates across multiple test cases (better than single ticket)

### Workflow
- **Cleaner git history** - one branch per pattern
- **Easier review** - see all related changes together
- **Better metrics** - track pattern-level success rates

## Example End-to-End

```bash
# 1. Bootstrap: Extract and discover patterns
python scripts/extract_jira_tickets.py --limit 50
python scripts/discover_ticket_patterns.py

# 2. Review patterns
cat patterns_report.json | jq '.patterns'
# Output:
# {
#   "pattern_id": "EOL_CONTAINER_COMPATIBILITY",
#   "ticket_count": 15,
#   "representative_tickets": ["RSPEED-2482", "RSPEED-2511"],
#   "matched_tickets": ["RSPEED-2482", "RSPEED-2511", "RSPEED-2520", ...]
# }

# 3. Fix pattern (not individual tickets)
python scripts/okp_mcp_agent.py fix-pattern EOL_CONTAINER_COMPATIBILITY \
    --max-iterations 10 \
    --threshold 0.8

# 4. Validate pattern fix
python scripts/okp_mcp_agent.py validate-pattern EOL_CONTAINER_COMPATIBILITY

# 5. Review branch
git log fix/pattern-eol-container-compat --oneline

# 6. Merge to main
git checkout main
git merge --squash fix/pattern-eol-container-compat
git commit -m "fix: EOL container compatibility pattern (15 tickets)"
```

## Implementation Checklist

- [ ] Add `fix-pattern` command to okp_mcp_agent.py
- [ ] Load pattern data from tickets_with_patterns.yaml
- [ ] Create PatternEvaluationResult dataclass
- [ ] Modify evaluate loop to test all tickets in pattern
- [ ] Update LLM advisor prompt to include pattern context
- [ ] Add pattern-based branch naming
- [ ] Add pattern validation command
- [ ] Add list-patterns and show-pattern commands
- [ ] Update documentation
- [ ] Add tests for pattern-based fixing

## Future Enhancements

### Smart Pattern Selection
```bash
# Auto-prioritize patterns by impact
python scripts/okp_mcp_agent.py fix-patterns --auto-prioritize
# Fixes patterns in order:
# 1. Highest ticket count (biggest impact)
# 2. Highest confidence from pattern discovery
# 3. Lowest current pass rate
```

### Pattern Metrics Dashboard
```bash
# Show pattern-level health
python scripts/okp_mcp_agent.py pattern-dashboard
# Output:
# Pattern                        | Tickets | Pass Rate | Status
# ------------------------------ | ------- | --------- | ------
# EOL_CONTAINER_COMPATIBILITY    | 15      | 20%       | ❌ NEEDS FIX
# VERSION_MISMATCH               | 8       | 75%       | 🟡 PARTIAL
# DEPRECATED_FEATURE             | 12      | 95%       | ✅ PASSING
```

### Cross-Pattern Dependencies
```bash
# Some patterns may depend on others
# Fix in dependency order
python scripts/okp_mcp_agent.py fix-patterns --resolve-dependencies
```

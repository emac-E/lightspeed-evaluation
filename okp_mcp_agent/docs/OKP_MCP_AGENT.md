# OKP-MCP Autonomous Agent

Autonomous agent for fixing okp-mcp RSPEED tickets using Claude Code and the lightspeed-evaluation framework.

## Overview

The `okp_mcp_agent.py` script automates the [INCORRECT_ANSWER_LOOP workflow](https://github.com/RedHatInsights/okp-mcp/blob/main/INCORRECT_ANSWER_LOOP.md) documented in okp-mcp:

```
┌──────────────┐
│  1. Diagnose │  Run eval to identify problem type (retrieval vs answer)
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  2. Claude Analyzes & Suggests Code Changes              │
│     - Receives: metrics, Solr explain, current config    │
│     - Returns: specific parameter change + reasoning     │
└──────┬───────────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│  3. Apply    │  Parse suggestion → edit file → restart container
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
│ Retrieval   │   │ Full eval   │         │
│ metrics     │   │ + answer    │         │
└──────┬──────┘   └──────┬──────┘         │
       │                 │                 │
       ├────TEST─────────┤                 │
       │                 │                 │
       ▼                 ▼                 │
┌──────────────────────────┐              │
│ 4. Test & Decision       │              │
│  • Improved? → Commit    │              │
│  • No change? → Revert   │              │
│  • Plateau? → Escalate   │              │
└──────┬───────────────────┘              │
       │                                  │
       ▼                                  │
┌─────────────┐                           │
│ 5. Repeat   │                           │
│ or Done     │◄──────────────────────────┘
└─────────────┘
```

## Key Features

### 🚀 **Dual-Mode Iteration**
- **Retrieval-Only Mode** (~30 sec): Fast iteration for search/ranking problems
- **Full Mode** (~3 min): Complete evaluation including answer generation
- Automatically switches based on problem type

### 🔬 **Solr Expert System**
Claude has deep Solr expertise and can optimize:
- Query field weights (`qf`)
- Phrase boosts (`pf`, `pf2`, `pf3`)
- Phrase slop (`ps`, `ps2`, `ps3`)
- Minimum match (`mm`)
- BM25 parameters (`hl.score.k1`, `hl.score.b`, `hl.score.pivot`)
- Boost/demote keywords and multipliers

See [SOLR_EXPERT_AGENT.md](./SOLR_EXPERT_AGENT.md) for details.

### 🧪 **Test-Then-Commit Workflow**
- Changes applied to isolated git worktree
- Container restarted with worktree mounted
- Metrics evaluated BEFORE committing
- **Commits only if test passes** (not before!)
- Reverts automatically if no improvement

### 🎯 **Smart Iteration**
- Model escalation: Haiku → Sonnet → Opus → Human
- Plateau detection (2 iterations without improvement)
- Regression protection (penalizes metrics that drop >0.1)
- Iteration history (Claude learns from failed attempts)

### 🛡️ **Safe Isolation**
- Git worktrees for parallel development
- Automatic cleanup on completion or failure
- Container mount redirection for testing
- Changes visible only in worktree until approved

## Quick Start

### Setup (One Time)

**Prerequisites:**
- Python 3.11+
- `uv` package manager installed
- Access to Google Cloud with Anthropic Vertex AI enabled
- okp-mcp running in container (via lscore-deploy)
- Solr running on `localhost:8983/solr/portal`

**1. Install dependencies:**
```bash
uv sync --group dev
make install-deps-test
```

**2. Set up environment:**
```bash
# Copy template
cp .env.example .env

# Edit .env
vim .env
```

Required variables in `.env`:
```bash
# For Gemini (evaluation judge)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/gemini-service-account.json
GOOGLE_CLOUD_PROJECT=your-gemini-project-id

# For Claude (LLM advisor)
ANTHROPIC_VERTEX_PROJECT_ID=your-claude-project-id
```

**3. Authenticate with Google Cloud:**
```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project <your-claude-project-id>
```

**That's it!** The agent automatically handles credential separation internally.

### Commands

#### Diagnose a Ticket (Read-Only Analysis)

Get AI-powered analysis **without** making changes:

```bash
uv run python -m scripts.okp_mcp_agent diagnose RSPEED-2482
```

**What it does:**
- ✅ Runs evaluation and analyzes metrics
- ✅ Classifies problem type (retrieval vs answer)
- ✅ Shows what Claude would suggest
- ❌ **Does NOT apply changes or commit**

**Use this when:** You want to preview suggestions before committing to the fix.

#### Fix a Ticket (Full Autonomous Loop)

Run the complete iteration loop:

```bash
uv run python -m scripts.okp_mcp_agent fix RSPEED-2482 --max-iterations 5
```

**What it does:**
1. ✅ Creates isolated git worktree
2. ✅ Runs initial diagnosis
3. ✅ Gets Claude suggestion
4. ✅ Applies code change to worktree
5. ✅ Updates container mount to worktree
6. ✅ Restarts container
7. ✅ Re-evaluates metrics
8. ✅ **Commits if improved, reverts if not**
9. ✅ Repeats until fixed or max iterations

**Flags:**
- `--max-iterations N` - Maximum iterations before giving up (default: 5)
- `--use-existing` - Skip re-running evaluation, use cached results (for debugging)

**Use this when:** You want to actually fix the ticket with AI assistance.

#### Validate All Test Suites

Check for regressions across all test suites:

```bash
uv run python -m scripts.okp_mcp_agent validate
```

Runs stability analysis across the full test suite (3 runs each).

### Key Difference: Diagnose vs Fix

| Feature | `diagnose` | `fix` |
|---------|-----------|-------|
| Analyzes metrics | ✅ | ✅ |
| Claude suggests change | ✅ | ✅ |
| Creates git worktree | ❌ | ✅ |
| Applies code change | ❌ | ✅ |
| Updates container mount | ❌ | ✅ |
| Restarts container | ❌ | ✅ |
| Re-evaluates metrics | ❌ | ✅ |
| Commits if improved | ❌ | ✅ |
| Iterates until fixed | ❌ | ✅ |

**TL;DR:**
- `diagnose` = Preview what Claude would suggest
- `fix` = Actually do it with test-then-commit workflow

## How It Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ okp_mcp_agent.py (Main Orchestrator)                            │
│                                                                  │
│  1. Initial Diagnosis                                           │
│     └─> Run evaluation → Parse metrics → Classify problem      │
│                                                                  │
│  2. Iteration Loop (max 5 iterations)                           │
│     ┌────────────────────────────────────────────────────────┐ │
│     │ a. Get Claude Suggestion                               │ │
│     │    ├─> okp_mcp_llm_advisor.py                         │ │
│     │    │   └─> Claude Agent SDK (Edit tool enabled)       │ │
│     │    │       └─> Returns: SolrConfigSuggestion          │ │
│     │    │                                                    │ │
│     │ b. Apply Code Change                                   │ │
│     │    ├─> Parse suggestion.code_snippet                   │ │
│     │    ├─> Apply via regex (7+ parameter types supported) │ │
│     │    └─> Write to worktree/src/okp_mcp/solr.py         │ │
│     │                                                         │ │
│     │ c. Update Container Mount                              │ │
│     │    ├─> Edit lscore-deploy/local/podman-compose.yml   │ │
│     │    └─> Mount worktree instead of main repo            │ │
│     │                                                         │ │
│     │ d. Restart Container                                   │ │
│     │    └─> podman-compose restart okp-mcp                 │ │
│     │                                                         │ │
│     │ e. Test (Dual-Mode)                                    │ │
│     │    ├─> Retrieval problem? → retrieval-only (~30s)    │ │
│     │    └─> Answer problem? → full eval (~3min)           │ │
│     │                                                         │ │
│     │ f. Decision                                            │ │
│     │    ├─> Metrics improved? → git commit                 │ │
│     │    ├─> No improvement? → git restore (revert)         │ │
│     │    ├─> Plateau? → escalate model tier                 │ │
│     │    └─> Fixed? → exit loop                             │ │
│     └────────────────────────────────────────────────────────┘ │
│                                                                  │
│  3. Cleanup                                                     │
│     ├─> Restore container mount to main repo                   │
│     ├─> Remove worktree (if no commits)                        │
│     └─> Restore LLM advisor to main repo                       │
└─────────────────────────────────────────────────────────────────┘
```

### Credential Management

**The Challenge:** Both Gemini (for evaluation) and Claude (for suggestions) use Vertex AI, which expects `GOOGLE_APPLICATION_CREDENTIALS`. Setting this environment variable causes conflicts.

**The Solution:** Automatic credential isolation in `okp_mcp_llm_advisor.py`:

```python
# When calling Claude:
saved_creds = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
try:
    # Call Claude Agent SDK (uses ADC instead)
    result = await query(...)
finally:
    # Restore credentials for Gemini
    if saved_creds:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved_creds
```

**You don't need to manage this manually** - it's handled automatically!

### File Application Logic

Claude's `Edit` tool doesn't actually write files to disk. The agent manually applies changes by parsing `code_snippet` and using regex.

**Supported change types:**
1. **Query field weights** (`qf`): `"qf": "title^5 ..."` → `"qf": "title^7 ..."`
2. **Phrase boosts** (`pf`, `pf2`, `pf3`): `"pf": "title^8"` → `"pf": "title^12"`
3. **Phrase slop** (`ps`, `ps2`, `ps3`): `"ps": "3"` → `"ps": "5"`
4. **Minimum match** (`mm`): `"2<-1 5<75%"` → `"2<-1 5<90%"`
5. **BM25 parameters** (`hl.score.k1`, `hl.score.b`, `hl.score.pivot`)
6. **Boost keywords** (`_EXTRACTION_BOOST_KEYWORDS`): Add to frozenset
7. **Demote keywords** (`_EXTRACTION_DEMOTE_RHV`): Add to frozenset
8. **Boost multiplier**: `multiplier *= 2.0` → `multiplier *= 3.0`
9. **Demote multiplier**: `multiplier *= 0.05` → `multiplier *= 0.01`

See `scripts/okp_mcp_agent.py` lines 1810-1995 for implementation.

### Test-Then-Commit Workflow

**Critical:** Changes are **tested BEFORE committing**, not after!

```python
# 1. Apply change to file
apply_code_change(suggestion)

# 2. Store pending commit (don't commit yet!)
self._pending_commit_msg = "Fix RSPEED-2482: Add container keywords"
self._pending_commit_file = "src/okp_mcp/solr.py"

# 3. Restart container
restart_okp_mcp()

# 4. Test
current_result = diagnose_retrieval_only(ticket_id)

# 5. Check if improved
if metrics_improved(current_result, previous_result):
    # ✅ COMMIT (test passed)
    git commit -m self._pending_commit_msg
else:
    # ❌ REVERT (test failed)
    git restore self._pending_commit_file
```

This prevents failed changes from being committed to the worktree.

### Improvement Detection

**Checks all retrieval metrics** (not just URL F1):
```python
improvements = [
    (new.url_f1 or 0) - (old.url_f1 or 0),
    (new.mrr or 0) - (old.mrr or 0),
    (new.context_relevance or 0) - (old.context_relevance or 0),
    (new.context_precision or 0) - (old.context_precision or 0),  # FIX: Was missing!
]
```

**Regression protection:**
If any metric drops >0.1, requires net improvement ≥ 0.10 (2× threshold).

**First iteration validation:**
Rejects all-zero results (requires at least one metric >0.05).

## Troubleshooting

### All Metrics Return 0.00

**Symptom:**
```
URL F1: 0.00
Context Relevance: 0.00
Context Precision: 0.00
```

**Common Causes:**

#### 1. **Wrong Solr Core**
Solr core is named `portal`, not `mcp`.

**Check:**
```bash
curl -s "http://localhost:8983/solr/admin/cores?action=STATUS" | python3 -m json.tool | grep '"name"'
```

**Fix:** All tools should use `http://localhost:8983/solr/portal`

#### 2. **Wrong Expected URLs in Test Config**
Test config has outdated or invalid URLs.

**Check:**
```bash
# Check what URLs are expected
grep -A5 "RSPEED_2482" config/okp_mcp_test_suites/functional_tests_retrieval.yaml

# Check if they exist in Solr
uv run python -c "
from scripts.okp_solr_checker import SolrDocumentChecker
checker = SolrDocumentChecker()
result = checker.check_document_exists('access.redhat.com/support/policy/rhel-container-compatibility')
print(f'Exists: {result[\"exists\"]}')
"
```

**Fix:** Update test configs with correct URLs that exist in Solr index.

#### 3. **Container Mounting Wrong Directory**
Container still uses main repo instead of worktree.

**Check:**
```bash
# Check what's mounted
cat ~/Work/lscore-deploy/local/podman-compose.yml | grep "okp-mcp" -A20 | grep "/dev/src"

# Should show worktree path like:
# - ../../okp-mcp-worktrees/fix-rspeed_2482/src:/dev/src:z
```

**Fix:** The `update_compose_mount()` method must handle comments in mount lines.

#### 4. **Cached Config**
Old single-ticket config cached with stale URLs.

**Fix:**
```bash
rm .temp_configs/RSPEED_*_single.yaml
```

#### 5. **MCP Not Returning Documents**
MCP search returns empty or wrong results.

**Test manually:**
```bash
# Initialize session
SESSION_ID=$(curl -s "http://localhost:8001/mcp" -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -D - \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}' \
  2>&1 | grep -i "mcp-session-id" | cut -d: -f2 | tr -d ' \r')

# Search
curl -s "http://localhost:8001/mcp" -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "mcp-session-id: $SESSION_ID" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"search_portal","arguments":{"query":"RHEL 6 container on RHEL 9","max_results":10}},"id":2}'
```

#### 6. **MCP Client Skipping Documents with Warning Emoji**
MCP client filters out valid documents that start with "⚠️" (deprecation notices).

**Symptom:**
```
URL F1: 0.00
Context Relevance: 0.00
Context Precision: 0.00
```

Even though MCP returns documents, the client discards them because they start with deprecation/removal warnings.

**Cause:**
The `mcp_client.py` parser was skipping entire sections starting with "⚠️":

```python
# WRONG - skips valid documents
if doc.startswith("⚠️"):
    continue
```

This filtered out sections like:
```
⚠️ Deprecation/Removal Notice
**Replacing TCP Wrappers in RHEL 8 and 9**
URL: https://access.redhat.com/solutions/3906701
Content: ...
```

**Check:**
```bash
# See raw MCP response
SESSION_ID=$(curl -s "http://localhost:8001/mcp" -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}' \
  2>&1 | grep -i "mcp-session-id" | cut -d: -f2 | tr -d ' \r')

curl -s "http://localhost:8001/mcp" -X POST \
  -H "mcp-session-id: $SESSION_ID" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"search_portal","arguments":{"query":"RHEL 6 container on RHEL 9","max_results":10}},"id":2}' \
  | grep -oP 'URL: \Khttps://[^\s"]+'
```

If URLs are returned but metrics are still 0.00, the MCP client is filtering them out.

**Fix:** Already fixed in `src/lightspeed_evaluation/core/api/mcp_client.py` lines 272-286.

The parser now only skips sections **without URLs** (warning headers only), not all sections starting with "⚠️":

```python
# CORRECT - only skip headers without URLs
if not doc:
    continue

url = extract_url(doc)
if not url:
    continue  # Skip only if no URL found
```

### Claude Agent SDK Fails with "Command failed with exit code 1"

**Symptom:**
```
⚠️  claude-opus-4-6 failed with: Command failed with exit code 1
  Falling back to claude-sonnet-4-5@20250929...
```

**Cause:** Opus model sometimes fails mid-execution (known Claude Agent SDK issue).

**Fix:** Already handled! Agent automatically falls back to Sonnet. No action needed.

### UnboundLocalError: cannot access local variable 're'

**Symptom:**
```
UnboundLocalError: cannot access local variable 're' where it is not associated with a value
```

**Cause:** Missing `import re` in `EXTRACTION_BOOST_KEYWORDS` branch.

**Fix:** Already fixed in `scripts/okp_mcp_agent.py` line 1945.

### TypeError: object of type 'numpy.float64' has no len()

**Symptom:**
```
TypeError: object of type 'numpy.float64' has no len()
```

**Cause:** Pandas reads empty CSV fields as `NaN` (numpy.float64) instead of None.

**Fix:** Already fixed with `pd.notna()` checks in:
- `scripts/okp_mcp_agent.py` lines 1223-1227
- `scripts/okp_mcp_llm_advisor.py` lines 173, 180

### Changes Not Visible in Container

**Symptom:** You see commits in worktree but metrics don't change.

**Cause:** Container still mounting main repo instead of worktree.

**Debug:**
```bash
# 1. Check worktree has changes
cd ~/Work/okp-mcp-worktrees/fix-rspeed_2482
git diff HEAD~1

# 2. Check what container is mounting
cat ~/Work/lscore-deploy/local/podman-compose.yml | grep "/dev/src"

# 3. Check if container sees the change
podman exec okp-mcp cat /dev/src/okp_mcp/solr.py | grep -A5 "EXTRACTION_BOOST_KEYWORDS"
```

**Fix:** Ensure `update_compose_mount()` successfully updates the mount path.

### Metrics Don't Change After Code Modification (Cached Results)

**Symptom:**
```
Iteration 1: URL F1 = 0.50 ← Works correctly
Applied change: Added "container" to boost keywords
Restarted container
Iteration 2: URL F1 = 0.50 ← Same value! Change had no effect?
```

**Cause:** MCP direct mode cache returns stale results.

The MCP direct client caches responses based on query text only. The cache key **does not include**:
- Solr configuration (boost keywords, field weights, etc.)
- okp-mcp code changes
- Container state

So after modifying `okp-mcp/src/okp_mcp/solr.py` and restarting the container, the cache still returns results from **before the code change**.

**Cache key formula:**
```python
# Only these are hashed to create cache key:
cache_key = hash(query, provider, model, system_prompt, attachments)

# These are NOT in the cache key:
# - Solr boost keywords ❌
# - Field weights ❌
# - BM25 parameters ❌
# - Any okp-mcp code ❌
```

**Check if this is the issue:**
```bash
# 1. Check cache directory exists
ls -lh .caches/mcp_direct_cache/

# 2. Check cache modification time
stat .caches/mcp_direct_cache/cache.db

# 3. Clear cache manually
rm -rf .caches/mcp_direct_cache/

# 4. Re-run evaluation - metrics should change now
```

**Fix:** Already fixed in `scripts/okp_mcp_agent.py` line 2311-2313.

The agent now **automatically clears the MCP cache** after every code change:

```python
# After restarting container
self.restart_okp_mcp()

# CRITICAL: Clear cache (cache key doesn't include Solr config)
self._clear_mcp_cache()

# Now re-evaluate with fresh (uncached) results
current_result = self.diagnose_retrieval_only(ticket_id)
```

## Configuration Files

### Test Suites

- **`config/okp_mcp_test_suites/functional_tests_full.yaml`**
  - Full evaluation with answer generation
  - Includes `expected_response`, `expected_keywords`, `forbidden_claims`
  - Used by `diagnose()` and full-mode iterations

- **`config/okp_mcp_test_suites/functional_tests_retrieval.yaml`**
  - Retrieval-only mode (no answer generation)
  - Only includes `expected_urls` and retrieval metrics
  - Used by `diagnose_retrieval_only()` for fast iteration
  - **⚠️ IMPORTANT:** Keep in sync with `functional_tests_full.yaml`!

### System Configs

- **`config/system_okp_mcp_agent.yaml`**
  - Focused config for agent use
  - Only 6 metrics (not all 20+)
  - Faster evaluation (~3 min vs ~10 min)

- **`config/system_mcp_direct.yaml`**
  - Retrieval-only config
  - Only 3 metrics: `url_retrieval_eval`, `context_precision`, `context_relevance`
  - Used for fast iteration (~30 sec)

## Advanced Usage

### Model Escalation

**Automatic escalation path:**
1. Start with **Haiku** (classification only)
2. Try **Sonnet** for suggestions (default)
3. After 2 failed attempts → **Opus**
4. After 2 more failed attempts → **Human**

**Override starting model:**
```python
# In code (not exposed via CLI yet)
fix_ticket_with_iteration(ticket_id, starting_model="complex")  # Start with Opus
```

### Plateau Detection

If metrics don't improve for 2 iterations → forces model escalation.

**Thresholds** (in `scripts/okp_mcp_agent.py`):
```python
ESCALATION_THRESHOLD = 2  # Failed attempts before escalating
PLATEAU_THRESHOLD = 2     # Iterations without improvement
MIN_IMPROVEMENT_THRESHOLD = 0.05  # Minimum improvement to accept
```

### Iteration History

Claude sees what was tried before:
```python
iteration_history = [
    {
        "iteration": 1,
        "change": "Add 'compatibility matrix' to boost keywords",
        "metric_before": 0.00,
        "metric_after": 0.45,
        "improved": True,
    },
    # ... previous attempts
]
```

This helps Claude avoid repeating failed approaches.

## Development

### Running Tests

```bash
# All quality checks (same as CI)
make pre-commit

# Individual checks
make black-format  # Format code
make ruff         # Lint
make pylint       # Lint
make bandit       # Security scan
make test         # Pytest
```

### Adding Support for New Parameter Types

To add a new Solr parameter type to the agent:

1. **Add detection pattern** in `apply_code_change()`:
```python
elif 'NEW_PARAM' in suggestion.code_snippet:
    # Extract and apply new parameter
```

2. **Add regex pattern** to extract value from `code_snippet`

3. **Test manually:**
```bash
uv run python -m scripts.okp_mcp_agent diagnose RSPEED-XXXX
# Check that Claude suggests the new parameter correctly
```

See `scripts/okp_mcp_agent.py` lines 1810-1995 for examples.

## See Also

- [SOLR_EXPERT_AGENT.md](./SOLR_EXPERT_AGENT.md) - Details on Solr optimization capabilities
- [DESIGN_INTENT_AND_INTEGRATION.md](./DESIGN_INTENT_AND_INTEGRATION.md) - Architecture and design decisions
- [OKP_MCP_INTEGRATION.md](./OKP_MCP_INTEGRATION.md) - Integration with okp-mcp
- [okp-mcp INCORRECT_ANSWER_LOOP.md](https://github.com/RedHatInsights/okp-mcp/blob/main/INCORRECT_ANSWER_LOOP.md) - Original workflow

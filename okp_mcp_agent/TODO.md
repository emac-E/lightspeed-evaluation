# OKP-MCP Agent Migration TODO

## 🚀 Before Moving to okp-mcp Repo

- [ ] Verify all import fixes work
  ```bash
  python okp_mcp_agent/agents/okp_mcp_agent.py --help
  python okp_mcp_agent/runners/run_pattern_fix_poc.py --help
  ```

- [ ] Run agent tests to ensure nothing broke
  ```bash
  uv run pytest okp_mcp_agent/tests/ -v
  ```

- [ ] Update any remaining `scripts/` references in docstrings/comments

- [ ] Create final commit in lightspeed-evaluation
  ```bash
  git add okp_mcp_agent/
  git commit -m "Prepare agent system for migration to okp-mcp"
  ```

---

## 📦 After Moving to okp-mcp Repo

### 1. Setup Python Package Structure

- [ ] Create `okp-mcp/pyproject.toml` (or update existing)

**Add to pyproject.toml:**
```toml
[project]
name = "okp-mcp"
version = "0.1.0"
dependencies = [
    # Core dependencies
    "pydantic>=2.0",
    "httpx",
    "requests",
    "pandas",
    "pyyaml",
    "diskcache",
    
    # Agent-specific
    "claude-agent-sdk",  # For LLM advisor
    
    # Core dependency: evaluation framework
    "lightspeed-evaluation",  # Provides evaluation capabilities
]

[project.optional-dependencies]
agents = [
    "claude-agent-sdk",  # Only needed if using autonomous agents
]

[tool.uv]
packages = [
    { include = "okp_mcp", from = "src" },
    { include = "agents" }  # Agent system
]
```

### 2. Generate Lock File

- [ ] Generate new uv.lock for okp-mcp
  ```bash
  cd ~/Work/okp-mcp
  uv lock
  ```

- [ ] Verify dependencies resolve correctly
  ```bash
  uv sync
  uv sync --group agents  # If using optional group
  ```

### 3. Update Import Paths (if needed)

If moving agents/ to a different location in okp-mcp, update:

- [ ] Check if any paths need adjustment for okp-mcp repo structure
- [ ] Update sys.path manipulation in scripts (lines 40-43 in okp_mcp_agent.py)
- [ ] Update config paths if test_suites/ moves

### 4. Update Documentation

- [ ] Create `agents/README.md` with:
  - What the agent system does
  - How to install with agents extras
  - Quick start examples
  - Link to full docs

- [ ] Update okp-mcp main README to mention agent system

- [ ] Move `okp_mcp_agent/docs/` content to okp-mcp docs folder

### 5. CI/CD Integration

- [ ] Add agent tests to okp-mcp CI
  ```yaml
  # .github/workflows/test-agents.yml
  - name: Test Agent System
    run: |
      uv sync --group agents
      uv run pytest agents/tests/ -v
  ```

- [ ] Add environment variable requirements to CI:
  - `GOOGLE_APPLICATION_CREDENTIALS` (for Gemini)
  - `ANTHROPIC_VERTEX_PROJECT_ID` (for Claude advisor)

### 6. Verify End-to-End

- [ ] Test agent runs evaluation using lightspeed-evaluation
  ```bash
  cd ~/Work/okp-mcp
  uv run python agents/okp_mcp_agent.py diagnose RSPEED-2482
  ```

- [ ] Test pattern fix POC
  ```bash
  uv run python agents/runners/run_pattern_fix_poc.py RHEL10_DEPRECATED_FEATURES
  ```

- [ ] Test bootstrap workflow
  ```bash
  uv run python agents/bootstrap/fetch_jira_open_tickets.py
  ```

---

## 🗂️ Directory Structure After Move

```
okp-mcp/
├── pyproject.toml          # ✅ NEW: Add agent dependencies
├── uv.lock                 # ✅ NEW: Generate after adding deps
├── src/okp_mcp/            # Existing okp-mcp code
│   └── ...
├── agents/                 # ✅ MOVED: From lightspeed-evaluation
│   ├── README.md           # ✅ NEW: Agent system overview
│   ├── agents/
│   │   ├── okp_mcp_agent.py
│   │   ├── okp_mcp_llm_advisor.py
│   │   └── ...
│   ├── bootstrap/
│   ├── pattern_discovery/
│   ├── runners/
│   ├── core/
│   ├── tests/
│   ├── config/
│   └── docs/
└── README.md               # ✅ UPDATE: Mention agent system
```

---

## ⚠️ Important Notes

### Dependency on lightspeed-evaluation

The agent system will **always depend on lightspeed-evaluation** because:
- It uses `EvaluationPipeline` to run evals
- It uses evaluation metrics (`url_retrieval_eval`, etc.)
- It reads/writes evaluation configs (YAML)
- It parses evaluation results (CSV)

**This is correct!** The agent is an **autonomous operator** of the evaluation framework, not a replacement for it.

### Environment Variables

Agents require:
```bash
# For running evaluations (Gemini judge)
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

# For AI-powered suggestions (Claude advisor)
export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id
gcloud auth application-default login

# For API evaluation (optional)
export API_KEY=your-lightspeed-api-key
```

### Testing Strategy

1. **Unit tests**: `agents/tests/` (agent-specific logic)
2. **Integration tests**: Require both okp-mcp and lightspeed-evaluation
3. **E2E tests**: Full workflow (JIRA → pattern discovery → fix → validate)

---

## 📋 Migration Checklist

**Pre-Migration:**
- [ ] All imports fixed (see IMPORT_FIXES_NEEDED.md)
- [ ] Tests pass in lightspeed-evaluation
- [ ] Documentation updated

**Migration:**
- [ ] Copy `okp_mcp_agent/` → `okp-mcp/agents/`
- [ ] Update okp-mcp pyproject.toml
- [ ] Generate uv.lock
- [ ] Update paths if needed

**Post-Migration:**
- [ ] Tests pass in okp-mcp
- [ ] CI/CD configured
- [ ] Documentation published
- [ ] README updated

**Cleanup (lightspeed-evaluation):**
- [ ] Remove `src/lightspeed_evaluation/agents/` (now in okp-mcp)
- [ ] Keep evaluation framework in lightspeed-evaluation
- [ ] Update README to link to okp-mcp for agent features

---

## 🔗 Related Files

- `IMPORT_FIXES_NEEDED.md` - Import fixes applied
- `BRANCH_ORGANIZATION_REPORT.md` - What moved where (in main repo)
- `docs/api/` - API documentation (move to okp-mcp docs)
- `docs/PATTERN_FIX_LOOP_SPEC.md` - Design specs (move to okp-mcp)

---

**Last Updated:** 2026-04-09  
**Status:** Ready for migration to okp-mcp repo

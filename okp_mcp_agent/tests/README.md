# Multi-Agent JIRA Extraction Tests

## Status: Partial Implementation

### What Works ✅
- **Solr Expert Agent**: Tests pass (`TP-004`, `TP-005`)
  - Direct Solr querying
  - Verification workflow
- **Test Plan**: Documented in `TEST_PLAN.md`
- **Test Structure**: Proper pytest organization

### What Doesn't Work ❌
- **Claude Agent SDK**: All tests fail with "Command failed with exit code 1"
  - Affects: `TP-001`, `TP-002`, `TP-003`, `TP-006`, `TP-007`, `TP-008`
  - Issue: Claude CLI subprocess fails when invoked via pytest
  - Works: Same code works fine in standalone scripts

## Known Issue: Claude Agent SDK + Pytest Incompatibility

**Symptom:** Claude Agent SDK fails when called from pytest but works in standalone scripts.

**Error:**
```
Exception: Command failed with exit code 1 (exit code: 1)
Error output: Check stderr output for details
```

**Investigation:**
1. ✅ Simple prompts work standalone
2. ✅ Long prompts work standalone  
3. ✅ Class methods work standalone
4. ✅ Location (src/ vs tests/) doesn't matter for standalone
5. ❌ ALL Claude SDK calls fail under pytest

**Root Cause:** Unknown - likely related to:
- Pytest's process/environment handling
- Subprocess spawning under pytest
- Missing `.claude_config.json` (but standalone works without it)

## Current Workaround

Two options:
1. **Skip Claude tests in pytest**: Mark with `@pytest.mark.skip(reason="Claude SDK pytest issue")`
2. **Use standalone agents**: `agents_standalone.py` (copy of src/ agents in tests/)

## Running Tests

```bash
# Run all tests (Solr tests will pass, Claude tests will fail)
source .env && uv run pytest tests/agents/ -v

# Run only Solr tests
source .env && uv run pytest tests/agents/ -k "Solr" -v

# Skip failing Claude tests
source .env && uv run pytest tests/agents/ -v --ignore-glob="*claude*"
```

## Next Steps

1. **Option A**: Debug Claude Agent SDK subprocess issue under pytest
2. **Option B**: Switch to Anthropic Python SDK (simpler, no subprocess)
3. **Option C**: Accept limitation and document workaround

Recommendation: **Option B** - Use Anthropic Python SDK directly for simpler, more reliable testing.

# HEAL Migration Checklist

## Pre-Migration Cleanup Tasks

### 🔒 Security & Sensitive Data
- [ ] Remove any API keys, tokens, or credentials from code/docs
- [ ] Check artifacts for customer/internal data
- [ ] Review JIRA ticket data in `okp_mcp_agent/artifacts/` for sensitive info
- [ ] Scan for hardcoded URLs/hostnames that shouldn't be public
- [ ] Run `make detect-secrets` and fix any issues

### 📁 File Cleanup
- [ ] Remove large artifact files (>100KB) or move to .gitignore
- [ ] Clean up temporary/test files
- [ ] Remove or archive old planning docs (`plans_04032026.txt`, etc.)
- [ ] Consolidate duplicate documentation
- [ ] Remove `IMPORT_FIXES_NEEDED.md` (internal notes)
- [ ] Archive bootstrap artifacts (keep structure, remove large data files)

### 📝 Documentation Quality
- [ ] Review and update `okp_mcp_agent/README.md` (make it the main entry point)
- [ ] Ensure `QUICKSTART.md` has no internal references
- [ ] Update `TODO.md` to remove completed items
- [ ] Check all docs for broken links
- [ ] Add clear license headers (Apache 2.0)
- [ ] Create comprehensive main README for HEAL

### 🧹 Code Quality
- [ ] Run `make pre-commit` and fix all issues
- [ ] Run `make test` and ensure all tests pass
- [ ] Remove commented-out code
- [ ] Fix all TODO/FIXME comments or document them
- [ ] Ensure all imports work standalone (no lightspeed-evaluation deps in core)

### 📦 Dependencies
- [ ] Create standalone `pyproject.toml` for HEAL
- [ ] List only necessary dependencies (no evaluation framework deps)
- [ ] Document MCP server requirements
- [ ] Document Claude SDK requirements

### 🎯 Branding
- [ ] Replace "okp_mcp_agent" references with "heal" in code
- [ ] Update module names: `okp_mcp_agent` → `heal`
- [ ] Update CLI commands and script names
- [ ] Create HEAL acronym expansion in README
- [ ] Design/add project logo or badge (optional)

### 📊 Content Review
- [ ] Decide which artifacts to keep (functional tests vs bootstrap data)
- [ ] Keep: `config/test_suites/functional_tests*.yaml`
- [ ] Archive: `artifacts/bootstrap_20260407/` (too large/specific)
- [ ] Keep: Pattern definitions in `config/patterns_v2/`
- [ ] Review: `config/tickets_SME_needed.yaml` (customer data?)

### 🔧 Repository Structure
- [ ] Plan final directory structure for HEAL
- [ ] Decide on top-level organization (src/heal vs heal/)
- [ ] Prepare .gitignore for new repo
- [ ] Prepare GitHub templates (ISSUE_TEMPLATE, PR_TEMPLATE)

## Migration Execution Tasks

### Repository Creation
- [ ] Create new repo: rhel-lightspeed/HEAL
- [ ] Set up branch protection on main
- [ ] Configure GitHub Actions/CI
- [ ] Add repository description and topics
- [ ] Set up README, LICENSE, CONTRIBUTING

### Code Migration
- [ ] Copy cleaned code to new repo
- [ ] Rename modules (okp_mcp_agent → heal)
- [ ] Test imports and functionality
- [ ] Run full test suite
- [ ] Fix any broken paths/imports

### Documentation
- [ ] Write main README with HEAL branding
- [ ] Add architecture diagram
- [ ] Document installation process
- [ ] Add examples and tutorials
- [ ] Link to MCP server setup guides

### Testing & Validation
- [ ] Full integration test with MCP servers
- [ ] Verify JIRA integration works
- [ ] Test agent workflows end-to-end
- [ ] Check all documentation links

### Launch Preparation
- [ ] Add GitHub topics/tags
- [ ] Prepare announcement blog post/docs
- [ ] Update references in other repos
- [ ] Archive or deprecate old code location

## Post-Migration Tasks
- [ ] Update lightspeed-evaluation to remove okp_mcp_agent/
- [ ] Add link from lightspeed-evaluation README to HEAL
- [ ] Monitor for issues in first week
- [ ] Respond to community feedback

---

## Notes

**HEAL Acronym Candidates:**
- **H**euristic **E**valuation **A**nd **L**earning
- **H**elper for **E**valuation **A**nd **L**earning
- **H**olistic **E**valuation **A**gent **L**oop
- **H**ealing **E**valuation **A**gent **L**ogic
- _(Add your chosen expansion here)_

**Estimated Timeline:**
- Phase 1 (Cleanup): 4-8 hours
- Phase 2 (Migration): 2-4 hours  
- Phase 3 (Testing): 2-4 hours
- **Total: 1-2 days of focused work**

**Risk Areas:**
- JIRA ticket data may contain customer info
- Artifacts folder has large files (1.4MB)
- Dependencies on lightspeed-evaluation framework
- Hard-coded internal paths/URLs

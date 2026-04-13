# HEAL Migration Quick Start

**TL;DR:** Move `okp-mcp-integration` code to new public repo `rhel-lightspeed/HEAL`

---

## The Simple Version (1-2 days)

### Morning: Cleanup & Prep

```bash
# 1. Security scan
make detect-secrets

# 2. Archive sensitive files (automated)
./migrate_to_heal.sh
# Select: 2 (Archive sensitive files)

# 3. Review and clean TODO.md
nano okp_mcp_agent/TODO.md
```

### Afternoon: Copy & Rename

```bash
# 4. Create new repo structure (automated)
./migrate_to_heal.sh
# Select: 3 (Create destination directory)

# 5. Copy and rename files (automated)
./migrate_to_heal.sh
# Select: 4 (Copy and rename)

# 6. Create pyproject.toml (from guide template)
cd ~/Work/rhel-lightspeed/HEAL
# Copy template from HEAL_MIGRATION_GUIDE.md Phase 5

# 7. Set up uv and install dependencies
uv sync --group dev

# 8. Test it works
uv run python -c "import heal; print('OK')"
uv run pytest tests/ -v
```

### Next Morning: Documentation & Push

```bash
# 7. Create project files
# Copy templates from HEAL_MIGRATION_GUIDE.md:
#   - pyproject.toml
#   - README.md
#   - LICENSE
#   - CONTRIBUTING.md

# 8. Create GitHub repo
# Go to github.com/rhel-lightspeed → New Repository → "HEAL"

# 9. Push to GitHub
cd ~/Work/rhel-lightspeed/HEAL
git add .
git commit -m "feat: Initial HEAL repository"
git remote add origin git@github.com:rhel-lightspeed/HEAL.git
git push -u origin main

# 10. Update original repo
cd /home/emackey/Work/lightspeed-core/lightspeed-evaluation
# Add deprecation notice to okp_mcp_agent/README.md
```

---

## Or Use Full Automation

```bash
# Run automated migration (steps 2-4)
./migrate_to_heal.sh
# Select: 6 (Full automated migration)

# Then just do documentation and push (steps 7-10)
```

---

## Files Created for You

- ✅ **HEAL_MIGRATION_CHECKLIST.md** - Complete task checklist
- ✅ **HEAL_MIGRATION_GUIDE.md** - Detailed step-by-step guide (15+ pages)
- ✅ **migrate_to_heal.sh** - Automation script
- ✅ **This file** - Quick reference

---

## What Gets Moved

✅ **Moving to HEAL (using src/ layout):**
- `okp_mcp_agent/agents/` → `src/heal/agents/` (Core agent code)
- `okp_mcp_agent/core/` → `src/heal/core/` (Linux/Solr experts)
- `okp_mcp_agent/bootstrap/` → `src/heal/bootstrap/` (JIRA extraction)
- `okp_mcp_agent/pattern_discovery/` → `src/heal/pattern_discovery/` (Pattern analysis)
- `okp_mcp_agent/tests/` → `tests/` (Test suite - top level)
- `okp_mcp_agent/docs/` → `docs/` (Documentation - top level)
- `okp_mcp_agent/config/test_suites/` → `config/test_suites/` (Functional tests)
- `okp_mcp_agent/config/patterns_v2/` → `config/patterns/` (Pattern definitions)

**Why src/ layout?** Industry standard for modern Python projects - prevents import issues and ensures proper packaging.

❌ **NOT Moving (archived):**
- Large log files (*.log)
- Internal planning docs (plans_04032026.txt, etc.)
- Bootstrap artifacts with customer data
- Completed TODO items

---

## Critical Pre-Flight Checks

Before making repo public, verify:

1. **No secrets**: `make detect-secrets`
2. **No customer data**: Review JIRA ticket artifacts
3. **Tests pass**: `pytest tests/`
4. **Quality checks**: `make pre-commit`
5. **Imports work**: `python -c "import heal"`

---

## Post-Migration

1. Add deprecation notice to `okp_mcp_agent/README.md`
2. Link to HEAL from `lightspeed-evaluation` README
3. Configure GitHub repo settings (branch protection, topics)
4. Announce to team

---

## Timeline

- **Phase 1** (Cleanup): 2-3 hours
- **Phase 2** (Copy/Rename): 1-2 hours
- **Phase 3** (Documentation): 1-2 hours
- **Phase 4** (GitHub setup): 30 min
- **Total**: 5-8 hours spread over 1-2 days

---

## Need Help?

- **Detailed guide**: See `HEAL_MIGRATION_GUIDE.md`
- **Checklist**: See `HEAL_MIGRATION_CHECKLIST.md`
- **Automation**: Run `./migrate_to_heal.sh`

---

## HEAL Acronym

Pick your favorite or create your own:
- **H**euristic **E**valuation **A**nd **L**earning
- **H**elper for **E**valuation **A**nd **L**earning  
- **H**olistic **E**valuation **A**gent **L**oop
- **H**ealing **E**valuation **A**gent **L**ogic

_(Update README with your choice)_

---

**Ready?** Start with `./migrate_to_heal.sh` or follow the detailed guide! 🚀

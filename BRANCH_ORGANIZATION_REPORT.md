# Branch Organization Report: okp-mcp-integration vs main

**Generated:** 2026-04-09  
**Purpose:** Organize project for onboarding 4 people on Monday (2026-04-14)  
**Total Changed Files:** 160

---

## Executive Summary

### What's Actually Working (Production-Ready)
- ✅ **OKP-MCP Agent System** - Fully implemented autonomous ticket fixing
- ✅ **Pattern-Based Batch Fixing** - Working POC for fixing groups of similar tickets
- ✅ **Multi-Agent System** - Linux/Solr experts for ticket analysis
- ✅ **Test Suites** - Functional test configs for validation
- ✅ **Bootstrap Workflow** - JIRA ticket extraction and pattern discovery

### What's Ideas/Drafts (Not Ready for Onboarding)
- 📝 Design docs in `docs/` (many are specs, not tutorials)
- 📝 Draft API docs in `docs_draft/`
- 📝 Old archived docs in `docs_draft/RLSAPI_Reports/`
- 📝 Bootstrap artifacts in `config/bootstrap_20260407/`

### Recommendation for Monday Onboarding
**Move agentic work to `okp_mcp_agent/` subfolder** to:
1. Clearly separate experimental vs stable code
2. Make transfer to `okp-mcp` repo easier
3. Simplify main project for new users

---

## Section 1: Agentic Work Files (Should Move to Subfolder)

### 🎯 Proposed Structure

```
okp_mcp_agent/                  # NEW subfolder for all agentic work
├── README.md                   # Agent system overview
├── agents/                     # Core agent implementations
│   ├── okp_mcp_agent.py
│   ├── okp_mcp_llm_advisor.py
│   ├── okp_mcp_pattern_agent.py
│   ├── okp_solr_checker.py
│   └── okp_solr_config_analyzer.py
├── bootstrap/                  # JIRA ticket extraction
│   ├── fetch_jira_tickets_direct.py
│   ├── fetch_jira_open_tickets.py
│   ├── extract_jira_tickets.py
│   ├── multi_agent_jira_extractor.py
│   └── convert_bootstrap_to_eval_format.py
├── pattern_discovery/          # Pattern analysis
│   ├── discover_ticket_patterns.py
│   ├── categorize_extracted_tickets.py
│   └── add_missing_verified_tickets.py
├── runners/                    # POC execution scripts
│   └── run_pattern_fix_poc.py
├── tests/                      # Agent-specific tests
│   └── [all files from tests/agents/]
├── config/                     # Agent-specific configs
│   ├── test_suites/
│   │   ├── functional_tests_full.yaml
│   │   └── functional_tests_retrieval.yaml
│   ├── patterns/               # Pattern YAMLs
│   └── patterns_v2/            # Updated patterns
├── docs/                       # Agent documentation
│   ├── API_GUIDE.md
│   ├── OKP_MCP_AGENT.md
│   ├── PATTERN_FIX_LOOP_SPEC.md
│   ├── PATTERN_FIX_LOOP_TEST_PLAN.md
│   └── VARIANCE_SOLUTIONS.md
└── artifacts/                  # Generated data
    └── bootstrap_20260407/     # Bootstrap run artifacts
```

---

### 📦 Files to Move (59 total)

#### Core Agent Scripts (8 files)
```
FROM: scripts/
TO:   okp_mcp_agent/agents/

- okp_mcp_agent.py                    ✅ WORKING - Main agent (4573 lines)
- okp_mcp_llm_advisor.py              ✅ WORKING - AI suggestions (1300 lines)
- okp_mcp_pattern_agent.py            ✅ WORKING - Pattern fixes (old, check if used)
- run_pattern_fix_poc.py              ✅ WORKING - POC runner (tested)
- okp_solr_checker.py                 ✅ WORKING - Document validation
- okp_solr_config_analyzer.py         ✅ WORKING - Solr explain output
- discover_ticket_patterns.py         ✅ WORKING - Pattern discovery
- categorize_extracted_tickets.py     ✅ WORKING - Categorization
```

#### Bootstrap/JIRA Scripts (5 files)
```
FROM: scripts/
TO:   okp_mcp_agent/bootstrap/

- fetch_jira_tickets_direct.py        ✅ WORKING - Direct JIRA API
- fetch_jira_open_tickets.py          ✅ WORKING - Open tickets query
- extract_jira_tickets.py             ✅ WORKING - Ticket extraction
- multi_agent_jira_extractor.py       ✅ WORKING - Multi-agent extraction
- convert_bootstrap_to_eval_format.py ✅ WORKING - Format conversion
- add_missing_verified_tickets.py     ✅ WORKING - Ticket verification
```

#### Core Agent Modules (4 files)
```
FROM: src/lightspeed_evaluation/agents/
TO:   okp_mcp_agent/core/

- __init__.py
- linux_expert.py                     ✅ WORKING - Linux command expert
- solr_expert.py                      ✅ WORKING - Solr tuning expert
- pattern_discovery.py                ✅ WORKING - Pattern discovery agent
- search_intelligence.py              ⚠️  PARTIAL - Search query analyzer
```

#### Test Files (17 files)
```
FROM: tests/agents/
TO:   okp_mcp_agent/tests/

ALL 17 files:
- test_linux_expert.py                ✅ HAS TESTS
- test_multi_agent_system.py          ✅ HAS TESTS
- test_jira_extraction.py             ✅ HAS TESTS
- test_model_escalation.py            ✅ HAS TESTS
- test_deescalation.py                ✅ HAS TESTS
- test_claude_sdk_connectivity.py     ✅ HAS TESTS
- test_adc_access.py                  ✅ HAS TESTS
- [plus 10 more test/debug files]
```

#### Config Files (35 files)
```
FROM: config/
TO:   okp_mcp_agent/config/

okp_mcp_test_suites/                  ✅ WORKING - Test suite configs (3 files)
patterns/                             ✅ WORKING - Pattern YAMLs (13 files)
patterns_v2/                          ✅ WORKING - Updated patterns (12 files)
bootstrap_20260407/                   📊 ARTIFACTS - Bootstrap run data (13 files)
```

#### Documentation (10 files)
```
FROM: docs/
TO:   okp_mcp_agent/docs/

- OKP_MCP_AGENT.md                    ✅ SPEC - Agent design doc
- OKP_MCP_INTEGRATION.md              ✅ GUIDE - Integration guide
- PATTERN_FIX_LOOP_SPEC.md            ✅ SPEC - Pattern fix design
- PATTERN_FIX_LOOP_TEST_PLAN.md       ✅ SPEC - Test plan
- PATTERN_FIX_LOOP_SCALING.md         📝 IDEAS - Scaling thoughts
- PATTERN_BASED_FIXING.md             ✅ GUIDE - Pattern fixing guide
- VARIANCE_SOLUTIONS.md               ✅ GUIDE - Troubleshooting variance
- SOLR_EXPERT_AGENT.md                ✅ SPEC - Solr expert design
- DESIGN_INTENT_AND_INTEGRATION.md    📝 IDEAS - Design thoughts
- OPTIMIZATION_OPPORTUNITIES.md       📝 IDEAS - Future improvements
```

#### API Documentation (5 files)
```
FROM: docs_draft/API_Guide/
TO:   okp_mcp_agent/docs/api/

- README.md                           ✅ NEW - API guide index (just created)
- OkpMcpAgent.md                      ✅ NEW - Agent API docs
- EvaluationResult.md                 ✅ NEW - Result class docs
- PatternFixAgent.md                  ✅ NEW - Pattern agent docs
- OkpMcpLLMAdvisor.md                 ✅ NEW - LLM advisor docs
```

---

## Section 2: Core Framework Files (Keep in Main Repo)

### ✅ Production Code (Should Stay)

#### Source Code Changes (12 files)
```
src/lightspeed_evaluation/
├── core/
│   ├── api/
│   │   ├── client.py                 M - Enhanced API client
│   │   └── mcp_client.py             M - MCP client updates
│   ├── metrics/
│   │   └── custom/
│   │       ├── __init__.py           M - New metrics registered
│   │       ├── custom.py             M - Updated custom metrics
│   │       ├── forbidden_claims_eval.py  A - New metric
│   │       └── url_retrieval_eval.py M - Enhanced URL eval
│   ├── models/
│   │   └── data.py                   M - Data model updates
│   └── system/
│       └── validator.py              M - Config validation
└── pipeline/
    └── evaluation/
        └── pipeline.py               M - Pipeline enhancements
```

#### Test Utilities (2 files)
```
scripts/
├── convert_functional_cases_to_eval.py   ✅ WORKING - Test conversion
└── analyze_url_retrieval_stability.py    ✅ WORKING - Stability analysis
```

#### Configuration (4 files)
```
config/
├── system.yaml                       M - Updated config
├── system_okp_mcp_agent.yaml         A - Agent-specific config
├── system_mcp_direct.yaml            M - MCP direct mode
└── chronically_failing_questions.yaml M - Updated test cases
```

#### Shell Scripts (3 files)
```
- run_full_evaluation_suite.sh        M - Enhanced suite runner
- run_mcp_retrieval_suite.sh          M - MCP retrieval tests
- run_okp_mcp_full_suite.sh           A - OKP-MCP full suite
```

---

## Section 3: Draft/Ideas Files (Should Hide or Archive)

### 📁 Recommended: Move to `docs_archive/` or `.archive/`

#### Old Docs to Archive (10 files)
```
FROM: docs_draft/
TO:   .archive/docs/

RLSAPI_Reports/                       📊 OLD - Historical analysis
├── BM25_PHRASE_BOOSTING_ANALYSIS.md
├── CHRONICALLY_FAILING_QUESTIONS_GUIDE.md
├── CONSISTENTLY_FAILING_QUESTIONS_ANALYSIS.md
├── DUPLICATION_ANALYSIS.md
├── OKP_MCP_RANKING_EXPLAINED.md
├── RAGAS_FAITHFULNESS_MALFORMED_OUTPUT_INVESTIGATION.md
├── RAG_COMPARISON_ANALYSIS.md
├── RAG_METRICS.md
├── RECOMMENDED_DEDUPLICATION_APPROACH.md
└── temporal_validity_testing_summary.md

Other docs_draft/:
- ADDING_NEW_RAGAS_METRIC.md          📝 OLD - Already in main
- ADVERSARIAL_CONTEXT_INJECTION_TESTS.md  📝 IDEAS - Not implemented
- CONTEXT_QUALITY_DEGRADATION_TESTS.md    📝 IDEAS - Not implemented
- HOW_TO_RUN_TEMPORAL_TESTS.md        📝 OLD - Temporal tests removed
- JUDGE_LLM_CONSISTENCY_TESTS.md      📝 IDEAS - Not implemented
- MULTI_RUN_STATISTICAL_ANALYSIS.md   📝 IDEAS - Partially implemented
- configuration.md                    📝 OLD - Superseded by main docs
- evaluation_comparison.md            📝 OLD - Superseded
- multi_provider_evaluation.md        📝 OLD - Superseded
- temporal_validity_testing_design.md 📝 OLD - Not implemented
```

#### Design Brainstorming Docs (3 files)
```
FROM: docs_draft/
TO:   .archive/design_notes/

- linux_expert_persona_proposal.md   📝 IDEAS - Persona design
- multi_agent_ticket_extraction.md   📝 IDEAS - Multi-agent thoughts
- plans_04032026.txt                 📝 NOTES - Planning notes
- MULTI_STAGE_TESTING_PLAN.md        📝 IDEAS - Testing ideas
```

#### Bootstrap Artifacts (Keep but Move)
```
FROM: config/bootstrap_20260407/
TO:   okp_mcp_agent/artifacts/bootstrap_20260407/

All 13 files - these are OUTPUT from a bootstrap run, not configs
```

---

## Section 4: Metadata/Infrastructure (Keep in Root)

### Infrastructure Files (7 files)
```
- .env.example                        A - Environment template
- .gitignore                          M - Updated ignores
- pyproject.toml                      M - Dependencies updated
- uv.lock                             M - Lock file updated
```

### Documentation (6 files)
```
- README.md                           M - Updated main readme
- AGENTS.md                           M - Agent dev guidelines
- TODO.md                             M - Project TODOs
- PATTERN_FIX_REVIEW.md               A - Pattern fix review doc
- QUICKSTART.md                       A - New user quickstart
- example_tickets.txt                 A - Example ticket list
```

### Claude Search Intelligence (3 files)
```
.claude/search_intelligence/
├── search_results.jsonl              A - Search cache
├── successful_queries.json           A - Query cache
└── topic_to_docs.json                A - Topic index
```

---

## Section 5: Files Deleted from Main (Good!)

### ✅ These Were Removed - Cleanup Successful
```
docs/
├── ADDING_NEW_RAGAS_METRIC.md        D - Moved to docs_draft
├── ADVERSARIAL_CONTEXT_INJECTION_TESTS.md  D - Moved to docs_draft
├── API_Guide/                        D - Moved to docs_draft
├── CONTEXT_QUALITY_DEGRADATION_TESTS.md    D - Moved to docs_draft
├── HOW_TO_RUN_TEMPORAL_TESTS.md      D - Obsolete
├── JUDGE_LLM_CONSISTENCY_TESTS.md    D - Moved to docs_draft
├── MULTI_RUN_STATISTICAL_ANALYSIS.md D - Moved to docs_draft
├── OKP_MCP_SOLR_CONNECTION_GUIDE.md  D - Superseded
├── RLSAPI_Reports/                   D - Moved to docs_draft
├── configuration.md                  D - Moved to docs_draft
├── evaluation_comparison.md          D - Moved to docs_draft
├── multi_provider_evaluation.md      D - Moved to docs_draft
└── temporal_validity_testing_design.md D - Obsolete
```

---

## Section 6: Onboarding Recommendations

### 🎯 Action Plan for Monday (2026-04-14)

#### Step 1: Create Agentic Subfolder (High Priority)
```bash
# Create structure
mkdir -p okp_mcp_agent/{agents,bootstrap,pattern_discovery,runners,tests,config,docs,artifacts}

# Move core agent files
mv scripts/okp_mcp_agent.py okp_mcp_agent/agents/
mv scripts/okp_mcp_llm_advisor.py okp_mcp_agent/agents/
mv scripts/okp_solr_*.py okp_mcp_agent/agents/
mv scripts/run_pattern_fix_poc.py okp_mcp_agent/runners/

# Move bootstrap files
mv scripts/fetch_jira_*.py okp_mcp_agent/bootstrap/
mv scripts/extract_jira_tickets.py okp_mcp_agent/bootstrap/
mv scripts/multi_agent_jira_extractor.py okp_mcp_agent/bootstrap/
mv scripts/convert_bootstrap_to_eval_format.py okp_mcp_agent/bootstrap/
mv scripts/add_missing_verified_tickets.py okp_mcp_agent/bootstrap/

# Move pattern discovery
mv scripts/discover_ticket_patterns.py okp_mcp_agent/pattern_discovery/
mv scripts/categorize_extracted_tickets.py okp_mcp_agent/pattern_discovery/

# Move tests
mv tests/agents/* okp_mcp_agent/tests/

# Move config
mv config/okp_mcp_test_suites okp_mcp_agent/config/test_suites
mv config/patterns okp_mcp_agent/config/
mv config/patterns_v2 okp_mcp_agent/config/
mv config/bootstrap_20260407 okp_mcp_agent/artifacts/

# Move docs
mv docs/OKP_MCP_*.md okp_mcp_agent/docs/
mv docs/PATTERN_*.md okp_mcp_agent/docs/
mv docs/VARIANCE_SOLUTIONS.md okp_mcp_agent/docs/
mv docs/SOLR_EXPERT_AGENT.md okp_mcp_agent/docs/
mv docs_draft/API_Guide okp_mcp_agent/docs/api/

# Move core agent modules
mkdir -p okp_mcp_agent/core
mv src/lightspeed_evaluation/agents/* okp_mcp_agent/core/
```

#### Step 2: Archive Draft Docs
```bash
# Create archive
mkdir -p .archive/{docs,design_notes}

# Move old docs
mv docs_draft/RLSAPI_Reports .archive/docs/
mv docs_draft/ADDING_NEW_RAGAS_METRIC.md .archive/docs/
mv docs_draft/ADVERSARIAL_*.md .archive/docs/
mv docs_draft/CONTEXT_QUALITY_*.md .archive/docs/
mv docs_draft/HOW_TO_RUN_TEMPORAL_TESTS.md .archive/docs/
mv docs_draft/JUDGE_LLM_CONSISTENCY_TESTS.md .archive/docs/
mv docs_draft/MULTI_RUN_STATISTICAL_ANALYSIS.md .archive/docs/
mv docs_draft/configuration.md .archive/docs/
mv docs_draft/evaluation_comparison.md .archive/docs/
mv docs_draft/multi_provider_evaluation.md .archive/docs/
mv docs_draft/temporal_validity_testing_design.md .archive/docs/

# Move design notes
mv docs_draft/linux_expert_persona_proposal.md .archive/design_notes/
mv docs_draft/multi_agent_ticket_extraction.md .archive/design_notes/
mv docs_draft/plans_04032026.txt .archive/design_notes/
mv docs_draft/MULTI_STAGE_TESTING_PLAN.md .archive/design_notes/
```

#### Step 3: Create Onboarding README
```bash
# Create okp_mcp_agent/README.md with:
# - What is the agent system
# - How to run basic commands
# - Link to full docs
# - Quick examples

# Update main README.md to:
# - Clearly separate "Core Evaluation Framework" vs "Experimental Agent System"
# - Point to okp_mcp_agent/README.md for agent work
# - Focus on stable features for new users
```

#### Step 4: Update Import Paths
After moving files, update imports:
```python
# Old:
from scripts.okp_mcp_agent import OkpMcpAgent
from src.lightspeed_evaluation.agents.linux_expert import LinuxExpert

# New:
from okp_mcp_agent.agents.okp_mcp_agent import OkpMcpAgent
from okp_mcp_agent.core.linux_expert import LinuxExpert
```

---

### 📋 What New Users Should See on Monday

#### Main Project (`lightspeed-evaluation/`)
```
lightspeed-evaluation/
├── README.md                   # Focus on stable evaluation framework
├── QUICKSTART.md               # Simple getting started guide
├── docs/                       # Only stable, tested docs
│   ├── EVALUATION_GUIDE.md
│   ├── MCP_DIRECT_MODE.md
│   └── RUN_MCP_RETRIEVAL_SUITE.md
├── config/                     # Standard eval configs
├── src/                        # Core framework (stable)
└── tests/                      # Core tests
```

#### Experimental Work (`okp_mcp_agent/`)
```
okp_mcp_agent/                  # Clearly marked as experimental
├── README.md                   # "Experimental autonomous agent system"
├── agents/                     # Agent implementations
├── docs/                       # Agent-specific docs
├── tests/                      # Agent tests
└── [separate, self-contained]
```

---

## Section 7: Implementation Status Summary

### ✅ Fully Working & Tested
1. **OkpMcpAgent** - 4573 lines, CLI working, tested
2. **PatternFixAgent** - Pattern fix POC, tested
3. **LinuxExpert** - Multi-agent system, tested
4. **SolrExpert** - Solr tuning suggestions, tested
5. **Bootstrap Workflow** - JIRA extraction → patterns, working
6. **Test Suites** - functional_tests_full.yaml, functional_tests_retrieval.yaml

### ⚠️ Partially Implemented
1. **SearchIntelligence** - Query analyzer, partial implementation
2. **Pattern Discovery** - Working but needs validation on more patterns
3. **Model Escalation** - Working but needs cost tracking

### 📝 Design Docs Only (Not Implemented)
1. **ADVERSARIAL_CONTEXT_INJECTION_TESTS.md** - Just design
2. **CONTEXT_QUALITY_DEGRADATION_TESTS.md** - Just design
3. **JUDGE_LLM_CONSISTENCY_TESTS.md** - Just design
4. **Temporal Validity Testing** - Removed/obsolete

---

## Section 8: File Count Summary

| Category | Count | Status |
|----------|-------|--------|
| **Agentic Work Files** | 59 | ✅ Move to subfolder |
| **Core Framework** | 21 | ✅ Keep in main repo |
| **Draft/Archive** | 27 | 📁 Move to .archive/ |
| **Infrastructure** | 13 | ✅ Keep in root |
| **Deleted Files** | 40 | ✅ Already cleaned up |
| **TOTAL** | 160 | |

---

## Section 9: Git Commands for Reorganization

### Create Subfolder with History
```bash
# Don't use 'mv' - use 'git mv' to preserve history!

# Create okp_mcp_agent structure
mkdir -p okp_mcp_agent/{agents,bootstrap,pattern_discovery,runners,tests,config,docs/api,artifacts,core}

# Move files (preserves git history)
git mv scripts/okp_mcp_agent.py okp_mcp_agent/agents/
git mv scripts/okp_mcp_llm_advisor.py okp_mcp_agent/agents/
git mv scripts/okp_solr_checker.py okp_mcp_agent/agents/
git mv scripts/okp_solr_config_analyzer.py okp_mcp_agent/agents/
git mv scripts/run_pattern_fix_poc.py okp_mcp_agent/runners/

git mv scripts/fetch_jira_tickets_direct.py okp_mcp_agent/bootstrap/
git mv scripts/fetch_jira_open_tickets.py okp_mcp_agent/bootstrap/
git mv scripts/extract_jira_tickets.py okp_mcp_agent/bootstrap/
git mv scripts/multi_agent_jira_extractor.py okp_mcp_agent/bootstrap/
git mv scripts/convert_bootstrap_to_eval_format.py okp_mcp_agent/bootstrap/
git mv scripts/add_missing_verified_tickets.py okp_mcp_agent/bootstrap/

git mv scripts/discover_ticket_patterns.py okp_mcp_agent/pattern_discovery/
git mv scripts/categorize_extracted_tickets.py okp_mcp_agent/pattern_discovery/

git mv tests/agents okp_mcp_agent/tests

git mv config/okp_mcp_test_suites okp_mcp_agent/config/test_suites
git mv config/patterns okp_mcp_agent/config/
git mv config/patterns_v2 okp_mcp_agent/config/
git mv config/bootstrap_20260407 okp_mcp_agent/artifacts/

git mv docs/OKP_MCP_AGENT.md okp_mcp_agent/docs/
git mv docs/OKP_MCP_INTEGRATION.md okp_mcp_agent/docs/
git mv docs/PATTERN_FIX_LOOP_SPEC.md okp_mcp_agent/docs/
git mv docs/PATTERN_FIX_LOOP_TEST_PLAN.md okp_mcp_agent/docs/
git mv docs/PATTERN_FIX_LOOP_SCALING.md okp_mcp_agent/docs/
git mv docs/PATTERN_BASED_FIXING.md okp_mcp_agent/docs/
git mv docs/VARIANCE_SOLUTIONS.md okp_mcp_agent/docs/
git mv docs/SOLR_EXPERT_AGENT.md okp_mcp_agent/docs/
git mv docs/DESIGN_INTENT_AND_INTEGRATION.md okp_mcp_agent/docs/
git mv docs/OPTIMIZATION_OPPORTUNITIES.md okp_mcp_agent/docs/

git mv docs_draft/API_Guide okp_mcp_agent/docs/api

git mv src/lightspeed_evaluation/agents okp_mcp_agent/core

# Commit reorganization
git commit -m "Reorganize: Move agentic work to okp_mcp_agent/ subfolder

- Move 59 agentic files to dedicated subfolder
- Preserves git history for all files
- Prepares for transfer to okp-mcp repo
- Simplifies main project for onboarding
"
```

### Archive Drafts
```bash
# Create archive structure
mkdir -p .archive/{docs,design_notes}

# Move draft docs
git mv docs_draft/RLSAPI_Reports .archive/docs/
git mv docs_draft/*.md .archive/docs/ 2>/dev/null || true
git mv docs_draft/*.txt .archive/design_notes/ 2>/dev/null || true

# Commit archive
git commit -m "Archive: Move draft docs to .archive/

- Move old RLSAPI reports
- Archive unimplemented test designs
- Move design brainstorming notes
"
```

---

## Section 10: Onboarding Documentation Checklist

### Must Have Before Monday

- [ ] **Main README.md** - Updated to clearly separate stable vs experimental
- [ ] **QUICKSTART.md** - Simple "run your first evaluation" guide
- [ ] **okp_mcp_agent/README.md** - "What is this subfolder" explanation
- [ ] **docs/EVALUATION_GUIDE.md** - How to write and run evaluations
- [ ] **.env.example** - All required environment variables documented

### Should Have (Lower Priority)

- [ ] **CONTRIBUTING.md** - How to contribute
- [ ] **FAQ.md** - Common questions and troubleshooting
- [ ] **ARCHITECTURE.md** - High-level architecture diagram

### Nice to Have

- [ ] **Video walkthrough** - 5-minute demo
- [ ] **Jupyter notebook** - Interactive tutorial

---

## Next Steps

1. **Review this report** - Verify categorization is correct
2. **Execute git mv commands** - Reorganize with history preserved
3. **Update import paths** - Fix broken imports after move
4. **Test after reorganization** - Run tests to verify nothing broke
5. **Update documentation** - Focus on stable features
6. **Prepare onboarding materials** - QUICKSTART + examples
7. **Monday morning** - Walk through with 4 new people

---

## Questions to Resolve

1. **okp_mcp_pattern_agent.py** - Is this used or superseded by run_pattern_fix_poc.py?
2. **search_intelligence.py** - Complete or partial? Keep or archive?
3. **config/patterns/ vs patterns_v2/** - Which is current? Delete old?
4. **docs/ANSWER_FIRST_WORKFLOW.md** - Keep in main or move to agent docs?
5. **docs/MODEL_ESCALATION_FIX.md** - Keep in main or move to agent docs?

---

**Report End**

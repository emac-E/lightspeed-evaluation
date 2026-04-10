# OKP-MCP Agent System - Quick Start Guide

Welcome! This guide will get you up and running with the OKP-MCP autonomous agent system for automated JIRA ticket processing and fixing.

## 📋 Prerequisites

Before you begin, make sure you have:

- **LightSpeed Evaluation Framework** installed (see main [docs/QUICKSTART.md](../docs/QUICKSTART.md))
- **Python 3.11+** installed
- **Claude Agent SDK** for AI-powered suggestions
- **MCP Servers** configured:
  - Atlassian/JIRA MCP server
  - Linux MCP server
- **API credentials**:
  - `ANTHROPIC_VERTEX_PROJECT_ID` - for Claude Advisor (Vertex AI)
  - `GOOGLE_APPLICATION_CREDENTIALS` - for Gemini judge
  - JIRA access token (via MCP server)

## 🚀 Installation

### Step 1: Install Agent Dependencies

From the repository root:

```bash
# Install base evaluation framework
uv sync

# Install agent-specific dependencies (Claude SDK)
uv sync --group agents  # If using optional dependency group
# OR the dependencies are already in main pyproject.toml
```

### Step 2: Configure MCP Servers

The agent system requires two MCP servers:

**1. Atlassian/JIRA MCP Server**

For fetching JIRA tickets and metadata.

```bash
# See mcp-servers/atlassian/ for setup instructions
# Configure in your Claude Desktop config or environment
```

**2. Linux MCP Server**

For Linux expertise and system knowledge.

```bash
# See MCP setup documentation
# Provides Linux commands, troubleshooting context
```

### Step 3: Set Environment Variables

Create a `.env` file in the repository root or export these variables:

```bash
# For Gemini judge (evaluation metrics)
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# For Claude Advisor (AI-powered suggestions)
export ANTHROPIC_VERTEX_PROJECT_ID=your-gcp-project-id

# Ensure gcloud auth is set up
gcloud auth application-default login

# Optional: For API evaluation
export API_KEY=your-lightspeed-api-key
```

## 🎯 Quick Test

Verify the agent system is working:

```bash
# Test agent help
python okp_mcp_agent/agents/okp_mcp_agent.py --help

# Test simple diagnosis (requires okp-mcp running)
python okp_mcp_agent/agents/okp_mcp_agent.py diagnose RSPEED-2482
```

Expected output:
- 📊 Evaluation metrics (URL F1, context relevance, answer correctness)
- 🔍 Problem classification (retrieval vs. answer issue)
- 💡 AI-powered suggestions for fixes

## 🤖 Agent Workflows

The system provides two main workflows:

### Workflow 1: Answer-First Diagnostic Agent

**What it does:**
- Diagnoses individual JIRA tickets
- Runs evaluation to identify retrieval vs. answer problems
- Provides AI-powered fix suggestions
- Fast iteration loop (30 seconds per ticket)

**When to use:** Single-ticket debugging, understanding issues, prototyping fixes.

**Commands:**

```bash
# Diagnose a ticket
python okp_mcp_agent/agents/okp_mcp_agent.py diagnose RSPEED-2482

# Fix a ticket with suggestions
python okp_mcp_agent/agents/okp_mcp_agent.py fix RSPEED-2482

# Validate all test suites
python okp_mcp_agent/agents/okp_mcp_agent.py validate
```

**Output:**
- Evaluation results (metrics, pass/fail)
- Problem diagnosis (retrieval or answer issue)
- Fix suggestions (boost query changes, prompt changes)

**Time:** ~30 seconds per ticket

---

### Workflow 2: Pattern-Based Batch Fixing

**What it does:**
- Fetches multiple JIRA tickets
- Discovers common patterns (e.g., "EOL RHEL version support")
- Fixes entire patterns (6-15 tickets) as one batch
- 10-15x more efficient than single-ticket fixing

**When to use:** Automating fixes for clustered tickets with common root causes.

**Commands:**

```bash
# Step 1: Fetch tickets and discover patterns
python okp_mcp_agent/bootstrap/fetch_jira_open_tickets.py --limit 20

# Step 2: Analyze patterns
python okp_mcp_agent/pattern_discovery/discover_ticket_patterns.py \
  --input okp_mcp_agent/artifacts/bootstrap_20260407/extracted_tickets.yaml \
  --output okp_mcp_agent/artifacts/bootstrap_20260407/patterns_report_v2.json

# Step 3: Fix a specific pattern
python okp_mcp_agent/runners/run_pattern_fix_poc.py RHEL10_DEPRECATED_FEATURES \
  --max-iterations 10 \
  --answer-threshold 0.8
```

**Output:**
- `extracted_tickets.yaml` - Verified query/answer pairs
- `tickets_with_patterns.yaml` - Tickets tagged with pattern IDs
- `patterns_report_v2.json` - Pattern analysis and grouping
- Git branch per pattern with fixes

**Time:** ~5-10 minutes for bootstrap + ~10-30 minutes per pattern fix

**Efficiency Gain:**
- Traditional: 15 tickets × 5 iterations = 75 fix attempts
- Pattern-based: 1 pattern × 5 iterations = 5 fix attempts (validates all 15 tickets each time)

---

## 📂 Directory Structure

```
okp_mcp_agent/
├── agents/                    # Core agent implementations
│   ├── okp_mcp_agent.py      # Main diagnostic agent
│   ├── okp_mcp_llm_advisor.py # AI-powered suggestions
│   └── okp_mcp_pattern_agent.py # Pattern batch fixing
├── bootstrap/                 # JIRA ticket extraction
│   ├── fetch_jira_open_tickets.py
│   └── multi_agent_jira_extractor.py
├── pattern_discovery/         # Pattern analysis
│   └── discover_ticket_patterns.py
├── core/                      # Agent components
│   ├── linux_expert.py       # Linux expertise agent
│   └── solr_expert.py        # Solr verification agent
├── runners/                   # Workflow runners
│   └── run_pattern_fix_poc.py
├── config/                    # Test suites and patterns
│   ├── test_suites/          # Functional test definitions
│   └── patterns_v2/          # Pattern definitions
├── tests/                     # Agent tests
└── docs/                      # Documentation
```

## 🔧 Configuration

### Test Suites

Agent-specific test suites are in `okp_mcp_agent/config/test_suites/`:

- `functional_tests_full.yaml` - Complete test suite (all metrics)
- `functional_tests_retrieval.yaml` - Retrieval-only tests (faster)
- `functional_tests.yaml` - Basic subset

### Pattern Definitions

Patterns are defined in `okp_mcp_agent/config/patterns_v2/`:

- `RHEL10_DEPRECATED_FEATURES.yaml` - RHEL 10 deprecation issues
- `EOL_RHEL_VERSION_SUPPORT.yaml` - End-of-life RHEL versions
- `CONTAINER_UNSUPPORTED_CONFIG.yaml` - Container configuration issues
- etc.

Each pattern contains:
- Description of the issue
- Common characteristics
- Affected ticket IDs
- Expected fix strategy

## 🐛 Common Issues

### Issue 1: "ANTHROPIC_VERTEX_PROJECT_ID not set"

**Solution**: Set up Vertex AI credentials for Claude Advisor.

```bash
export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id
gcloud auth application-default login
```

### Issue 2: "JIRA MCP server not responding"

**Solution**: Ensure MCP servers are configured and running.

Check your MCP server configuration and restart if needed.

### Issue 3: "No GOOGLE_APPLICATION_CREDENTIALS"

**Solution**: This is for the Gemini judge used in evaluation metrics.

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
```

### Issue 4: Import errors from okp_mcp_agent

**Solution**: Make sure you're running from the repository root.

```bash
cd /path/to/lightspeed-evaluation
python okp_mcp_agent/agents/okp_mcp_agent.py diagnose TICKET-ID
```

## 📚 Next Steps

1. **Try Answer-First Workflow**
   - Diagnose a few tickets: `python okp_mcp_agent/agents/okp_mcp_agent.py diagnose RSPEED-2482`
   - Review suggestions and metrics
   - See [docs/ANSWER_FIRST_WORKFLOW.md](docs/ANSWER_FIRST_WORKFLOW.md)

2. **Extract and Analyze Patterns**
   - Fetch 10-20 tickets: `python okp_mcp_agent/bootstrap/fetch_jira_open_tickets.py --limit 20`
   - Discover patterns: `python okp_mcp_agent/pattern_discovery/discover_ticket_patterns.py`
   - Review pattern groupings

3. **Run Pattern-Based Fixing**
   - Fix a small pattern first: `python okp_mcp_agent/runners/run_pattern_fix_poc.py RHEL10_DEPRECATED_FEATURES`
   - Validate fixes across all tickets in pattern
   - See [docs/PATTERN_FIX_LOOP_SPEC.md](docs/PATTERN_FIX_LOOP_SPEC.md)

4. **Explore API Documentation**
   - [OkpMcpAgent API](docs/OkpMcpAgent.md)
   - [PatternFixAgent API](docs/PatternFixAgent.md)
   - [OkpMcpLLMAdvisor API](docs/OkpMcpLLMAdvisor.md)
   - [EvaluationResult API](docs/EvaluationResult.md)

## 🔬 Understanding the Workflow

### Answer-First Diagnostic Flow

```
┌─────────────────┐
│  JIRA Ticket    │
│  RSPEED-2482    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Run Evaluation │ ← Query okp-mcp, get response
│  5 metrics      │ ← URL retrieval, context, answer
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Classify Issue │ ← Retrieval problem? Answer problem?
│  Get Suggestions│ ← AI-powered fix recommendations
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Apply Fix      │ ← Modify boost query or prompt
│  Re-evaluate    │ ← Verify improvement
└─────────────────┘
```

### Pattern-Based Batch Flow

```
┌─────────────────┐
│  Fetch Tickets  │ ← Get 10-20 JIRA tickets
│  Multi-agent   │ ← Linux + Solr verification
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Discover       │ ← Cluster by similarity
│  Patterns       │ ← Group 6-15 tickets per pattern
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Fix Pattern    │ ← One fix for entire pattern
│  Validate Batch │ ← Test against all tickets
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Git Branch     │ ← Create branch: fix/pattern-{id}
│  Review Report  │ ← Pass rate, metrics, suggestions
└─────────────────┘
```

## 🆘 Getting Help

- **Agent Documentation**: Browse `okp_mcp_agent/docs/`
- **API Reference**: See `okp_mcp_agent/docs/README.md`
- **Tests**: Check `okp_mcp_agent/tests/` for examples
- **Migration Guide**: See `okp_mcp_agent/TODO.md` for moving to okp-mcp repo

---

**🎉 Ready to go!** Start with single-ticket diagnosis, then scale up to pattern-based batch fixing for maximum efficiency.

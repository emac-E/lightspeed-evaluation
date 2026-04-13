# LightSpeed Evaluation Framework
## Onboarding Guide for New Contributors

---

## What Is This Project?

A comprehensive framework for evaluating GenAI applications (chatbots, RAG systems, AI assistants) with:

- **Multi-framework support**: Ragas, DeepEval, custom metrics
- **Turn & conversation-level evaluation**: Single queries + multi-turn dialogs
- **LLM provider flexibility**: OpenAI, Gemini, Watsonx, vLLM, and more
- **Rich output**: CSV, JSON, TXT reports + visualizations (heatmaps, distributions)
- **Panel of judges**: Multiple LLMs evaluate to reduce bias

**Status**: Active development, work-in-progress with expanding features

---

## Branch Overview

### Main Branch: Core Evaluation Framework

**What it does:**
- Evaluates RAG/chatbot responses against expected answers
- Measures faithfulness, relevance, answer correctness, context quality
- Supports both API-enabled (real-time) and static data evaluation
- Generates detailed reports with statistics and visualizations

**Key features:**
- 6+ Ragas metrics (faithfulness, context_recall, response_relevancy, etc.)
- Custom metrics (answer_correctness, intent_eval, keywords_eval, tool_eval)
- Script-based evaluations for infrastructure changes
- Token usage tracking and streaming performance metrics
- Caching for faster re-runs

**Use case:** Testing and validating GenAI applications at scale

---

### OKP-MCP Integration Branch: Autonomous Agent System

**What it adds:**
- Autonomous agents for diagnosing and fixing RAG retrieval issues
- Multi-agent system with Linux Expert, Solr Expert, Pattern Discovery
- JIRA ticket integration for automated bug processing
- Answer-First Workflow: Start with just question + answer, discover documents automatically

**Key features:**

1. **Answer-First Diagnostic Agent**
   - Diagnose individual JIRA tickets (~30 sec per ticket)
   - Classify retrieval vs. answer issues
   - AI-powered fix suggestions (Claude Advisor)

2. **Pattern-Based Batch Fixing**
   - Fetch multiple JIRA tickets
   - Discover common patterns (e.g., "EOL RHEL version support")
   - Fix entire patterns (6-15 tickets) as one batch
   - **10-15x more efficient** than single-ticket fixing

3. **Multi-Agent Orchestration**
   - Linux Expert: Validates Linux commands/concepts
   - Solr Expert: Verifies Solr document content
   - Pattern Discovery: Groups similar tickets

**Use case:** Automating bug fixes for RAG systems at scale

---

## Quick Start: Main Branch

### Prerequisites
- Python 3.11+
- API credentials (OpenAI, Google Cloud, etc.)
- `uv` package manager (recommended)

### Installation
```bash
# Clone repo
git clone https://github.com/your-org/lightspeed-evaluation.git
cd lightspeed-evaluation

# Switch to main branch
git checkout main

# Install dependencies
uv sync

# Install dev tools (for contributors)
make install-deps-test
```

### Configuration
```bash
# Copy example environment file
cp .env.example .env

# Edit with your credentials
nano .env  # Add OPENAI_API_KEY, GOOGLE_APPLICATION_CREDENTIALS, etc.

# Configure system settings
nano config/system.yaml  # Set LLM provider, embedding model
```

### First Run
```bash
# Run with example data
lightspeed-eval \
  --system-config config/system.yaml \
  --eval-data config/evaluation_data.yaml \
  --tags basic

# View results
cat output/lightspeed_eval_summary_*.txt
```

**What you'll see:**
- Progress output for each evaluation
- Pass/fail counts with metrics
- Reports in `output/` directory (CSV, JSON, TXT, PNG)

---

## Quick Start: OKP-MCP Integration Branch

### Prerequisites
- Everything from main branch +
- Claude Agent SDK
- MCP Servers: Atlassian/JIRA, Linux
- Additional credentials: `ANTHROPIC_VERTEX_PROJECT_ID`, JIRA access token

### Installation
```bash
# Switch to okp-mcp-integration branch
git checkout okp-mcp-integration

# Install agent dependencies
uv sync

# Configure environment
export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
gcloud auth application-default login
```

### Test Agent System
```bash
# Diagnose a single ticket
python okp_mcp_agent/agents/okp_mcp_agent.py diagnose RSPEED-2482

# Expected output:
# - Evaluation metrics (URL F1, context relevance, answer correctness)
# - Problem classification (retrieval vs. answer issue)
# - AI-powered fix suggestions
```

### Answer-First Workflow Example
```bash
# 1. Create test with just question + answer (no URLs!)
cat > config/okp_mcp_test_suites/customer_bugs.yaml <<EOF
- conversation_group_id: CUSTOMER_BUG_123
  turns:
  - query: "Is SPICE available to help with RHEL VMs?"
    expected_response: |
      SPICE is deprecated in RHEL 8.3 and removed in RHEL 9.
      Use VNC instead for VM console access.
    turn_metrics:
    - custom:answer_correctness
    - ragas:faithfulness
EOF

# 2. Diagnose (checks if answer is correct)
python okp_mcp_agent/agents/okp_mcp_agent.py diagnose CUSTOMER-BUG-123

# 3. Auto-fix with document discovery + optimization
python okp_mcp_agent/agents/okp_mcp_agent.py bootstrap CUSTOMER-BUG-123 --yolo --max-iterations 20
```

**What it does:**
1. Tests if system gives correct answer
2. If wrong, finds which documents contain the answer
3. Optimizes Solr config to retrieve those documents
4. Saves discovered URLs as regression test

---

## Directory Structure

### Main Branch
```
lightspeed-evaluation/
├── src/lightspeed_evaluation/    # Core framework
│   ├── core/                     # LLM, metrics, config, output
│   ├── pipeline/                 # Evaluation orchestration
│   └── runner/                   # CLI interface
├── config/                       # YAML configs
│   ├── system.yaml              # LLM provider, metrics config
│   └── evaluation_data.yaml     # Test cases
├── tests/                        # Test suite (pytest)
├── scripts/                      # Utility scripts
├── docs/                         # Documentation
│   ├── QUICKSTART.md            # Getting started guide
│   └── EVALUATION_GUIDE.md      # Detailed usage
└── AGENTS.md                     # AI agent guidelines
```

### OKP-MCP Integration Branch (Additional)
```
okp_mcp_agent/                    # Agent system (new!)
├── agents/                       # Core agent implementations
│   ├── okp_mcp_agent.py         # Main diagnostic agent
│   ├── okp_mcp_llm_advisor.py   # AI-powered suggestions
│   └── okp_mcp_pattern_agent.py # Pattern batch fixing
├── bootstrap/                    # JIRA ticket extraction
├── pattern_discovery/            # Pattern analysis
├── core/                         # Linux Expert, Solr Expert
├── config/                       # Test suites, patterns
│   ├── test_suites/             # functional_tests.yaml
│   └── patterns_v2/             # Pattern definitions
├── tests/                        # Agent tests
└── docs/                         # Agent documentation
    ├── QUICKSTART.md            # Agent getting started
    ├── ANSWER_FIRST_WORKFLOW.md # Answer-first guide
    └── PATTERN_FIX_LOOP_SPEC.md # Pattern fixing docs
```

---

## Development Workflow

### Before Making Changes

1. **Read the guidelines**
   ```bash
   cat AGENTS.md           # AI agent guidelines
   cat docs/QUICKSTART.md  # Usage guide
   ```

2. **Understand directory status**
   - `src/lightspeed_evaluation/` - Active development ✅
   - `lsc_agent_eval/` - Deprecated, being removed ❌
   - `okp_mcp_agent/` - Active on okp-mcp-integration branch ✅

3. **Use pytest mocking** (NOT unittest.mock)
   ```python
   # ✅ CORRECT
   def test_example(mocker):
       mocker.patch('module.function')
   
   # ❌ WRONG
   from unittest.mock import patch
   ```

### Making Changes

1. **Create a feature branch**
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make changes** following code standards:
   - Type hints required
   - Google-style docstrings
   - Use custom exceptions from `core.system.exceptions`
   - Structured logging

3. **Run quality checks** (MANDATORY before commit)
   ```bash
   # Format code
   make black-format
   
   # Run all pre-commit checks (same as CI)
   make pre-commit
   
   # Run tests
   make test
   ```

4. **Update documentation** when changing features:
   - `docs/` - Update relevant guide if behavior changes
   - `README.md` - Update when adding new features
   - `AGENTS.md` - Update if adding new conventions

5. **Commit and push**
   ```bash
   git add <files>
   git commit -m "feat: Add your feature description"
   git push origin feat/your-feature-name
   ```

---

## Tasks for New Contributors

### Beginner-Friendly Tasks

#### 1. Documentation Improvements
**Branch:** main or okp-mcp-integration  
**Effort:** Low  
**Skills:** Markdown, reading code

- Add missing docstrings to public functions
- Update outdated examples in docs/
- Create quick reference guides
- Add troubleshooting tips to QUICKSTART.md

**Example:**
```bash
# Find functions missing docstrings
grep -r "def " src/ | grep -v '"""'

# Add Google-style docstrings
```

#### 2. Test Coverage Improvements
**Branch:** main  
**Effort:** Low-Medium  
**Skills:** Python, pytest

- Add tests for uncovered code paths
- Improve test coverage for `src/lightspeed_evaluation/core/`
- Target: >80% coverage on new code

**Example:**
```bash
# Check current coverage
uv run pytest tests --cov=src --cov-report=html

# Open htmlcov/index.html to see gaps
```

#### 3. Bug Fixes
**Branch:** main or okp-mcp-integration  
**Effort:** Medium  
**Skills:** Python, debugging

- Fix linting issues (run `make ruff` to find them)
- Fix type checking issues (run `make pyright`)
- Address TODO items in code
- Fix deprecated code warnings

**Example:**
```bash
# Find TODO items
grep -r "TODO" src/

# Find FIXME items
grep -r "FIXME" src/
```

---

### Intermediate Tasks

#### 4. Add New Custom Metrics
**Branch:** main  
**Effort:** Medium  
**Skills:** Python, LLM prompting, evaluation metrics

- Create new custom metrics in `src/lightspeed_evaluation/core/metrics/custom/`
- Register in `MetricManager`
- Add metadata to `config/system.yaml`
- Write comprehensive tests

**Example metrics to add:**
- Tone/style evaluation
- Safety/toxicity detection
- Code quality evaluation
- Multi-language support evaluation

**Template:**
```python
# src/lightspeed_evaluation/core/metrics/custom/my_metric.py
from lightspeed_evaluation.core.metrics.base import BaseMetric

class MyMetricEvaluator(BaseMetric):
    """Evaluates X quality."""
    
    def evaluate(self, query, response, expected, **kwargs):
        # Your evaluation logic
        return {"score": 0.95, "reason": "High quality"}
```

#### 5. Improve Agent Intelligence
**Branch:** okp-mcp-integration  
**Effort:** Medium-High  
**Skills:** Python, LLM prompting, multi-agent systems

- Enhance Linux Expert prompts
- Improve Solr Expert verification logic
- Add new pattern discovery heuristics
- Optimize suggestion quality from Claude Advisor

**Example:**
```python
# okp_mcp_agent/core/linux_expert.py
# Improve the prompt to better validate Linux commands
```

#### 6. Pattern Discovery Improvements
**Branch:** okp-mcp-integration  
**Effort:** Medium-High  
**Skills:** Python, clustering algorithms, NLP

- Improve pattern clustering algorithm
- Add semantic similarity for better grouping
- Tune pattern discovery thresholds
- Add pattern validation logic

**Example:**
```python
# okp_mcp_agent/pattern_discovery/discover_ticket_patterns.py
# Improve clustering to group similar tickets
```

---

### Advanced Tasks

#### 7. New LLM Provider Integration
**Branch:** main  
**Effort:** High  
**Skills:** Python, LLM APIs, authentication

- Add support for new LLM provider (e.g., Mistral, Cohere)
- Implement provider class in `src/lightspeed_evaluation/core/llm/`
- Add authentication and configuration
- Write integration tests

**Steps:**
1. Create `src/lightspeed_evaluation/core/llm/your_provider.py`
2. Implement provider interface (see `openai.py` for reference)
3. Update `LLMManager` to support new provider
4. Add configuration examples to `config/system.yaml`
5. Add tests in `tests/core/llm/test_your_provider.py`

#### 8. Multi-Agent Orchestration Enhancement
**Branch:** okp-mcp-integration  
**Effort:** High  
**Skills:** Python, multi-agent systems, async programming

- Add new specialized agents (e.g., Networking Expert, Storage Expert)
- Improve agent coordination logic
- Add agent communication protocols
- Implement agent state management

**Example:**
```python
# okp_mcp_agent/core/networking_expert.py
class NetworkingExpert:
    """Expert agent for network-related questions."""
    
    async def verify_network_concept(self, question, answer):
        # Verify networking concepts
        pass
```

#### 9. Cost Optimization
**Branch:** main  
**Effort:** High  
**Skills:** Python, LLM APIs, caching strategies

- Improve caching strategies to reduce API calls
- Implement batch processing for evaluations
- Add cost estimation before runs
- Optimize prompt engineering for fewer tokens

**Example:**
```python
# src/lightspeed_evaluation/core/llm/cost_optimizer.py
class CostOptimizer:
    """Optimize LLM API costs."""
    
    def estimate_cost(self, eval_config):
        # Estimate cost before running
        pass
```

#### 10. Batch Processing for Pattern Fixes
**Branch:** okp-mcp-integration  
**Effort:** High  
**Skills:** Python, workflow orchestration, error handling

- Improve batch processing robustness
- Add progress tracking and resumability
- Implement parallel pattern fixing
- Add comprehensive error handling

**Example:**
```python
# okp_mcp_agent/runners/batch_pattern_fixer.py
class BatchPatternFixer:
    """Fix multiple patterns in parallel."""
    
    async def fix_patterns(self, pattern_ids, max_workers=3):
        # Parallel pattern fixing
        pass
```

---

## Key Differences: Main vs OKP-MCP Branch

| Feature | Main Branch | OKP-MCP Integration |
|---------|-------------|---------------------|
| **Purpose** | Evaluate GenAI apps | Evaluate + Auto-fix RAG issues |
| **Use Case** | Testing, validation | Bug fixing, automation |
| **JIRA Integration** | ❌ No | ✅ Yes (fetch tickets) |
| **Auto-fix** | ❌ Manual | ✅ Autonomous agents |
| **Pattern Discovery** | ❌ No | ✅ Yes (batch fixing) |
| **Multi-Agent System** | ❌ No | ✅ Yes (Linux, Solr experts) |
| **Answer-First Workflow** | ❌ No | ✅ Yes (discover docs) |
| **Extra Dependencies** | Standard | + Claude SDK, MCP servers |
| **Maturity** | Stable | Experimental (WIP) |

---

## Common Pitfalls to Avoid

### 1. Don't Skip Quality Checks
```bash
# ❌ WRONG - Committing without checks
git commit -m "quick fix"

# ✅ CORRECT - Always run checks first
make pre-commit && make test
git commit -m "fix: Correct validation logic"
```

### 2. Don't Use unittest.mock
```python
# ❌ WRONG
from unittest.mock import patch, MagicMock

# ✅ CORRECT
def test_example(mocker):  # pytest-mock
    mocker.patch('module.function')
```

### 3. Don't Add Features to Deprecated Directories
```bash
# ❌ WRONG - Adding to deprecated dir
# New feature in lsc_agent_eval/

# ✅ CORRECT - Add to active dir
# New feature in src/lightspeed_evaluation/
```

### 4. Don't Disable Lint Warnings
```python
# ❌ WRONG - Hiding issues
def foo():  # noqa: D103
    pass

# ✅ CORRECT - Fix the issue
def foo():
    """Document the function."""
    pass
```

### 5. Don't Skip Documentation Updates
```bash
# ❌ WRONG - Code change without docs

# ✅ CORRECT - Update docs when changing behavior
# Edit docs/QUICKSTART.md, README.md, etc.
```

---

## Getting Help

### Resources
- **Main docs**: `docs/QUICKSTART.md`
- **Agent docs**: `okp_mcp_agent/docs/QUICKSTART.md`
- **Agent guidelines**: `AGENTS.md`
- **API reference**: Auto-generated from docstrings

### Troubleshooting
1. Check `docs/QUICKSTART.md` for common issues
2. Review error messages (they're usually helpful!)
3. Run with DEBUG logging: `lightspeed-eval --log-level DEBUG ...`
4. Check GitHub issues for similar problems

### Questions?
- Read the codebase documentation
- Check existing tests for usage examples
- Look at recent commits for similar changes
- Ask in team chat or create a GitHub issue

---

## Success Criteria

Before submitting a PR, verify:

- [ ] All quality checks pass: `make pre-commit`
- [ ] All tests pass: `make test`
- [ ] Code is formatted: `make black-format`
- [ ] Documentation updated (if applicable)
- [ ] New features have tests (>80% coverage)
- [ ] No lint warnings added (run `make ruff`, `make pylint`)
- [ ] Type hints added for public functions
- [ ] Docstrings added for public APIs

---

## Next Steps

1. **Choose your branch**
   - **Main**: Core evaluation framework
   - **OKP-MCP**: Autonomous agent system

2. **Pick a task** from the lists above (beginner → advanced)

3. **Set up your environment**
   - Follow Quick Start guide for your branch
   - Run example to verify setup

4. **Make your contribution**
   - Create feature branch
   - Make changes following guidelines
   - Run quality checks
   - Submit PR

5. **Celebrate!** 🎉

---

## Welcome to the Team!

This project is actively evolving. Your contributions make a real difference in making GenAI evaluation accessible and powerful.

**Start small, learn the codebase, then tackle bigger challenges. Happy coding!**

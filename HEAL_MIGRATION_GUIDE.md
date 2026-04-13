# HEAL Migration Guide: Step-by-Step Instructions

Complete guide for moving okp-mcp-integration code to a new public repository called HEAL.

---

## Overview

**Source:** `lightspeed-evaluation/okp_mcp_agent/` (okp-mcp-integration branch)  
**Destination:** New repo `rhel-lightspeed/HEAL`  
**Timeline:** 1-2 days focused work  
**Goal:** Clean, public-ready autonomous agent system

---

## Phase 1: Security & Content Audit (2-3 hours)

### Step 1.1: Scan for Secrets
```bash
# In lightspeed-evaluation repo
cd /home/emackey/Work/lightspeed-core/lightspeed-evaluation

# Run secrets detection
make detect-secrets

# Manual check for sensitive patterns
grep -r "api[_-]key\|secret\|password\|token" okp_mcp_agent/ \
  --include="*.py" --include="*.md" --include="*.yaml" \
  | grep -v "# Example\|TODO\|FIXME"
```

**Action:** Remove or redact any found secrets.

### Step 1.2: Review Artifact Files
```bash
# Check artifact sizes
find okp_mcp_agent/artifacts -type f -exec ls -lh {} \; | awk '{print $5, $9}'

# Review JIRA ticket data for customer info
less okp_mcp_agent/artifacts/bootstrap_20260407/extracted_tickets.yaml
less okp_mcp_agent/config/jira_open_tickets.yaml
```

**Decision Points:**
- ✅ **Keep:** Functional test definitions (sanitized)
- ✅ **Keep:** Pattern definitions (generic patterns)
- ❌ **Remove:** Bootstrap artifacts with customer data
- ❌ **Remove:** Large log files (extract.log, patterns.log)

**Actions:**
```bash
# Create archive directory (don't commit to new repo)
mkdir -p ~/heal_migration_archive

# Move sensitive/large artifacts to archive
mv okp_mcp_agent/artifacts/bootstrap_20260407/*.log ~/heal_migration_archive/
mv okp_mcp_agent/artifacts/bootstrap_20260407/extracted_tickets.yaml ~/heal_migration_archive/

# Create sanitized versions if needed
# (manually review and remove customer-specific content)
```

### Step 1.3: Remove Internal Planning Docs
```bash
# Move to archive (these are internal notes)
mv okp_mcp_agent/plans_04032026.txt ~/heal_migration_archive/
mv okp_mcp_agent/IMPORT_FIXES_NEEDED.md ~/heal_migration_archive/
mv okp_mcp_agent/PATTERN_FIX_REVIEW.md ~/heal_migration_archive/
mv okp_mcp_agent/MULTI_STAGE_TESTING_PLAN.md ~/heal_migration_archive/

# Keep TODO.md but clean it up
nano okp_mcp_agent/TODO.md  # Remove completed items, internal references
```

---

## Phase 2: Code Cleanup (2-3 hours)

### Step 2.1: Run Quality Checks
```bash
# Format code
make black-format

# Run all checks
make pre-commit

# Fix any issues found
# (Focus on okp_mcp_agent files)
```

### Step 2.2: Remove Dead Code
```bash
# Find TODO/FIXME comments
grep -rn "TODO\|FIXME" okp_mcp_agent/ --include="*.py"

# Review and either:
# - Fix the issue
# - Document it properly in GitHub issues
# - Remove if no longer relevant
```

### Step 2.3: Check Dependencies
```bash
# Find all imports from lightspeed_evaluation
grep -r "from lightspeed_evaluation" okp_mcp_agent/ --include="*.py"
grep -r "import lightspeed_evaluation" okp_mcp_agent/ --include="*.py"
```

**Action:** Document which dependencies are needed. These will go into HEAL's `pyproject.toml`.

---

## Phase 3: Prepare New Repository Structure (1-2 hours)

### Step 3.1: Create Local Working Directory
```bash
# Create fresh directory for HEAL
mkdir -p ~/Work/rhel-lightspeed/HEAL
cd ~/Work/rhel-lightspeed/HEAL

# Initialize git
git init
git branch -m main
```

### Step 3.2: Plan Directory Structure

**Recommended structure (using src/ layout - Python best practice):**
```
HEAL/
├── src/
│   └── heal/                 # Main package (renamed from okp_mcp_agent)
│       ├── __init__.py
│       ├── agents/          # Agent implementations
│       ├── core/            # Core components
│       ├── bootstrap/       # JIRA extraction
│       ├── pattern_discovery/  # Pattern analysis
│       ├── runners/         # Workflow runners
│       └── utils/           # Utilities
├── tests/                   # Test suite
├── config/                  # Configuration files
│   ├── test_suites/        # Test definitions
│   └── patterns/           # Pattern definitions
├── docs/                    # Documentation
├── examples/                # Example workflows
├── scripts/                 # Utility scripts
├── .github/                 # GitHub templates
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── pyproject.toml          # Project config
├── README.md               # Main README
├── LICENSE                 # Apache 2.0
├── CONTRIBUTING.md         # Contribution guide
├── .gitignore              # Git ignore rules
└── Makefile                # Dev commands
```

**Why src/ layout?**
- Industry standard for modern Python projects
- Prevents accidental imports from working directory
- Ensures proper package installation
- Better for testing and distribution

### Step 3.3: Create .gitignore
```bash
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
env/
.venv

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

# Evaluation outputs
output/
.caches/
*.csv
*.png
!docs/**/*.png

# Sensitive
.env
*.key
*.pem
credentials*.json

# Artifacts (large data)
artifacts/bootstrap_*/
*.log

# OS
.DS_Store
Thumbs.db
EOF
```

---

## Phase 4: Copy and Rename (1 hour)

### Step 4.1: Copy Files to New Repo
```bash
# From lightspeed-evaluation directory
cd /home/emackey/Work/lightspeed-core/lightspeed-evaluation

# Copy okp_mcp_agent to new location with src/ layout
mkdir -p ~/Work/rhel-lightspeed/HEAL/src
cp -r okp_mcp_agent ~/Work/rhel-lightspeed/HEAL/src/heal

# Move to HEAL repo
cd ~/Work/rhel-lightspeed/HEAL

# Copy specific config files
mkdir -p config
cp -r src/heal/config/test_suites config/
cp -r src/heal/config/patterns_v2 config/patterns
rm -rf src/heal/config  # Remove old config location

# Move tests to top level
[ -d "src/heal/tests" ] && mv src/heal/tests ./

# Move docs to top level  
[ -d "src/heal/docs" ] && mv src/heal/docs ./
```

### Step 4.2: Rename Module References
```bash
cd ~/Work/rhel-lightspeed/HEAL

# Rename all Python imports
find . -name "*.py" -type f -exec sed -i 's/from okp_mcp_agent/from heal/g' {} +
find . -name "*.py" -type f -exec sed -i 's/import okp_mcp_agent/import heal/g' {} +

# Update documentation references
find docs -name "*.md" -type f -exec sed -i 's/okp_mcp_agent/heal/g' {} + 2>/dev/null || true

# Update config file paths
find config -name "*.yaml" -type f -exec sed -i 's/okp_mcp_agent/heal/g' {} +
```

### Step 4.3: Create __init__.py Files
```bash
# Ensure all packages have __init__.py
find src/heal -type d -exec touch {}/__init__.py \;
```

---

## Phase 5: Create Project Files (1-2 hours)

### Step 5.1: Create pyproject.toml
```bash
cat > pyproject.toml << 'EOF'
[project]
name = "heal"
version = "0.1.0"
description = "HEAL: Heuristic Evaluation And Learning - Autonomous agent system for RAG diagnostics and fixes"
authors = [
    {name = "Red Hat Lightspeed Team", email = "lightspeed@redhat.com"}
]
readme = "README.md"
license = {text = "Apache-2.0"}
requires-python = ">=3.11"
keywords = ["agent", "rag", "evaluation", "jira", "automation", "llm"]

dependencies = [
    "anthropic[vertex]>=0.39.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "pandas>=2.0.0",
    "requests>=2.31.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.11.1",
    "black>=23.7.0",
    "ruff>=0.0.285",
    "mypy>=1.5.0",
]

[project.scripts]
heal = "heal.runner.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/heal"]

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
mypy_path = "src"
EOF
```

### Step 5.2: Create Main README.md
```bash
cat > README.md << 'EOF'
# HEAL: Heuristic Evaluation And Learning

**Autonomous agent system for diagnosing and fixing RAG retrieval issues at scale.**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## What is HEAL?

HEAL is an autonomous multi-agent system that:

- 🔍 **Diagnoses RAG retrieval failures** by analyzing answer quality vs document relevance
- 🤖 **Provides AI-powered fix suggestions** using Claude as an expert advisor
- 📊 **Discovers patterns** in JIRA tickets to batch-fix common issues (10-15x efficiency)
- ✅ **Validates fixes** through comprehensive evaluation metrics
- 🔄 **Automates the entire workflow** from ticket → diagnosis → fix → validation

### Key Features

#### Answer-First Workflow
Start with just a question and expected answer - HEAL discovers which documents should be retrieved automatically.

#### Multi-Agent Orchestration
- **Linux Expert**: Validates Linux commands and concepts
- **Solr Expert**: Verifies document content and search configuration
- **Pattern Discovery**: Groups similar tickets for batch fixing
- **Claude Advisor**: Provides intelligent fix suggestions

#### Pattern-Based Batch Fixing
Instead of fixing tickets one-by-one, HEAL groups 6-15 similar tickets and fixes them as a batch - dramatically more efficient.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Claude API access (via Anthropic Vertex AI)
- MCP Servers: Atlassian/JIRA, Linux
- Gemini API for evaluation metrics

### Installation

**Recommended: Using uv (fast, modern)**
```bash
# Clone repository
git clone https://github.com/rhel-lightspeed/HEAL.git
cd HEAL

# Install uv if you don't have it
pip install uv

# Install all dependencies
uv sync

# Install with dev tools
uv sync --group dev
```

**Alternative: Using pip**
```bash
# Clone repository
git clone https://github.com/rhel-lightspeed/HEAL.git
cd HEAL

# Install dependencies
pip install -e .

# Or with development tools
pip install -e ".[dev]"
```

### Configuration

```bash
# Set up credentials
export ANTHROPIC_VERTEX_PROJECT_ID=your-project-id
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Configure MCP servers (see docs/MCP_SETUP.md)
```

### First Run

```bash
# Diagnose a single JIRA ticket
heal diagnose TICKET-123

# Fix with AI suggestions
heal fix TICKET-123

# Batch process pattern
heal pattern-fix PATTERN_ID --max-iterations 10
```

---

## Documentation

- [Quick Start Guide](docs/QUICKSTART.md)
- [Answer-First Workflow](docs/ANSWER_FIRST_WORKFLOW.md)
- [Pattern Discovery](docs/PATTERN_DISCOVERY.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Reference](docs/API_REFERENCE.md)

---

## Use Cases

### 1. Customer Bug Triage
Quickly diagnose why a RAG system gave a wrong answer and get fix recommendations.

### 2. Batch Fixing Common Issues
Discover that 15 tickets all fail because of "EOL RHEL version" confusion, fix once, validate all.

### 3. Regression Test Generation
Create test suites automatically from JIRA tickets with verified answers and expected documents.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  JIRA Tickets                                       │
│  (Questions + Expert Answers)                       │
└───────────────┬─────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────┐
│  HEAL Agent System                                  │
│  ┌─────────────────┐  ┌──────────────────┐         │
│  │ Linux Expert    │  │ Solr Expert      │         │
│  └─────────────────┘  └──────────────────┘         │
│  ┌─────────────────┐  ┌──────────────────┐         │
│  │ Pattern Agent   │  │ Claude Advisor   │         │
│  └─────────────────┘  └──────────────────┘         │
└───────────────┬─────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────┐
│  Outputs                                            │
│  • Fix suggestions                                  │
│  • Updated Solr configs                             │
│  • Regression test suites                           │
│  • Validation reports                               │
└─────────────────────────────────────────────────────┘
```

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/rhel-lightspeed/HEAL/issues)
- **Documentation**: [docs/](docs/)
- **Discussions**: [GitHub Discussions](https://github.com/rhel-lightspeed/HEAL/discussions)
EOF
```

### Step 5.3: Create LICENSE
```bash
# Copy Apache 2.0 license
curl -o LICENSE https://www.apache.org/licenses/LICENSE-2.0.txt

# Or if you have it locally
cp /home/emackey/Work/lightspeed-core/lightspeed-evaluation/LICENSE ./
```

### Step 5.4: Create CONTRIBUTING.md
```bash
cat > CONTRIBUTING.md << 'EOF'
# Contributing to HEAL

Thank you for your interest in contributing to HEAL!

## Getting Started

1. Fork the repository
2. Clone your fork
3. Install development dependencies: `pip install -e ".[dev]"`
4. Create a feature branch: `git checkout -b feat/your-feature`

## Development Workflow

### Running Tests
```bash
pytest tests/
pytest tests/ --cov=heal --cov-report=html
```

### Code Quality
```bash
# Format code
black heal tests

# Lint
ruff check heal tests

# Type check
mypy heal
```

### Before Submitting PR

- [ ] Tests pass
- [ ] Code is formatted with Black
- [ ] No linting errors
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (if applicable)

## Code Standards

- Python 3.11+
- Type hints for public APIs
- Google-style docstrings
- Test coverage >80% for new code

## Questions?

Open an issue or discussion on GitHub!
EOF
```

### Step 5.5: Set Up uv (Modern Python Package Management)
```bash
cd ~/Work/rhel-lightspeed/HEAL

# Initialize uv.lock file
uv sync

# This will:
# - Read pyproject.toml
# - Resolve all dependencies
# - Create uv.lock with pinned versions
# - Install the package in editable mode

# Install dev dependencies
uv sync --group dev

# Or install all extras if you have them
# uv sync --all-extras --group dev
```

**Why uv?**
- ✅ Much faster than pip (10-100x)
- ✅ Reproducible builds with uv.lock
- ✅ Better dependency resolution
- ✅ Modern Python best practice

**Note:** After this, you can use `uv run` prefix for commands or activate the virtual environment:
```bash
# Option A: Use uv run prefix
uv run pytest tests/
uv run python -c "import heal"

# Option B: Activate venv (uv creates .venv/)
source .venv/bin/activate
python -c "import heal"
pytest tests/
```

---

## Phase 6: Test & Validate (2-3 hours)

### Step 6.1: Test Imports
```bash
cd ~/Work/rhel-lightspeed/HEAL

# Package already installed by 'uv sync' in previous step

# Test that imports work
uv run python -c "import heal; print('OK')"
uv run python -c "from heal.agents.okp_mcp_agent import OkpMcpAgent; print('OK')"
```

**Fix any import errors.**

### Step 6.2: Run Tests
```bash
# Run test suite
uv run pytest tests/ -v

# Check coverage
uv run pytest tests/ --cov=heal --cov-report=term-missing
```

**Fix any failing tests.**

### Step 6.3: Check for Hardcoded Paths
```bash
# Find absolute paths
grep -r "/home/emackey" src/heal/ --include="*.py"
grep -r "/home/emackey" tests/ --include="*.py"

# Find references to old repo
grep -r "lightspeed-evaluation" src/heal/ --include="*.py"
grep -r "lightspeed-evaluation" docs/ --include="*.md"
```

**Fix any hardcoded paths to use relative paths or config.**

---

## Phase 7: Create GitHub Repository (30 minutes)

### Step 7.1: Create Repo on GitHub
1. Go to https://github.com/rhel-lightspeed
2. Click "New Repository"
3. Name: `HEAL`
4. Description: "Heuristic Evaluation And Learning - Autonomous agent system for RAG diagnostics"
5. Public repository
6. **DO NOT** initialize with README (we have our own)
7. Click "Create repository"

### Step 7.2: Push to GitHub
```bash
cd ~/Work/rhel-lightspeed/HEAL

# Add remote
git remote add origin git@github.com:rhel-lightspeed/HEAL.git

# Initial commit
git add .
git commit -m "feat: Initial HEAL repository

- Multi-agent system for RAG diagnostics
- Answer-first workflow
- Pattern-based batch fixing
- JIRA integration
- Comprehensive documentation"

# Push to GitHub
git push -u origin main
```

### Step 7.3: Configure Repository Settings

On GitHub:
1. **Settings → General**
   - Add topics: `rag`, `agents`, `llm`, `jira`, `automation`, `evaluation`
   - Add description and website

2. **Settings → Branches**
   - Add branch protection rule for `main`
   - Require PR reviews
   - Require status checks

3. **Settings → Features**
   - Enable Issues
   - Enable Discussions
   - Disable Wiki (use docs/ instead)

---

## Phase 8: Post-Migration Cleanup (30 minutes)

### Step 8.1: Update Original Repository

In `lightspeed-evaluation`:
```bash
cd /home/emackey/Work/lightspeed-core/lightspeed-evaluation
git checkout okp-mcp-integration

# Add deprecation notice
cat >> okp_mcp_agent/README.md << 'EOF'

---

## ⚠️ DEPRECATION NOTICE

This code has been moved to a dedicated repository: **[HEAL](https://github.com/rhel-lightspeed/HEAL)**

Please use the new repository for:
- Latest features and updates
- Bug reports and issues
- Contributions

This directory will be removed in a future release.
EOF

git add okp_mcp_agent/README.md
git commit -m "docs: Add deprecation notice for okp_mcp_agent (moved to HEAL)"
git push origin okp-mcp-integration
```

### Step 8.2: Update Main Branch README

```bash
git checkout main

# Add link to HEAL in main README
# (Edit README.md to add a "Related Projects" section)
nano README.md

git add README.md
git commit -m "docs: Add link to HEAL autonomous agent project"
git push origin main
```

---

## Phase 9: Announcement & Documentation (Optional)

### Step 9.1: Create Announcement
- Write blog post or announcement
- Share in team channels
- Update related documentation

### Step 9.2: Monitor Initial Usage
- Watch for issues in first week
- Respond to community feedback
- Update docs based on questions

---

## Troubleshooting

### Issue: Import Errors After Renaming
```bash
# Make sure all __init__.py files exist
find heal -type d ! -path "*/\.*" -exec test -e {}/__init__.py \; -print

# Check for missed renames
grep -r "okp_mcp_agent" heal/ --include="*.py"
```

### Issue: Missing Dependencies
```bash
# Check what's imported but not in pyproject.toml
python -c "import heal" 2>&1 | grep "ModuleNotFoundError"

# Add missing deps to pyproject.toml
```

### Issue: Test Failures
```bash
# Run tests with verbose output
pytest tests/ -vv --tb=short

# Check for path issues
pytest tests/ -vv -k "test_name"
```

---

## Final Checklist

Before announcing the new repository:

- [ ] All tests pass
- [ ] Documentation is complete
- [ ] No secrets or sensitive data
- [ ] License file present
- [ ] README is comprehensive
- [ ] GitHub topics configured
- [ ] Branch protection enabled
- [ ] Original repo updated with deprecation notice
- [ ] Examples work end-to-end

---

## Estimated Timeline

| Phase | Duration | Task |
|-------|----------|------|
| 1 | 2-3 hours | Security audit & content review |
| 2 | 2-3 hours | Code cleanup & quality checks |
| 3 | 1-2 hours | New repository structure planning |
| 4 | 1 hour | Copy & rename files |
| 5 | 1-2 hours | Create project files (README, pyproject.toml) |
| 6 | 2-3 hours | Testing & validation |
| 7 | 30 min | GitHub repository creation |
| 8 | 30 min | Post-migration cleanup |
| **Total** | **10-15 hours** | **1-2 days focused work** |

---

Good luck with the migration! 🚀

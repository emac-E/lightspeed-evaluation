# Import and Path Fixes Needed After Reorganization

## 🔴 CRITICAL: Broken Imports (Must Fix)

### 1. Agent Scripts Importing from Old `scripts/` Path

**Files with broken imports:**

#### `okp_mcp_agent/agents/okp_mcp_agent.py`
```python
# LINE ~46-66: BROKEN IMPORTS
from scripts.okp_mcp_llm_advisor import OkpMcpLLMAdvisor, MetricSummary
from scripts.okp_solr_checker import SolrDocumentChecker
from scripts.okp_solr_config_analyzer import SolrConfigAnalyzer

# FIX: Change to relative imports
from okp_mcp_agent.agents.okp_mcp_llm_advisor import OkpMcpLLMAdvisor, MetricSummary
from okp_mcp_agent.agents.okp_solr_checker import SolrDocumentChecker
from okp_mcp_agent.agents.okp_solr_config_analyzer import SolrConfigAnalyzer

# OR: Use relative imports (preferred for same directory)
from .okp_mcp_llm_advisor import OkpMcpLLMAdvisor, MetricSummary
from .okp_solr_checker import SolrDocumentChecker
from .okp_solr_config_analyzer import SolrConfigAnalyzer
```

#### `okp_mcp_agent/agents/okp_mcp_pattern_agent.py`
```python
# LINE ~60: BROKEN IMPORT
from scripts.okp_mcp_agent import (
    OkpMcpAgent,
    EvaluationResult,
)

# FIX: Change to relative import
from .okp_mcp_agent import (
    OkpMcpAgent,
    EvaluationResult,
)
```

---

### 2. Core Agent Modules Importing from Old Location

**Files with broken imports:**

#### Multiple files trying to import from `lightspeed_evaluation.agents.*`
- `okp_mcp_agent/bootstrap/extract_jira_tickets.py`
- `okp_mcp_agent/bootstrap/multi_agent_jira_extractor.py`
- `okp_mcp_agent/pattern_discovery/discover_ticket_patterns.py`
- `okp_mcp_agent/tests/test_linux_expert.py`
- `okp_mcp_agent/tests/test_multi_agent_system.py`
- `okp_mcp_agent/core/__init__.py`
- `okp_mcp_agent/core/linux_expert.py`
- `okp_mcp_agent/core/solr_expert.py`

```python
# BROKEN (old path - agents moved out of src/):
from lightspeed_evaluation.agents import LinuxExpertAgent, SolrExpertAgent
from lightspeed_evaluation.agents.linux_expert import LinuxExpertAgent
from lightspeed_evaluation.agents.solr_expert import SolrExpertAgent
from lightspeed_evaluation.agents.pattern_discovery import PatternDiscoveryAgent
from lightspeed_evaluation.agents.search_intelligence import SearchResult

# FIX: Change to new location
from okp_mcp_agent.core.linux_expert import LinuxExpertAgent
from okp_mcp_agent.core.solr_expert import SolrExpertAgent
from okp_mcp_agent.core.pattern_discovery import PatternDiscoveryAgent
from okp_mcp_agent.core.search_intelligence import SearchResult

# OR in okp_mcp_agent/core/__init__.py, use relative:
from .linux_expert import LinuxExpertAgent
from .solr_expert import SolrExpertAgent
```

---

### 3. Broken Config Paths

**Files with hardcoded old config paths:**

#### `okp_mcp_agent/agents/okp_mcp_agent.py` (lines ~378-383)
```python
# BROKEN:
self.functional_full = (
    eval_root / "config/okp_mcp_test_suites/functional_tests_full.yaml"
)
self.functional_retrieval = (
    eval_root / "config/okp_mcp_test_suites/functional_tests_retrieval.yaml"
)

# FIX:
self.functional_full = (
    eval_root / "okp_mcp_agent/config/test_suites/functional_tests_full.yaml"
)
self.functional_retrieval = (
    eval_root / "okp_mcp_agent/config/test_suites/functional_tests_retrieval.yaml"
)
```

#### `okp_mcp_agent/runners/run_pattern_fix_poc.py` (default patterns_dir)
```python
# LINE ~199: BROKEN DEFAULT
parser.add_argument(
    '--patterns-dir',
    default='config/patterns_v2'  # BROKEN
)

# FIX:
parser.add_argument(
    '--patterns-dir',
    default='okp_mcp_agent/config/patterns_v2'
)
```

---

## ⚠️ MODERATE: Usage Examples in Docstrings

**Files with outdated usage examples (won't break code, but confusing):**

### `okp_mcp_agent/agents/okp_mcp_agent.py`
```python
# Lines 10-21: Usage examples still say "scripts/"
Usage:
    # Diagnose a single ticket (runs new evaluation)
    python scripts/okp_mcp_agent.py diagnose RSPEED-2482  # OUTDATED

# FIX:
    python okp_mcp_agent/agents/okp_mcp_agent.py diagnose RSPEED-2482
# OR (if you make it a package):
    python -m okp_mcp_agent.agents.okp_mcp_agent diagnose RSPEED-2482
```

### Multiple files with old script path examples
- `okp_mcp_agent/agents/okp_mcp_pattern_agent.py` (lines ~14-24)
- `okp_mcp_agent/bootstrap/fetch_jira_open_tickets.py` (lines ~10-16)
- `okp_mcp_agent/bootstrap/convert_bootstrap_to_eval_format.py`

---

## 📊 Summary of Fixes Needed

| Category | Files Affected | Severity |
|----------|----------------|----------|
| **Import from scripts/** | 2 files | 🔴 CRITICAL |
| **Import from lightspeed_evaluation.agents** | 8 files | 🔴 CRITICAL |
| **Hardcoded config paths** | 2 files | 🔴 CRITICAL |
| **Docstring examples** | 5 files | ⚠️ MODERATE |
| **TOTAL** | **17 files** | |

---

## 🛠️ Fix Strategy

### Option 1: Make okp_mcp_agent a Python Package (Recommended)

**Create `okp_mcp_agent/__init__.py`:**
```python
"""OKP-MCP Autonomous Agent System."""

__version__ = "0.1.0"
```

**Update pyproject.toml to include package:**
```toml
[tool.uv]
packages = [
    { include = "lightspeed_evaluation", from = "src" },
    { include = "okp_mcp_agent" }  # Add this
]
```

**Then imports become:**
```python
# From anywhere in the project:
from okp_mcp_agent.agents.okp_mcp_agent import OkpMcpAgent
from okp_mcp_agent.core.linux_expert import LinuxExpertAgent
```

**Run from anywhere:**
```bash
python -m okp_mcp_agent.agents.okp_mcp_agent diagnose RSPEED-2482
```

---

### Option 2: Standalone Scripts (Quick Fix)

Keep scripts standalone but fix sys.path manipulation at top of each:

```python
# At top of each script (after imports but before local imports)
import sys
from pathlib import Path

# Add project root to path
REPO_ROOT = Path(__file__).parent.parent.parent  # okp_mcp_agent/agents/script.py -> repo root
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Now imports work:
from okp_mcp_agent.agents.okp_mcp_llm_advisor import OkpMcpLLMAdvisor
```

**Run from repo root only:**
```bash
cd /path/to/lightspeed-evaluation
python okp_mcp_agent/agents/okp_mcp_agent.py diagnose RSPEED-2482
```

---

## 🎯 Recommended Fix Order

1. **Fix critical imports first** (agents importing each other)
2. **Fix config paths**
3. **Update docstrings** (can wait)
4. **Test each script** to verify it works

---

## ✅ Quick Test After Fixes

```bash
# Test main agent
python okp_mcp_agent/agents/okp_mcp_agent.py --help

# Test pattern POC
python okp_mcp_agent/runners/run_pattern_fix_poc.py --help

# Test bootstrap script
python okp_mcp_agent/bootstrap/fetch_jira_open_tickets.py --help

# Run agent tests
uv run pytest okp_mcp_agent/tests/ -v
```

---

## 🚨 Files That Need Immediate Attention

**Priority 1 (Won't Run):**
1. `okp_mcp_agent/agents/okp_mcp_agent.py` - Main agent (imports broken)
2. `okp_mcp_agent/agents/okp_mcp_pattern_agent.py` - Pattern agent (imports broken)
3. `okp_mcp_agent/bootstrap/*.py` - All bootstrap scripts (import LinuxExpert)
4. `okp_mcp_agent/core/__init__.py` - Core package init (imports broken)

**Priority 2 (May Run but uses wrong paths):**
5. `okp_mcp_agent/runners/run_pattern_fix_poc.py` - Wrong default patterns dir

**Priority 3 (Documentation only):**
6. Various docstrings with old usage examples

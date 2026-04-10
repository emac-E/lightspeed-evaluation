# LightSpeed Evaluation - Quick Start Guide

Welcome! This guide will get you up and running with the LightSpeed Evaluation Framework in ~10 minutes.

## 📋 Prerequisites

Before you begin, make sure you have:

- **Python 3.11+** installed
- **Git** for cloning the repository
- **API credentials** for your LLM provider (OpenAI, Google Cloud, etc.)
- **Optional**: `uv` package manager (recommended for faster installs)

## 🚀 Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/lightspeed-evaluation.git
cd lightspeed-evaluation
```

### Step 2: Install Dependencies

**Option A: Using `uv` (Recommended - faster)**

```bash
# Install uv if you don't have it
pip install uv

# Install project dependencies
uv sync
```

**Option B: Using `pip`**

```bash
pip install -e .
```

### Step 3: Install Development Tools (Optional)

If you're contributing or want to run tests:

```bash
make install-deps-test
```

This installs git hooks that run quality checks before commits.

## 🔑 Environment Setup

The framework needs credentials to call LLM providers. You have two options:

### Option 1: Using `.env` File (Recommended)

Create a `.env` file in the project root:

```bash
# Copy the example
cp .env.example .env

# Edit with your credentials
nano .env  # or use your favorite editor
```

**Example `.env` file:**

```bash
# For Vertex AI / Gemini (Google Cloud)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# For OpenAI
OPENAI_API_KEY=sk-your-openai-api-key-here

# For Anthropic Claude
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# For Watsonx
WATSONX_API_KEY=your-watsonx-key
WATSONX_API_BASE=https://your-instance.cloud.ibm.com
WATSONX_PROJECT_ID=your-project-id

# For Azure OpenAI
AZURE_API_KEY=your-azure-key
AZURE_API_BASE=https://your-instance.openai.azure.com

# Optional: For API-enabled evaluations (okp-mcp, lightspeed-stack, etc.)
API_KEY=your-api-endpoint-key
```

**Note:** The `.env` file is automatically loaded when you run `lightspeed-eval`. It does NOT override environment variables you've already set, so it's safe to use alongside scripts that manage credentials.

### Option 2: Export Environment Variables

If you prefer not to use `.env`:

```bash
# For Vertex AI
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GOOGLE_CLOUD_PROJECT=your-project-id

# For OpenAI
export OPENAI_API_KEY=sk-your-key-here
```

## ⚙️ Configuration

### Choose Your Embedding Provider

**IMPORTANT**: You need to configure embeddings for LLM-as-judge metrics. You have two options:

#### Option A: Remote Embeddings (No Extra Install) ✅ Recommended for Getting Started

Edit `config/system.yaml`:

```yaml
embedding:
  provider: "openai"  # or "gemini"
  model: "text-embedding-3-small"  # or for gemini: "text-embedding-004"
  cache_dir: ".caches/embedding_cache"
  cache_enabled: true
```

**Pros**: No extra dependencies, faster installation
**Cons**: Requires API calls (minimal cost)

#### Option B: Local Embeddings (HuggingFace)

First, install the extra dependencies:

```bash
# CPU-only (~2GB)
uv sync --extra local-embeddings

# OR for GPU with CUDA (~6GB)
cp uv-gpu.lock uv.lock && uv sync --extra local-embeddings --frozen
```

Then in `config/system.yaml`:

```yaml
embedding:
  provider: "huggingface"
  model: "sentence-transformers/all-MiniLM-L6-v2"
  cache_dir: ".caches/embedding_cache"
  cache_enabled: true
```

**Pros**: No API costs, works offline
**Cons**: Large download (~2GB), slower on CPU

### Configure Your LLM Provider

Edit `config/system.yaml` to match your LLM provider:

```yaml
llm:
  provider: "openai"  # or "vertex", "gemini", "anthropic", "watsonx"
  model: "gpt-4o"     # Provider-specific model name
  temperature: 0.0
  max_tokens: 32768
  cache_enabled: true
```

**Example providers:**
- **OpenAI**: `provider: openai`, `model: gpt-4o`
- **Vertex AI**: `provider: vertex`, `model: gemini-2.5-pro`
- **Anthropic**: `provider: anthropic`, `model: claude-sonnet-4`
- **Gemini**: `provider: gemini`, `model: gemini-2.5-flash`

## 🎯 First Run

### Test with Example Data

The repo includes sample evaluation data. Try running a quick test:

```bash
# Run with default configs
lightspeed-eval \
  --system-config config/system.yaml \
  --eval-data config/evaluation_data.yaml

# Or use a minimal test suite
lightspeed-eval \
  --system-config config/system.yaml \
  --eval-data config/evaluation_data.yaml \
  --tags basic
```

**What to expect:**
- 📊 Progress output showing evaluation runs
- ✅ Summary with pass/fail counts
- 📁 Reports generated in `output/` directory

### View Results

```bash
# Check the output directory
ls -lh output/

# View the summary report
cat output/lightspeed_eval_summary_*.txt

# Open CSV results
open output/lightspeed_eval_*.csv  # macOS
xdg-open output/lightspeed_eval_*.csv  # Linux
```

## 🐛 Common Issues

### Issue 1: "GOOGLE_APPLICATION_CREDENTIALS environment variable is required"

**Solution**: You're using Vertex AI but haven't set credentials.

```bash
# Option A: Set in .env file
echo 'GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json' >> .env

# Option B: Export directly
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### Issue 2: "HuggingFace embedding provider requires sentence-transformers"

**Solution**: You're using local embeddings but haven't installed them.

**Option A**: Switch to remote embeddings (easier)
```yaml
# In config/system.yaml
embedding:
  provider: "openai"
  model: "text-embedding-3-small"
```

**Option B**: Install local embeddings
```bash
uv sync --extra local-embeddings
```

### Issue 3: "OPENAI_API_KEY environment variable is required"

**Solution**: Set your OpenAI API key.

```bash
# In .env file
echo 'OPENAI_API_KEY=sk-your-key-here' >> .env

# Or export
export OPENAI_API_KEY=sk-your-key-here
```

### Issue 4: "No module named 'lightspeed_evaluation'"

**Solution**: You need to install the package.

```bash
# Using uv
uv sync

# Or using pip
pip install -e .
```

### Issue 5: Evaluation runs but all metrics fail

**Possible causes:**
1. **Wrong model name** - Check your provider's model list
2. **API rate limits** - Add retry configuration in `system.yaml`
3. **Insufficient permissions** - Check your API key has correct permissions
4. **Missing context data** - If using static evaluation, ensure `contexts` field is populated

## 📚 Next Steps

Now that you're up and running:

1. **Create Your Own Tests**
   - Copy `config/evaluation_data.yaml` as a template
   - Add your own queries, expected responses, and metrics
   - See [Evaluation Data Guide](EVALUATION_DATA_GUIDE.md)

2. **Customize Metrics**
   - Configure thresholds in `config/system.yaml`
   - Add custom metrics with GEval
   - See [Metrics Guide](METRICS_GUIDE.md)

3. **Advanced Features**
   - Multi-turn conversations
   - Panel of judges (multiple LLMs)
   - API-enabled real-time evaluation
   - See [Advanced Usage Guide](ADVANCED_USAGE.md)

4. **OKP-MCP Autonomous Agent** (This Fork)
   - Automated RAG retrieval optimization
   - Answer-first workflow for customer bugs
   - See [Answer-First Workflow](ANSWER_FIRST_WORKFLOW.md)

## 🤖 Demo: OKP-MCP Agentic Workflows

This fork includes two proof-of-concept agentic workflows for automated JIRA ticket processing and fixing. Choose based on your needs:

### Demo 1: Bootstrap Workflow (Simpler POC)

**What it does:**
- Extracts JIRA tickets with multi-agent verification (Linux Expert + Solr Expert)
- Discovers common patterns across tickets
- Creates knowledge artifacts for downstream automation
- Logs successful Solr searches for retrieval optimization

**When to use:** Understanding the ticket extraction and pattern discovery process, or preparing data for manual review.

**Run it:**
```bash
# Extract 5 tickets (default)
bash scripts/test_bootstrap_workflow.sh

# Extract more tickets for better pattern discovery
bash scripts/test_bootstrap_workflow.sh --limit 10
```

**What you get:**
- `extracted_tickets.yaml` - Verified query/answer pairs
- `tickets_with_patterns.yaml` - Tickets tagged with pattern IDs
- `patterns_report.json` - Pattern analysis and grouping
- `.claude/search_intelligence/` - Database of successful Solr searches

**Time:** ~2-5 minutes for 5 tickets

**Next step:** Review patterns and manually fix tickets, or proceed to Demo 2 for automated fixing.

---

### Demo 2: Pattern-Based Fixing Workflow (Advanced POC)

**What it does:**
- Everything from Demo 1 (bootstrap + pattern discovery)
- PLUS: Automated pattern-based batch fixing
- Fixes entire patterns (e.g., 15 similar tickets) as one unit
- Creates git branches per pattern with stacked commits
- 10-15x more efficient than single-ticket fixing

**When to use:** Automating fixes for clustered tickets with common root causes.

**Run it:**
```bash
# Full workflow: extract → discover → analyze patterns
bash scripts/test_pattern_workflow.sh --limit 10

# Then fix a specific pattern
python scripts/okp_mcp_pattern_agent.py list-patterns
python scripts/okp_mcp_pattern_agent.py fix-pattern EOL_CONTAINER_COMPATIBILITY \
  --max-iterations 10 \
  --threshold 0.8  # 80% of tickets must pass
```

**What you get:**
- All artifacts from Demo 1
- Pattern-specific git branches (e.g., `fix/pattern-eol-container-compat`)
- Batch validation across all tickets in the pattern
- Pass rate metrics showing pattern coverage

**Time:** ~5-10 minutes for bootstrap + pattern analysis, then ~10-30 minutes per pattern fix (depending on complexity)

**Key Difference:** Fixes 15 tickets as 1 pattern instead of 15 separate fix attempts. If the pattern fix works, all tickets pass together.

---

### Understanding the Efficiency Gain

**Traditional approach:** 15 tickets × 5 iterations each = 75 fix attempts

**Pattern-based approach:** 1 pattern × 5 iterations = 5 fix attempts (validates against all 15 tickets each time)

**Efficiency:** 15x fewer iterations, plus fixes are consistent across similar tickets.

---

### Demo Workflow Comparison

| Feature | Bootstrap Workflow | Pattern-Based Workflow |
|---------|-------------------|------------------------|
| **Script** | `test_bootstrap_workflow.sh` | `test_pattern_workflow.sh` |
| **Ticket Extraction** | ✅ Multi-agent verification | ✅ Multi-agent verification |
| **Pattern Discovery** | ✅ Clustering & analysis | ✅ Clustering & analysis |
| **Automated Fixing** | ❌ Manual review | ✅ Batch pattern fixing |
| **Git Branching** | ❌ Not applicable | ✅ Per-pattern branches |
| **Use Case** | Data prep & exploration | End-to-end automation |
| **Time** | ~2-5 min | ~20-40 min |
| **Best For** | Learning the system | Production workflows |

---

### Requirements for Demos

Both demos require:
- JIRA MCP server configured (see `mcp-servers/atlassian/`)
- Linux MCP server configured (see MCP setup docs)
- Environment variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- Access to JIRA project (default: `RSPEED`)

See [scripts/README.md](../scripts/README.md) for detailed script documentation.

## 🆘 Getting Help

- **Documentation**: Browse the `docs/` directory
- **Examples**: Check `config/` for example configurations
- **Issues**: Report bugs at [GitHub Issues](https://github.com/your-org/lightspeed-evaluation/issues)
- **AGENTS.md**: Guidelines for AI coding agents working on this codebase

## 🎓 Understanding the Workflow

```
┌─────────────────┐
│  Prepare        │
│  - System config │ ← LLM provider, embedding settings
│  - Eval data     │ ← Questions, expected answers, metrics
│  - .env file     │ ← API credentials
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Run            │
│  lightspeed-eval │ ← Executes evaluations
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Analyze        │
│  - CSV reports   │ ← Detailed metrics per conversation
│  - JSON output   │ ← Machine-readable results
│  - Visualizations│ ← Heatmaps, distributions
└─────────────────┘
```

---

**🎉 Congratulations!** You're ready to evaluate your GenAI applications. Start small, experiment, and scale up as you get comfortable with the framework.

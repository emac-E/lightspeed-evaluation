# LightSpeed Evaluation - Quick Reference Card

## Essential Links
- **New Contributors**: [ONBOARDING_PRESENTATION.md](ONBOARDING_PRESENTATION.md)
- **Contributing Guide**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **AI Agent Guidelines**: [AGENTS.md](AGENTS.md)
- **Main Framework**: [docs/QUICKSTART.md](docs/QUICKSTART.md)
- **Agent System**: [okp_mcp_agent/QUICKSTART.md](okp_mcp_agent/QUICKSTART.md)

---

## 5-Minute Setup

```bash
# Clone and install
git clone <repo-url> && cd lightspeed-evaluation
uv sync && make install-deps-test

# Configure
cp .env.example .env  # Add your API keys
```

---

## Common Commands

### Running Evaluations
```bash
# Main branch - Run evaluation
lightspeed-eval --system-config config/system.yaml \
                --eval-data config/evaluation_data.yaml \
                --tags basic

# OKP-MCP branch - Diagnose ticket
python okp_mcp_agent/agents/okp_mcp_agent.py diagnose RSPEED-2482
```

### Development
```bash
make black-format    # Format code
make pre-commit      # Run all quality checks
make test           # Run tests
```

### Quality Checks
```bash
make pre-commit      # ALL checks (runs below)
make bandit          # Security scan
make detect-secrets  # Secrets detection
make check-types     # Type hints (mypy)
make pyright         # Type hints (pyright)
make docstyle        # Docstrings
make ruff            # Fast linter
make pylint          # Thorough linter
make black-check     # Format check
```

---

## Branch Quick Guide

| Feature | Main | OKP-MCP |
|---------|------|---------|
| Evaluate GenAI apps | ✅ | ✅ |
| Auto-fix RAG issues | ❌ | ✅ |
| JIRA integration | ❌ | ✅ |
| Multi-agent system | ❌ | ✅ |
| Answer-first workflow | ❌ | ✅ |

---

## Directory Status

| Directory | Add Features? | Add Tests? |
|-----------|---------------|------------|
| `src/lightspeed_evaluation/` | ✅ Yes | ✅ Yes |
| `okp_mcp_agent/` | ✅ Yes (okp-mcp branch) | ✅ Yes |
| `lsc_agent_eval/` | ❌ Deprecated | ⚠️ Ask first |
| `tests/`, `config/`, `docs/` | ✅ Yes | ✅ Yes |

---

## Code Standards Checklist

Before every commit:
- [ ] Code formatted: `make black-format`
- [ ] Checks pass: `make pre-commit`
- [ ] Tests pass: `make test`
- [ ] Docs updated (if applicable)
- [ ] Used `pytest-mock` (NOT `unittest.mock`)
- [ ] Type hints added
- [ ] Docstrings added

---

## Mocking Pattern

```python
# ✅ CORRECT - Use pytest-mock
def test_example(mocker):
    mock_obj = mocker.patch('module.function')
    mock_obj.return_value = "test"

# ❌ WRONG - Don't use unittest.mock
from unittest.mock import patch  # DON'T
```

---

## Finding Tasks

See [ONBOARDING_PRESENTATION.md](ONBOARDING_PRESENTATION.md) for full task lists:

**Beginner**
- Add docstrings
- Improve test coverage
- Fix linting issues

**Intermediate**
- Add custom metrics
- Enhance agent prompts
- Improve pattern discovery

**Advanced**
- New LLM provider integration
- Multi-agent orchestration
- Cost optimization

---

## Help & Troubleshooting

### Common Issues
1. **Import errors**: Run from repo root
2. **Credential errors**: Check `.env` file
3. **Lint failures**: Run `make black-format` first
4. **Test failures**: Check `tests/` for examples

### Getting Help
- Check `docs/QUICKSTART.md` first
- Review error messages carefully
- Search existing GitHub issues
- Run with `--log-level DEBUG`

---

## File Structure

```
lightspeed-evaluation/
├── src/lightspeed_evaluation/  # Main framework
├── okp_mcp_agent/             # Agent system (okp-mcp branch)
├── config/                     # YAML configs
├── tests/                      # Test suite
├── docs/                       # Documentation
└── scripts/                    # Utilities
```

---

## Before Submitting PR

- [ ] All quality checks pass
- [ ] Tests have >80% coverage
- [ ] Documentation updated
- [ ] No lint warnings
- [ ] Type hints added
- [ ] Follows code standards

---

**Need more detail?** See [ONBOARDING_PRESENTATION.md](ONBOARDING_PRESENTATION.md) for comprehensive guide.

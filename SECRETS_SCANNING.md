# Secrets Scanning with detect-secrets

This project uses [detect-secrets](https://github.com/Yelp/detect-secrets) to prevent accidentally committing API keys, passwords, and other sensitive data to git.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Install detect-secrets with other dev dependencies
uv sync --group dev
```

### 2. Initialize Baseline (First Time)

```bash
# Create initial baseline (scans all files, creates .secrets.baseline)
make detect-secrets
```

This will:
- Scan all files for potential secrets
- Create `.secrets.baseline` (committed to git)
- Exclude known directories (okp_test_data/, .venv/, etc.)

### 3. Audit False Positives

The initial scan will flag many "secrets" that are actually:
- Documentation examples (`BEGIN PRIVATE KEY` in Red Hat docs)
- Placeholder values (`<password>`, `your-api-key-here`)
- Test data (`example@example.com`)

Review and mark false positives:

```bash
# Interactive audit (use arrow keys + 'n' for false positive, 'y' for real secret)
make detect-secrets-audit
```

**Important:** Only mark as false positive if you're SURE it's not a real secret!

### 4. Commit the Baseline

```bash
git add .secrets.baseline
git commit -m "Add detect-secrets baseline"
```

The baseline file tracks which findings have been reviewed, so they won't be flagged again.

---

## 🔄 Daily Workflow

### Pre-commit Hook (Automatic)

The git hook automatically runs `make pre-commit` which includes `detect-secrets`. If new secrets are detected:

1. **Pre-commit hook fails** with a message showing the finding
2. **Review the flagged line** - is it a real secret?
3. **If real secret:**
   - Remove it from the file
   - Use environment variables instead (`.env` file, never committed)
   - Try commit again
4. **If false positive:**
   - Run `make detect-secrets-audit` to review
   - Mark as false positive
   - Baseline is automatically updated
   - Try commit again

### Manual Scanning

```bash
# Scan for new secrets (doesn't update baseline)
make detect-secrets

# Update baseline after adding new files
make detect-secrets-update
```

---

## 📝 Common Scenarios

### Scenario 1: I Added a New Config File

```bash
# After adding config/new_service.yaml
make detect-secrets-update  # Updates baseline with new file

# If it flags something incorrectly
make detect-secrets-audit   # Mark false positives interactively
```

### Scenario 2: Pre-commit Hook Failed

```
$ git commit -m "Add feature"
...
detect-secrets...............................Failed
- hook id: detect-secrets
- exit code: 1

ERROR: Potential secrets detected in config/system.yaml:42
```

**Steps:**
1. Check `config/system.yaml` line 42
2. If it's a real secret → remove it, use environment variable
3. If it's a false positive → `make detect-secrets-audit`, mark it, commit again

### Scenario 3: I Need to Add a Real Secret for Testing

**DON'T** commit secrets, even for tests. Instead:

1. Use environment variables:
   ```python
   # In test file
   import os
   api_key = os.getenv("TEST_API_KEY")  # Set in .env or CI
   ```

2. Or use pytest fixtures with fake data:
   ```python
   @pytest.fixture
   def mock_api_key():
       return "fake-key-for-testing-12345"
   ```

3. If you MUST have a test secret in a file:
   - Add it to `.gitignore`
   - Document in README how to create it locally

---

## 🛠️ Configuration

### Excluded Directories

The following are automatically excluded from scans:
- `okp_test_data/` - Evaluation output
- `.claude/search_intelligence/` - Scraped documentation (contains example keys)
- `.venv/` - Virtual environment
- `*.lock` - Lock files

### Excluded Patterns

To exclude a specific line from scanning, add an inline comment:

```python
api_key = "sk-fake-key-for-documentation"  # pragma: allowlist secret
```

**Warning:** Only use for documentation/examples, never real secrets!

---

## 🔍 How It Works

1. **Baseline File (`.secrets.baseline`):**
   - JSON file tracking all findings
   - Each finding has `is_secret: false` (reviewed) or `true` (needs review)
   - Committed to git so team shares same baseline

2. **Scanning:**
   - Runs on every commit via git hook
   - Compares current files against baseline
   - Only flags NEW findings (not in baseline)

3. **Audit Process:**
   - Interactive CLI walks through each finding
   - You mark as real secret (remove from code) or false positive (add to baseline)
   - Baseline auto-updates

---

## 🚨 What to Do if Secrets Are Already Committed

If you accidentally committed a secret to git history:

1. **Rotate the secret immediately** (generate new API key, password, etc.)
2. **Remove from git history** (dangerous, requires force push):
   ```bash
   # Use BFG Repo-Cleaner or git-filter-repo
   # See: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
   ```
3. **Update baseline** to prevent it from happening again

**Note:** Removing from git history requires coordination with your team and force-pushing. It's better to rotate the secret than try to erase history.

---

## 📚 Additional Resources

- [detect-secrets GitHub](https://github.com/Yelp/detect-secrets)
- [GitHub: Removing Sensitive Data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

---

## 🤝 Team Guidelines

1. **Never commit `.env` files** - They're in `.gitignore` for a reason
2. **Always use environment variables** for secrets
3. **Review the audit carefully** - Don't blindly mark everything as false positive
4. **Rotate secrets if committed** - Better safe than sorry
5. **Ask if unsure** - It's better to ask than leak credentials

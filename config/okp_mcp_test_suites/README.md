# OKP-MCP Test Suites

Test configurations for okp-mcp functional tests converted from `~/Work/okp-mcp/tests/functional_cases.py`.

## Test Modes

### Retrieval-Only Mode (Fast)
**File:** `functional_tests_retrieval.yaml`
**Purpose:** Isolate and test document retrieval quality
**Metrics:** 3 metrics, no LLM response needed
**Speed:** ~30 seconds per run

```bash
./run_mcp_retrieval_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_retrieval.yaml \
  --runs 3
```

**What it tests:**
- ✓ Document retrieval quality (URL F1, MRR, ranking)
- ✓ Context precision (retrieved docs ranked correctly)
- ✓ Context relevance (retrieved docs match query intent)

**Use when:**
- Tuning okp-mcp boost queries
- Optimizing Solr filters
- Testing document ranking changes
- Rapid iteration (no LLM inference overhead)

---

### Full Mode (Complete, Slow)
**File:** `functional_tests_full.yaml`
**Purpose:** End-to-end validation with complete answer checking
**Metrics:** 5 metrics, requires full LLM response
**Speed:** ~3-5 minutes per run

```bash
./run_okp_mcp_full_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_full.yaml \
  --runs 3
```

**What it tests:**
- ✓ Everything from retrieval-only mode, PLUS:
- ✓ Required facts present in LLM response (keywords_eval)
- ✓ Forbidden claims avoided (regression detection)

**Use when:**
- Pre-commit validation
- Verifying end-to-end correctness
- Checking if LLM properly uses retrieved docs
- Testing complete INCORRECT_ANSWER_LOOP workflow

---

## File Summary

| File | Metrics | Use With | Purpose |
|------|---------|----------|---------|
| `functional_tests_retrieval.yaml` | 3 (retrieval) | `run_mcp_retrieval_suite.sh` | Fast iteration |
| `functional_tests_full.yaml` | 5 (retrieval + answer) | `run_okp_mcp_full_suite.sh` | Complete validation |
| `functional_tests.yaml` | 5 (same as full) | Either script | Default/convenience |

## Regenerating Test Suites

```bash
# Regenerate retrieval-only tests
python scripts/convert_functional_cases_to_eval.py \
  --input ~/Work/okp-mcp/tests/functional_cases.py \
  --output config/okp_mcp_test_suites/functional_tests_retrieval.yaml \
  --mode retrieval_only

# Regenerate full tests
python scripts/convert_functional_cases_to_eval.py \
  --input ~/Work/okp-mcp/tests/functional_cases.py \
  --output config/okp_mcp_test_suites/functional_tests_full.yaml \
  --mode full
```

## Workflow: Fast Iteration → Full Validation

### Day-to-day Development (Fast)
```bash
# 1. Edit okp-mcp boost queries
cd ~/Work/okp-mcp
vim src/okp_mcp/portal.py

# 2. Restart okp-mcp
cd ~/Work/lscore-deploy/local
podman-compose restart okp-mcp

# 3. Test retrieval quality (fast)
cd ~/Work/lightspeed-core/lightspeed-evaluation
./run_mcp_retrieval_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_retrieval.yaml \
  --runs 3

# 4. Check results
cat mcp_retrieval_output/suite_*/analysis/*.png
```

### Before Commit (Slow, Complete)
```bash
# Run full suite to validate complete correctness
./run_okp_mcp_full_suite.sh \
  --config config/okp_mcp_test_suites/functional_tests_full.yaml \
  --runs 3

# Check all metrics passed
cat okp_mcp_full_output/suite_*/run_001/evaluation_*_summary.txt
```

## Test Case Coverage

All test suites contain **20 RSPEED test cases**:
- RSPEED-2482: RHEL 6 container compatibility
- RSPEED-2481: SPICE deprecation
- RSPEED-2480: VM management tools
- RSPEED-2479: EUS support duration
- RSPEED-2478: EUS release availability
- RSPEED-2698: RHEL 10 support lifecycle
- RSPEED-2697: RHEL 10 release date
- RSPEED-2294: Python version for RHEL 10
- RSPEED-2201: AWS Secure Boot
- RSPEED-2200: Hugepages configuration
- fuse_regression_eol: Red Hat Fuse migration
- gluster_regression_eol: Gluster Storage migration
- rhv_regression_eol: RHV to OpenShift Virtualization
- RSPEED-1998: SAP package list
- sap_004: SAP System Roles
- RSPEED-2136: SELinux custom policy
- RSPEED-2123: bnxt_en driver debugging
- RSPEED-2745: RHEL 7 maintenance end date
- RSPEED-2113: LACP bonding configuration
- RSPEED-1931: rpm-ostree kernel arguments

See `~/Work/okp-mcp/tests/functional_cases.py` for full test case details.

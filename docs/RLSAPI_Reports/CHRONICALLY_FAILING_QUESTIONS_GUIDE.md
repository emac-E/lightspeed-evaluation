# Chronically Failing Questions - Usage Guide

## Overview

The `config/chronically_failing_questions.yaml` file contains the **top 10 worst performing questions** identified across 15+ evaluation runs. Use this focused test suite to:

- **Measure okp-mcp improvements** (lifecycle de-boost, version filtering)
- **Fast iteration** (10 questions vs 100+)
- **Targeted debugging** (each question has specific root cause documented)

## Performance Baseline (Before Fixes)

| Metric | Current | Target After Fixes |
|--------|---------|-------------------|
| Average answer_correctness | **45%** | **75%+** |
| Average context_recall | **35%** | **70%+** |
| Lifecycle docs per query | **6.5** | **< 2** |
| Expected contexts found | **30%** | **80%+** |

## Quick Start

### Run Against Current okp-mcp (Baseline)

```bash
cd ~/Work/lightspeed-core/lightspeed-evaluation

# Set environment
export OPENAI_API_KEY="your-key"
export API_KEY="your-api-key"

# Run evaluation
make run-evaluation \
  EVAL_CONFIG=config/chronically_failing_questions.yaml \
  SYSTEM_CONFIG=config/system.yaml

# Results will be in: eval_output/chronically_failing_<timestamp>/
```

### Run Against Modified okp-mcp (After Fixes)

```bash
# Option 1: Point to modified okp-mcp deployment
# Update config/system.yaml:
#   api:
#     api_base: "http://localhost:8080"  # Modified okp-mcp

# Option 2: Use pre-built cache from rls-dev-tests
cp -r ~/Work/rls-dev-tests/.caches/lifecycle_test_cache .caches/api_cache

# Update config/system.yaml:
#   api:
#     cache_enabled: true
#     cache_dir: ".caches/api_cache"

# Run evaluation
make run-evaluation \
  EVAL_CONFIG=config/chronically_failing_questions.yaml \
  SYSTEM_CONFIG=config/system.yaml
```

## What Each Question Tests

### 1. TEMPORAL-ADDED-003 (23% correct)
**Question:** "What kernel version does RHEL 10 use?"

**Problem:**
- Retrieves 37 lifecycle/policy documents
- ZERO kernel version documentation
- context_recall: 0%

**Fix validates:**
- De-boosting lifecycle docs works
- Technical documentation (release notes) ranks higher

### 2. TEMPORAL-MIGRATION-001 (33% correct)
**Question:** "How do I migrate my DHCP server from RHEL 9 to RHEL 10?"

**Problem:**
- Retrieves 8 generic upgrade docs
- ZERO Kea migration documentation
- LLM missed ISC DHCP → Kea change entirely

**Fix validates:**
- Kea documentation is indexed and retrievable
- Version-specific migration docs rank higher

### 3. TEMPORAL-MIGRATION-002 (38% correct)
**Question:** "What changed in Python between RHEL 9 and RHEL 10?"

**Problem:**
- Retrieves 9 lifecycle docs
- ZERO Python version comparison docs

**Fix validates:**
- Version comparison queries work
- Release notes rank higher

### 4. RSPEED-1998 (49% correct)
**Question:** "How to set up Kea?"

**Problem:**
- LLM says "Kea is NOT a Red Hat product" (WRONG!)
- 51 contexts retrieved but NONE mention Kea setup

**Fix validates:**
- Kea setup documentation ranks in top 10 results
- Installation guide is retrievable

### 5. RSPEED-1930 (51% correct)
**Question:** "How do I install a package on a system using rpm-ostree?"

**Problem:**
- ZERO contexts retrieved
- rpm-ostree docs not indexed or poorly ranked

**Fix validates:**
- rpm-ostree documentation exists and is retrievable
- Image mode / ostree queries work

### 6. TEMPORAL-IMPLICIT-001 (52% correct)
**Question:** "How do I set up a DHCP server?" (no version specified)

**Problem:**
- 39 contexts retrieved
- Only 7.7% are RHEL 10 (rest are RHEL 7/8/9)
- No default to current version

**Fix validates:**
- Version filtering defaults to current RHEL (10)
- Old RHEL versions are de-prioritized

### 7. TEMPORAL-REMOVED-001 (53% correct)
**Question:** "How to install and configure a DHCP server in RHEL 10?"

**Problem:**
- Retrieves RHEL 6 documentation (5 major versions old!)
- No version filtering applied

**Fix validates:**
- Version filtering works correctly
- Ancient RHEL versions excluded

### 8. TEMPORAL-ADDED-002 (54% correct)
**Question:** "What DHCP server options are available in RHEL 10?"

**Problem:**
- Retrieves generic DHCP docs
- Doesn't highlight Kea as ONLY option

**Fix validates:**
- RHEL 10-specific feature documentation ranks higher
- Removal notices ("ISC DHCP removed") are surfaced

### 9. RSPEED-2294 (55% correct)
**Question:** "What is most current version of Python for RHEL 10?"

**Problem:**
- LLM says "RHEL 10 not released yet" (WRONG!)
- Outdated contexts retrieved

**Fix validates:**
- Current release documentation is surfaced
- Recency bias works correctly

### 10. RSPEED-1812 (56% correct)
**Question:** "Where can I find documentation for RHEL System Roles?"

**Problem:**
- LLM provides broken/fabricated URLs
- Real URLs not in retrieved contexts

**Fix validates:**
- Official documentation URLs are retrieved
- URL faithfulness improves

## Analyzing Results

### Compare Before/After

```bash
# Before fixes
cd eval_output/chronically_failing_20260330_120000/

# After fixes
cd eval_output/chronically_failing_20260330_140000/

# Compare metrics
diff detailed_summary_report.txt ../chronically_failing_20260330_120000/detailed_summary_report.txt
```

### Key Metrics to Track

**1. Context Recall (Most Important)**
- Measures: How much of ground truth is in retrieved contexts
- Goal: > 70% (currently ~35%)
- File: `detailed_summary_report.txt` → "context_recall"

**2. Answer Correctness**
- Measures: LLM answer quality vs expected response
- Goal: > 75% (currently ~45%)
- File: `detailed_summary_report.txt` → "answer_correctness"

**3. Context Precision**
- Measures: Relevance of retrieved contexts
- Goal: > 60% (currently ~38%)
- Note: Can be misleadingly high if lifecycle docs are well-formatted

**4. Faithfulness**
- Measures: LLM answer supported by contexts
- Goal: > 80% (currently ~40%)
- Indicates RAG_BYPASS when low (LLM uses parametric knowledge)

### Per-Question Analysis

Check `detailed.csv` for per-question breakdown:

```bash
# Extract context_recall for each question
grep "TEMPORAL-ADDED-003" eval_output/*/detailed.csv | cut -d',' -f7

# Count lifecycle docs per question (manual review of contexts column)
grep "TEMPORAL-ADDED-003" eval_output/*/detailed.csv | cut -d',' -f5
```

## Expected Improvements After Fixes

### Lifecycle De-boost Fix

**Questions affected:** TEMPORAL-ADDED-003, TEMPORAL-MIGRATION-001, TEMPORAL-ADDED-002

**Expected changes:**
- Lifecycle docs per query: 6.5 → 1.2 (-82%)
- context_recall: 35% → 65% (+86%)
- Technical docs in top 10: 30% → 80% (+167%)

### Version Filtering Fix

**Questions affected:** TEMPORAL-REMOVED-001, TEMPORAL-IMPLICIT-001, TEMPORAL-MIGRATION-002

**Expected changes:**
- Wrong-version docs retrieved: 60% → 5% (-92%)
- context_recall: 30% → 70% (+133%)
- RHEL 10 docs in top 10: 20% → 90% (+350%)

### Missing Documentation Fix

**Questions affected:** RSPEED-1998, RSPEED-1930

**Expected changes:**
- Zero-context retrieval rate: 30% → 5% (-83%)
- Expected keywords found: 30% → 75% (+150%)
- RAG_BYPASS rate: 40% → 10% (-75%)

## Troubleshooting

### Question still fails after fixes

1. **Check contexts retrieved:**
   ```bash
   # Extract contexts for failing question
   grep "QUESTION_ID" eval_output/*/detailed.csv | cut -d',' -f5 > contexts.txt
   ```

2. **Verify expected content is present:**
   ```bash
   # Search for expected keywords in contexts
   grep -i "expected_keyword" contexts.txt
   ```

3. **Check Solr query:**
   ```bash
   # Enable debug logging to see Solr queries
   export LOG_LEVEL=DEBUG
   make run-evaluation EVAL_CONFIG=config/chronically_failing_questions.yaml
   ```

### Metrics don't improve

- **If context_recall doesn't improve:** Contexts still don't contain ground truth → okp-mcp changes didn't work
- **If answer_correctness doesn't improve but context_recall does:** LLM not using contexts well → try different LLM or prompt
- **If faithfulness is low:** LLM ignoring contexts → check system prompt, try lower temperature

## Next Steps

1. **Run baseline** with current okp-mcp
2. **Deploy fixes** to okp-mcp (lifecycle de-boost, version filtering)
3. **Run comparison** with modified okp-mcp
4. **Measure improvement** on these 10 questions
5. **If good (> 70% improvement):** Run full evaluation suite
6. **If not:** Debug specific questions and iterate

## Integration with Full Evaluation

Once the 10 questions show improvement, validate across full suite:

```bash
# Run all temporal validity tests (15 questions)
make run-evaluation \
  EVAL_CONFIG=config/temporal_validity_tests_runnable.yaml \
  SYSTEM_CONFIG=config/system.yaml

# Run all jira incorrect answers (30+ questions)
make run-evaluation \
  EVAL_CONFIG=config/jira_incorrect_answers.yaml \
  SYSTEM_CONFIG=config/system.yaml

# Run full suite (100+ questions)
# Create combined config or run multiple configs
```

## Summary

The `chronically_failing_questions.yaml` config gives you:
- **Fast feedback** (10 questions, ~5 minutes vs 100+ questions, ~60 minutes)
- **Targeted validation** (each question tests specific fix)
- **Clear success criteria** (documented baselines and targets)
- **Debugging info** (root causes documented per question)

Use it to iterate quickly on okp-mcp improvements before running expensive full evaluations.

# RAG Quality Comparison: Main Branch (Today) vs Test Branch (Friday)

**Analysis Date:** 2026-03-30
**Comparison:** `full_suite_20260330_114104` (main) vs `full_suite_20260327_170453` (test branch)

---

## Executive Summary

### Overall Performance: Main Branch Shows Mixed Results

**Improvements (✅):**
- **Response Relevancy:** +6.2% (84.0% → 90.2%) - LLM responses are more relevant to questions
- **Answer Correctness:** +6.5% (70.0% → 76.5%) - More factually correct answers
- **Faithfulness:** +3.1% (40.0% → 43.1%) - Slightly better adherence to contexts
- **Context Relevance:** +3.2% (36.0% → 39.2%) - Marginally better topic matching

**Regressions (❌):**
- **Context Recall:** -6.5% (24.5% → 18.0%) - Retrieved docs contain LESS of the needed info
- **Context Precision:** -6.7% (44.0% → 37.3%) - MORE irrelevant docs in retrieval

### Key Insight
The LLM is getting better at answering despite WORSE retrieval quality. This suggests the LLM is relying more on parametric knowledge (memorized information) rather than the RAG contexts provided by okp-mcp.

---

## Critical RAG Context Problems

### Problem 1: Completely Irrelevant Document Retrieval

**Example: RSPEED-1859**
- **Query:** "How do I see the list of deployments on a system using rpm-ostree?"
- **Expected:** Documentation about `rpm-ostree status` command
- **Retrieved Instead:**
  1. Service Telemetry Framework deprecation notices
  2. Red Hat Gluster Storage Life Cycle docs
  3. Red Hat Lightspeed information pages
  4. Keycloak Life Cycle policies

**Impact:**
- context_precision: 0.0 (0% useful docs)
- context_relevance: 0.0 (0% topic match)
- context_recall: 0.0 (0% of needed info present)
- **BUT** answer_correctness: 1.0 (100% correct!) ← LLM used parametric knowledge

### Problem 2: Wrong Version/Outdated Documentation

**Example: TEMPORAL-MIGRATION-001**
- **Query:** "How do I migrate my DHCP server from RHEL 9 to RHEL 10?"
- **Expected:** Kea DHCP (RHEL 10) vs ISC DHCP (RHEL 9) migration guide
- **Retrieved Instead:**
  1. RHEL 5 documentation (3 major versions old!)
  2. RHEL 6 multihomed DHCP server config (obsolete, wrong topic)
  3. SSH protocol documentation (completely wrong service)

**Impact:**
- Query needs RHEL 9→10 migration info
- Gets RHEL 5, RHEL 6 legacy docs
- No mention of Kea DHCP (the critical new technology in RHEL 10)

### Problem 3: Missing Context on Version-Specific Changes

**Pattern across temporal validity tests:**
- Questions about RHEL 10 features get RHEL 7/8/9 docs
- Questions about removed features (ISC DHCP, network-scripts) don't retrieve deprecation notices
- Questions about new features (Kea, Python 3.12, kernel 6.x) get generic/old version docs

---

## Metric-by-Metric Analysis

### Context Precision (37.3%, -6.7%)
**What it measures:** % of retrieved contexts that are actually useful

**Why it's failing:**
1. Over-retrieval: Returning 8-13 documents per query when only 1-2 are relevant
2. Topic drift: Queries about "rpm-ostree" returning docs about "Gluster Storage" and "Keycloak"
3. No negative filtering: Old RHEL versions aren't being filtered out

**Examples:**
- RSPEED-1859: 13 docs retrieved, 0 relevant (precision: 0.0)
- RSPEED-2200: 200+ contexts mentioned in appendix, only 8 mention Kea DHCP (precision: 0.04)

### Context Recall (18.0%, -6.5%)
**What it measures:** Does retrieved context contain the information needed to answer?

**Why it's worsening:**
1. Missing key technical details (e.g., grubby command parameters for hugepages)
2. Missing version-specific information (RHEL 10 changes)
3. Missing migration/deprecation documentation

**Critical gaps:**
- TEMPORAL-MIGRATION-001: No ISC DHCP → Kea migration docs
- TEMPORAL-REMOVED-001: No clear "ISC DHCP removed in RHEL 10" notice
- RSPEED-2200: Missing `default_hugepagesz=1G` parameter documentation

### Context Relevance (39.2%, +3.2%)
**What it measures:** How well contexts match query intent

**Slight improvement but still poor:**
- Still below 40% pass rate
- Marginal gains masked by severe failures on specific query types
- rpm-ostree, temporal validity, and migration queries especially bad

### Answer Correctness (76.5%, +6.5%)
**What it measures:** Is the final answer factually correct?

**Good news, but concerning:**
- LLM is often correct DESPITE bad contexts
- 21 "RAG_BYPASS" anomalies detected across runs
- "PARAMETRIC_KNOWLEDGE" anomalies: LLM answered correctly with zero context scores

**This means:** The LLM knows RHEL better than okp-mcp's retrieval can show it!

---

## Specific Question-Level Analysis

### Questions That Got Worse

| Question | Friday | Today | Issue |
|----------|--------|-------|-------|
| RSPEED-1998 (Kea setup) | 0% answer correct | 100% answer correct | ✅ Massive improvement! |
| TEMPORAL-IMPLICIT-001 (DHCP setup) | 5/6 fail | 6/6 fail | ❌ Complete RAG failure, wrong era docs |
| TEMPORAL-MIGRATION-001 (DHCP migration) | 3/6 fail | 5/6 fail | ❌ No Kea migration docs retrieved |
| RSPEED-2482 (RHEL 6 containers) | 2/5 fail | 5/6 fail | ❌ Compatibility matrix not retrieved |

### Questions That Improved

| Question | Improvement |
|----------|-------------|
| RSPEED-1998 (Kea setup) | 0.0 → 1.0 answer_correctness |
| TEMPORAL-ADDED-002 (DHCP options) | All RAG metrics now passing |
| virtualization_deprecation/spice_status | All metrics passing |

---

## Root Cause Analysis

### 1. **Vector Search/Semantic Matching Issues**
- Keywords like "rpm-ostree" matching unrelated deprecation notices
- "DHCP migration" not matching Kea vs ISC DHCP context
- Version filtering not working (RHEL 5/6/7/8 docs returned for RHEL 10 queries)

### 2. **Document Chunking/Indexing Problems**
- Relevant docs may exist but aren't being retrieved
- Deprecation warnings getting higher relevance than technical docs
- Legal notices, product announcements polluting results

### 3. **Missing or Poorly Tagged Documents**
Based on retrieval failures, okp-mcp may be missing:
- RHEL 10-specific migration guides (ISC DHCP → Kea)
- rpm-ostree command reference docs
- RHEL version compatibility matrices
- Temporal validity markers (when features added/removed)

---

## Recommendations for Improving ~/Work/okp-mcp

### High Priority (Critical for RAG Quality)

#### 1. **Implement RHEL Version Filtering**
```python
# Current behavior: Returns RHEL 5/6/7/8 docs for RHEL 10 queries
# Needed: Version-aware filtering

# When query mentions RHEL 10:
- Filter: version >= 9 (current and previous major version)
- Boost: version == 10
- Penalize: version < 8
```

**Impact:** Would fix ~40% of context_relevance failures

#### 2. **Add Negative Keywords/Topic Filtering**
```python
# Query: "rpm-ostree deployments"
# Block retrieval of:
- "Service Telemetry Framework"
- "Gluster Storage"
- "Keycloak"
- Product life cycle docs (unless query contains "life cycle" or "support")
```

**Impact:** Would improve context_precision from 37% → ~60%

#### 3. **Enhance Kea DHCP Documentation Coverage**
Missing critical docs:
- ISC DHCP (RHEL ≤9) → Kea DHCP (RHEL 10) migration guide
- Kea configuration examples for common scenarios
- DHCP server comparison table (ISC vs Kea)

**Where to add:**
- Check if `/content/en-us/red_hat_enterprise_linux/10/html/considerations_in_adopting_rhel_10/infrastructure-services` exists in okp-mcp
- If missing: This is your gap!

#### 4. **Improve rpm-ostree Documentation Retrieval**
Current failure: 0% relevant docs for rpm-ostree queries

**Check okp-mcp for:**
- `/content/en-us/red_hat_enterprise_linux/*/html/composing*` (CoreOS/Image Mode docs)
- `/content/en-us/red_hat_enterprise_linux/*/html/managing_software*` sections on rpm-ostree
- `man` pages for rpm-ostree commands

### Medium Priority

#### 5. **Add Temporal Validity Metadata**
Tag documents with:
- `introduced_in: RHEL X.Y`
- `deprecated_in: RHEL X.Y`
- `removed_in: RHEL X.Y`

**Use cases:**
- Query: "Is network-scripts available in RHEL 10?" → Retrieve removal notice
- Query: "DHCP options in RHEL 10" → Retrieve Kea docs, suppress ISC DHCP docs

#### 6. **Boost Technical Documentation Over Lifecycle Docs**
```python
# Scoring adjustments:
- Technical docs (installation, configuration, troubleshooting): +2.0x boost
- Product lifecycle/support policy docs: -0.5x penalty (unless query contains "support" or "lifecycle")
- Legal notices, deprecation warnings: Only include if explicitly requested
```

#### 7. **Reduce Retrieved Document Count**
Current: 8-13 documents per query
Optimal: 3-5 highly relevant documents

**Why:** Lower precision (37%) means more docs = more noise

### Low Priority (Nice to Have)

#### 8. **Add Query Expansion for Version Migration**
```python
# Query: "migrate DHCP from RHEL 9 to RHEL 10"
# Expand to:
- "ISC DHCP Kea migration"
- "dhcp-server deprecated RHEL 10"
- "Kea DHCP installation RHEL 10"
```

#### 9. **Improve Chunk Boundaries**
Ensure complete concepts in each chunk:
- Full command syntax + all parameters
- Complete procedure steps (1-N, not split across chunks)
- Context about what changed between versions

---

## Testing Your Improvements

### Benchmark Questions (Current Failures)

Test these after okp-mcp changes:

1. **rpm-ostree queries:**
   - "How do I see the list of deployments on a system using rpm-ostree?"
   - Expected: Retrieve `rpm-ostree status` command docs
   - Current: 0% relevant docs

2. **DHCP migration:**
   - "How do I migrate my DHCP server from RHEL 9 to RHEL 10?"
   - Expected: ISC DHCP → Kea migration guide
   - Current: RHEL 5/6 legacy docs, no Kea mention

3. **Version-specific features:**
   - "What is the default Python version in RHEL 10?"
   - Expected: Python 3.12 docs
   - Current: Generic Python docs, no version specificity

4. **Removed features:**
   - "Is network-scripts still available in RHEL 10?"
   - Expected: Removal notice + NetworkManager alternative
   - Current: Mixed messages, unclear

### Success Criteria

| Metric | Current | Target | Stretch Goal |
|--------|---------|--------|--------------|
| context_precision | 37.3% | 60% | 75% |
| context_recall | 18.0% | 50% | 70% |
| context_relevance | 39.2% | 65% | 80% |
| answer_correctness | 76.5% | 85% | 90% |

### Re-evaluation Command
```bash
cd ~/Work/lightspeed-core/lightspeed-evaluation
./run_full_evaluation_suite.sh
```

Compare with: `full_suite_20260330_114104` (baseline)

---

## Questions for okp-mcp Team

1. **RHEL Version Filtering:**
   - Does okp-mcp have RHEL version metadata on documents?
   - Is there version-aware filtering in the retrieval pipeline?

2. **Kea DHCP Coverage:**
   - What RHEL 10 Kea DHCP documentation is indexed?
   - Is the ISC → Kea migration guide in the knowledge base?

3. **rpm-ostree Documentation:**
   - What Image Mode / rpm-ostree docs are available?
   - Why would "rpm-ostree" query return Gluster/Keycloak docs?

4. **Document Ranking:**
   - How are deprecation notices, lifecycle docs, and technical docs weighted?
   - Can we boost technical documentation for how-to queries?

5. **Retrieval Count:**
   - Is 8-13 documents per query configurable?
   - What's the rationale for current count?

---

## Appendix: Anomaly Types Detected

**RAG_BYPASS (21 cases):** LLM answered correctly despite poor context retrieval
- Indicates LLM parametric knowledge > RAG quality
- Examples: RSPEED-1859, RSPEED-1902, RSPEED-2200, RSPEED-2479

**PARAMETRIC_KNOWLEDGE (2-6 cases):** Correct answer with zero context scores
- LLM relied entirely on training data, not retrieved docs
- Examples: RSPEED-1859, RSPEED-2200, RSPEED-1930

**WRONG_DESPITE_GOOD_CONTEXT (3-6 cases):** Good retrieval but wrong answer
- Less common, but shows LLM can still fail with good docs
- Examples: rhel10_operations/gnome_configuration

**UNFAITHFUL_RESPONSE (2 cases):** Response not supported by contexts
- Retrieved docs don't contain the answer given
- Examples: eus_support_timeline/eus_duration

---

**Bottom Line:** The main branch improved LLM answer quality (+6.5%) but RAG retrieval quality worsened (context precision -6.7%, context recall -6.5%). This is concerning because it means okp-mcp is becoming less effective at providing useful context. The LLM is compensating with its own knowledge, but this undermines the value proposition of RAG-based answers.

**Primary Action Items:**
1. Implement RHEL version filtering
2. Add Kea DHCP migration documentation
3. Fix rpm-ostree documentation retrieval
4. Reduce irrelevant document pollution (Gluster, Keycloak, etc.)

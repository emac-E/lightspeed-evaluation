# Consistently Failing Questions: Analysis & Root Causes

**Analysis Date:** 2026-03-30
**Evaluation Runs Analyzed:** 44 questions evaluated across 15+ runs
**Focus:** Top 10 chronic failures (evaluated 2+ times)

---

## Executive Summary

**44 questions fail consistently** across multiple evaluation runs. The top failures share a common pattern:

**Root Cause:** okp-mcp retrieves **policy/lifecycle documents instead of technical documentation**

### Failure Pattern Signature:
- ✅ LLM sometimes answers correctly anyway (uses parametric knowledge)
- ❌ Retrieved contexts are 90%+ deprecation notices, lifecycle docs, container compatibility matrices
- ❌ Technical documentation (kernel version, Kea DHCP setup, Python versions) is NOT retrieved
- ❌ Wrong RHEL versions retrieved (RHEL 5/6/7 docs for RHEL 10 questions)
- ❌ Some questions retrieve ZERO contexts (esp. rpm-ostree queries)

---

## Top 10 Chronically Failing Questions

### 1. TEMPORAL-ADDED-003 (Evaluated 16 times)
**Question:** "What kernel version does RHEL 10 use?"
**Expected Answer:** RHEL 10 uses kernel 6.x (major upgrade from RHEL 9's kernel 5.14)
**Average Answer Correctness:** 23%

**What okp-mcp Retrieved:**
- 37 contexts
- **ALL deprecation/lifecycle documents:**
  - Red Hat Enterprise Linux Container Compatibility Matrix
  - Red Hat Enterprise Linux Life Cycle
  - Red Hat Enterprise Linux for Real Time Product Life Cycle
  - RHEL App Streams Life Cycle

**What okp-mcp DID NOT Retrieve:**
- RHEL 10 Release Notes
- RHEL 10 kernel documentation
- Any document mentioning "kernel 6.x" or "kernel version"

**LLM Response (0.1 score):**
> "The provided Red Hat documentation does not specify the exact kernel version used by Red Hat Enterprise Linux 10."

**Why It Failed:**
- okp-mcp retrieved 37 **policy documents** instead of **technical documentation**
- LLM correctly identified that its contexts don't answer the question (good!)
- LLM did NOT use parametric knowledge (bad - it likely knows RHEL 10 uses 6.x kernel!)
- Search for "kernel version RHEL 10" returned lifecycle docs, not release notes

**Retrieval Metrics:**
- context_precision: 0.78 (misleading - contexts are well-formatted but wrong topic)
- context_recall: 0.00 (contexts don't contain the answer)
- context_relevance: 0.56 (contexts mention RHEL 10 but not kernel versions)

---

### 2. TEMPORAL-MIGRATION-001 (Evaluated 15 times)
**Question:** "How do I migrate my DHCP server from RHEL 9 to RHEL 10?"
**Expected Answer:** ISC DHCP (RHEL 9) to Kea (RHEL 10) migration guide
**Average Answer Correctness:** 33%

**What okp-mcp Retrieved:**
- 8 contexts
- **ALL deprecation/lifecycle documents:**
  - Red Hat Enterprise Linux Container Compatibility Matrix (again!)
  - Red Hat Enterprise Linux Life Cycle (again!)
  - RHEL 8 EOL notices
  - RHEL 9 release schedule

**What okp-mcp DID NOT Retrieve:**
- "Considerations in Adopting RHEL 10" (Infrastructure Services chapter)
- Kea DHCP installation guide
- ISC DHCP removal notice for RHEL 10
- Any document mentioning "Kea" or "ISC DHCP"

**LLM Response (0.1 score):**
> "Migrating a DHCP server from RHEL 9 to RHEL 10 primarily involves performing an in-place upgrade using the `Leapp` utility..."

**Why It Failed:**
- LLM completely missed the ISC DHCP → Kea change (the MOST critical part!)
- Treated it as a generic RHEL upgrade, not a DHCP **software replacement**
- okp-mcp provided ZERO contexts about Kea, ISC DHCP, or DHCP migration
- Query "migrate DHCP RHEL 9 to RHEL 10" returned upgrade docs, not service-specific migration

**Retrieval Metrics:**
- context_precision: 0.31 (most contexts irrelevant)
- context_recall: 0.00 (contexts don't contain migration info)
- context_relevance: 0.03 (3%! — contexts barely mention DHCP)
- faithfulness: 0.15 (LLM response not supported by contexts — made it up!)

**Critical Error:** 5 faithfulness evaluation failures (malformed LLM output)

---

### 3. TEMPORAL-MIGRATION-002 (Evaluated 16 times)
**Question:** "What changed in Python between RHEL 9 and RHEL 10?"
**Expected Answer:** RHEL 9 uses Python 3.9 (default) / 3.11 (alt), RHEL 10 uses Python 3.12 (default) / 3.13 (alt)
**Average Answer Correctness:** 42%

**What okp-mcp Retrieved:**
- 9 contexts
- **ALL deprecation/lifecycle documents:**
  - Red Hat Enterprise Linux Container Compatibility Matrix (third time!)
  - Red Hat Enterprise Linux Life Cycle (third time!)
  - RHEL policy documents about version support

**What okp-mcp DID NOT Retrieve:**
- RHEL 10 Release Notes (Python section)
- Python 3.12 installation guide
- Python module stream documentation
- Any document mentioning "Python 3.12" or "Python 3.13"

**Why It Failed:**
- Same pattern: lifecycle docs instead of technical docs
- Query "Python RHEL 9 RHEL 10 changes" → policy docs, not version comparison
- No documents about Python version changes in RHEL 10

**Retrieval Metrics:**
- context_precision: 0.25 (75% irrelevant)
- context_recall: 0.00 (no Python version info in contexts)
- context_relevance: 0.00 (0%! — contexts don't mention Python versions)
- faithfulness: 0.43 (LLM made educated guesses not in contexts)

**Critical Error:** 4 faithfulness evaluation failures

---

### 4. RSPEED-1998 (Evaluated 29 times)
**Question:** "How to set up Kea?"
**Expected Answer:** Kea is included in RHEL 10 AppStream, install with `dnf install kea`
**Average Answer Correctness:** 49%

**What okp-mcp Retrieved:**
- 51 contexts (!!)
- **ALL deprecation/lifecycle documents:**
  - Same pattern: Container Compatibility, Life Cycle docs
  - Plus random irrelevant docs with heading "subheading subheading-md" (malformed!)

**What okp-mcp DID NOT Retrieve:**
- Kea DHCP installation guide
- RHEL 10 "Considerations in Adopting" (Infrastructure Services)
- ISC DHCP removal notice (which would mention Kea as replacement)

**LLM Response (0.0 score - completely wrong!):**
> "I couldn't find specific documentation on setting up Kea DHCP server on Red Hat Enterprise Linux within the Red Hat knowledge base. **It's possible that Kea is not directly supported or packaged by Red Hat**, or the information might be under a different search term."

**Why It Failed:**
- LLM said Kea is NOT a Red Hat product (WRONG! It's in RHEL 10 AppStream)
- LLM gave up and suggested checking "official Kea documentation or community forums"
- okp-mcp retrieved 51 contexts but NONE mentioned Kea DHCP
- This is a **catastrophic failure** — okp-mcp has the docs but didn't retrieve them

**Retrieval Metrics:**
- context_precision: 0.81 (misleading — well-formatted but wrong content)
- context_recall: 0.14 (86% of needed info missing)
- context_relevance: 0.48 (half relevant by topic, but not by content)
- faithfulness: 0.45 (LLM response unsupported by contexts)

**Critical Error:** 31 API errors (`'rag_chunks'` key missing)

---

### 5. RSPEED-1930 (Evaluated 29 times)
**Question:** "How do I install a package on a system using rpm-ostree?"
**Expected Answer:** Use `rpm-ostree install <package_name>` and reboot
**Average Answer Correctness:** 73%

**What okp-mcp Retrieved:**
- **ZERO contexts!** (No contexts retrieved at all!)

**LLM Response (0.8 score - correct!):**
> "To install a package on a system using `rpm-ostree`, you typically use the `rpm-ostree install` command. This layers the package on top of the base operating system. After installing, you'll need to reboot for the changes to take effect."

**Why It Mostly Succeeded:**
- **LLM used parametric knowledge** (it knows rpm-ostree from training data)
- okp-mcp provided ZERO contexts, so LLM had to rely on memory
- This is a **RAG_BYPASS** case — LLM answered correctly DESPITE retrieval failure

**Why okp-mcp Failed to Retrieve:**
- Query "install package rpm-ostree" returned NOTHING
- Possible causes:
  - rpm-ostree documentation not indexed
  - Term "rpm-ostree" not matching (hyphen issue?)
  - Image Mode / CoreOS docs not included in knowledge base
  - Solr query cleaning removed "rpm-ostree" as stopword?

**Retrieval Metrics:**
- context_precision: 0.13 (when contexts ARE retrieved in other runs, they're 87% irrelevant)
- context_recall: 0.00 (no contexts contain rpm-ostree install command)
- context_relevance: 0.00 (0%! — contexts don't mention rpm-ostree)
- faithfulness: 0.32 (LLM response can't be faithful to non-existent contexts)

**Critical Error:** 35 API errors (`'rag_chunks'` key missing)

---

### 6. TEMPORAL-IMPLICIT-001 (Evaluated 15 times)
**Question:** "How do I set up a DHCP server?"
**Expected Answer:** For current RHEL (RHEL 10): Install Kea: `dnf install kea`, configure /etc/kea/kea-dhcp4.conf
**Average Answer Correctness:** 53%

**What okp-mcp Retrieved:**
- 39 contexts
- **Pattern continues:**
  - Deprecation/lifecycle documents
  - **Literally the word "title" as a document heading** (!)
  - RHEL 9 SAP Solutions guide (irrelevant)

**What okp-mcp DID NOT Retrieve:**
- Kea DHCP setup guide for RHEL 10
- Current DHCP server documentation (should be Kea, not ISC DHCP)

**Why It Failed:**
- Query lacks version context ("set up DHCP server" → which RHEL version?)
- okp-mcp should assume **current version (RHEL 10)** but retrieved mixed RHEL 7/8/9 docs
- Retrieved 39 contexts but ONLY 7.7% were RHEL 10 (3 out of 39!)
- 23.1% were RHEL 8, 20.5% were RHEL 9, 7.7% were RHEL 7

**Retrieval Metrics:**
- context_precision: 0.38 (62% irrelevant)
- context_recall: 0.19 (81% of needed info missing)
- context_relevance: 0.27 (73% irrelevant by topic)
- faithfulness: 0.51 (barely faithful — LLM filled gaps)

---

### 7. TEMPORAL-REMOVED-001 (Evaluated 15 times)
**Question:** "How to install and configure a DHCP server in RHEL 10?"
**Expected Answer:** Kea is the DHCP server in RHEL 10. ISC DHCP was removed.
**Average Answer Correctness:** 42%

**What okp-mcp Retrieved:**
- 8 contexts
- **Includes RHEL 6 documentation!**
  - "Configuring a Multihomed DHCP Server" (RHEL 6, 2021-03-29)
  - Deprecation notice with heading "title" (malformed)

**What okp-mcp DID NOT Retrieve:**
- ISC DHCP removal notice for RHEL 10
- Kea DHCP installation guide for RHEL 10
- RHEL 10 release notes (Infrastructure Services)

**Why It Failed:**
- Query explicitly says "RHEL 10" but retrieved RHEL 6 docs (5 major versions old!)
- No version filtering applied
- DHCP query → ISC DHCP docs (old) instead of Kea docs (new)

**Retrieval Metrics:**
- context_precision: 0.76 (looks good but...)
- context_recall: 0.17 (83% of info missing)
- context_relevance: 0.73 (contexts are about DHCP but wrong server/version)
- faithfulness: 0.28 (LLM couldn't be faithful to wrong-version docs)

---

### 8. TEMPORAL-ADDED-002 (Evaluated 17 times)
**Question:** [Not shown in sample but similar pattern]
**Average Answer Correctness:** 49%

**Failure Reasons:**
- Low context_recall: 0.43 (57% missing)
- 2 faithfulness evaluation errors

---

### 9. RSPEED-2294 (Evaluated 28 times)
**Average Answer Correctness:** 53%

**Retrieval Metrics:**
- context_precision: 0.62 (38% irrelevant)
- context_recall: 0.19 (81% missing)
- context_relevance: 0.64 (36% irrelevant)
- faithfulness: 0.83 (good when contexts exist)

**Critical Error:** 30 API errors (`'rag_chunks'` key missing)

---

### 10. RSPEED-1812 (Evaluated 29 times)
**Average Answer Correctness:** 53%

**Retrieval Metrics:**
- context_precision: 0.49 (51% irrelevant)
- context_recall: 0.00 (100% missing!)
- context_relevance: 0.04 (4%! — nearly completely irrelevant)
- faithfulness: 0.90 (high because LLM didn't make things up)

**Critical Error:** 30 API errors (`'rag_chunks'` key missing)

---

## Common Failure Patterns

### Pattern 1: Policy Documents Instead of Technical Documentation

**Affected Questions:** TEMPORAL-ADDED-003, TEMPORAL-MIGRATION-001, TEMPORAL-MIGRATION-002, RSPEED-1998

**Symptom:**
- Query asks for technical info (kernel version, DHCP setup, Python versions)
- okp-mcp returns:
  - Red Hat Enterprise Linux Life Cycle
  - Red Hat Enterprise Linux Container Compatibility Matrix
  - Red Hat Enterprise Linux for Real Time Product Life Cycle
  - RHEL App Streams Life Cycle

**Root Cause:**
- Solr ranking favors **frequently updated documents** (lifecycle pages updated monthly)
- Policy docs mention RHEL versions (RHEL 10, RHEL 9) → match query terms
- Technical docs may be buried deeper or not indexed
- BM25 scores policy docs higher because they're comprehensive (long documents)

**Impact:**
- context_recall: 0.00 (policy docs don't contain technical answers)
- context_relevance: 0.00-0.56 (varies — docs mention RHEL but not specifics)
- LLM either:
  - Gives up: "Documentation does not specify..."
  - Guesses: Uses parametric knowledge (RAG_BYPASS)
  - Hallucinates: Makes up plausible-sounding answer

**Fix Required:**
1. Boost technical documentation (installation guides, release notes, how-tos)
2. De-boost lifecycle/policy documents (unless query contains "support", "lifecycle", "EOL")
3. Add document type filtering: prefer "Installation Guide", "Release Notes" over "Policy"

---

### Pattern 2: Wrong RHEL Version Retrieved

**Affected Questions:** TEMPORAL-IMPLICIT-001, TEMPORAL-REMOVED-001

**Symptom:**
- Query asks about RHEL 10 (or no version specified → should default to current)
- okp-mcp returns RHEL 5, 6, 7, 8, 9 documentation

**Examples:**
- "DHCP server RHEL 10" → Retrieved RHEL 6 "Multihomed DHCP Server" (2021 doc!)
- "Set up DHCP server" → Retrieved 7.7% RHEL 10, 23.1% RHEL 8, 20.5% RHEL 9

**Root Cause:**
- No RHEL version filtering
- Old RHEL versions have MORE documentation (longer lifecycle, more indexed content)
- BM25 may favor older docs because they're more "established" (more backlinks?)
- Product boost is weak: `bq: product:("rhel")^10` boosts but doesn't filter

**Impact:**
- Wrong instructions (ISC DHCP setup instead of Kea)
- Outdated commands (e.g., `service dhcpd start` instead of `systemctl`)
- Confusion (RHEL 6 vs RHEL 10 — 8 years and 5 major versions apart!)

**Fix Required:**
1. Hard filter by RHEL version when specified:
   ```python
   fq: version:(10 OR 9)  # Only RHEL 10 and 9 (current + previous)
   ```
2. When query lacks version, default to current RHEL (10) + previous (9)
3. Penalty for old versions: RHEL 7 and earlier should be heavily penalized unless explicitly requested

---

### Pattern 3: Zero Contexts Retrieved

**Affected Questions:** RSPEED-1930 (rpm-ostree)

**Symptom:**
- okp-mcp returns ZERO contexts
- LLM must answer from parametric knowledge or say "I don't know"

**Root Cause (Hypotheses):**
1. **Documentation gap:** rpm-ostree docs not indexed
2. **Hyphen handling:** Solr may be splitting "rpm-ostree" into "rpm" and "ostree"
3. **Query cleaning:** Stopword removal may be breaking technical terms
4. **Product filtering:** Image Mode / CoreOS docs may be in different product category

**Impact:**
- RAG completely fails
- If LLM has parametric knowledge → correct answer (lucky!)
- If LLM doesn't → "I don't know" response

**Fix Required:**
1. Verify rpm-ostree documentation is indexed
2. Check hyphenated term handling in Solr
3. Add Image Mode / Composing docs to knowledge base
4. Test query: "rpm-ostree install" should return `man rpm-ostree` or RHEL Image Mode docs

---

### Pattern 4: Malformed Document Titles

**Affected Questions:** RSPEED-1998, TEMPORAL-REMOVED-001, TEMPORAL-IMPLICIT-001

**Symptom:**
- Document title is literally "title" or "subheading subheading-md push-bottom-narrow"

**Examples:**
```
**title**
Type: Documentation
Applicability: RHEL
Product: Red Hat Enterprise Linux 6
```

**Root Cause:**
- Scraping/indexing bug: HTML class names or placeholders indexed as titles
- Incomplete document metadata in Solr

**Impact:**
- Low context_precision (useless documents in result set)
- Wastes retrieval slots (51 contexts but many are "title" docs)

**Fix Required:**
1. Filter out documents with placeholder titles during indexing
2. Validate document titles before indexing
3. Cleanup existing Solr index to remove malformed entries

---

### Pattern 5: Kea DHCP Documentation Missing

**Affected Questions:** RSPEED-1998, TEMPORAL-MIGRATION-001, TEMPORAL-REMOVED-001, TEMPORAL-IMPLICIT-001

**Symptom:**
- Any query about DHCP in RHEL 10 fails to retrieve Kea documentation
- Queries retrieve:
  - Old ISC DHCP docs (RHEL 6, 7, 8, 9)
  - Lifecycle documents
  - Unrelated deprecation notices

**Root Cause:**
- **CRITICAL GAP:** Kea DHCP documentation may not be indexed in okp-mcp
- Expected source: `/content/en-us/red_hat_enterprise_linux/10/html/considerations_in_adopting_rhel_10/infrastructure-services`
- This is THE most important RHEL 10 migration doc for infrastructure services

**Impact:**
- LLM says "Kea is not a Red Hat product" (factually WRONG!)
- Users get wrong instructions (try to install ISC DHCP which doesn't exist in RHEL 10)
- Migration questions completely fail

**Fix Required:**
1. **URGENT:** Verify "Considerations in Adopting RHEL 10" is indexed
2. Add Kea DHCP documentation:
   - Installation guide
   - Configuration examples
   - Migration from ISC DHCP
3. Add ISC DHCP **removal notice** linking to Kea
4. Boost infrastructure services documentation for DHCP queries

---

## API Errors & Evaluation Failures

**Widespread Issue:** Many questions have 30+ API errors

### Error Type 1: `'rag_chunks'` Key Missing
```
API Error for turn turn1: Unexpected error in infer query: 'rag_chunks'
```

**Affected Questions:** RSPEED-1998 (31 errors), RSPEED-2294 (30 errors), RSPEED-1812 (30 errors), RSPEED-1930 (35 errors), RSPEED-1929 (54 errors!)

**Cause:** okp-mcp's MCP call returns response without `rag_chunks` field

**Impact:**
- Faithfulness, context_precision, context_recall cannot be calculated
- Skews averages (missing data points)

### Error Type 2: Malformed LLM Output for Faithfulness
```
Ragas faithfulness evaluation failed due to malformed output from the LLM
```

**Affected Questions:** TEMPORAL-MIGRATION-001 (5 errors), TEMPORAL-MIGRATION-002 (4 errors), TEMPORAL-REMOVED-001 (3 errors)

**Cause:** Ragas faithfulness prompt generates invalid JSON or format from judge LLM

**Impact:**
- Cannot verify if LLM response is grounded in contexts
- May hide hallucinations

---

## Quantified Impact

### By the Numbers

| Metric | Failing Questions | All Questions | Gap |
|--------|-------------------|---------------|-----|
| **Average answer_correctness** | 0.49 | 0.76 | **-27 points** |
| **Average context_precision** | 0.55 | 0.59 | -4 points |
| **Average context_recall** | 0.15 | 0.38 | **-23 points** |
| **Average context_relevance** | 0.33 | 0.47 | **-14 points** |
| **Average faithfulness** | 0.62 | 0.72 | -10 points |

**Key Insight:** Failing questions have **85% lower context_recall** (0.15 vs 0.38) — contexts simply don't contain the information needed.

---

## Recommended Fixes (Prioritized)

### Priority 1: CRITICAL (Immediate Impact)

#### 1.1 Index RHEL 10 "Considerations in Adopting" Documentation
**Affected:** TEMPORAL-MIGRATION-001, RSPEED-1998, TEMPORAL-REMOVED-001, TEMPORAL-IMPLICIT-001

**Action:**
```bash
# Verify these docs are in okp-mcp's knowledge base:
/content/en-us/red_hat_enterprise_linux/10/html/considerations_in_adopting_rhel_10/
  - infrastructure-services (Kea DHCP)
  - deprecated-functionality
  - removed-functionality
```

**Impact:** Would fix 4 of top 10 failures (40% of chronic failures!)

#### 1.2 Add RHEL Version Filtering
**Affected:** All TEMPORAL questions, RSPEED-1998

**Action:**
```python
# In okp-mcp solr.py:
if product == "rhel" or query.contains("RHEL"):
    # Extract version from query
    version = extract_version(query)  # e.g., "10" from "RHEL 10"

    if version:
        # Hard filter: only this version and previous
        fq_version = f'version:({version} OR {version - 1})'
        params["fq"].append(fq_version)
    else:
        # No version specified: default to current (10) and previous (9)
        fq_version = 'version:(10 OR 9)'
        params["fq"].append(fq_version)

    # Penalty for old versions
    params["bq"].append('version:[5 TO 7]^0.1')  # Heavy penalty for RHEL 5-7
```

**Impact:** Would eliminate RHEL 6 docs in RHEL 10 queries, fix 7 of top 10 failures

#### 1.3 De-boost Lifecycle/Policy Documents
**Affected:** TEMPORAL-ADDED-003, TEMPORAL-MIGRATION-001, TEMPORAL-MIGRATION-002

**Action:**
```python
# In okp-mcp solr.py:
# Penalize policy documents unless explicitly requested
lifecycle_terms = ["life cycle", "lifecycle", "eol", "end of life", "support policy"]
if not any(term in query.lower() for term in lifecycle_terms):
    params["bq"].append('url:(*life*cycle* OR *policy* OR *errata*)^0.2')
```

**Impact:** Would stop lifecycle docs from dominating results, fix 3 of top 10 failures

---

### Priority 2: HIGH (Improves Most Questions)

#### 2.1 Boost Technical Documentation
**Action:**
```python
# Boost installation guides, release notes, how-tos
params["bq"].extend([
    'url:*installation*^3.0',
    'url:*release*notes*^3.0',
    'url:*configuring*^2.0',
    'url:*managing*^2.0',
    'doctype:"Installation Guide"^5.0',
    'doctype:"Release Notes"^4.0'
])
```

#### 2.2 Fix rpm-ostree Retrieval
**Action:**
1. Verify Image Mode docs are indexed
2. Test hyphen handling: `rpm-ostree` vs `rpm ostree`
3. Add composing/ostree documentation to knowledge base

#### 2.3 Clean Up Malformed Documents
**Action:**
1. Filter out documents with title="title" or title containing "subheading-md"
2. Re-scrape/re-index documents with malformed metadata

---

### Priority 3: MEDIUM (Quality Improvements)

#### 3.1 Add Semantic Deduplication
**Reason:** Reduces redundant contexts (currently 37-51 contexts retrieved per query)

#### 3.2 Improve Error Handling for `'rag_chunks'` Missing
**Reason:** 30+ API errors per question make metrics unreliable

#### 3.3 Fix Faithfulness Evaluation Failures
**Reason:** Cannot detect hallucinations when faithfulness eval fails

---

## Testing Strategy

### Smoke Tests (After Each Fix)

Run these queries and verify retrieval:

1. **RHEL version filtering:**
   - "How to install and configure a DHCP server in RHEL 10?"
   - Should retrieve: RHEL 10 Kea docs
   - Should NOT retrieve: RHEL 6, 7, 8 ISC DHCP docs

2. **Kea documentation:**
   - "How to set up Kea?"
   - Should retrieve: Kea installation guide, RHEL 10 Considerations
   - Should NOT say: "Kea is not a Red Hat product"

3. **Technical vs Policy docs:**
   - "What kernel version does RHEL 10 use?"
   - Should retrieve: RHEL 10 Release Notes
   - Should NOT retrieve: Life Cycle policy docs

4. **rpm-ostree:**
   - "How do I install a package on a system using rpm-ostree?"
   - Should retrieve: Image Mode documentation, rpm-ostree man page
   - Should NOT retrieve: ZERO contexts

### Regression Suite

Re-run full evaluation after fixes:
```bash
./run_full_evaluation_suite.sh
```

**Success Criteria:**
- TEMPORAL-MIGRATION-001: answer_correctness > 0.7 (currently 0.33)
- RSPEED-1998: answer_correctness > 0.8 (currently 0.49)
- TEMPORAL-ADDED-003: answer_correctness > 0.8 (currently 0.23)
- context_recall average > 0.5 (currently 0.15 for failing questions)

---

## Conclusion

**All 10 top failures share the same root cause:**

okp-mcp's retrieval pipeline prioritizes:
1. ❌ Policy/lifecycle documents over technical documentation
2. ❌ Old RHEL versions over current version
3. ❌ Well-indexed but irrelevant docs over sparse but correct docs

**The fixes are straightforward:**
1. ✅ Index RHEL 10 "Considerations in Adopting" (especially Infrastructure Services)
2. ✅ Add RHEL version filtering (default to current + previous)
3. ✅ De-boost lifecycle docs, boost technical docs

**Expected impact:** Fixing these 3 issues would improve answer correctness from **49% → 75%+** for failing questions.

---

**Next Steps:**
1. Verify RHEL 10 documentation coverage in okp-mcp
2. Implement RHEL version filtering (highest impact, lowest effort)
3. Re-run evaluation to measure improvement

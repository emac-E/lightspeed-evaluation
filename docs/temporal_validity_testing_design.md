# Temporal Context Validity Testing Design

**Task:** #10 (Design temporal context validity tests)
**Created:** 2026-03-23
**Status:** Design Complete

---

## Overview

Temporal validity testing evaluates whether the RAG system correctly handles **version-specific information** and avoids providing **outdated or incorrect answers** based on old documentation.

This is a critical real-world problem:
- Users ask about RHEL 10, but okp-mcp might return RHEL 9 docs
- Features are deprecated/removed between versions
- Syntax and defaults change between releases
- Security vulnerabilities are version-specific

---

## Testing Objectives

### Primary Goals
1. **Detect version mismatches:** Identify when okp-mcp retrieves wrong-version documentation
2. **Validate metric sensitivity:** Test if ragas metrics catch temporal issues
3. **Measure retrieval accuracy:** How often does okp-mcp prioritize current docs?
4. **Benchmark LLM behavior:** Does the LLM notice version mismatches in contexts?

### Success Criteria
- `ragas:context_relevance` should be LOW when wrong-version docs are retrieved
- `ragas:faithfulness` should be LOW when LLM ignores outdated contexts
- `custom:answer_correctness` should detect version-specific wrong answers
- okp-mcp should prioritize RHEL 10 docs for RHEL 10 queries

---

## Test Categories

### Category 1: Removed Features (High Impact)
**Scenario:** Feature available in RHEL 9 but removed in RHEL 10

**Example: ISC DHCP Server**
- **RHEL 9:** ISC DHCP (`dhcp-server` package) available
- **RHEL 10:** ISC DHCP removed, replaced with Kea
- **Query:** "How to set up a DHCP server in RHEL 10?"
- **Wrong answer (RHEL 9 docs):** Install `dhcp-server` package
- **Correct answer (RHEL 10 docs):** Install `kea` package

**Expected Metrics:**
- If okp-mcp returns RHEL 9 docs → `context_relevance` should be LOW
- If LLM uses RHEL 9 docs → `answer_correctness` should FAIL
- If LLM ignores RHEL 9 docs → `faithfulness` should be LOW

### Category 2: Added Features (Medium Impact)
**Scenario:** Feature NOT in RHEL 9 but added in RHEL 10

**Example: New Python Version**
- **RHEL 9:** Python 3.9, 3.11 available
- **RHEL 10:** Python 3.12 is default, 3.13 available
- **Query:** "What is the default Python version in RHEL 10?"
- **Wrong answer (RHEL 9 docs):** Python 3.9
- **Correct answer (RHEL 10 docs):** Python 3.12

**Expected Metrics:**
- If okp-mcp returns RHEL 9 docs → `context_precision` should be LOW
- If LLM says Python 3.9 → `answer_correctness` should FAIL

### Category 3: Changed Syntax/Defaults (Medium Impact)
**Scenario:** Command syntax or default behavior changed between versions

**Example: Firewalld Service Name**
- **RHEL 8:** `firewall-cmd --add-service=http`
- **RHEL 9+:** `firewall-cmd --add-service=http --permanent` recommended
- **Query:** "How to open HTTP port on RHEL 10?"

**Expected Metrics:**
- Both answers might work, but RHEL 10 docs should be preferred
- `context_relevance` should favor newer docs

### Category 4: Deprecated Warnings (Low Impact but Common)
**Scenario:** Approach works but is deprecated in favor of new method

**Example: Network Configuration**
- **RHEL 8:** `network-scripts` (deprecated but works)
- **RHEL 9+:** NetworkManager keyfiles preferred
- **Query:** "How to configure network in RHEL 10?"
- **Outdated answer:** Use `/etc/sysconfig/network-scripts/ifcfg-*`
- **Current answer:** Use NetworkManager keyfiles

### Category 5: Version-Specific CVEs/Bugs (Critical)
**Scenario:** Security vulnerability or bug fix specific to version

**Example: Known CVE**
- **RHEL 9.2:** CVE-2023-XXXXX affects specific kernel version
- **RHEL 10:** CVE fixed in initial release
- **Query:** "Is RHEL 10 affected by CVE-2023-XXXXX?"
- **Wrong (RHEL 9 docs):** Yes, apply patch
- **Correct (RHEL 10 docs):** No, fixed in kernel 6.x

---

## Test Design Patterns

### Pattern 1: Direct Version Query
**Format:** "How to [task] in RHEL [version]?"

**Purpose:** Most explicit test of version filtering

**Examples:**
```yaml
- query: "How to install DHCP server in RHEL 10?"
  expected_version: "RHEL 10"
  wrong_versions: ["RHEL 9", "RHEL 8"]

- query: "What is default Python in RHEL 10?"
  expected_version: "RHEL 10"
  expected_answer: "Python 3.12"
  wrong_answers: ["Python 3.9", "Python 3.11"]
```

### Pattern 2: Implicit Current Version
**Format:** "How to [task]?" (user assumes current RHEL)

**Purpose:** Test if okp-mcp defaults to latest version

**Examples:**
```yaml
- query: "How to configure DHCP server?"
  implicit_version: "latest (RHEL 10)"
  should_mention: "Kea"
  should_not_mention: "dhcp-server package"
```

### Pattern 3: Cross-Version Comparison
**Format:** "Differences between RHEL [v1] and RHEL [v2]"

**Purpose:** Requires accurate info from BOTH versions

**Examples:**
```yaml
- query: "What changed in Python between RHEL 9 and RHEL 10?"
  requires_versions: ["RHEL 9", "RHEL 10"]
  should_mention: ["3.12", "default change", "AppStream"]
```

### Pattern 4: Migration Scenarios
**Format:** "Migrating from RHEL [old] to RHEL [new]"

**Purpose:** Tests understanding of version transitions

**Examples:**
```yaml
- query: "Migrating DHCP server from RHEL 9 to RHEL 10"
  should_mention: ["ISC DHCP deprecated", "migrate to Kea", "configuration differences"]
```

### Pattern 5: Deliberate Poisoning
**Format:** Explicitly provide wrong-version contexts, measure detection

**Purpose:** Test metric sensitivity to temporal issues

**Examples:**
```yaml
- query: "How to install DHCP server in RHEL 10?"
  # Deliberately inject RHEL 9 contexts
  poisoned_contexts:
    - version: "RHEL 9"
      content: "Install dhcp-server package..."
  expected_behavior:
    - ragas:context_relevance < 0.5  # Should detect wrong version
    - ragas:faithfulness < 0.7       # Should ignore or contradict
```

---

## Test Data Structure

### Minimal Test Case
```yaml
- conversation_group_id: TEMPORAL-001
  description: "Removed feature test: ISC DHCP in RHEL 10"
  tag: temporal_validity
  temporal_test: true
  target_version: "RHEL 10"
  wrong_versions: ["RHEL 9", "RHEL 8"]

  turns:
    - turn_id: turn1
      query: "How to set up a DHCP server in RHEL 10?"

      # These will be populated by okp-mcp (may include wrong versions)
      response: null
      contexts: null

      # Evaluation criteria
      expected_response: |
        Kea is the DHCP server in RHEL 10. ISC DHCP was removed.
        Install: dnf install kea
        Configure: /etc/kea/kea-dhcp4.conf

      forbidden_terms:
        - "dhcp-server"       # RHEL 9 package name
        - "dhcpd.conf"        # ISC DHCP config file
        - "ISC DHCP"          # Should mention it's removed, not recommend it

      required_terms:
        - "Kea"
        - "RHEL 10"

      version_detection:
        should_mention_version: "RHEL 10"
        should_not_use_version: ["RHEL 9", "RHEL 8"]

      turn_metrics:
        - ragas:context_relevance      # Should detect wrong-version contexts
        - ragas:faithfulness           # Should be low if using wrong docs
        - custom:answer_correctness    # Should fail if recommending ISC DHCP
```

### Advanced Test Case (Poisoned Contexts)
```yaml
- conversation_group_id: TEMPORAL-POISON-001
  description: "Temporal poisoning: Inject RHEL 9 docs for RHEL 10 query"
  tag: temporal_validity_poisoned
  temporal_test: true
  api:
    enabled: false  # We provide contexts manually

  turns:
    - turn_id: turn1
      query: "How to install DHCP server in RHEL 10?"

      # Manually provide WRONG version contexts
      contexts:
        - |
          RHEL 9 Documentation: Installing DHCP Server

          To install DHCP server on Red Hat Enterprise Linux 9:

          1. Install the dhcp-server package:
             # dnf install dhcp-server

          2. Configure /etc/dhcp/dhcpd.conf

          3. Start the service:
             # systemctl enable --now dhcpd

        - |
          RHEL 8 Documentation: DHCP Server Configuration

          The dhcp-server package provides ISC DHCP server...

      # Pre-generated response (simulating LLM using wrong contexts)
      response: |
        To install DHCP server in RHEL 10, use:
        dnf install dhcp-server

      expected_response: |
        Kea is the DHCP server in RHEL 10. ISC DHCP was removed.

      turn_metrics:
        - ragas:context_relevance      # Expected: LOW (wrong version docs)
        - ragas:faithfulness           # Expected: HIGH (response matches contexts)
        - custom:answer_correctness    # Expected: FAIL (wrong answer)

      turn_metrics_metadata:
        "ragas:context_relevance":
          # Lower threshold because we EXPECT wrong contexts
          threshold: 0.3

        "custom:answer_correctness":
          # Should fail - using RHEL 9 package for RHEL 10
          threshold: 0.8
```

---

## Metric Expectations by Scenario

### Scenario A: okp-mcp returns CORRECT version docs
```
Expected Metrics:
✅ ragas:context_relevance: HIGH (0.7-1.0)
✅ ragas:context_precision: HIGH (0.6-1.0)
✅ ragas:faithfulness: HIGH (0.7-1.0)
✅ custom:answer_correctness: PASS
```

### Scenario B: okp-mcp returns MIXED versions (50/50)
```
Expected Metrics:
🟡 ragas:context_relevance: MEDIUM (0.4-0.6)
🟡 ragas:context_precision: MEDIUM (0.3-0.6)
? ragas:faithfulness: DEPENDS on LLM choice
? custom:answer_correctness: DEPENDS on LLM choice

If LLM chooses correct version:
✅ faithfulness: LOW (ignores half the contexts)
✅ answer_correctness: PASS

If LLM chooses wrong version:
✅ faithfulness: HIGH (uses wrong contexts)
❌ answer_correctness: FAIL
```

### Scenario C: okp-mcp returns WRONG version docs only
```
Expected Metrics:
❌ ragas:context_relevance: LOW (0.0-0.3)
❌ ragas:context_precision: LOW (0.0-0.3)

If LLM uses wrong contexts:
✅ faithfulness: HIGH (0.7-1.0)  # Faithful to wrong contexts!
❌ answer_correctness: FAIL

If LLM rejects wrong contexts:
❌ faithfulness: LOW (0.0-0.3)   # Ignored contexts
? answer_correctness: UNKNOWN (may use parametric knowledge)
```

---

## Implementation Plan

### Phase 1: Test Data Creation
**Output:** `config/temporal_validity_tests.yaml`

**Content:**
- 10 removed feature tests (ISC DHCP, legacy network-scripts, etc.)
- 10 added feature tests (new packages, new defaults)
- 5 syntax change tests
- 5 migration scenario tests
- 5 poisoned context tests (controlled wrong versions)

**Total:** 35 test cases covering RHEL 8, 9, 10 transitions

### Phase 2: okp-mcp Version Filter Testing
**Test:** Does okp-mcp prioritize correct versions?

**Method:**
1. Run evaluation with `temporal_validity_tests.yaml`
2. Check retrieved contexts for version strings
3. Measure: What % of contexts match target version?
4. Expected: >80% should be target version

**Script:** `scripts/analyze_version_distribution.py`
- Parse contexts for "RHEL X" version markers
- Count contexts by version
- Report: "For RHEL 10 query, 15% RHEL 9, 5% RHEL 8, 80% RHEL 10"

### Phase 3: Metric Sensitivity Analysis
**Test:** Do metrics detect temporal issues?

**Method:**
1. Run poisoned context tests (known wrong versions)
2. Measure metric responses
3. Expected patterns:
   - `context_relevance` drops when wrong version
   - `faithfulness` vs `answer_correctness` diverge
   - LLM sometimes uses wrong contexts faithfully

**Output:** `analysis_output/temporal_metric_sensitivity_report.txt`

### Phase 4: LLM Version Awareness Testing
**Test:** Does gemini-2.5-flash notice version mismatches?

**Method:**
1. Provide RHEL 9 docs for RHEL 10 query
2. Check if LLM:
   - Ignores wrong-version contexts (faithfulness LOW)
   - Mentions version mismatch in response
   - Uses parametric knowledge instead

**Analysis:**
- Compare faithfulness scores: correct vs wrong version contexts
- Check response text for version disclaimers
- Measure parametric knowledge usage rate

---

## Novel Insights from Temporal Testing

### Insight 1: Version Tagging in okp-mcp
**Discovery:** okp-mcp may not be filtering by version at all

**Evidence:**
- If RHEL 10 queries return significant RHEL 9 docs
- If version distribution is uniform regardless of query

**Fix:** Add version boost/filter in Solr query

### Insight 2: LLM Version Blindness
**Discovery:** LLMs may not notice version mismatches

**Evidence:**
- High faithfulness scores with wrong-version contexts
- No version disclaimers in responses
- Confidently uses outdated syntax

**Implication:** Can't rely on LLM to filter bad contexts

### Insight 3: Metric Limitations
**Discovery:** Current metrics may not penalize wrong versions

**Evidence:**
- `context_relevance` scores high for RHEL 9 docs answering RHEL 10 query
- Content is relevant, but VERSION is wrong
- Metrics focus on semantic relevance, not temporal validity

**Solution:** Need new metric: `temporal_accuracy` or version filter

### Insight 4: Removal Detection Gap
**Discovery:** Harder to detect removed features than added ones

**Evidence:**
- "Install dhcp-server" seems reasonable without RHEL 10 knowledge
- No error until user tries the command
- Metrics can't detect "this package doesn't exist in this version"

**Solution:** Require version verification in tests

---

## Recommended New Metrics

### metric: version_match
**Type:** Custom boolean metric

**Purpose:** Verify contexts match query version

**Implementation:**
```python
def version_match(query: str, contexts: list[str]) -> float:
    """
    Check if retrieved contexts match version in query.

    Returns:
        1.0 if >80% contexts match target version
        0.5 if 50-80% match
        0.0 if <50% match
    """
    target_version = extract_version_from_query(query)
    if not target_version:
        return None  # No version in query

    matching_contexts = [
        ctx for ctx in contexts
        if f"RHEL {target_version}" in ctx
        or f"Red Hat Enterprise Linux {target_version}" in ctx
    ]

    match_ratio = len(matching_contexts) / len(contexts)

    if match_ratio >= 0.8:
        return 1.0
    elif match_ratio >= 0.5:
        return 0.5
    else:
        return 0.0
```

### metric: forbidden_terms_check
**Type:** Custom boolean metric

**Purpose:** Detect version-specific forbidden terms in response

**Implementation:**
```python
def forbidden_terms_check(response: str, forbidden_terms: list[str]) -> float:
    """
    Check if response contains forbidden terms (e.g., deprecated packages).

    Returns:
        0.0 if ANY forbidden term found
        1.0 if NO forbidden terms found
    """
    for term in forbidden_terms:
        if term.lower() in response.lower():
            return 0.0
    return 1.0
```

---

## Expected Outcomes

### Success Criteria
After implementing temporal validity tests:

1. **okp-mcp improvements identified:**
   - Quantify: X% of RHEL 10 queries return RHEL 9 docs
   - Recommendation: Add version boost in Solr query

2. **Metric gaps documented:**
   - `context_relevance` doesn't catch wrong versions
   - Need new `version_match` metric

3. **LLM behavior characterized:**
   - Does gemini-2.5-flash notice version mismatches?
   - Faithfulness vs correctness divergence measured

4. **Test coverage expanded:**
   - 35 new temporal validity test cases
   - Covers RHEL 8→9→10 transitions
   - Includes removed features, added features, changed syntax

### Failure Modes to Test
- **Silent failures:** Wrong version docs, LLM uses them faithfully
- **Version hallucination:** LLM invents non-existent version features
- **Mixed-version synthesis:** LLM combines RHEL 9 + RHEL 10 docs incorrectly
- **Temporal confusion:** Can't determine if feature exists in target version

---

## Integration with Existing Tests

### Add to Current JIRA Tests
Enhance existing tests with temporal markers:

```yaml
- conversation_group_id: RSPEED-2294  # Existing Python test
  temporal_validation: true  # NEW FLAG
  target_version: "RHEL 10"
  version_sensitive: true    # Answer changes by version
  wrong_versions: ["RHEL 9", "RHEL 8"]
```

### New Evaluation Data File
Create: `config/temporal_validity_tests.yaml`

Structure:
- **Section 1:** Removed features (10 tests)
- **Section 2:** Added features (10 tests)
- **Section 3:** Changed syntax (5 tests)
- **Section 4:** Migration scenarios (5 tests)
- **Section 5:** Poisoned contexts (5 tests)

---

## Tooling Requirements

### Script 1: Version Distribution Analyzer
**File:** `scripts/analyze_version_distribution.py`

**Purpose:** Count RHEL version mentions in retrieved contexts

**Usage:**
```bash
python scripts/analyze_version_distribution.py \
    --input eval_output/temporal_tests_detailed.csv \
    --output analysis_output/version_distribution.json
```

### Script 2: Temporal Metric Calculator
**File:** `scripts/calculate_temporal_metrics.py`

**Purpose:** Calculate `version_match` and `forbidden_terms` metrics

**Usage:**
```bash
python scripts/calculate_temporal_metrics.py \
    --input config/temporal_validity_tests.yaml \
    --results eval_output/temporal_tests_detailed.csv \
    --output analysis_output/temporal_metrics.csv
```

### Script 3: LLM Version Awareness Tester
**File:** `scripts/test_llm_version_awareness.py`

**Purpose:** Deliberately poison contexts with wrong versions, measure detection

**Usage:**
```bash
python scripts/test_llm_version_awareness.py \
    --model gemini-2.5-flash \
    --test-cases config/version_awareness_tests.yaml
```

---

## Timeline

### Week 1: Test Data Creation
- [ ] Identify 35 version-sensitive test cases
- [ ] Write evaluation_data YAML
- [ ] Document expected outcomes for each test

### Week 2: okp-mcp Baseline
- [ ] Run tests to measure current version distribution
- [ ] Analyze: What % of contexts match target version?
- [ ] Create improvement recommendations for okp-mcp

### Week 3: Metric Development
- [ ] Implement `version_match` custom metric
- [ ] Implement `forbidden_terms_check` metric
- [ ] Test metric sensitivity with poisoned contexts

### Week 4: Analysis & Reporting
- [ ] Run full temporal validity suite
- [ ] Generate version distribution reports
- [ ] Document findings and recommendations

---

## Related Work

### Builds On
- Task #6: Cross-metric correlation analysis
- Task #4: RSPEED-2200 investigation (okp-mcp retrieval issues)
- RSPEED-2685: Test framework stabilization

### Enables
- okp-mcp version filtering improvements
- New temporal validity metrics
- Better test coverage for version-specific features
- Migration scenario testing

### Future Extensions
- Extend to RHEL 7→8 transitions
- Test CentOS Stream → RHEL version mappings
- Cross-product version testing (RHEL + Satellite versions)

---

## Appendix: Version-Specific Changes (RHEL 8→9→10)

### Major Removals
| Feature | Last Version | Removed In | Replacement |
|---------|--------------|------------|-------------|
| ISC DHCP | RHEL 9 | RHEL 10 | Kea DHCP |
| network-scripts | RHEL 8 | RHEL 9 | NetworkManager keyfiles |
| iptables (default) | RHEL 8 | RHEL 9 | nftables |
| Python 2 | RHEL 7 | RHEL 8 | Python 3 |

### Major Additions
| Feature | Added In | Notes |
|---------|----------|-------|
| Kea DHCP | RHEL 10 | Only DHCP option |
| Python 3.12 | RHEL 10 | Default system Python |
| Kernel 6.x | RHEL 10 | Major kernel upgrade |
| Image Builder | RHEL 8 | Web console feature |

### Changed Defaults
| Feature | RHEL 8 | RHEL 9 | RHEL 10 |
|---------|--------|--------|---------|
| Default firewall | iptables | nftables | nftables |
| Default Python | 3.6 | 3.9 | 3.12 |
| Network config | network-scripts | NetworkManager | NetworkManager |

---

**Status:** Design Complete ✅
**Next Step:** Implement test data in `config/temporal_validity_tests.yaml`
**Owner:** Task #10

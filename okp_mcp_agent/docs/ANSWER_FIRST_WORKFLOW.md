# Answer-First Evaluation Workflow

**The Realistic Way to Handle Customer Bugs**

---

## Overview

When a customer reports a bug, you typically have:
- ✅ **The question** they asked
- ✅ **The correct answer** (from a subject matter expert)
- ❌ **NO idea which documents should be retrieved**

This workflow is designed for this **real-world scenario**. It evaluates the system based on answer quality first, then uses that to discover the correct documents.

---

## Table of Contents

1. [Workflow Overview](#workflow-overview)
2. [YAML Configuration](#yaml-configuration)
3. [Phase 1: Answer Quality Check](#phase-1-answer-quality-check)
4. [Phase 2: Root Cause Diagnosis](#phase-2-root-cause-diagnosis)
5. [Phase 3: Document Discovery](#phase-3-document-discovery)
6. [Phase 4: Retrieval Optimization](#phase-4-retrieval-optimization)
7. [Phase 5: Regression Test Creation](#phase-5-regression-test-creation)
8. [Complete Examples](#complete-examples)
9. [Comparison: Traditional vs Answer-First](#comparison-traditional-vs-answer-first)

---

## Workflow Overview

```
┌──────────────────────────────────────────────────────┐
│ Customer Bug: "Is SPICE available for RHEL VMs?"    │
│ Expert Answer: "SPICE is deprecated in RHEL 8.3..." │
│ Expected URLs: ??? (Don't know yet!)                 │
└────────────┬─────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────┐
│ PHASE 1: Answer Quality Check                       │
│  • Run system with question                          │
│  • Judge answer vs expert answer                     │
│  • Answer Correctness: 0.45 ❌                       │
└────────────┬─────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────┐
│ PHASE 2: Root Cause Diagnosis                       │
│  • Do retrieved docs contain the answer?             │
│  • LLM judges: NO ❌                                 │
│  • Diagnosis: WRONG DOCUMENTS                        │
└────────────┬─────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────┐
│ PHASE 3: Document Discovery                         │
│  • Search Solr using expert answer                   │
│  • LLM verifies which docs have the answer           │
│  • Found: solutions/6955095, solutions/5414901       │
└────────────┬─────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────┐
│ PHASE 4: Retrieval Optimization                     │
│  • Target: Retrieve verified docs                    │
│  • Iterate on Solr config (qf, pf, mm, etc.)        │
│  • URL F1: 0.00 → 0.67 → 1.00 ✅                    │
│  • Answer Correctness: 0.45 → 0.95 ✅               │
└────────────┬─────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────┐
│ PHASE 5: Save as Regression Test                    │
│  • Add discovered URLs to YAML config                │
│  • Now have ground truth for future testing          │
│  • Bug fix complete + regression test created        │
└──────────────────────────────────────────────────────┘
```

---

## YAML Configuration

### For New Customer Bugs (Answer-Only Mode)

```yaml
- conversation_group_id: CUSTOMER_BUG_123
  tag: okp-mcp-functional
  turns:
  - turn_id: '1'
    query: "Is SPICE available to help with RHEL VMs?"

    # REQUIRED: Expert-provided correct answer
    expected_response: |
      SPICE is deprecated in RHEL 8.3 and removed in RHEL 9.
      Use VNC instead for VM console access.

    # OPTIONAL: Keywords that should appear (if known)
    expected_keywords:
    - - spice
    - - deprecated
    - - vnc

    # NOT NEEDED: expected_urls will be discovered!
    # expected_urls: null

    # Metrics to evaluate
    turn_metrics:
    - custom:answer_correctness  # Compare to expert answer
    - ragas:faithfulness          # No hallucination
    - ragas:context_relevance     # Docs are on-topic
    - custom:keywords_eval        # Keywords present
```

### After Fix (Regression Test with Discovered URLs)

```yaml
- conversation_group_id: CUSTOMER_BUG_123
  tag: okp-mcp-functional
  turns:
  - turn_id: '1'
    query: "Is SPICE available to help with RHEL VMs?"
    expected_response: |
      SPICE is deprecated in RHEL 8.3 and removed in RHEL 9.
      Use VNC instead for VM console access.

    # NOW we have ground truth (auto-discovered and verified)
    expected_urls:
    - access.redhat.com/solutions/6955095
    - access.redhat.com/solutions/5414901
    - access.redhat.com/solutions/6999469

    turn_metrics:
    - custom:url_retrieval_eval   # Now can check URL F1
    - custom:answer_correctness
    - ragas:faithfulness
    - ragas:context_relevance
    - custom:keywords_eval
```

---

## Phase 1: Answer Quality Check

**Goal:** Determine if the system is giving the correct answer.

### Run Evaluation

```bash
# Diagnose with answer-only config
uv run scripts/okp_mcp_agent.py diagnose CUSTOMER-BUG-123
```

### Output

```
================================================================================
DIAGNOSING: CUSTOMER-BUG-123
================================================================================

🔄 Running Evaluation...
✓ Evaluation complete (3 results generated)

📋 ANSWER-FIRST MODE (No expected URLs in config)
   → Evaluating based on answer quality only
   → Will discover correct URLs if answer is wrong

❌ ANSWER IS INCORRECT
   Answer Correctness: 0.45

🔍 Checking if retrieved documents contain the expected answer...
```

---

## Phase 2: Root Cause Diagnosis

**Goal:** Determine WHY the answer is wrong.

### Two Possible Outcomes

#### Outcome A: Docs Contain Answer (Extraction Problem)

```
✅ Retrieved docs CONTAIN the answer
   Confidence: 0.85
   Reason: Documents discuss SPICE deprecation and VNC alternative

🔍 DIAGNOSIS: ANSWER EXTRACTION PROBLEM
   → Correct docs retrieved but LLM failed to extract answer
   → May need prompt engineering or context window optimization

   💾 Saving URLs for future regression testing...
   ✅ Saved 3 URLs to config

   🎯 ITERATION STRATEGY:
   → This is a prompt/LLM problem, not a retrieval problem
   → Consider: prompt engineering, model selection, temperature
   → Retrieved docs are correct (save as expected_urls)
```

**Fix:** Prompt engineering, not retrieval tuning.

#### Outcome B: Docs DON'T Contain Answer (Retrieval Problem)

```
❌ Retrieved docs DO NOT contain the answer
   Confidence: 0.90
   Reason: Documents discuss unrelated topics (JBoss, databases)

🔍 DIAGNOSIS: WRONG DOCUMENTS RETRIEVED
   → Need to find which docs actually contain the answer
   → Will use document discovery to find correct docs

   🎯 ITERATION STRATEGY:
   → Run bootstrap mode to discover correct documents
   → Search Solr using expected_response as query
   → Verify discovered docs with LLM
   → Iterate to improve retrieval of verified docs

   💡 Next command:
      uv run scripts/okp_mcp_agent.py bootstrap CUSTOMER-BUG-123 --yolo
```

**Fix:** Document discovery → Retrieval optimization.

---

## Phase 3: Document Discovery

**Goal:** Find which documents in Solr actually contain the answer.

### Run Bootstrap Mode

```bash
uv run scripts/okp_mcp_agent.py bootstrap CUSTOMER-BUG-123 --yolo --max-iterations 20
```

### Discovery Process

```
📍 STAGE 2: Document Discovery
================================================================================
Searching Solr for documents containing the correct answer...

🔍 DOCUMENT DISCOVERY for CUSTOMER-BUG-123
================================================================================
Query: Is SPICE available to help with RHEL VMs?
Looking for documents containing:
SPICE is deprecated in RHEL 8.3 and removed in RHEL 9...
================================================================================

📄 Found 10 candidate documents:

1. Unable to define, create or start a Virtual Machine using spice
   URL: https://access.redhat.com/solutions/6955095
   Score: 485.32
   Snippet: SPICE was deprecated in RHEL 8.3 and removed in RHEL 9...

2. Spice protocol is being deprecated in RHEL 8.3
   URL: https://access.redhat.com/solutions/5414901
   Score: 423.17
   Snippet: The SPICE protocol is deprecated as of RHEL 8.3...

3. Some VMs that used to work are invalid with RHEL 9
   URL: https://access.redhat.com/solutions/6999469
   Score: 391.24
   Snippet: VMs configured with SPICE display are no longer supported...

🔍 Verifying which documents actually contain the answer information...

✅ VERIFIED: Unable to define, create or start a Virtual Machine...
             Documents clearly state SPICE removal in RHEL 9

✅ VERIFIED: Spice protocol is being deprecated in RHEL 8.3
             Contains deprecation timeline and migration guidance

✅ VERIFIED: Some VMs that used to work are invalid with RHEL 9
             Explains VNC as replacement for SPICE

✅ Auto-selected 3 verified documents:
   - access.redhat.com/solutions/6955095
     Confidence: 0.92
     Reason: Contains SPICE deprecation facts and VNC guidance
   - access.redhat.com/solutions/5414901
     Confidence: 0.88
     Reason: Details deprecation timeline
   - access.redhat.com/solutions/6999469
     Confidence: 0.85
     Reason: Shows impact and migration path
```

### What Just Happened

1. **Searched Solr** using expert answer as query text
2. **LLM verified** each candidate doc: "Does this contain the answer?"
3. **Auto-selected** only docs that passed verification
4. **Filtered out** irrelevant high-scoring docs (JBoss, etc.)

---

## Phase 4: Retrieval Optimization

**Goal:** Tune Solr config to retrieve the verified documents.

### Fast Retrieval Loop (15 iterations, ~75 seconds)

```
================================================================================
🚀 FAST RETRIEVAL LOOP - CUSTOMER-BUG-123
================================================================================
Mode: Direct Solr queries (no LLM judges)
Max iterations: 15
================================================================================

📊 Getting baseline metrics...
Baseline URL F1: 0.00
Baseline MRR: 0.00

--- Fast Iteration 1/15 ---
💡 Suggestion: Increase title boost from ^5 to ^8
✅ Improved! Committing...
URL F1: 0.00 → 0.33 (+0.33)
MRR: 0.00 → 0.50 (+0.50)

--- Fast Iteration 2/15 ---
💡 Suggestion: Add phrase boosting for "spice deprecated"
✅ Improved! Committing...
URL F1: 0.33 → 0.67 (+0.34)
MRR: 0.50 → 0.67 (+0.17)

--- Fast Iteration 3/15 ---
💡 Suggestion: Loosen minimum match from "2<-1 5<75%" to "2<-1 5<60%"
✅ Improved! Committing...
URL F1: 0.67 → 1.00 (+0.33)
MRR: 0.67 → 1.00 (+0.33)

🔍 VALIDATION CHECKPOINT (iteration 5)
✅ Context quality OK (relevance: 0.85)

🏁 Fast loop complete - running final full validation...

Final metrics:
  URL F1: 1.00 (started: 0.00)
  Context Relevance: 0.85
  Context Precision: 0.90
  Answer Correctness: 0.95 ✅
```

### Progress Report

Saved to: `.diagnostics/CUSTOMER_BUG_123/iteration_summary.txt`

```
================================================================================
PROGRESS REPORT - CUSTOMER_BUG_123
================================================================================

RUN STATISTICS:
  Status:           ✅ Fixed
  Start Time:       2026-04-03 10:15:22
  End Time:         2026-04-03 10:16:37
  Duration:         1m 15s
  Total Iterations: 3
  Changes Applied:  3 (kept)
  Changes Reverted: 0 (didn't improve)

================================================================================
METRIC PROGRESSION
================================================================================

Iter   URL_F1   MRR      CtxRel   AnsCorr
1      0.33     0.50     0.75     0.62
2      0.67     0.67     0.82     0.78
3      1.00     1.00     0.85     0.95

================================================================================
BEST SCORES ACHIEVED
================================================================================

  URL F1:                   1.00 (iteration 3)
  Answer Correctness:       0.95 (iteration 3)
  Context Relevance:        0.85 (iteration 3)
```

---

## Phase 5: Regression Test Creation

**Goal:** Save discovered URLs as ground truth for future testing.

### Auto-Update YAML Config

The agent automatically updates your config file:

```yaml
# Before (answer-only mode)
- conversation_group_id: CUSTOMER_BUG_123
  turns:
  - query: "Is SPICE available to help with RHEL VMs?"
    expected_response: "SPICE is deprecated..."
    # expected_urls: null  # Don't know yet

# After (regression test mode)
- conversation_group_id: CUSTOMER_BUG_123
  turns:
  - query: "Is SPICE available to help with RHEL VMs?"
    expected_response: "SPICE is deprecated..."
    expected_urls:  # AUTO-GENERATED
    - access.redhat.com/solutions/6955095
    - access.redhat.com/solutions/5414901
    - access.redhat.com/solutions/6999469
    turn_metrics:
    - custom:url_retrieval_eval  # AUTO-ADDED
    - custom:answer_correctness
    - ragas:faithfulness
    - ragas:context_relevance
```

### Future Regression Detection

Now when you run the full test suite, this ticket will be checked:

```bash
# Run regression testing
uv run scripts/okp_mcp_agent.py validate

# Output shows this ticket is now a regression test
✅ CUSTOMER-BUG-123: URL F1 = 1.00, Answer = 0.95 (PASSING)
```

If a future change breaks this ticket:
```
❌ CUSTOMER-BUG-123: URL F1 = 0.33 → REGRESSION DETECTED!
   Expected: solutions/6955095, solutions/5414901, solutions/6999469
   Got: documentation/rhel9/release_notes, ...
```

---

## Complete Examples

### Example 1: New Customer Bug (Answer-Only)

**Step 1: Create YAML config**
```yaml
# config/okp_mcp_test_suites/customer_bugs.yaml
- conversation_group_id: CUSTOMER_BUG_123
  turns:
  - query: "Is SPICE available to help with RHEL VMs?"
    expected_response: |
      SPICE is deprecated in RHEL 8.3 and removed in RHEL 9.
      Use VNC instead.
    turn_metrics:
    - custom:answer_correctness
    - ragas:faithfulness
```

**Step 2: Diagnose**
```bash
uv run scripts/okp_mcp_agent.py diagnose CUSTOMER-BUG-123
```

**Step 3: Bootstrap & Fix (if wrong answer)**
```bash
uv run scripts/okp_mcp_agent.py bootstrap CUSTOMER-BUG-123 --yolo --max-iterations 20
```

**Step 4: Review Results**
```bash
# Check progress report
cat .diagnostics/CUSTOMER_BUG_123/iteration_summary.txt

# Check updated config (now has expected_urls)
cat config/okp_mcp_test_suites/customer_bugs.yaml
```

---

### Example 2: Batch Processing Customer Bugs

**Step 1: Create batch file**
```bash
cat > customer_bugs.txt <<EOF
CUSTOMER-BUG-101
CUSTOMER-BUG-102
CUSTOMER-BUG-103
EOF
```

**Step 2: Run batch**
```bash
uv run scripts/okp_mcp_agent.py fix --ticket-file customer_bugs.txt --yolo --max-iterations 20
```

**Step 3: Review batch summary**
```bash
cat .diagnostics/batch_summary_20260403_101522.txt
```

Output:
```
BATCH RUN SUMMARY
================================================================================
Total:       3 tickets
Fixed:       2
Failed:      1
Duration:    2h 15m

RESULTS BY TICKET
================================================================================
  CUSTOMER-BUG-101     ✅ Fixed
  CUSTOMER-BUG-102     ✅ Fixed
  CUSTOMER-BUG-103     ❌ Failed (Knowledge Gap)

INDIVIDUAL REPORTS
================================================================================
  CUSTOMER-BUG-101: .diagnostics/CUSTOMER_BUG_101/iteration_summary.txt
  CUSTOMER-BUG-102: .diagnostics/CUSTOMER_BUG_102/iteration_summary.txt
  CUSTOMER-BUG-103: .diagnostics/CUSTOMER_BUG_103/iteration_summary.txt
```

---

## Comparison: Traditional vs Answer-First

### Traditional Workflow (With Ground Truth URLs)

**Requirements:**
- ✅ Question
- ✅ Expected answer
- ✅ **Expected URLs** (must know which docs are correct)

**Process:**
```
1. Create test with expected_urls
2. Run evaluation
3. Compare retrieved URLs to expected
4. Calculate URL F1
5. Iterate if F1 < 0.7
```

**Limitation:** You must already know which docs are correct!

---

### Answer-First Workflow (Realistic for Customer Bugs)

**Requirements:**
- ✅ Question
- ✅ Expected answer (from SME)
- ❌ Expected URLs (don't need!)

**Process:**
```
1. Create test with just question + answer
2. Run evaluation
3. Check answer correctness
4. If wrong:
   a. Check if docs contain answer
   b. If no → discover correct docs
   c. Iterate on retrieval
5. Save discovered URLs for regression
```

**Advantage:** Works for new bugs where you don't know the correct docs yet!

---

## When to Use Each Mode

### Use Answer-First Mode When:
- ✅ New customer bug report
- ✅ Creating new test from scratch
- ✅ Don't know which docs should be retrieved
- ✅ Have SME who can provide correct answer
- ✅ Want automatic document discovery

### Use Traditional Mode When:
- ✅ Regression testing existing tickets
- ✅ Already know the correct documents
- ✅ Testing retrieval optimization changes
- ✅ Validating against known ground truth

---

## Troubleshooting

### Issue: Discovery Finds Wrong Documents

**Symptom:**
```
📄 Found 10 candidate documents:
1. JBoss Operations Network Database Reference
   ...
```

**Cause:** Expected answer isn't specific enough for good Solr matching.

**Solution:** Make expected_response more specific with unique keywords:
```yaml
expected_response: |
  SPICE display protocol is deprecated in RHEL 8.3 and removed in RHEL 9.
  Solution IDs: 6955095, 5414901, 6999469
  Use VNC protocol instead for virtual machine console access.
```

---

### Issue: No Documents Pass Verification

**Symptom:**
```
❌ REJECTED: Unable to define VM using spice
❌ REJECTED: Spice protocol deprecated
⚠️  No documents passed verification!
```

**Cause:** LLM judge is being too strict or expected_response format mismatch.

**Solution:** Check expected_response format matches doc content:
```bash
# View what's actually in the docs
uv run scripts/okp_mcp_agent.py diagnose CUSTOMER-BUG-123 --use-existing

# Look at RETRIEVED DOCUMENTS section
# Update expected_response to match terminology
```

---

### Issue: Knowledge Gap Detected

**Symptom:**
```
❌ KNOWLEDGE GAP DETECTED
No documents in Solr contain the expected answer.
```

**Cause:** Answer legitimately not in knowledge base.

**Solutions:**
1. **Verify docs exist** at access.redhat.com
2. **Check Solr indexing** - may need reindex
3. **Mark as unanswerable** if content truly missing
4. **File content gap ticket** with doc team

---

## Advanced: Customizing Document Discovery

### Adjust Auto-Selection Threshold

```bash
# More selective (only very high-scoring docs)
uv run scripts/okp_mcp_agent.py bootstrap TICKET-ID --auto-select-threshold 50.0

# Less selective (lower-scoring docs too)
uv run scripts/okp_mcp_agent.py bootstrap TICKET-ID --auto-select-threshold 5.0

# Manual selection (asks user)
uv run scripts/okp_mcp_agent.py bootstrap TICKET-ID --auto-select-threshold 0.0
```

### Customize Verification Prompt

Edit `okp_mcp_agent.py:check_answer_in_retrieved_docs()` to adjust verification criteria.

---

## Best Practices

### 1. Write Good Expected Answers

**Bad (too vague):**
```yaml
expected_response: "SPICE is not available"
```

**Good (specific with facts):**
```yaml
expected_response: |
  SPICE is deprecated in RHEL 8.3 and removed in RHEL 9.
  Key facts:
  - Deprecated: RHEL 8.3
  - Removed: RHEL 9.0
  - Alternative: VNC protocol
  - Impacts: VM console access
```

### 2. Include Solution IDs (If Known)

```yaml
expected_response: |
  SPICE is deprecated (see solution 5414901).
  For RHEL 9, use VNC instead (solutions 6955095, 6999469).
```

This helps discovery find the exact right docs.

### 3. Use Bootstrap for Initial Discovery, Fix for Refinement

```bash
# First time: Discover docs
uv run scripts/okp_mcp_agent.py bootstrap TICKET-ID --yolo

# Later: Refine retrieval with known docs
uv run scripts/okp_mcp_agent.py fix TICKET-ID --yolo --max-iterations 5
```

### 4. Review Discovered URLs Before Committing

```bash
# Check what URLs were discovered
cat .temp_configs/TICKET_ID_single.yaml

# Manually adjust if needed
vi .temp_configs/TICKET_ID_single.yaml
```

### 5. Start with Small Batches

```bash
# Test with 1 ticket first
uv run scripts/okp_mcp_agent.py bootstrap TICKET-1 --yolo --max-iterations 5

# Then scale up
uv run scripts/okp_mcp_agent.py fix TICKET-1 TICKET-2 TICKET-3 --yolo --max-iterations 20
```

---

## Summary

**Answer-First Workflow = Customer Bug Reality**

You get:
- Question from customer
- Correct answer from SME
- **Automatic discovery** of correct documents
- **Automatic optimization** of retrieval
- **Automatic creation** of regression test

Result: From customer bug to fixed system + regression test in one run!

**Next Steps:**
- Read [README.md](../README.md) for setup instructions
- See [OPTIMIZATION_OPPORTUNITIES.md](OPTIMIZATION_OPPORTUNITIES.md) for performance tuning
- Check [example_tickets.txt](../example_tickets.txt) for batch processing examples

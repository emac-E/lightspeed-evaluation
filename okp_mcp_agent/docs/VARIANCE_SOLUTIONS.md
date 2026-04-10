# Variance Solutions - Diagnosing and Fixing Answer Instability

## Overview

When running stability checks (N repeated evaluations), variance in `answer_correctness` scores indicates instability. **High variance is usually fixable** - it's rarely just LLM randomness.

## Variance Thresholds

```python
if variance < 0.01:
    # ✅ STABLE - Normal LLM non-determinism
    # Action: Accept as good
    
elif variance < 0.05:
    # ⚠️ BORDERLINE - Possibly fixable
    # Action: Review ground truth and retrieval
    
else:  # variance >= 0.05
    # ❌ UNSTABLE - Definitely fixable!
    # Action: Investigate root cause
```

## Root Causes (Most to Least Common)

### 1. Bad Ground Truth (MOST COMMON) 🎯

**Problem:** Vague or ambiguous `expected_response` allows multiple valid answers

**Example:**
```yaml
# BAD: Too vague
expected_response: "GFS2 is deprecated in RHEL 10"

# LLM produces semantically equivalent but differently worded answers:
Run 1: "GFS2 is deprecated in RHEL 10" → 0.95
Run 2: "GFS2 has been removed starting with RHEL 10" → 0.85
Run 3: "RHEL 10 no longer supports GFS2 filesystem" → 0.88

Mean: 0.89
Variance: 0.0023
```

**Symptoms:**
- Variance between 0.01 - 0.05
- All answers are factually correct
- Answers use different wording/phrasing
- Scores vary even though content is similar

**Solutions:**

**Option A: Make expected_response more specific**
```yaml
# BETTER: More specific
expected_response: |
  GFS2 (Global File System 2) is NOT available in RHEL 10.
  Red Hat discontinued the Resilient Storage Add-On with RHEL 10.
  The gfs2 and dlm kernel modules are removed in RHEL 10.
  Organizations must migrate to alternative clustered storage solutions.
```

**Option B: Use semantic similarity instead of exact match**
```yaml
# Accept any semantically equivalent answer
# (Would require custom metric that doesn't penalize paraphrasing)
```

**Option C: Focus on key facts only**
```yaml
expected_response: "GFS2 is not available in RHEL 10"
# Short and unambiguous - less room for variation
```

**How to Identify:**
```bash
# Read actual responses from stability runs
cat .diagnostics/{pattern}/stability_run_*.json | jq '.actual_response'

# Compare them - are they saying the same thing differently?
```

---

### 2. Retrieval Variance (COMMON)

**Problem:** Documents come back in different order across runs, LLM weights first docs higher

**Example:**
```python
Run 1: Retrieved = [doc_A, doc_B, doc_C, doc_D, ...]
Run 2: Retrieved = [doc_B, doc_A, doc_C, doc_D, ...]  # Same docs, different order

# LLM might quote doc_A more heavily in Run 1
# → Different emphasis → Different answer_correctness score
```

**Symptoms:**
- Variance between 0.02 - 0.08
- Retrieved URLs are the same across runs
- But order changes (check with `url_overlap_with_previous`)
- Scores vary significantly despite same docs

**Solutions:**

**Option A: Add deterministic tiebreakers to Solr**
```python
# In okp-mcp/src/okp_mcp/solr.py
sort = "score desc, id asc"  # Break ties by document ID
# Ensures consistent ordering when scores are equal
```

**Option B: Boost critical docs higher**
```python
# Make score gaps larger so ties are less likely
qf = "title^5.0 main_content^2.0"  # Bigger multipliers
```

**Option C: Use more specific queries**
```python
# More specific queries → clearer score separation → less ties
# Example: "RHEL 9 GFS2 EOL" instead of just "GFS2"
```

**How to Identify:**
```bash
# Compare retrieved URLs across runs
for f in .diagnostics/{pattern}/stability_run_*.json; do
    echo "=== $f ==="
    jq -r '.retrieved_urls[]' "$f" | head -5
done

# Are the same 5 docs in different order?
```

---

### 3. Ambiguous System Prompts (MODERATE)

**Problem:** Prompt allows multiple valid response strategies

**Example:**
```python
# VAGUE PROMPT
"Answer the question using the documentation."

# LLM might:
Run 1: Direct quote from docs → answer_correctness: 0.90
Run 2: Paraphrase + explanation → answer_correctness: 0.75
Run 3: Summary with examples → answer_correctness: 0.85
```

**Symptoms:**
- Variance between 0.01 - 0.04
- Response style varies (quote vs paraphrase vs summary)
- Content is similar but presentation differs
- Scores vary based on how closely style matches expected

**Solutions:**

**Option A: More specific prompt instructions**
```python
# BETTER: Specific strategy
"Quote directly from documentation when answering. 
Include exact phrasing from the docs, then provide context."
```

**Option B: Constrain response format**
```python
"Answer in this format:
1. Direct answer (1 sentence)
2. Supporting documentation quote
3. Source URL"
```

**Option C: Align with expected_response style**
```python
# If expected_response is detailed, prompt for detailed
# If expected_response is concise, prompt for concise
```

**How to Identify:**
```bash
# Read responses and check if style/structure varies
cat .diagnostics/{pattern}/stability_run_*.json | jq '.actual_response' | less

# Are they all quotes? All paraphrases? Mixed?
```

---

### 4. LLM Non-Determinism (RARE)

**Problem:** Even with `temperature=0`, LLMs have some inherent randomness

**Causes:**
- Numerical precision in softmax calculations
- Multiple tokens with identical probabilities
- Model version changes (API updates)
- Hardware differences (different GPUs)

**Expected Variance:** < 0.01 (very small)

**Symptoms:**
- Variance between 0.001 - 0.01
- Responses are nearly identical
- Minor word choice differences
- No pattern to changes

**Solutions:**

**This is NOT usually fixable - but if variance is this low, you don't need to fix it!**

If variance from LLM alone is > 0.01, check:
- Is temperature truly 0?
- Is model/API version pinned?
- Are you comparing across different API providers?

**How to Identify:**
```bash
# If you've ruled out causes 1-3 and variance is still < 0.01
# → It's just normal LLM behavior, accept it
```

---

## Diagnostic Workflow

### Step 1: Check Variance Level

```python
variance = calculate_variance(stability_runs)

if variance < 0.01:
    # Acceptable - likely just LLM randomness
    return "STABLE"
elif variance < 0.05:
    # Investigate - probably fixable
    proceed_to_step_2()
else:
    # Definitely fixable!
    proceed_to_step_2()
```

### Step 2: Compare Actual Responses

```bash
# Read all stability run responses
cat .diagnostics/{pattern}/stability_run_*.json | jq '.actual_response'
```

**Ask:**
1. Are they saying the same thing in different words? → **Bad ground truth**
2. Are they emphasizing different docs/facts? → **Retrieval variance**
3. Are they using different styles (quote vs summary)? → **Ambiguous prompts**
4. Are they nearly identical with minor differences? → **LLM non-determinism (OK)**

### Step 3: Check Retrieved Documents

```bash
# Compare retrieved URLs across runs
for f in .diagnostics/{pattern}/stability_run_*.json; do
    echo "=== Run $(basename $f) ==="
    jq -r '.retrieved_urls[:5][]' "$f"
    echo
done
```

**Ask:**
1. Same docs, different order? → **Retrieval variance**
2. Different docs entirely? → **Query is too broad** (different Solr results)
3. Same docs, same order? → Not a retrieval issue

### Step 4: Review Ground Truth

```bash
# Check expected_response
cat config/patterns_v2/{pattern}.yaml | grep -A 20 "expected_response"
```

**Ask:**
1. Is it vague or ambiguous? → **Bad ground truth**
2. Does it allow multiple valid answers? → **Bad ground truth**
3. Is it very specific and unambiguous? → Not a ground truth issue

### Step 5: Apply Fix

Based on diagnosis, apply appropriate solution from above.

---

## Examples from Real Tickets

### Example 1: Vague Ground Truth

**Ticket:** RSPEED-2794 (GFS2 in RHEL 10)

**Stability Runs:**
```
Run 1: "GFS2 is deprecated in RHEL 10" → 0.95
Run 2: "RHEL 10 removed GFS2 support" → 0.87
Run 3: "GFS2 not available in RHEL 10" → 0.91

Variance: 0.0016 (borderline)
```

**Diagnosis:** All correct, differently worded

**Fix:** Make expected_response more specific
```yaml
expected_response: "GFS2 is NOT available in RHEL 10. The Resilient Storage Add-On was discontinued."
```

### Example 2: Retrieval Order Variance

**Ticket:** RSPEED-1998 (Kea DHCP)

**Stability Runs:**
```
Run 1: Docs = [kea_install, kea_config, dhcp_migrate] → 0.88
Run 2: Docs = [kea_config, kea_install, dhcp_migrate] → 0.82
Run 3: Docs = [kea_install, kea_config, dhcp_migrate] → 0.87

Variance: 0.0009 (acceptable but could be better)
```

**Diagnosis:** Same docs, slightly different order

**Fix:** Add Solr tiebreaker
```python
sort = "score desc, id asc"
```

### Example 3: Prompt Ambiguity

**Ticket:** RSPEED-2003 (DHCP deprecation)

**Stability Runs:**
```
Run 1: [Short answer, 2 sentences] → 0.78
Run 2: [Detailed answer with examples] → 0.92
Run 3: [Quote from docs] → 0.85

Variance: 0.0049 (borderline)
```

**Diagnosis:** Different response styles

**Fix:** More specific prompt
```python
system_prompt += "\nProvide detailed answers with specific examples when available."
```

---

## Agent Awareness

### Current Agent Capabilities

**What agents CAN detect:**
- ✅ Low URL F1 (retrieval problem)
- ✅ Low context_relevance (wrong docs)
- ✅ Low answer_correctness (answer problem)
- ✅ Low faithfulness (hallucination)
- ✅ Iteration-to-iteration changes

**What agents CANNOT detect (yet):**
- ❌ Variance across multiple runs
- ❌ Root cause of variance (ground truth vs retrieval vs prompt)
- ❌ Retrieval order instability
- ❌ Ground truth quality issues

### Future Enhancement: Variance-Aware Agent

**Proposed:** Add variance analysis to LLM advisor

```python
class VarianceAnalyzer:
    def analyze_stability_runs(self, runs):
        """Analyze variance and suggest root cause."""
        
        variance = calculate_variance(runs)
        
        if variance < 0.01:
            return "Stable - no action needed"
        
        # Compare responses
        responses = [r['actual_response'] for r in runs]
        semantic_similarity = calculate_similarity(responses)
        
        if semantic_similarity > 0.9 and variance > 0.02:
            return {
                'cause': 'BAD_GROUND_TRUTH',
                'reason': 'Responses are semantically similar but score varies',
                'fix': 'Review expected_response for ambiguity'
            }
        
        # Compare retrieved docs
        url_sets = [set(r['retrieved_urls']) for r in runs]
        if url_sets[0] == url_sets[1] == url_sets[2]:
            # Same docs, check order
            if [r['retrieved_urls'][:5] for r in runs] differ:
                return {
                    'cause': 'RETRIEVAL_ORDER_VARIANCE',
                    'reason': 'Same docs retrieved but in different order',
                    'fix': 'Add Solr tiebreaker: sort="score desc, id asc"'
                }
        
        # ... more analysis
```

**This would enable agents to:**
1. Detect variance automatically
2. Diagnose root cause
3. Suggest specific fixes
4. Apply fixes and re-test

**Implementation Priority:** Medium (useful but not critical for POC)

---

## Summary

### Key Takeaways

1. **High variance is usually fixable** - It's rarely just LLM randomness
2. **Most common cause: Bad ground truth** - Vague expected_response
3. **Second most common: Retrieval variance** - Inconsistent doc ordering
4. **Variance thresholds:**
   - < 0.01 = Stable (acceptable)
   - 0.01-0.05 = Borderline (investigate)
   - \> 0.05 = Unstable (definitely fixable)
5. **Use variance as a signal** - It tells you ground truth needs improvement

### Quick Reference

| Variance | Status | Action |
|----------|--------|--------|
| < 0.01 | ✅ Stable | Accept |
| 0.01-0.05 | ⚠️ Borderline | Review ground truth |
| \> 0.05 | ❌ Unstable | Investigate and fix |

### Diagnostic Questions

1. Are responses saying the same thing differently? → Ground truth
2. Are same docs coming back in different order? → Retrieval
3. Are response styles varying (quote vs summary)? → Prompt
4. Are responses nearly identical? → Normal LLM (OK)

---

## References

- Pattern Fix Loop Spec: `docs/PATTERN_FIX_LOOP_SPEC.md`
- Test Plan: `docs/PATTERN_FIX_LOOP_TEST_PLAN.md`
- OKP-MCP Agent: `scripts/okp_mcp_agent.py`
- Diagnostics format: `.diagnostics/{pattern}/stability_run_*.json`

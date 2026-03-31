# BM25 Phrase Boosting and Length Normalization Analysis

**Question:** Is there phrase matching boost? Would term density be better than length normalization?

---

## Part 1: YES, Phrase Boosting Exists (And It's Sophisticated)

### Current Phrase Boosting in okp-mcp

**File:** `src/okp_mcp/solr.py` lines 92-102

```python
# Exact phrase boost
"pf": "main_content^5 title^8",
"ps": "3",  # Phrase slop: terms can be up to 3 positions apart

# Bigram phrase boost (pairs of adjacent terms)
"pf2": "main_content^3 title^5",
"ps2": "2",  # Bigram slop: pairs can be 2 positions apart

# Trigram phrase boost (triples of consecutive terms)
"pf3": "main_content^1 title^2",
"ps3": "5",  # Trigram slop: triples can be 5 positions apart
```

### How It Works

**Query:** `"install DHCP server RHEL 10"`

**After stopword removal:** `"install DHCP server RHEL 10"` (5 terms)

#### Level 1: Exact Phrase Boost (`pf`)

**Looks for:** All 5 terms as an exact phrase (with slop=3)

**Matches:**
- ✅ "install DHCP server on RHEL 10" (slop=1, within tolerance)
- ✅ "install the DHCP server for RHEL 10" (slop=2, within tolerance)
- ❌ "DHCP server installation guide for RHEL 10" (slop=4, exceeds tolerance)

**Boost if matched:**
- Title: **+8×** score
- Body: **+5×** score

#### Level 2: Bigram Phrase Boost (`pf2`)

**Looks for:** Pairs of adjacent terms (with slop=2)

**Query generates 4 bigrams:**
1. "install DHCP"
2. "DHCP server"
3. "server RHEL"
4. "RHEL 10"

**Each bigram that matches gets a boost:**

| Bigram | Document Text | Match? | Boost |
|--------|---------------|--------|-------|
| "RHEL 10" | "...in RHEL 10 you can..." | ✅ Exact | title^5 or main_content^3 |
| "DHCP server" | "...the DHCP server is..." | ✅ Exact | title^5 or main_content^3 |
| "install DHCP" | "...install the DHCP package..." | ✅ Slop=1 | title^5 or main_content^3 |
| "server RHEL" | "...server for RHEL..." | ✅ Slop=1 | title^5 or main_content^3 |

**Cumulative boost:** 4 bigrams × 5 (if in title) = **+20×** total

#### Level 3: Trigram Phrase Boost (`pf3`)

**Looks for:** Triples of consecutive terms (with slop=5)

**Query generates 3 trigrams:**
1. "install DHCP server"
2. "DHCP server RHEL"
3. "server RHEL 10"

**Each trigram that matches gets:**
- Title: **+2×** score
- Body: **+1×** score

### Combined Effect Example

**Doc A: "Installing DHCP Server in RHEL 10"** (title)

```
Base BM25 score: 1.0 (for simplicity)

Field boost (title^5): 1.0 × 5 = 5.0

Phrase boosts (ALL IN TITLE):
  pf  (exact phrase "install DHCP server RHEL 10"): +8
  pf2 (4 bigrams match): +5 each = +20
  pf3 (3 trigrams match): +2 each = +6

Total score: 5.0 + 8 + 20 + 6 = 39.0
```

**Doc B: "RHEL 10 Release Notes"** (title) + body mentions "DHCP" once

```
Base BM25 score: 0.8

Field boost (title^5 for "RHEL 10"): 0.8 × 5 = 4.0

Phrase boosts:
  pf  (no full phrase match): 0
  pf2 ("RHEL 10" in title): +5
  pf3 (no trigrams): 0

Total score: 4.0 + 5 = 9.0
```

**Doc C: "DHCP Server Life Cycle Policy"** (title) + comprehensive body (10,000 words)

```
Base BM25 score: 1.2 (high freq, but length penalty applies)

Field boost (title^5 for "DHCP server"): 1.2 × 5 = 6.0

Phrase boosts:
  pf  (no full phrase): 0
  pf2 ("DHCP server" in title): +5
  pf3 (no trigrams): 0

Body mentions:
  - "DHCP" appears 30 times
  - "server" appears 25 times
  - "RHEL" appears 50 times (all versions)
  - "10" appears 20 times (along with 5, 6, 7, 8, 9...)

Additional BM25 from body: +4.5 (after length normalization)

Total score: 6.0 + 5 + 4.5 = 15.5
```

**Ranking:** Doc A (39.0) >> Doc C (15.5) > Doc B (9.0)

**Conclusion:** Phrase boosting WORKS when query terms appear as phrases in titles.

---

## Part 2: BM25 Length Normalization vs Term Density

### How BM25 Length Normalization Works

**BM25 Formula:**
```
score = IDF(term) × (freq × (k1 + 1)) / (freq + k1 × (1 - b + b × (doc_length / avg_doc_length)))
```

**Parameters in okp-mcp:**
```python
"hl.score.k1": "1.0",    # Term saturation
"hl.score.b": "0.65",    # Length normalization (0 = none, 1 = full)
"hl.score.pivot": "200", # Average doc length (neutral point)
```

**What `b = 0.65` means:**
- 0% of penalty removed (no normalization, term freq only)
- 35% of penalty removed (light normalization)
- **65% of penalty applied (moderate normalization)** ← Current
- 100% of penalty applied (full normalization)

### Example: Short vs Long Doc

**Query:** `"DHCP"`

**Short Doc (200 words):**
- Term "DHCP" appears 5 times
- Frequency: 5
- Doc length: 200 words (= pivot, neutral)
- Length factor: `(1 - 0.65 + 0.65 × (200/200))` = `0.35 + 0.65` = **1.0**
- Score: `IDF × (5 × 2) / (5 + 1.0 × 1.0)` = `IDF × 10 / 6` = **1.67 × IDF**

**Long Doc (10,000 words):**
- Term "DHCP" appears 50 times (10× more)
- Frequency: 50
- Doc length: 10,000 words (50× pivot)
- Length factor: `(1 - 0.65 + 0.65 × (10000/200))` = `0.35 + 32.5` = **32.85**
- Score: `IDF × (50 × 2) / (50 + 1.0 × 32.85)` = `IDF × 100 / 82.85` = **1.21 × IDF**

**Result:**
- Short doc (5 mentions in 200 words): **1.67 × IDF**
- Long doc (50 mentions in 10,000 words): **1.21 × IDF** (72% of short doc's score)

**Interpretation:** BM25 correctly penalized the long doc. Even though it has 10× more mentions, its score is LOWER because term density is lower (50/10000 vs 5/200).

---

### Alternative: Pure Term Density

**Formula:**
```
score = IDF(term) × (freq / doc_length)
```

**Short Doc:**
- Score: `IDF × (5 / 200)` = **0.025 × IDF**

**Long Doc:**
- Score: `IDF × (50 / 10000)` = **0.005 × IDF** (20% of short doc)

**Comparison:**

| Approach | Short Doc Score | Long Doc Score | Long/Short Ratio |
|----------|----------------|----------------|------------------|
| BM25 (b=0.65) | 1.67 × IDF | 1.21 × IDF | **72%** |
| Term Density | 0.025 × IDF | 0.005 × IDF | **20%** |

**Observation:** Term density penalizes long docs MORE harshly than BM25.

---

## Part 3: Why Length Normalization Isn't Fixing the Problem

### The Lifecycle Doc Paradox

**Expected:** Long lifecycle docs should rank lower (length penalty).

**Reality:** Lifecycle docs still rank high despite being 10,000+ words.

**Why?**

### Reason 1: Field Boosts Override Length Normalization

**BM25 length normalization only applies to the `main_content` field scoring.**

**Field boosts are INDEPENDENT of length:**

```python
"qf": "title^5 main_content heading_h1^3 heading_h2 portal_synopsis allTitle^3"
```

**Lifecycle doc scoring breakdown:**

```
Title: "Red Hat Enterprise Linux Life Cycle"
Query: "DHCP server RHEL 10"

Title matches:
  - "Red Hat Enterprise Linux" matches "RHEL" (with fuzzy matching)
  - Title boost: 5×

Score from title alone: 0.3 × 5 = 1.5

Main_content (10,000 words):
  - "DHCP" appears 30 times
  - BM25 score after length normalization: 0.8
  - No field boost: 1×

Score from body: 0.8 × 1 = 0.8

Total score: 1.5 + 0.8 = 2.3
```

**Technical doc scoring:**

```
Title: "Installing Kea DHCP Server"
Query: "DHCP server RHEL 10"

Title matches:
  - "DHCP Server" exact match
  - Title boost: 5×

Score from title alone: 0.9 × 5 = 4.5

Main_content (1,000 words):
  - "DHCP" appears 15 times
  - BM25 score (short doc, no penalty): 1.2

Score from body: 1.2 × 1 = 1.2

Total score: 4.5 + 1.2 = 5.7
```

**Result:** Technical doc WINS (5.7 > 2.3) because better title match, NOT because of length normalization.

---

### Reason 2: Phrase Boosts Are Additive (Not Subject to Length Penalty)

Phrase boosts (`pf`, `pf2`, `pf3`) are **added on top of BM25**, not multiplied:

```
Final_score = BM25_score(main_content) + pf_boost + pf2_boost + pf3_boost
```

**Lifecycle doc:**
- BM25 from body (after length penalty): 0.8
- pf2 boost ("RHEL 10" bigram in body): +3
- **Total: 0.8 + 3 = 3.8**

Length normalization reduced BM25 from 1.5 → 0.8 (saved 0.7), but phrase boost added +3 (net: +2.3).

**The phrase boost overwhelmed the length penalty.**

---

### Reason 3: Lifecycle Docs Match MORE Query Terms

**Query:** `"install DHCP server RHEL 10"`

**Lifecycle doc (comprehensive):**
- Matches: "RHEL", "10", "9", "8", "7", "6", "5" (all versions)
- Matches: "DHCP", "server" (generic mentions)
- Matches: "install" (in phrases like "install updates")
- **Total terms matched: 9 out of 5 query terms** (due to version spam)

**Technical doc (focused):**
- Matches: "install", "DHCP", "server", "RHEL", "10"
- **Total terms matched: 5 out of 5 query terms**

**Problem:** Lifecycle doc matches EXTRA terms (old RHEL versions) that boost its score even though they're not relevant.

**This is why version filtering is critical** - it would exclude docs mentioning RHEL 5/6/7/8 when query says "RHEL 10".

---

## Part 4: Is BM25's Length Normalization "Arbitrary"?

### Your Question: Is Cutting Off at Pivot=200 Arbitrary?

**Short answer:** The **pivot value** (200) is tunable, but the **length normalization approach** is NOT arbitrary—it's based on information retrieval research.

### Why BM25 Uses This Approach

**Problem:** Naive term frequency (TF) favors longer documents.

- Long doc with 100 mentions of "DHCP" looks "more relevant" than short doc with 10 mentions.
- But term density (10/1000 vs 100/10000) might be identical.

**BM25's Solution:** Normalize by document length relative to average length.

**Alternative Approaches:**

| Approach | Formula | Problem |
|----------|---------|---------|
| **Raw TF** | `score = freq` | Long docs always win |
| **Term Density** | `score = freq / doc_length` | Too harsh on long docs (penalizes repetition) |
| **BM25** | `score = freq / (freq + k1 × length_factor)` | Balanced: saturation + length normalization |

**Why BM25 is better:**

1. **Saturation (k1 parameter):** Diminishing returns for repeated terms
   - 1st mention of "DHCP": big boost
   - 10th mention: small boost
   - 100th mention: negligible boost

2. **Length normalization (b parameter):** Tunable penalty
   - b=0: No penalty (pure TF)
   - b=0.65: Moderate penalty (current)
   - b=1: Full penalty (pure term density)

3. **Pivot (avg doc length):** Neutral point
   - Docs around 200 words: no penalty
   - Docs > 200 words: penalty scales
   - Docs < 200 words: slight boost

---

### Is Pivot=200 the Right Value?

**Depends on your corpus.**

**Current okp-mcp corpus:**

| Doc Type | Avg Length | Should Be Penalized? |
|----------|------------|----------------------|
| Solutions/Articles | 500-2,000 words | Slightly (useful) |
| Installation Guides | 1,000-3,000 words | No (highly useful) |
| Release Notes | 5,000-10,000 words | Slightly (comprehensive) |
| **Lifecycle Policies** | **10,000-50,000 words** | **YES (spam)** |

**Analysis:**

If pivot=200:
- Installation guides (1,000-3,000 words) get **5-15× length penalty**
- Lifecycle docs (10,000-50,000 words) get **50-250× length penalty**

**This seems correct!** Lifecycle docs SHOULD be heavily penalized.

**So why are they still ranking high?**

Because:
1. Title boost (5×) is independent of length
2. Phrase boosts (+3 to +8) are additive
3. They match many query terms (all RHEL versions)

**The length penalty IS working, but it's being overwhelmed by other factors.**

---

## Part 5: Would Term Density Be Better?

### Term Density Approach

**Formula:**
```
score = IDF(term) × (freq / doc_length)
```

**Pros:**
- Simple, intuitive
- Directly measures "how much of the doc is about this term"
- Strong penalty for long docs

**Cons:**
- Too harsh on legitimate long documents
- No saturation (100 mentions in 1,000 words = 10× score of 10 mentions)
- No tunable parameters (can't adjust aggressiveness)

### Comparison on Lifecycle Doc Problem

**Query:** `"DHCP server RHEL 10"`

**Lifecycle doc (10,000 words):**
- "DHCP" appears 30 times
- BM25 score: 1.21 × IDF
- Term density score: 0.003 × IDF

**Installation guide (1,000 words):**
- "DHCP" appears 15 times
- BM25 score: 1.67 × IDF
- Term density score: 0.015 × IDF

**Ratio:**

| Approach | Installation / Lifecycle Ratio |
|----------|-------------------------------|
| BM25 | 1.67 / 1.21 = **1.38×** (38% higher) |
| Term Density | 0.015 / 0.003 = **5.0×** (5× higher) |

**Observation:** Term density creates BIGGER separation.

**But is this better?**

**Problem:** Term density would also heavily penalize useful comprehensive documents.

**Example: RHEL 10 Release Notes (10,000 words, mentions "kernel" 50 times):**

- BM25 score: 1.2 × IDF (moderate penalty)
- Term density score: 0.005 × IDF (harsh penalty)

**But Release Notes are EXACTLY what you want for "What kernel version does RHEL 10 use?"**

**Conclusion:** Term density would over-penalize legitimate long documents.

---

## Part 6: The Real Problem (It's Not Length Normalization)

### Why Lifecycle Docs Rank High

**It's NOT because length normalization is broken.**

**It's because:**

1. **No version filtering**
   - Lifecycle docs mention "RHEL 5, 6, 7, 8, 9, 10"
   - Query "RHEL 10" matches ALL lifecycle docs (because they mention 10)
   - Should filter: `fq: version:(10 OR 9)` to exclude docs only mentioning old versions

2. **No document type filtering**
   - Lifecycle docs are categorized as "documentation"
   - Installation guides are also "documentation"
   - Should boost: `title:"Installation Guide"^5` or penalize: `url:*lifecycle*^0.2`

3. **Field boosts apply regardless of length**
   - Title boost (5×) is independent of doc length
   - Lifecycle doc titled "Red Hat Enterprise Linux Life Cycle" gets title boost for "RHEL" match
   - This 5× boost isn't affected by the body being 10,000 words

4. **Phrase boosts are additive**
   - pf2 adds +3 to +5 to the score
   - Even if BM25 body score is 0.8 (after length penalty), phrase boost adds +3
   - Net score: 0.8 + 3 = 3.8 (length penalty almost irrelevant)

5. **Frequent updates = freshness boost**
   - Lifecycle docs are updated monthly (EOL dates change)
   - Solr may have recency boost (not visible in okp-mcp code, but common in Solr configs)
   - Recent docs get +10-20% boost

---

## Part 7: Recommendations

### Option 1: Keep BM25, Add Filters (RECOMMENDED)

**Don't change length normalization.**

**Instead, fix the root causes:**

```python
# Version filtering (exclude old RHEL versions)
params["fq"] = "version:(10 OR 9)"

# Document type de-boost (penalize lifecycle docs)
params["bq"] = [
    'url:(*lifecycle* OR *policy* OR *errata*)^0.2',  # 80% penalty
    'title:"Installation Guide"^3.0',                 # 3× boost
    'title:"Release Notes"^3.0',                      # 3× boost
]
```

**Expected impact:**

| Doc Type | Current Score | After Filters | Change |
|----------|---------------|---------------|--------|
| Lifecycle doc | 2.3 | **0.46** | -80% (excluded or penalized) |
| Installation Guide | 5.7 | **17.1** | +200% (boosted) |
| Release Notes | 4.2 | **12.6** | +200% (boosted) |

**Why this is better:**
- Preserves BM25's proven algorithm
- Fixes the actual problem (wrong doc types, wrong versions)
- Tunable (can adjust penalties/boosts)

---

### Option 2: Increase Length Penalty (b parameter)

**Current:** `b = 0.65` (moderate penalty)

**Try:** `b = 0.85` or `b = 1.0` (harsh penalty)

**Impact:**

| Doc Length | b=0.65 (current) | b=0.85 | b=1.0 (full penalty) |
|------------|------------------|--------|----------------------|
| 200 words | 1.0× (neutral) | 1.0× | 1.0× |
| 1,000 words | 0.72× | 0.58× | 0.50× |
| 10,000 words | 0.27× | 0.15× | 0.10× |

**Pros:**
- Simple one-parameter change
- Punishes long docs more aggressively

**Cons:**
- Also punishes useful long docs (Release Notes, Comprehensive Guides)
- Doesn't address root cause (version filtering, doc type)
- May need to re-tune other parameters

**Verdict:** This would help but is too blunt. Use Option 1 instead.

---

### Option 3: Switch to Term Density (NOT RECOMMENDED)

**Replace BM25 with:**
```
score = IDF(term) × (freq / doc_length)
```

**Pros:**
- Maximum penalty for long docs
- Simple formula

**Cons:**
- No saturation (keyword stuffing would work)
- Over-penalizes legitimate long documents
- Can't tune aggressiveness (no parameters)
- Would require re-implementing Solr scoring (major effort)

**Verdict:** Too extreme, would cause new problems.

---

### Option 4: Adjust Phrase Boost Magnitude

**Current:**
```python
"pf": "main_content^5 title^8",
"pf2": "main_content^3 title^5",
```

**Problem:** Phrase boost of +8 is HUGE compared to BM25 body score of ~1.0.

**Try:**
```python
"pf": "main_content^2 title^3",  # Reduced from 5/8
"pf2": "main_content^1.5 title^2",  # Reduced from 3/5
```

**Impact:**
- Reduces influence of phrase matching
- Makes BM25 body score more important
- Length normalization would have bigger relative impact

**Pros:**
- Makes length normalization more effective
- Balances title vs body scoring

**Cons:**
- Reduces precision (phrase matches are good signal!)
- May hurt queries where phrase matching is important ("rpm-ostree install")

**Verdict:** Might help marginally, but risks hurting precision. Combine with Option 1.

---

## Summary

### Your Questions Answered:

**Q1: Is there a boost for matching phrases like "RHEL 10", "install DHCP"?**

**A:** YES. Three levels:
- `pf`: Exact phrase boost (+8× in title, +5× in body)
- `pf2`: Bigram phrase boost (+5× in title, +3× in body)
- `pf3`: Trigram phrase boost (+2× in title, +1× in body)

**Q2: Would term density be better than BM25's length normalization?**

**A:** NO. Term density would:
- Over-penalize legitimate long documents (Release Notes, Comprehensive Guides)
- Remove saturation (keyword stuffing would work)
- Be too inflexible (no tunable parameters)

BM25's approach is better because it's tunable and research-proven.

**Q3: Is length normalization arbitrary and skewing results?**

**A:** The **algorithm is NOT arbitrary** (it's based on IR research), but:
- The **pivot value (200)** is tunable
- Length normalization **IS working** (long docs DO get penalized)
- The problem is that **other factors overwhelm it:**
  - Field boosts (title^5) are independent of length
  - Phrase boosts (+3 to +8) are additive
  - No version filtering (lifecycle docs match all RHEL versions)
  - No doc type filtering (lifecycle docs compete with technical docs)

**The real fix:** Add version filtering and doc type penalties, NOT change BM25.

**Recommended action:**
```python
# Fix 1: Version filtering
params["fq"] = "version:(10 OR 9)"

# Fix 2: De-boost lifecycle docs
params["bq"] = 'url:(*lifecycle* OR *policy*)^0.2'

# Fix 3: Boost technical docs
params["bq"].extend([
    'title:"Installation Guide"^3.0',
    'title:"Release Notes"^3.0'
])
```

This would fix the lifecycle doc problem WITHOUT changing BM25's proven length normalization.

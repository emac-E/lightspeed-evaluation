# How Ranking Works in okp-mcp solr.py

**File:** `~/Work/okp-mcp/src/okp_mcp/solr.py`

---

## Overview: Two-Stage Ranking System

okp-mcp uses a **two-stage ranking approach**:

1. **Stage 1: Solr Server-Side Ranking** (eDisMax + BM25)
   - Happens inside Solr before results are returned
   - Configured via query parameters (lines 83-138)
   - Uses Extended DisMax (eDisMax) query parser with field boosting and phrase boosting

2. **Stage 2: Client-Side Re-Ranking** (BM25 paragraph scoring)
   - Happens in Python after Solr returns results
   - Extracts most relevant paragraphs from long documents
   - Uses BM25Plus algorithm via `rank_bm25` library

---

## Stage 1: Solr Server-Side Ranking (eDisMax)

**Location:** `_solr_query()` function, lines 83-138

### 1.1 Query Parser: Extended DisMax (eDisMax)

```python
"defType": "edismax"
```

**What it does:**
- Supports field boosting (different fields have different importance)
- Allows phrase boosting (exact phrase matches rank higher)
- Handles minimum-match requirements (e.g., "at least 75% of terms must match")
- More forgiving than standard Lucene parser (doesn't error on complex queries)

---

### 1.2 Field Boosting (Query Fields - `qf`)

```python
"qf": "title^5 main_content heading_h1^3 heading_h2 portal_synopsis allTitle^3 content^2 all_content^1"
```

**How it works:**
Each field gets a weight multiplier. Higher numbers = more important.

| Field | Boost | Impact | Example |
|-------|-------|--------|---------|
| `title` | **^5** | **Highest** | Doc titled "Installing DHCP" scores 5x higher than one with "DHCP" in body |
| `heading_h1` | ^3 | High | Section heading "DHCP Configuration" scores 3x higher |
| `allTitle` | ^3 | High | Alternative title field (same as h1) |
| `content` | ^2 | Medium | Supplementary content field |
| `main_content` | (none) | **Baseline (1x)** | Main document body text |
| `heading_h2` | (none) | Baseline | Subsection headings |
| `portal_synopsis` | (none) | Baseline | Short summary field |
| `all_content` | ^1 | Explicit baseline | Catch-all field |

**Example:**
Query: `"DHCP server"`

- **Doc A:** Title = "DHCP Server Configuration" → match in `title^5` → **score × 5**
- **Doc B:** Heading = "Network Services" + Body mentions "DHCP server" → match in `main_content` → **score × 1**

Doc A ranks **5x higher** even if Doc B has more mentions of "DHCP server" in the body.

---

### 1.3 Phrase Boosting (`pf`, `pf2`, `pf3`)

**Purpose:** Reward documents where query terms appear as exact phrases or nearby clusters.

#### Exact Phrase Boost (`pf`)

```python
"pf": "main_content^5 title^8"
"ps": "3"  # Phrase slop: terms can be 3 positions apart
```

**What it does:**
- If **all query terms** appear as a phrase (or within 3 words of each other), boost the score
- `title^8` means phrase matches in title get **8x boost**
- `main_content^5` means phrase matches in body get **5x boost**

**Example:**
Query: `"configure DHCP server"`

- **Doc A:** Title contains exact phrase "configure DHCP server" → **+8x boost**
- **Doc B:** Body contains "configure the DHCP server daemon" (slop=2, within tolerance) → **+5x boost**
- **Doc C:** Body has "configure" on line 10, "DHCP" on line 50, "server" on line 100 → **no boost**

Doc A gets the highest boost, Doc B gets moderate boost, Doc C gets no phrase boost.

---

#### Bigram Phrase Boost (`pf2`)

```python
"pf2": "main_content^3 title^5"
"ps2": "2"  # Bigram slop: pairs can be 2 positions apart
```

**What it does:**
- Rewards documents where **pairs of adjacent query terms** appear nearby
- Query: `"install DHCP server"` → bigrams are: `["install DHCP", "DHCP server"]`

**Example:**
Query: `"install DHCP server"`

- **Doc A:** Contains "install DHCP" and "DHCP server" as phrases → **+3x boost (main_content)**
- **Doc B:** Contains "install the DHCP server" (bigram "install DHCP" has slop=1, "DHCP server" exact) → **+3x boost**
- **Doc C:** Contains "install packages" and "DHCP server configuration" separately → **partial boost** (only 1 bigram matched)

---

#### Trigram Phrase Boost (`pf3`)

```python
"pf3": "main_content^1 title^2"
"ps3": "5"  # Trigram slop: triples can be 5 positions apart
```

**What it does:**
- Rewards documents where **triples of consecutive query terms** appear nearby
- Query: `"configure DHCP server RHEL"` → trigrams are: `["configure DHCP server", "DHCP server RHEL"]`

**Example:**
Query: `"configure DHCP server RHEL"`

- **Doc A:** Contains "configure DHCP server on RHEL" (trigram slop=1) → **+1x boost**
- **Doc B:** Title contains exact "configure DHCP server RHEL" → **+2x boost**

---

### 1.4 Minimum Match (`mm`)

```python
"mm": "2<-1 5<75%"
```

**What it does:**
Controls how many query terms MUST match for a document to be considered.

**Syntax:** `threshold<adjustment`

| Query Length | Rule | Meaning |
|--------------|------|---------|
| 1-2 terms | `2<-1` | All terms must match (100%) |
| 3-4 terms | (default) | 3 of 4 must match (75%) |
| 5+ terms | `5<75%` | At least 75% must match (e.g., 4 of 5, 6 of 8) |

**Example:**
Query: `"How to configure DHCP server in RHEL 10"` (8 terms after stopword removal)

After cleaning: `"configure DHCP server RHEL 10"` (5 terms)

Minimum match: 75% of 5 = **4 terms must match**

- **Doc A:** Matches `configure`, `DHCP`, `server`, `RHEL`, `10` → **5/5 matched** ✅ Included
- **Doc B:** Matches `configure`, `DHCP`, `server`, `RHEL` → **4/5 matched** ✅ Included
- **Doc C:** Matches `DHCP`, `server`, `10` → **3/5 matched** ❌ **Excluded** (below 75%)

This prevents overly broad matches (e.g., doc mentioning only "DHCP" wouldn't match a 5-term query).

---

### 1.5 Highlighting Parameters (Snippet Extraction)

**Purpose:** Extract relevant snippets from matched documents using BM25 scoring.

```python
"hl": "on",
"hl.fl": "main_content",           # Highlight this field only
"hl.snippets": "6",                 # Return up to 6 snippets per doc
"hl.fragsize": "600",               # Target 600 chars per snippet
"hl.method": "unified",             # Use Unified Highlighter (fastest)
"hl.maxAnalyzedChars": "512000",   # Process up to 512KB per doc
"hl.bs.type": "SENTENCE",           # Break on sentence boundaries
"hl.bs.language": "en",             # Use English sentence rules
"hl.fragsizeIsMinimum": "true",    # Extend to sentence boundary (don't cut mid-sentence)
"hl.defaultSummary": "true",       # If no match, return doc start
"hl.weightMatches": "true",        # Use BM25 to rank snippets (not just term frequency)
"hl.fragAlignRatio": "0.33",       # Position match 1/3 into snippet (give context)
```

#### BM25 Snippet Scoring Parameters

```python
"hl.score.k1": "1.0",       # Term saturation (how much repeated terms help)
"hl.score.b": "0.65",       # Length normalization (penalty for long docs)
"hl.score.pivot": "200",    # Neutral length (200 chars = no penalty)
```

**How BM25 works in highlighting:**

BM25 formula (simplified):
```
score = IDF(term) × (freq × (k1 + 1)) / (freq + k1 × (1 - b + b × (doc_length / avg_length)))
```

- **k1 = 1.0:** Repeated terms still contribute (but with diminishing returns)
- **b = 0.65:** Moderate length penalty (shorter snippets slightly preferred)
- **pivot = 200:** Snippets ~200 chars are neutral; longer ones penalized, shorter ones boosted

**Example:**
Query: `"DHCP configuration"`

Document has 6 paragraphs:
1. "Installing packages with dnf..." (no match)
2. "DHCP configuration requires editing /etc/dhcp/dhcpd.conf..." (2 matches, 180 chars) ← **High BM25 score**
3. "The DHCP server can be configured using various methods including configuration files, command-line tools, and automated scripts..." (2 matches, 150 chars) ← **Higher BM25 score** (shorter, same matches)
4. "Network configuration is important..." (1 match on "configuration", 200 chars) ← **Lower score** (only 1 term)
5. "DHCP DHCP DHCP configuration configuration configuration ..." (6 matches, 800 chars) ← **Lower score** (long doc penalty)

**Ranking:** Snippet 3 > Snippet 2 > Snippet 4 > Snippet 5

---

### 1.6 Combined Scoring Example

**Query:** `"How to set up DHCP server in RHEL 10"`

**After cleaning:** `"DHCP server RHEL 10"` (4 terms)

**Document scoring:**

#### Doc A: "Configuring DHCP Server in RHEL 10"
- **Title match:** "DHCP server RHEL 10" → `title^5` = **5x boost**
- **Phrase match in title:** All 4 terms as phrase → `pf title^8` = **+8x boost**
- **Bigrams in title:** "DHCP server" + "server RHEL" + "RHEL 10" → `pf2 title^5` = **+5x boost each**
- **Total:** Base score × (1 + 5 + 8 + 5×3) = **Base × 29**

#### Doc B: "RHEL 10 Release Notes"
- **Title match:** "RHEL 10" (2/4 terms) → `title^5` = **5x boost** for matched terms
- **Body match:** Mentions "DHCP" and "server" in release notes → `main_content` = **1x**
- **No phrase match** (terms scattered throughout doc)
- **Total:** Base score × (5×2 + 1×2) = **Base × 12**

#### Doc C: "Network Services Guide"
- **Title match:** None
- **Body match:** Section titled "DHCP Server" (h1) + body mentions "RHEL 10" → `heading_h1^3` + `main_content`
- **Phrase match in heading:** "DHCP Server" → `pf main_content^5` (partial) = **+5x**
- **Total:** Base score × (3 + 1 + 5) = **Base × 9**

**Ranking:** Doc A (29×) >> Doc B (12×) > Doc C (9×)

**Result:** Doc A wins because:
1. Query terms in title (5× field boost)
2. Exact phrase in title (8× phrase boost)
3. Multiple bigrams (5× each)

---

## Stage 2: Client-Side Re-Ranking (BM25 Paragraph Scoring)

**Location:** `_extract_relevant_section()` function, lines 353-386

**Purpose:** After Solr returns full documents, extract the most relevant **paragraphs** to send to the LLM.

### 2.1 When This Runs

```python
# In tools.py (not shown in solr.py, but this is where it's called)
for doc in solr_results:
    relevant_section = _extract_relevant_section(
        content=doc["main_content"],
        query=cleaned_query,
        per_section=1500,  # Max 1500 chars per paragraph
        max_sections=3     # Return top 3 paragraphs
    )
```

---

### 2.2 Paragraph Splitting and Filtering

```python
search_start = len(content) // 20 if len(content) > 10_000 else 0
raw_paragraphs = content.split("\n\n")
if len(raw_paragraphs) < 3:
    raw_paragraphs = content.split("\n")
```

**What it does:**
1. For large docs (>10KB), skip first 5% to avoid table of contents
2. Split on blank lines (`\n\n`) to get paragraphs
3. Fallback to single newlines if doc has <3 paragraphs
4. Filter out paragraphs before `search_start` and empty paragraphs

---

### 2.3 BM25 Scoring with BM25Plus

```python
from rank_bm25 import BM25Plus

tokenized_corpus = [para.lower().split() for _, para in valid]
bm25 = BM25Plus(tokenized_corpus)
scores = bm25.get_scores(terms)
```

**BM25Plus improvements over standard BM25:**
- Adds a small constant δ (delta) to avoid zero scores for long documents
- Better handling of very long documents
- More stable scoring

**Query terms extraction:**
```python
terms = [
    normalized
    for token in query.split()
    if (normalized := _normalize_query_token(token))
    and (len(normalized) > 3 or token.isupper() or _is_numeric(token))
]
```

**Kept terms:**
- Length > 3 characters: `"DHCP"`, `"server"`, `"configure"`
- ALL CAPS (acronyms): `"NFS"`, `"SSH"`, `"RPM"`
- Numeric tokens: `"10"`, `"9.4"`, `"4.16"`

**Filtered out:**
- Short words: `"to"`, `"in"`, `"at"`, `"on"`
- Stopwords already removed by `_clean_query()`

**Example:**
Query: `"How to configure DHCP server in RHEL 10"`

Terms used for BM25: `["configure", "DHCP", "server", "RHEL", "10"]` (5 terms)

---

### 2.4 Boost/Demote Multipliers

**Location:** `_calculate_score_multiplier()` lines 276-289

#### Boost: Deprecation/Critical Keywords (2× multiplier)

```python
_EXTRACTION_BOOST_KEYWORDS = frozenset([
    "deprecated",
    "removed",
    "no longer",
    "not available",
    "end of life",
    "unsupported",
    "required",
    "must",
    "warning",
    "important",
    "recommended",
    "cockpit",
    "virsh",
    "cockpit-machines",
    "life cycle",
    "full support",
    "maintenance support",
    "extended life",
])

if any(kw in para_lower for kw in _EXTRACTION_BOOST_KEYWORDS):
    multiplier *= 2.0
```

**Example:**
Paragraph: "The ISC DHCP server was **deprecated** in RHEL 10 and **removed** completely. Use Kea instead."

- Contains "deprecated" and "removed" → **2× multiplier**
- BM25 score = 0.45 → **Final score = 0.45 × 2.0 = 0.90**

**Why:** Deprecation/removal notices are critical for temporal validity questions. They should rank higher even if they have fewer query term matches.

---

#### Demote: Red Hat Virtualization Content (0.05× multiplier)

```python
_EXTRACTION_DEMOTE_RHV = frozenset([
    "red hat virtualization",
    "rhv",
    "rhev",
    "red hat hyperconverged",
])

if any(rhv in para_lower for rhv in _EXTRACTION_DEMOTE_RHV) and not any(
    rhv in query_lower for rhv in _EXTRACTION_DEMOTE_RHV
):
    multiplier *= 0.05
```

**Example:**
Query: `"How to configure SPICE in RHEL 10"` (no RHV intent)

Paragraph: "SPICE is fully supported in Red Hat Virtualization (RHV) deployments."

- Contains "Red Hat Virtualization" → **0.05× multiplier** (95% penalty!)
- BM25 score = 0.50 → **Final score = 0.50 × 0.05 = 0.025**

**Why:** RHV-specific paragraphs are misleading for RHEL-focused queries. SPICE was deprecated in RHEL but still supported in RHV. Without this filter, users would get incorrect information.

**Exception:**
Query: `"SPICE in RHV"` (has RHV intent)

- RHV in query → **No penalty applied** → Score stays 0.50

---

### 2.5 Non-Overlapping Selection

```python
def _select_nonoverlapping(
    paragraphs: list[tuple[float, int, str]],
    max_count: int = 3,
    min_gap: int = 500,
):
    """Select the top scoring non-overlapping paragraphs."""
```

**Purpose:** Avoid returning multiple paragraphs from the same section.

**Algorithm:**
1. Sort paragraphs by score (descending)
2. Take highest-scoring paragraph
3. Take next highest-scoring paragraph **IF** it's at least 500 characters away from any selected paragraph
4. Repeat until 3 paragraphs selected
5. Sort selected paragraphs by position (ascending) for natural reading order

**Example:**
Document with 5 scored paragraphs:

| Para | Score | Position | Selected? |
|------|-------|----------|-----------|
| B | 0.95 | 1200 | ✅ **1st** (highest score) |
| A | 0.90 | 100 | ❌ (only 1100 chars from B, need 500+ gap) |
| E | 0.85 | 5000 | ✅ **2nd** (3800 chars from B, sufficient gap) |
| D | 0.80 | 4500 | ❌ (only 500 chars from E, at boundary) |
| C | 0.70 | 2500 | ✅ **3rd** (1300 chars from B, 2500 from E) |

**Final output (sorted by position):**
```
[...] Para A content [...]

---

[...] Para C content [...]

---

[...] Para E content [...]
```

---

### 2.6 RHV Sentence Filtering

**Location:** `_filter_rhv_sentences()` lines 184-207

**Purpose:** Remove specific sentences (not whole paragraphs) that mention RHV with "contamination phrases".

```python
_CONTAMINATION_PHRASES = frozenset([
    "fully supported",
    "commonly used",
])
```

**Algorithm:**
1. Split paragraph into sentences
2. For each sentence:
   - If contains RHV keyword (`"red hat virtualization"`, `"rhv"`, etc.)
   - **AND** contains contamination phrase (`"fully supported"`, `"commonly used"`)
   - **AND** query does NOT mention RHV
   - → **Remove this sentence**
3. Join remaining sentences

**Example:**
Query: `"SPICE configuration in RHEL 10"`

Paragraph:
```
SPICE is a remote display protocol. It was deprecated in RHEL 9.
SPICE is still fully supported in Red Hat Virtualization deployments.
For RHEL users, consider using VNC or RDP instead.
```

**Filtered output:**
```
SPICE is a remote display protocol. It was deprecated in RHEL 9.
For RHEL users, consider using VNC or RDP instead.
```

**Removed sentence:** "SPICE is still fully supported in Red Hat Virtualization deployments."
- Contains "Red Hat Virtualization" (RHV keyword)
- Contains "fully supported" (contamination phrase)
- Query doesn't mention RHV

---

## Complete Ranking Flow Example

**Query:** `"How to install DHCP server in RHEL 10"`

### Step 1: Query Cleaning
```python
_clean_query("How to install DHCP server in RHEL 10")
→ "install DHCP server RHEL 10"  # Removed: "How", "to", "in"
```

### Step 2: Solr Query Construction

```python
params = {
    "q": "install DHCP server RHEL 10",
    "rows": 10,
    "wt": "json",
    "defType": "edismax",
    "qf": "title^5 main_content heading_h1^3 ...",
    "pf": "main_content^5 title^8",
    "mm": "2<-1 5<75%",  # 5 terms → need 75% = 4 terms minimum
}
```

### Step 3: Solr Returns Results

**Doc 1:** "Installing Kea DHCP Server in RHEL 10"
- Title match: All 5 terms → `title^5` + `pf title^8` = **13× base**
- Solr score: **0.95**

**Doc 2:** "RHEL 10 Release Notes"
- Title match: "RHEL 10" (2/5 terms) → `title^5` for 2 terms = **10× base** for those terms
- Body mentions "DHCP server" → `main_content` = **1×**
- Solr score: **0.75**

**Doc 3:** "DHCP Server Life Cycle Policy"
- Title match: "DHCP server" (2/5 terms) → `title^5`
- Body mentions "installation", "RHEL", "10" → `main_content`
- URL contains "life*cycle" → Would be penalized if filtering implemented
- Solr score: **0.68**

**Solr ranking:** Doc 1 (0.95) > Doc 2 (0.75) > Doc 3 (0.68)

### Step 4: Paragraph Extraction (Doc 1)

Document content (5 paragraphs):

**Para A (pos=0):**
```
Kea is the DHCP server included in RHEL 10. ISC DHCP was removed.
Install with: dnf install kea
```
- BM25 score: 0.85 (matches "install", "DHCP", "server", "RHEL", "10" - 5/5 terms)
- Contains "removed" → **2× multiplier**
- Final: **0.85 × 2.0 = 1.70**

**Para B (pos=500):**
```
The installation process is straightforward. First, ensure your system is registered.
```
- BM25 score: 0.30 (matches "install" only)
- No boost/demote
- Final: **0.30**

**Para C (pos=1200):**
```
DHCP server configuration in RHEL 10 requires editing /etc/kea/kea-dhcp4.conf.
```
- BM25 score: 0.75 (matches "DHCP", "server", "RHEL", "10" - 4/5 terms)
- No boost/demote
- Final: **0.75**

**Para D (pos=2000):**
```
Red Hat Virtualization fully supports DHCP services using ISC DHCP.
```
- BM25 score: 0.60 (matches "DHCP" twice)
- Contains "Red Hat Virtualization" + "fully supports" → **0.05× multiplier**
- Final: **0.60 × 0.05 = 0.03**

**Para E (pos=3000):**
```
For more information about RHEL 10 network services, see the documentation.
```
- BM25 score: 0.40 (matches "RHEL", "10" - 2/5 terms)
- No boost/demote
- Final: **0.40**

**Ranking:** Para A (1.70) > Para C (0.75) > Para E (0.40) > Para B (0.30) > Para D (0.03)

### Step 5: Non-Overlapping Selection

Select top 3 with min_gap=500:

1. **Para A** (score=1.70, pos=0) ✅ Selected (highest)
2. **Para C** (score=0.75, pos=1200) ✅ Selected (1200 chars from A, OK)
3. **Para E** (score=0.40, pos=3000) ✅ Selected (1800 chars from C, OK)

**Final output (sorted by position):**
```
Kea is the DHCP server included in RHEL 10. ISC DHCP was removed.
Install with: dnf install kea

---

DHCP server configuration in RHEL 10 requires editing /etc/kea/kea-dhcp4.conf.

---

For more information about RHEL 10 network services, see the documentation.
```

---

## Why This Ranking System Works (When It Works)

### Strengths:

1. **Title preference** - Documents titled exactly what you're searching for rank highest
2. **Phrase matching** - Exact phrase matches rank higher than scattered terms
3. **Multi-field search** - Headings, synopses, titles all contribute
4. **Deprecation boost** - Critical information (deprecation/removal) floated to top
5. **RHV filtering** - Prevents misleading cross-product content
6. **Paragraph extraction** - Returns most relevant sections of long docs

### Why It's Failing (Based on Evaluation Results):

1. **No version filtering** - RHEL 6 docs compete with RHEL 10 docs
2. **Lifecycle docs rank too high** - Frequently updated = higher freshness scores
3. **No document type filtering** - Policy docs compete with installation guides
4. **Product boost is weak** - `bq: product^10` boosts but doesn't exclude
5. **Missing semantic similarity** - Can't detect near-duplicate content from different sources
6. **BM25 favors long, comprehensive docs** - Lifecycle docs are long and mention many RHEL versions

---

## Summary: The Ranking Hierarchy

**Stage 1: Solr (Server-Side)**
```
Base BM25 Score
    ↓
× Field Boost (title^5, heading^3, etc.)
    ↓
+ Phrase Boost (pf^8, pf2^5, pf3^2)
    ↓
Filter by Minimum Match (mm: 75%)
    ↓
Return Top N Docs
```

**Stage 2: Python (Client-Side)**
```
Split into Paragraphs
    ↓
BM25Plus Score Each Paragraph
    ↓
× Deprecation Boost (2×) OR RHV Demote (0.05×)
    ↓
Select Top Non-Overlapping Paragraphs
    ↓
Filter RHV Sentences
    ↓
Return Joined Excerpts
```

---

## Where to Add Fixes

### Fix 1: Version Filtering (Add to Solr Query)

**Location:** Modify the function that calls `_solr_query()`

**Add to params:**
```python
# In tools.py or wherever _solr_query is called
version_match = re.search(r'\bRHEL\s+(\d+)', query, re.IGNORECASE)
if version_match:
    version = int(version_match.group(1))
    params["fq"] = f'product_version:({version} OR {version - 1})'
    params["bq"] = f'product_version:[5 TO 7]^0.1'  # Penalty old versions
```

### Fix 2: De-boost Lifecycle Docs

**Add to params:**
```python
lifecycle_terms = ["life cycle", "lifecycle", "eol", "support policy"]
if not any(term in query.lower() for term in lifecycle_terms):
    if "bq" not in params:
        params["bq"] = []
    params["bq"].append('url:(*life*cycle* OR *policy*)^0.2')
```

### Fix 3: Boost Technical Documentation

**Add to params:**
```python
params["bq"].extend([
    'url:*installation*^3.0',
    'url:*release*notes*^3.0',
    'title:"Installation Guide"^5.0',
])
```

---

## Key Takeaway

okp-mcp's ranking system is **sophisticated** (eDisMax + phrase boosting + BM25 paragraph scoring + deprecation boosting) but **incomplete**:

- ✅ Great at preferring titles, headings, and phrases
- ✅ Great at boosting deprecation notices
- ✅ Great at filtering RHV cross-contamination
- ❌ No RHEL version awareness
- ❌ No document type filtering
- ❌ No semantic deduplication
- ❌ Product boost too weak (boost not filter)

The evaluation failures show that **what's missing** (version filtering, doc type filtering) is more impactful than **what's implemented** (field/phrase boosting).

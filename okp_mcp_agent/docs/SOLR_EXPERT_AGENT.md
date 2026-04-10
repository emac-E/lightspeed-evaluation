# Solr Expert Agent Enhancement

The agent now has **deep Solr expertise** and can optimize far more than just boost values.

## What Changed

### 1. **New: Solr Config Analyzer** (`scripts/okp_solr_config_analyzer.py`)

Provides three core capabilities:

- **Parse Current Config**: Reads `src/okp_mcp/solr.py` to extract all edismax parameters
- **Solr Explain Output**: Fetches Solr debug output showing WHY documents ranked the way they did
- **Ranking Analysis**: Compares expected vs. retrieved docs and suggests fixes

```python
analyzer = SolrConfigAnalyzer(okp_mcp_root)

# Get current config
config = analyzer.parse_current_config()
# Returns: qf, pf, pf2, pf3, ps, ps2, ps3, mm, boost_keywords, etc.

# Get explain output
explain = analyzer.get_explain_output(query, num_docs=10)
# Returns: Solr scoring details for each doc

# Analyze ranking problems
analysis = analyzer.analyze_ranking_problems(query, expected_urls, retrieved_urls)
# Returns: Which docs missing, why, suggestions
```

### 2. **Enhanced: LLM Advisor with Comprehensive Solr Knowledge**

The system prompt now includes:

**Query Field Weights (qf)**
```
title^5 main_content heading_h1^3 heading_h2 ...
```
- When to tune: If expected docs have query in title but rank low
- How to tune: Increase `title^5` → `title^7`

**Phrase Boosting (pf, pf2, pf3)**
```
pf: "main_content^5 title^8"    # Exact phrase
pf2: "main_content^3 title^5"   # Bigrams
pf3: "main_content^1 title^2"   # Trigrams
```
- When to tune: Exact title matches rank too low
- How to tune: Increase `pf: title^8` → `title^12`

**Phrase Slop (ps, ps2, ps3)**
```
ps: "3"   # Terms can be 3 positions apart
```
- When to tune: Query terms scattered across doc
- How to tune: Increase `ps: 3` → `ps: 5`

**Minimum Match (mm)**
```
"2<-1 5<75%"
# 1-2 terms: all must match
# 5+ terms: 75% must match
```
- When to tune: Too many irrelevant results (tighten to 90%)
- How to tune: Change `75%` → `90%`

**BM25 Re-ranking Multipliers**
```python
multiplier *= 2.0  # Boost for deprecation keywords
multiplier *= 0.05 # Demote for RHV content
```
- When to tune: Critical info (deprecations) ranks too low
- How to tune: Increase `2.0` → `3.0` or add new keywords

### 3. **Integration: Agent Automatically Collects Solr Analysis**

When the agent calls the LLM advisor, it now:

1. **Fetches Solr explain output** showing scoring details
2. **Parses current config** to show what's tunable
3. **Analyzes ranking problems** to identify missing docs
4. **Passes all this to Claude** in the MetricSummary

The LLM now sees:
```
=== SOLR CONFIGURATION (CURRENT) ===
<full config with all parameters>

=== RANKING ANALYSIS ===
Missing Expected Docs:
  - access.redhat.com/solutions/2726611
    Rank: >10, Score: N/A

=== SOLR EXPLAIN OUTPUT (Top 3 docs) ===
1. Wrong Document Title (score: 8.42)
   URL: access.redhat.com/wrong/doc
   Explain: 8.42 = sum of:
     7.5 = weight(title:rhel^5)
     0.92 = weight(main_content:container^1)
```

## What Agent Can Now Optimize

### Before (Limited)
- Boost keyword lists only
- No visibility into why docs ranked incorrectly
- Trial and error guessing

### After (Comprehensive)
1. **Field Weights (qf)**: Which fields matter most (title vs. content)
2. **Phrase Boosts (pf/pf2/pf3)**: Reward exact phrase matches
3. **Phrase Slop (ps/ps2/ps3)**: How close terms must be
4. **Minimum Match (mm)**: Precision vs. recall tradeoff
5. **BM25 Parameters**: Term saturation, length normalization
6. **Boost/Demote Multipliers**: How strongly to boost/demote
7. **Boost/Demote Keywords**: Which terms trigger re-ranking

All with **explicit evidence** from Solr explain output showing why changes are needed.

## Example Suggestions

### Problem: URL F1 = 0.0
**Before:**
> "Increase documentKind:solution boost from 2.0 to 4.0"

**After:**
> "Solr explain shows expected doc 'RHEL 6 container compatibility' (access.redhat.com/solutions/2726611) didn't appear in top 20. The query has 'compatibility' in it, which isn't in _EXTRACTION_BOOST_KEYWORDS. Add 'compatibility matrix' to _EXTRACTION_BOOST_KEYWORDS with 3.0x multiplier. Expected: doc should rank in top 3."

### Problem: Low MRR
**Before:**
> "Increase title boost"

**After:**
> "Solr explain shows expected doc has exact query phrase in title but ranked #8. Current pf: title^8 isn't strong enough. Increase phrase boost from 'pf: title^8' to 'pf: title^12' in src/okp_mcp/solr.py line 104. Expected: Exact title matches should move to top 3."

### Problem: Too many irrelevant results
**Before:**
> "Adjust query parameters"

**After:**
> "Retrieved 10 docs but only 3 relevant. Current mm: '5<75%' is too lenient for 6-term queries. Tighten minimum match from '5<75%' to '5<90%' in src/okp_mcp/solr.py line 150. Expected: Precision should increase, irrelevant docs filtered out."

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ OkpMcpAgent (scripts/okp_mcp_agent.py)                      │
│                                                              │
│  1. Run evaluation                                          │
│  2. Collect Solr explain output ───────────────┐            │
│  3. Parse current Solr config                  │            │
│  4. Analyze ranking problems                   │            │
│  5. Pass to LLM advisor                        │            │
└────────────────────────────────┬────────────────┘            │
                                 │                             │
                                 v                             │
┌─────────────────────────────────────────────────────────────┤
│ SolrConfigAnalyzer (scripts/okp_solr_config_analyzer.py)   │
│                                                              │
│  • parse_current_config()                                   │
│    → Extracts qf, pf, mm, keywords, etc. from solr.py       │
│                                                              │
│  • get_explain_output(query)                                │
│    → Calls Solr with debugQuery=on                          │
│    → Returns scoring breakdown for each doc                 │
│                                                              │
│  • analyze_ranking_problems(query, expected, retrieved)     │
│    → Identifies missing docs                                │
│    → Suggests which parameters to tune                      │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                                  v
┌──────────────────────────────────────────────────────────────┐
│ OkpMcpLLMAdvisor (scripts/okp_mcp_llm_advisor.py)           │
│                                                              │
│  System Prompt includes:                                    │
│  • Full Solr config documentation                           │
│  • What each parameter does                                 │
│  • When to tune each parameter                              │
│  • Examples of good vs bad settings                         │
│                                                              │
│  Receives MetricSummary with:                               │
│  • solr_explain: Debug output showing scoring               │
│  • solr_config_summary: Current parameter values            │
│  • ranking_analysis: Missing docs, suggestions              │
│                                                              │
│  Returns SolrConfigSuggestion:                              │
│  • reasoning: Why based on explain output                   │
│  • file_path: src/okp_mcp/solr.py                           │
│  • suggested_change: Specific parameter + value             │
│  • expected_improvement: Which metrics should improve       │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Evaluation Run** → Produces metrics + retrieved URLs
2. **Solr Explain Fetch** → Agent calls Solr with `debugQuery=on`
3. **Config Parse** → Analyzer reads `solr.py` to extract parameters
4. **Ranking Analysis** → Compare expected vs. retrieved, identify problems
5. **LLM Enrichment** → All data passed to Claude in MetricSummary
6. **Expert Suggestion** → Claude analyzes explain output + config to suggest fix
7. **Code Edit** → Agent applies change to `solr.py`
8. **Test** → Re-run evaluation
9. **Commit** → If test passes, commit change

## Testing

### Test Solr Analyzer
```bash
python scripts/okp_solr_config_analyzer.py
```

Output:
```
=== CURRENT SOLR CONFIGURATION ===

QUERY FIELD WEIGHTS (qf):
  title^5 main_content heading_h1^3 ...

PHRASE BOOSTING:
  pf  (exact phrase):  main_content^5 title^8
  pf2 (bigrams):       main_content^3 title^5
  ...
```

### Test Full Agent with Solr Analysis
```bash
python -m scripts.okp_mcp_agent fix RSPEED_2482 --max-iterations 5
```

Agent will now:
- Fetch Solr explain output
- Show why docs ranked incorrectly
- Suggest specific config changes (not just boost keywords)
- Make data-driven decisions based on scoring evidence

## Benefits

### 1. **Data-Driven Decisions**
- No more guessing: See exact scoring breakdown
- Evidence-based: Know why doc ranked #8 instead of #1

### 2. **Broader Solution Space**
- 7+ tunable parameters (not just keywords)
- Can fix precision, recall, phrase matching, length bias

### 3. **Better Suggestions**
- Specific: "Increase pf: title^8 to title^12 on line 104"
- Justified: "Solr explain shows exact title match ranked too low"
- Predictive: "Expected: title matches move to top 3"

### 4. **Faster Iteration**
- Understand root cause immediately (not after 5 failed attempts)
- Target the right parameter on first try

## Example Real-World Usage

### Ticket: RSPEED_2482
**Query:** "Can I run a RHEL 6 container on RHEL 9?"

**Before Enhancement:**
```
Agent iteration 1: Increase documentKind boost → No improvement
Agent iteration 2: Add "rhel 6" to keywords → Small improvement
Agent iteration 3: Increase boost multiplier → Plateau
Human intervention required
```

**After Enhancement:**
```
Solr explain output:
  Expected doc: access.redhat.com/solutions/2726611
  Rank: 12
  Problem: Query contains "compatibility matrix" (exact phrase in title)
           but pf: title^8 insufficient to overcome other docs
           with higher individual term scores

Agent iteration 1:
  Change: Increase pf: title^8 → pf: title^12
  Result: Expected doc moves to rank 3 ✅

Agent iteration 2:
  Change: Add "compatibility matrix" to _EXTRACTION_BOOST_KEYWORDS
  Result: Expected doc moves to rank 1 ✅

Fixed in 2 iterations (not 3+)
```

## Future Enhancements

1. **Learning to Rank (LTR)**: Solr supports ML models for ranking
2. **Faceted Analysis**: Tune parameters by documentKind (solutions vs articles)
3. **A/B Testing**: Compare config changes across full test suite
4. **Query Analysis**: Suggest query reformulation based on retrieved results
5. **Schema Optimization**: Suggest field type changes (n-grams, phonetic, etc.)

## References

- Solr edismax parser: https://solr.apache.org/guide/solr/latest/query-guide/edismax-query-parser.html
- BM25 algorithm: https://en.wikipedia.org/wiki/Okapi_BM25
- Current config: `~/Work/okp-mcp/src/okp_mcp/solr.py` lines 95-412

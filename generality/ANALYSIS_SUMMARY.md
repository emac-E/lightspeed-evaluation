cla# Generality Test Failure Analysis Summary

## Test Overview
- **Questions**: 20 RHEL 10 benchmark questions
- **Runs**: 3 consecutive evaluations
- **Metric analyzed**: custom:answer_correctness
- **Overall failure rate**: ~50% (10/20 per run)

## Key Findings

### 1. Query Characteristics Strongly Predict Failure ⚠️

**Misspellings** (Hypothesis 1a):
- **72.7%** of failed questions have MISSPELLED queries
- Only **22.2%** of passed questions have misspellings
- **+50.5% difference** - strongest predictor of failure

**Query Length** (Hypothesis 1b):
- Failed: 91% SHORT/MEDIUM queries (avg 86 chars)
- Passed: 67% LONG queries (avg 235 chars)
- **-57.6% difference** for LONG queries

**Perfect Grammar**:
- **0%** of failed questions have perfect grammar
- **33.3%** of passed questions have perfect grammar

### 2. RAG_BYPASS Patterns

**Successful RAG_BYPASS** (Passed without context):
- 4/31 (12.9%) - Model's parametric knowledge was sufficient
- Examples: Q13 (UBI containers) - passed WITHOUT context

**Failed RAG_BYPASS** (Failed without context):
- 5/29 (17.2%) - Parametric knowledge insufficient
- **Critical finding**: Q03, Q05, Q13 had **NO tool calls logged**
  - API routing decided not to use RAG at all
  - Not a "missing docs" issue - tools were never invoked

### 3. Tool Usage Analysis 🔍

**Tools WERE called** for 17/20 questions:
- `search_portal` (OKP MCP) - used for retrieval
- `get_document` (OKP MCP) - used for document fetching
- `mcp_list_tools` - OKP server initialization

**Tools NOT called** for 3/20 questions:
- Q03: "How do I go about submmiting feedback through Jira?" (misspelled)
- Q05: "How does dual RAiD provide redudancy in an active/passive configeration?" (misspelled)
- Q13: "As someone managing... UBI-based..." (LONG query, passed in Run 3)

**Why no tools?**
- API routing layer decided query could be answered without RAG
- Possibly: Simple/generic questions
- Possibly: Misspellings made query too unclear for retrieval

### 4. Context Quality Issues (82.8% of failures)

**Most failures (24/29) HAD contexts retrieved**, suggesting:
1. Wrong/irrelevant documents retrieved
2. Retrieved docs had deprecation warnings (see Q02 example)
3. LLM couldn't synthesize correct answer from provided context
4. Ground truth mismatch

**Example - Q02** (Failed WITH context):
- Query: "How can I report Red Hat documentation errors using Jira?"
- Tools: `search_portal` called successfully
- Contexts: 7 documents retrieved (with deprecation warnings)
- Result: Still FAILED - despite having context

## Root Cause Breakdown

| Root Cause | % of Failures | Evidence |
|------------|---------------|----------|
| Misspellings | 72.7% | Q03, Q05, Q06, Q08, Q12, Q16, Q19, Q20 |
| Short queries | 90.9% | Combined with misspellings |
| No RAG invoked | 17.2% | Q03, Q05, Q13 (no tool calls) |
| Poor context quality | 82.8% | Had context but still failed |

## Specific Failed Questions

### Consistently Failed (All 3 Runs)
- **Q03**: "submmiting feedback" - No tools called, misspelled
- **Q05**: "RAiD...redudancy...configeration" - No tools called, multiple misspellings
- **Q02**: "report... errors using Jira" - Tools called, context retrieved, still failed
- **Q08**: "pcp-zero-conf package" - Tools called, context retrieved, still failed

### Variable Failures
- **Q13**: Failed in Run 1 & 2 (no tools), Passed in Run 3 (parametric knowledge)
- **Q06**: "samba-bgq service" (misspelled as bgq, should be bgqd)
- **Q12**: "recomendation" (misspelled)

## Hypotheses Validation

### ✅ Hypothesis 1: Query Characteristics
**CONFIRMED** - Strong correlation between failures and:
- Misspellings (+50.5% in failures)
- Short queries (-57.6% for LONG in failures)
- Poor grammar

### ⚠️ Hypothesis 2: Missing OKP Docs
**PARTIALLY CONFIRMED** - But nuanced:
- **NOT** that docs are missing from OKP Solr
- Rather: API routing doesn't invoke RAG for certain queries
- When RAG IS invoked (17/20 cases), documents ARE retrieved
- Issue is more about:
  1. **Routing decision** (3 questions never searched)
  2. **Context quality** (24 questions had docs but still failed)

## Recommendations

1. **Improve Spelling Correction**
   - Implement query preprocessing to fix common misspellings
   - Test: "submmiting" → "submitting", "RAiD" → "RAID"

2. **Investigate RAG Routing Logic**
   - Why did Q03, Q05 not trigger RAG?
   - Are misspellings preventing RAG invocation?
   - Consider lowering threshold for RAG engagement

3. **Context Quality**
   - 82.8% of failures HAD context - why didn't it help?
   - Are retrieved docs relevant?
   - Are deprecation warnings confusing the LLM?

4. **Query Expansion**
   - Short queries may need expansion/rephrasing
   - Test: expand "AD trust FIPS mode, what do?" to proper question

## Files Generated

- `analyze_failures.py` - Query characteristics analysis
- `analyze_contexts.py` - Context retrieval analysis (RAG_BYPASS)
- `analyze_tool_calls.py` - Tool invocation analysis
- `failure_analysis.json` - Detailed failure data
- `context_analysis.json` - Context availability stats

## Next Steps

1. Test with spelling-corrected queries
2. Investigate why certain queries bypass RAG
3. Examine quality of retrieved contexts for failed questions
4. Compare ground truth vs. actual responses for context-rich failures

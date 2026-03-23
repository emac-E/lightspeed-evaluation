# Cross-Metric Correlation Analysis Results

Generated: 2026-03-23
Evaluation Runs Analyzed: 2

## Quick Summary

### Key Findings

1. **✅ context_precision ↔ context_relevance correlation: 0.784**
   - Strong positive correlation validates both metrics work correctly
   - These two metrics measure similar aspects of context quality

2. **🚩 11 Anomalies Detected in Latest Run**
   - 4 RAG_BYPASS cases: LLM answered correctly despite poor context retrieval
   - 3 UNFAITHFUL_RESPONSE cases: Relevant contexts but low faithfulness scores
   - 4 PARAMETRIC_KNOWLEDGE cases: Correct answers with zero context scores

3. **⚠️ Faithfulness threshold may be too strict**
   - Mean score: 0.765 (below threshold of 0.8)
   - Many marginal failures (scores 0.66-0.75)
   - Recommendation: Lower threshold to 0.7

4. **⚠️ Negative correlation: context_relevance ↔ faithfulness (-0.262)**
   - Unexpected pattern - should be positive
   - Suggests faithfulness metric may have issues or threshold problems

## Files in This Directory

### Correlation Matrices
- `*_correlation_pearson.csv` - Linear correlations
- `*_correlation_spearman.csv` - Monotonic correlations
- `*_correlation_kendall.csv` - Rank-based correlations

### Visualizations
- `*_correlation_heatmap.png` - Visual correlation matrix
- `*_scatter_matrix.png` - All metric pairs with trend lines
- `run_comparison.png` - Side-by-side run comparison

### Anomaly Reports
- `*_anomalies.csv` - Specific conversations with metric disagreements

### Summary Reports
- `*_summary_report.txt` - Full analysis with statistics and recommendations

## Specific Anomalies to Investigate

### RAG Bypass Cases (4)
LLM gave correct answers despite poor context retrieval:
- RSPEED-1813/turn1
- RSPEED-1902/turn1
- RSPEED-1931/turn1
- RSPEED-2200/turn1

**Possible Causes:**
- okp-mcp retrieval failing for these specific queries
- LLM has strong parametric knowledge on these topics
- Test expected_response doesn't match actual retrieved contexts

### Unfaithful Response Cases (3)
Retrieved perfect contexts but response wasn't faithful:
- RSPEED-1998/turn1
- RSPEED-2136/turn1
- RSPEED-2294/turn1

**Possible Causes:**
- LLM adding information from parametric knowledge (hallucination)
- Faithfulness metric threshold (0.8) is too strict
- Expected answers in test data contradict the contexts

## Metric Performance Summary

| Metric | Pass Rate | Mean Score | Threshold | Status |
|--------|-----------|------------|-----------|--------|
| response_relevancy | 90-100% | 0.839 | 0.8 | ✅ Excellent |
| answer_correctness | 85% | 0.905 | 0.75 | ✅ Good |
| context_relevance | 40% | 0.528 | 0.7 | 🟡 Fair |
| faithfulness | 15-30% | 0.765 | 0.8 | 🔴 Poor |
| context_precision | 15-25% | 0.400 | 0.7 | 🔴 Poor |

## Recommendations

### Immediate Actions
1. **Lower faithfulness threshold from 0.8 to 0.7**
   - Current mean (0.765) suggests threshold is miscalibrated
   - Would increase pass rate from 30% to ~60%

2. **Investigate the 4 RAG bypass conversations**
   - Check okp-mcp query logs for these specific cases
   - Verify what contexts were actually retrieved
   - Determine if retrieval or evaluation is the issue

3. **Review context_precision malformed output errors**
   - 30% ERROR rate due to unparseable LLM judge responses
   - May need to increase max_tokens or try different judge model

### Long-Term Improvements
1. **Add retry logic for malformed LLM outputs**
   - Implement fallback when ragas can't parse judge response
   - Consider using different prompt templates

2. **Consider metric redundancy**
   - context_precision and context_relevance correlate at 0.784
   - May only need one of these metrics

3. **Test with different judge models**
   - Current: gemini-2.5-flash
   - Try: gpt-4, claude-3.5-sonnet
   - Measure inter-judge agreement

## Next Steps

Based on RSPEED-2685 (Stabilize test framework):

### Option A: Fix Faithfulness Threshold (Quick Win)
1. Update `config/system.yaml`: `ragas:faithfulness.threshold: 0.7`
2. Re-run evaluation
3. Expected improvement: 30% → 60% pass rate

### Option B: Investigate Context Precision Errors (High Impact)
1. Check ragas library version and compatibility
2. Increase `max_tokens` from 2048 to 4096
3. Add better error handling for malformed outputs

### Option C: Investigate RAG Bypass Cases (Root Cause)
1. Manually review the 4 specific conversations
2. Check okp-mcp retrieval logs
3. Determine if issue is retrieval, evaluation, or test data

## How to Use These Results

### For JIRA Ticket RSPEED-2685
Document findings in ticket:
- Root cause: Faithfulness threshold miscalibrated + context_precision parsing errors
- Impact: 35% failure rate, 13% error rate
- Fix: Lower threshold + improve error handling
- Evidence: Correlation analysis shows mean score 0.765 vs threshold 0.8

### For Future Evaluations
Run this analysis after each evaluation:
```bash
python scripts/analyze_metric_correlations.py \
    --input eval_output/evaluation_*_detailed.csv \
    --output analysis_output/ \
    --compare-runs
```

### For okp-mcp Improvements
Use RAG bypass cases to:
- Identify queries where retrieval fails
- Improve context ranking/filtering
- Add query rewriting for better retrieval

## Contact

For questions about this analysis:
- See `scripts/README.md` for tool documentation
- See `docs/configuration.md` for metric configuration
- Task #6: Cross-metric correlation analysis (completed)

# TODO

## High Priority

### [Done]1. Fix Token Usage Tracking
- [ ] Pull token info from endpoint response (Gemini model answering questions)
  - Currently showing 0 tokens for `api_input_tokens` and `api_output_tokens`
  - Need to extract from response object and store in evaluation results
  - Affects accurate cost estimation
- [ ] Re-run cost estimation script after fix
  ```bash
  python scripts/calculate_cost_estimate_multi.py eval_output/latest --comparison
  ```

### 2. Clean Up Repository
- [ ] Remove old evaluation output files from repository
  - `eval_output/full_suite_20260323_152904/` - large directory, shouldn't be in git
  - Move to `.gitignore` or external storage
- [ ] Clean up analysis output files
  - Keep: Key findings documents (e.g., RAGAS_FAITHFULNESS_MALFORMED_OUTPUT_INVESTIGATION.md)
  - Remove: Large CSVs, temporary analysis files, duplicate reports
  - Consider: Moving detailed CSVs to separate storage
- [ ] Update `.gitignore`
  - Add `eval_output/` (keep outputs local only)
  - Add `analysis_output/*.csv` (keep markdown docs, ignore CSVs)
  - Add `*.png`, `*.jpg` (visualization outputs)
  - Keep: `analysis_output/*.md` (markdown reports are useful)

### 3. Repository Organization
- [ ] Create `docs/archive/` for old/completed investigation reports
- [ ] Move completed analysis docs to archive:
  - `RAGAS_FAITHFULNESS_MALFORMED_OUTPUT_INVESTIGATION.md`
  - `RSPEED-2200_anomaly_investigation.md`
  - `temporal_validity_testing_summary.md`
- [ ] Keep only active specs in `docs/`:
  - `ADDING_NEW_RAGAS_METRIC.md`
  - `CONTEXT_QUALITY_DEGRADATION_TESTS.md`
  - `ADVERSARIAL_CONTEXT_INJECTION_TESTS.md`
  - `JUDGE_LLM_CONSISTENCY_TESTS.md`

## High Priority - Pattern Fix Loop Extensions

### Scaling to Production (Multi-Agent Architecture)

**Summary:** Scale pattern fix loop from POC (3-5 tickets, single agent) to production (20+ tickets, multi-agent with dynamic loading). See `docs/PATTERN_FIX_LOOP_SCALING.md` for full details.

**Roadmap:**
- **Phase 1 (POC):** ✅ Single agent, 3-5 tickets, sequential (current)
- **Phase 2 (Specialists):** Coordinator + specialist agents (Solr, Prompt, Validator), improves iteration quality
- **Phase 3 (Parallel):** Add parallel ticket validation, scale to 10-15 tickets, 5-10x speedup
- **Phase 4 (Learning):** Cross-pattern learning, scale to 20+ tickets, learn from past successes

**Key Techniques:**
- **Multi-agent decomposition:** Baseline → Specialist → Validator → Aggregator (each fresh context)
- **Dynamic loading:** Agents read from `.diagnostics/` files instead of accumulating context
- **Parallel validation:** Validate N tickets simultaneously (N validators in background)
- **External storage:** Iteration history, pattern metadata stored externally (not in context)
- **Specialist agents:** SolrExpert (4K context), PromptExpert (4K), VarianceAnalyzer (3K)

**Benefits:**
- Context per agent stays ~3-5K tokens (vs single agent growing to 12K+)
- Parallel validation: 10 tickets in 60s instead of 600s
- Specialist expertise improves suggestion quality
- Cross-pattern learning reduces iterations needed

**Implementation Priority:** Medium (after POC proves concept)

### Variance Detection and Auto-Fix (Future Enhancement)

- [ ] **Add Variance-Aware Agent** - High Impact, Medium Effort
  - [ ] Implement `VarianceAnalyzer` class in `scripts/okp_mcp_variance_analyzer.py`
    - Analyze variance across multiple stability runs
    - Diagnose root cause (bad ground truth vs retrieval variance vs prompt ambiguity)
    - Suggest specific fixes based on diagnosis
  - [ ] Add variance analysis to pattern fix loop Phase 4
    - Currently: Calculates variance and reports if > 0.05
    - Enhancement: Auto-diagnose cause and suggest fix
  - [ ] Implement variance detection capabilities:
    - ✅ Compare responses for semantic similarity (bad ground truth detection)
    - ✅ Compare retrieved URLs for order variance (retrieval variance detection)
    - ✅ Detect response style variance (prompt ambiguity detection)
    - ✅ Apply appropriate fix based on diagnosis
  - [ ] See: `docs/VARIANCE_SOLUTIONS.md` for diagnostic framework
  - **Impact:** Agents can automatically detect and fix unstable answers
  - **Current State:** Agents can only see single-run metrics, cannot detect variance
  - **Priority:** Medium (useful but not critical for POC)

- [ ] **Add Semantic Answer Correctness (If High Variance)** - Medium Impact, Low Effort
  - [ ] Implement hybrid answer_correctness metric in `src/lightspeed_evaluation/core/metrics/custom/semantic_answer.py`
    - Use sentence transformers for semantic similarity (fast, deterministic, no wording bias)
    - Combine with LLM judge for borderline cases (semantic similarity 0.50-0.85)
    - Weighted scoring: `0.6 * llm_score + 0.4 * semantic_score`
  - [ ] Add to VarianceAnalyzer for detecting wording-based variance:
    - If semantic_similarity > 0.90 but answer_correctness variance > 0.02 → bad ground truth
    - Auto-generate more specific expected_response using LLM
  - [ ] Add configuration option to switch between:
    - `answer_correctness_mode: "llm"` (current, good for absolute scoring)
    - `answer_correctness_mode: "semantic"` (embedding-based, no wording bias)
    - `answer_correctness_mode: "hybrid"` (best of both)
  - **When to use:** If stability checks show high variance (>0.05) due to wording differences
  - **Benefits:** Reduces variance from semantically identical but differently worded answers
  - **Tradeoff:** Pure semantic similarity less precise on factual correctness
  - **Priority:** Low (only implement if variance becomes major issue)

## High Priority - RAG Testing Improvements for RHEL 10

### Do These First (This Week)

- [ ] **1. Add RHEL Version-Aware Metrics** (1 hour) - High Impact, Low Effort
  - [ ] Create `src/lightspeed_evaluation/core/metrics/custom/version_accuracy.py`
    - Validates RHEL version accuracy in contexts and responses
    - Checks if target version is in contexts
    - Detects wrong version in response
    - Calculates target version ratio in contexts
  - [ ] Add to `config/system.yaml` metrics_metadata
  - [ ] Set threshold to 0.8
  - **Impact:** Directly measures what we care about - are we retrieving the right version?

- [ ] **2. Create RHEL 10-Specific Test Suite** (2 hours) - High Impact, Medium Effort
  - [ ] Create `config/rhel10_focused_tests.yaml`
  - [ ] Include test categories:
    - New features (bootc, performance improvements)
    - Version-specific configuration
    - Migration and upgrade paths
    - Common administrative tasks
    - Troubleshooting scenarios
    - Package management (DNF5)
    - Security (SELinux)
  - **Impact:** Focused test coverage on primary use case

- [ ] **3. Add Version Markers to Test Data** (1 hour) - Medium Impact, Low Effort
  - [ ] Update all test YAML files with:
    - `target_version: "10"`
    - `version_strictness: "required|preferred|mixed"`
    - `expected_version_in_response: "10"`
    - `expected_version_in_contexts: ["10"]`
    - `forbidden_versions: ["8", "9"]`
  - [ ] Create validator in evaluation pipeline
  - **Impact:** Explicit pass/fail criteria for version correctness

### Do These Next (Next 2 Weeks)

- [ ] **4. Add Context Quality Metrics** (3 hours) - High Impact, Low Effort
  - [ ] Create `src/lightspeed_evaluation/core/metrics/custom/context_validation.py`
  - [ ] Implement `ContextVersionPurityMetric`
    - Measure percentage of contexts matching target version
  - [ ] Implement `ContextRecencyMetric`
    - Check if contexts are from recent documentation
    - Flag old documentation (>2 years)
  - **Impact:** Better understanding of WHY context_precision is only 42.9%
  - **Related:** Currently context_precision pass rate is 42.9%, need better validation

- [ ] **5. Create Regression Test Suite from Current Failures** (2 hours) - High Impact, Medium Effort
  - [ ] Create `scripts/create_regression_suite.py`
    - Extract questions with scores below 0.5
    - Group by conversation and track worst metrics
    - Generate `config/regression_tests.yaml`
  - [ ] Track these specific questions over time
  - **Impact:** Systematic tracking of problematic questions
  - **Note:** Use this after each major evaluation run to build regression dataset

- [ ] **6. Add Gemini 2.5 Flash-Specific Optimizations** (2 hours) - Medium Impact, Medium Effort
  - [ ] Create `config/gemini_optimized_system.yaml`
  - [ ] Configure Gemini-specific parameters:
    - `top_p: 0.95`
    - `top_k: 40`
    - Safety settings for technical documentation
  - [ ] Add structured prompt templates
    - System prompt emphasizing RHEL version awareness
    - Instruction to only use provided documentation
  - [ ] Use same model for judge LLM for consistency
  - **Impact:** Better alignment with Gemini's strengths

### Do Eventually (Longer Term)

- [ ] **7. Create Golden Dataset with Human Validation** - High Impact, High Effort
  - [ ] Select 20 critical RHEL 10 questions (most common user queries)
  - [ ] Manually validate/write perfect expected responses
  - [ ] Have RHEL experts review
  - [ ] Create `config/golden_rhel10_tests.yaml` with:
    - `quality_level: "gold"`
    - `expert_validated: true`
    - `validation_date` and `validator` fields
    - `gold_standard_response` (expert written)
    - `required_facts` (must-have information)
    - `forbidden_statements` (common misconceptions)
  - [ ] Use as high-confidence regression suite
  - **Impact:** High-confidence baseline for measuring improvements

- [ ] **8. Add Failure Mode Detection** (3 hours) - Medium Impact, Low Effort
  - [ ] Create `src/lightspeed_evaluation/core/metrics/custom/failure_modes.py`
  - [ ] Implement `FailureModeDetector` to catch:
    - Version hallucination (query version ≠ response version)
    - Empty/refusal responses
    - Context ignored (response contradicts context)
    - Over-generic responses
    - Wrong doc type (KB article instead of documentation)
  - **Impact:** Better root cause analysis of failures

- [ ] **9. Add Cost Tracking and Optimization** - Low Impact, Low Effort
  - [ ] Add cost tracking to evaluation pipeline:
    - Track API calls, input/output tokens
    - Calculate estimated cost using Gemini 2.5 Flash pricing
      - $0.075 per 1M input tokens
      - $0.30 per 1M output tokens
  - [ ] Add to evaluation output and summary reports
  - **Impact:** Better budget management for testing

- [ ] **10. Implement Continuous Testing Dashboard** - Low Impact, High Effort
  - [ ] Create `scripts/generate_dashboard_data.py`
  - [ ] Build web dashboard to track:
    - Pass rate trends by metric over time
    - Cost per successful evaluation
    - Common failure patterns
    - Version accuracy over time
    - Per-question performance
  - [ ] Host at `http://localhost:8000/dashboard`
  - **Impact:** Long-term visibility into testing trends

## Medium Priority

### 4. Implement New Ragas Metrics
Following specs created this week:

- [ ] **Context Quality Degradation Tests** (1-2 days)
  - [ ] Create baseline test selection script
  - [ ] Implement degradation generators (partial removal, noise injection, shuffle)
  - [ ] Generate test configuration
  - [ ] Run tests and analyze
  - See: `docs/CONTEXT_QUALITY_DEGRADATION_TESTS.md`

- [ ] **Adversarial Context Injection Tests** (2-3 days)
  - [ ] Manually create test cases for version conflicts
  - [ ] Implement custom metrics:
    - [ ] `custom:context_source_selection`
    - [ ] `custom:authority_preference_score`
    - [ ] `custom:temporal_awareness_score`
  - [ ] Run security testing
  - [ ] Generate security scorecard
  - See: `docs/ADVERSARIAL_CONTEXT_INJECTION_TESTS.md`

- [ ] **Judge LLM Consistency Tests** (1 day)
  - [ ] Implement consistency test runner
  - [ ] Implement statistical analysis (Cohen's Kappa, correlation)
  - [ ] Run tests with multiple judge models
  - See: `docs/JUDGE_LLM_CONSISTENCY_TESTS.md`

### 5. Refactor Scripts Directory
- [ ] Consolidate cost estimation scripts
  - Consider merging `calculate_cost_estimate.py` and `calculate_cost_estimate_multi.py`
  - Or keep separate but add clear README
- [ ] Document all scripts in `scripts/README.md`
  - Add examples for each script
  - Document expected inputs/outputs
- [ ] Remove obsolete/one-off analysis scripts
  - Review each script for continued usefulness
  - Archive or delete unused scripts

## Low Priority

### 6. Documentation Updates
- [ ] Update main `README.md`
  - Add cost estimation section
  - Link to new testing specs
  - Update with recent capabilities
- [ ] Update `AGENTS.md`
  - Add conventions from recent work
  - Document analysis workflow
  - Add cost estimation guidelines
- [ ] Create `docs/TESTING_GUIDE.md`
  - Overview of all testing approaches
  - When to use each type (degradation vs adversarial vs consistency)
  - Cost/effort estimates

### 7. Test Framework Improvements
- [ ] Add cost tracking to evaluation runs
  - Store token usage in summary reports
  - Auto-generate cost estimates in output
- [ ] Improve error handling
  - Better messages for malformed output errors
  - Log actual LLM judge output for debugging
- [ ] Add progress indicators
  - Show estimated time remaining
  - Display cost-to-date during long runs

## Completed This Week ✅

- [x] Investigate ragas:faithfulness malformed output errors (13/1141 questions, 1.14%)
- [x] Implement cross-metric correlation analysis
- [x] Analyze ragas:faithfulness threshold calibration issues
- [x] Design temporal context validity tests
- [x] Design judge LLM consistency comparison tests
- [x] Create okp-mcp improvement ticket (RSPEED-2714 - hugepages)
- [x] Design context quality degradation test suite
- [x] Design adversarial context injection tests
- [x] Create cost estimation scripts
  - [x] `scripts/calculate_cost_estimate.py`
  - [x] `scripts/calculate_cost_estimate_multi.py`

## Expected Impact from RAG Testing Improvements

With items 1-6 implemented:
- **Better visibility** into version correctness (currently blind spot)
- **Higher confidence** in test results (know WHY things fail)
- **Faster debugging** of failures (failure mode detection)
- **Lower costs** from focused testing (RHEL 10 specific suite)
- **60% → 75%+ pass rate** expected on RHEL 10 temporal questions
- **Reduced variance** in results (better test data quality)

### Current Baseline (from version filtering analysis)
- Temporal test pass rate: 60% (was 40% before version filtering)
- Context precision: 42.9% pass rate (needs improvement)
- Faithfulness: 42.9% pass rate (was 14.3% before filtering)
- Version accuracy: Not currently measured (Item #1 will add this)

## Notes

### Testing Philosophy
This week we got carried away with investigation and report generation. Going forward:
- **Focus on test system itself**, not individual test results
- **Keep output files local** - don't commit to git
- **Document patterns**, not every anomaly
- **Automate analysis** where possible

### File Management Strategy
- **Keep in Git:**
  - Source code (`src/`, `tests/`)
  - Configuration templates (`config/*.yaml.example`)
  - Specifications and guides (`docs/*.md`)
  - Scripts (`scripts/*.py`)
  - Core documentation (`README.md`, `AGENTS.md`)

- **Keep Local Only (gitignore):**
  - Evaluation outputs (`eval_output/`)
  - Generated reports (`analysis_output/*.csv`, `*.png`)
  - Test data (large YAML files with actual test cases)
  - Cache directories

- **Archive Externally:**
  - Completed investigation reports (move to separate repo or storage)
  - Historical evaluation results (for long-term analysis)

### Cost Optimization
Current cost with Gemini 2.5 Flash:
- ~$0.0075 per question (judge only)
- ~$0.38 for 51 questions
- Estimated ~$8.50 for full 1,141 question suite

Keep using Gemini Flash models for cost-effectiveness unless quality issues arise.

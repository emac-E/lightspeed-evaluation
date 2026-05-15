# TODO

## High Priority

### [Done]1. Fix Token Usage Tracking
- [x] Pull token info from endpoint response (Gemini model answering questions)
  - Currently showing 0 tokens for `api_input_tokens` and `api_output_tokens`
  - Need to extract from response object and store in evaluation results
  - Affects accurate cost estimation
- [x] Re-run cost estimation script after fix
  ```bash
  $ python scripts/show_cost.py

  ```
  [] Fix existing bugs caused by claude

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

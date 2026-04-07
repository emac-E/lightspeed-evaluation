#!/bin/bash
#
# Master Evaluation Script - Run All Tests and Analysis
#
# This script:
# 1. Runs ALL evaluation test configs
# 2. Runs correlation analysis on outputs
# 3. Runs version distribution analysis on temporal tests
# 4. Generates comprehensive RAG quality report for okp-mcp developers
#
# Usage:
#   ./run_full_evaluation_suite.sh              # Normal mode (fresh queries)
#   ./run_full_evaluation_suite.sh --debug-test # Debug mode (reuse cached data)
#

set -e  # Exit on error

# Parse arguments
DEBUG_TEST=false
for arg in "$@"; do
    case $arg in
        --debug-test)
            DEBUG_TEST=true
            shift
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--debug-test]"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_BASE="${BASE_DIR}/eval_output/full_suite_${TIMESTAMP}"
ANALYSIS_OUTPUT="${BASE_DIR}/analysis_output/full_suite_${TIMESTAMP}"

# Track runtime
START_TIME=$(date +%s)

# Create output directories
mkdir -p "${OUTPUT_BASE}"
mkdir -p "${ANALYSIS_OUTPUT}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Full Evaluation Suite Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Mode: $([ "$DEBUG_TEST" = true ] && echo "${YELLOW}DEBUG (reusing cached data)${NC}" || echo "${GREEN}NORMAL (fresh queries)${NC}")"
echo -e "Timestamp: ${TIMESTAMP}"
echo -e "Output directory: ${OUTPUT_BASE}"
echo -e "Analysis directory: ${ANALYSIS_OUTPUT}"
echo ""

# Define test configs to run
# Excluded: evaluation_data.yaml, evaluation_data_multiple_expected_responses.yaml, multi_eval_config.yaml
TEST_CONFIGS=(
    "config/jira_incorrect_answers.yaml"
    "config/brian_tests.yaml"
    "config/rhel10_documentation.yaml"
    "config/rhel10_features.yaml"
    "config/temporal_validity_tests_runnable.yaml"
)

# Track which evals succeeded
SUCCESSFUL_EVALS=()
FAILED_EVALS=()

if [ "$DEBUG_TEST" = false ]; then
    echo -e "${GREEN}Step 0: Cache warmup - Clearing ALL caches before suite...${NC}"
    echo ""
    # Clear all caches once at the start to ensure fresh API/MCP data
    rm -rf .caches/*
    mkdir -p .caches/llm_cache
    mkdir -p .caches/api_cache
    mkdir -p .caches/embedding_cache
    echo -e "${GREEN}✓ All caches cleared - fresh data will be fetched${NC}"
    echo ""
else
    echo -e "${YELLOW}Step 0: Debug mode - Reusing existing cached data...${NC}"
    echo ""
    # Ensure cache directories exist but don't clear them
    mkdir -p .caches/llm_cache
    mkdir -p .caches/api_cache
    mkdir -p .caches/embedding_cache
    echo -e "${YELLOW}✓ Cache directories ready - will reuse cached responses${NC}"
    echo ""
fi

echo -e "${GREEN}Step 1: Running all evaluation configs...${NC}"
echo ""

for i in "${!TEST_CONFIGS[@]}"; do
    config="${TEST_CONFIGS[$i]}"
    config_name=$(basename "${config}" .yaml)
    output_dir="${OUTPUT_BASE}/${config_name}"

    echo -e "${YELLOW}Running: ${config}${NC}"

    # Clear ONLY LLM judge cache between test configs (after first run)
    # This ensures fresh evaluations but reuses API responses for consistent data
    # SKIP in debug mode to reuse judge evaluations too
    if [ "$DEBUG_TEST" = false ] && [ $i -gt 0 ]; then
        echo -e "${BLUE}  Clearing LLM judge cache for fresh evaluations...${NC}"
        rm -rf .caches/llm_cache/*
        mkdir -p .caches/llm_cache
    elif [ "$DEBUG_TEST" = true ] && [ $i -gt 0 ]; then
        echo -e "${BLUE}  Debug mode: Reusing LLM judge cache...${NC}"
    fi

    if uv run lightspeed-eval \
        --system-config config/system.yaml \
        --eval-data "${config}" \
        --output-dir "${output_dir}"; then

        echo -e "${GREEN}✓ Success: ${config_name}${NC}"
        SUCCESSFUL_EVALS+=("${config_name}")
    else
        echo -e "${RED}✗ Failed: ${config_name}${NC}"
        FAILED_EVALS+=("${config_name}")
    fi
    echo ""
done

echo -e "${GREEN}Step 2: Running correlation analysis on all outputs...${NC}"
echo ""

# Find all detailed CSV files from successful evals
DETAILED_CSVS=$(find "${OUTPUT_BASE}" -name "evaluation_*_detailed.csv" 2>/dev/null | tr '\n' ' ')
CORRELATION_ANALYSIS_RAN=false

if [ -n "$DETAILED_CSVS" ]; then
    echo -e "${YELLOW}Analyzing metrics from all evaluation runs...${NC}"

    if uv run python scripts/analyze_metric_correlations.py \
        --input ${DETAILED_CSVS} \
        --output "${ANALYSIS_OUTPUT}/correlation_analysis" \
        --compare-runs; then

        echo -e "${GREEN}✓ Correlation analysis complete${NC}"
        CORRELATION_ANALYSIS_RAN=true
    else
        echo -e "${RED}✗ Correlation analysis failed${NC}"
    fi
else
    echo -e "${RED}✗ No evaluation outputs found for correlation analysis${NC}"
fi
echo ""

echo -e "${GREEN}Step 3: Running version distribution analysis on temporal tests...${NC}"
echo ""

# Find temporal test output
TEMPORAL_CSV=$(find "${OUTPUT_BASE}/temporal_validity_tests_runnable" -name "evaluation_*_detailed.csv" 2>/dev/null | head -1)
VERSION_ANALYSIS_RAN=false

if [ -n "$TEMPORAL_CSV" ]; then
    echo -e "${YELLOW}Analyzing RHEL version distribution...${NC}"

    if uv run python scripts/analyze_version_distribution.py \
        --input "${TEMPORAL_CSV}" \
        --test-config config/temporal_validity_tests_runnable.yaml \
        --output "${ANALYSIS_OUTPUT}/version_analysis"; then

        echo -e "${GREEN}✓ Version distribution analysis complete${NC}"
        VERSION_ANALYSIS_RAN=true
    else
        echo -e "${RED}✗ Version distribution analysis failed${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Temporal test output not found, skipping version analysis${NC}"
fi
echo ""

echo -e "${GREEN}Step 4: Generating RAG Quality Report for okp-mcp developers...${NC}"
echo ""

# Calculate runtime
CURRENT_TIME=$(date +%s)
RUNTIME_SECONDS=$((CURRENT_TIME - START_TIME))

# Build command with optional analysis directories
REPORT_CMD="uv run python scripts/generate_okp_mcp_report.py --output-base \"${OUTPUT_BASE}\" --runtime-seconds ${RUNTIME_SECONDS}"

if [ "$CORRELATION_ANALYSIS_RAN" = true ]; then
    REPORT_CMD="$REPORT_CMD --correlation-analysis \"${ANALYSIS_OUTPUT}/correlation_analysis\""
fi

if [ "$VERSION_ANALYSIS_RAN" = true ]; then
    REPORT_CMD="$REPORT_CMD --version-analysis \"${ANALYSIS_OUTPUT}/version_analysis\""
fi

# Generate report
eval $REPORT_CMD

echo ""

echo -e "${GREEN}Step 5: Generating Question-Level Metrics Report...${NC}"
echo ""

# Generate detailed per-question report
if [ -n "$DETAILED_CSVS" ]; then
    echo -e "${YELLOW}Creating question-level metrics breakdown...${NC}"

    uv run python scripts/generate_question_metrics_report.py \
        --input ${DETAILED_CSVS} \
        --output "${OUTPUT_BASE}/QUESTION_METRICS_REPORT.md"

    echo -e "${GREEN}✓ Question metrics report complete${NC}"
else
    echo -e "${YELLOW}⚠ No evaluation outputs found for question report${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Successful evaluations: ${#SUCCESSFUL_EVALS[@]}"
for eval in "${SUCCESSFUL_EVALS[@]}"; do
    echo -e "  ${GREEN}✓${NC} ${eval}"
done
echo ""

if [ ${#FAILED_EVALS[@]} -gt 0 ]; then
    echo -e "Failed evaluations: ${#FAILED_EVALS[@]}"
    for eval in "${FAILED_EVALS[@]}"; do
        echo -e "  ${RED}✗${NC} ${eval}"
    done
    echo ""
fi

RAG_REPORT="${OUTPUT_BASE}/RAG_QUALITY_REPORT_FOR_OKP_MCP.md"
QUESTION_REPORT="${OUTPUT_BASE}/QUESTION_METRICS_REPORT.md"

echo -e "${GREEN}All outputs saved to:${NC} ${OUTPUT_BASE}"
echo -e "${GREEN}Analysis saved to:${NC} ${ANALYSIS_OUTPUT}"
if [ "$DEBUG_TEST" = true ]; then
    echo -e "${YELLOW}⚠ Debug mode: Results based on CACHED data (no new LLM queries)${NC}"
fi
echo -e "${GREEN}Reports generated:${NC}"
echo -e "  - RAG Quality Report: ${RAG_REPORT}"
echo -e "  - Question Metrics Report: ${QUESTION_REPORT}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. Read the RAG quality report (for okp-mcp team):"
echo -e "     ${YELLOW}cat ${RAG_REPORT}${NC}"
echo -e ""
echo -e "  2. Review question-level metrics (detailed breakdown):"
echo -e "     ${YELLOW}cat ${QUESTION_REPORT}${NC}"
echo -e ""
echo -e "  3. Review correlation analysis:"
echo -e "     ${YELLOW}cat ${ANALYSIS_OUTPUT}/correlation_analysis/summary_report.txt${NC}"
echo -e ""
echo -e "  3. Check visualizations:"
echo -e "     ${YELLOW}ls ${ANALYSIS_OUTPUT}/correlation_analysis/*.png${NC}"
echo -e ""
echo -e "  4. Review version analysis (if available):"
echo -e "     ${YELLOW}cat ${ANALYSIS_OUTPUT}/version_analysis/version_distribution_report.txt${NC}"
echo -e ""
echo -e "  5. Share report with okp-mcp team"
echo ""
echo -e "${GREEN}Done!${NC}"

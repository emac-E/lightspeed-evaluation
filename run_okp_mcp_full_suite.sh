#!/bin/bash
#
# OKP-MCP Full Evaluation Suite - Complete End-to-End Testing
#
# This script:
# 1. Runs full inference evaluation N times (with LLM responses)
# 2. Collects metrics for retrieval quality AND answer correctness
# 3. Generates heatmaps showing questions vs metrics across runs
#
# Usage:
#   ./run_okp_mcp_full_suite.sh                        # Run 3 times (default)
#   ./run_okp_mcp_full_suite.sh --runs 5               # Run 5 times
#   ./run_okp_mcp_full_suite.sh --config okp_mcp_agent/config/test_suites/functional_tests_full.yaml
#

set -e  # Exit on error

# Default configuration
NUM_RUNS=3
EVAL_CONFIG="okp_mcp_agent/config/test_suites/functional_tests_full.yaml"
SYSTEM_CONFIG="config/system_okp_mcp_agent.yaml"
METRICS=""  # Optional metrics filter

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --runs)
            NUM_RUNS="$2"
            shift 2
            ;;
        --config)
            EVAL_CONFIG="$2"
            shift 2
            ;;
        --system-config)
            SYSTEM_CONFIG="$2"
            shift 2
            ;;
        --metrics)
            METRICS="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --runs N                 Number of runs (default: 3)"
            echo "  --config FILE            Evaluation config (default: okp_mcp_agent/config/test_suites/functional_tests_full.yaml)"
            echo "  --system-config FILE     System config (default: config/system_okp_mcp_agent.yaml)"
            echo "  --metrics METRICS        Filter to specific metrics (e.g., 'custom:answer_correctness ragas:faithfulness')"
            echo "  --help                   Show this help"
            echo ""
            echo "Example:"
            echo "  $0 --runs 5 --config okp_mcp_agent/config/test_suites/functional_tests_full.yaml"
            echo "  $0 --metrics 'custom:answer_correctness' --runs 3"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Use --help for usage information"
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
BASE_DIR="$(pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_BASE="${BASE_DIR}/okp_mcp_full_output/suite_${TIMESTAMP}"
CONFIG_NAME=$(basename "${EVAL_CONFIG}" .yaml)

# Create output directories
mkdir -p "${OUTPUT_BASE}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}OKP-MCP Full Evaluation Suite${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Runs: ${NUM_RUNS}"
echo -e "Evaluation config: ${EVAL_CONFIG}"
echo -e "System config: ${SYSTEM_CONFIG}"
echo -e "Output directory: ${OUTPUT_BASE}"
echo ""

# Validate configs
if [ ! -f "${EVAL_CONFIG}" ]; then
    echo -e "${RED}Error: Evaluation config not found: ${EVAL_CONFIG}${NC}"
    exit 1
fi

if [ ! -f "${SYSTEM_CONFIG}" ]; then
    echo -e "${RED}Error: System config not found: ${SYSTEM_CONFIG}${NC}"
    exit 1
fi

# Check if okp-mcp is running
echo -e "${YELLOW}Checking okp-mcp status...${NC}"
if ! curl -s http://localhost:8001/mcp > /dev/null 2>&1; then
    echo -e "${RED}Error: okp-mcp not responding on http://localhost:8001${NC}"
    echo -e "${YELLOW}Start it with: cd ~/Work/lscore-deploy/local && podman-compose up -d okp-mcp${NC}"
    exit 1
fi
echo -e "${GREEN}✓ okp-mcp is running${NC}"
echo ""

# Track successful runs
SUCCESSFUL_RUNS=0
FAILED_RUNS=0

echo -e "${GREEN}Running full evaluations with LLM responses (${NUM_RUNS} runs)...${NC}"
echo ""

for run in $(seq 1 ${NUM_RUNS}); do
    RUN_DIR="${OUTPUT_BASE}/run_$(printf "%03d" ${run})"
    mkdir -p "${RUN_DIR}"

    echo -e "${YELLOW}[Run ${run}/${NUM_RUNS}] Starting evaluation...${NC}"

    # Clear API cache between runs to get fresh responses
    echo -e "${BLUE}  Clearing API cache...${NC}"
    rm -rf .caches/api_cache/*
    mkdir -p .caches/api_cache

    # Clear LLM judge cache too (for Ragas metrics)
    rm -rf .caches/llm_cache/*
    mkdir -p .caches/llm_cache

    # Run evaluation
    METRICS_ARGS=""
    if [ -n "${METRICS}" ]; then
        METRICS_ARGS="--metrics ${METRICS}"
    fi

    if uv run lightspeed-eval \
        --system-config "${SYSTEM_CONFIG}" \
        --eval-data "${EVAL_CONFIG}" \
        --output-dir "${RUN_DIR}" \
        ${METRICS_ARGS} 2>&1 | tee "${RUN_DIR}/eval.log"; then

        echo -e "${GREEN}✓ Run ${run} complete${NC}"
        SUCCESSFUL_RUNS=$((SUCCESSFUL_RUNS + 1))

        # Copy detailed CSV to consistent naming for heatmap generation
        DETAILED_CSV=$(find "${RUN_DIR}" -name "evaluation_*_detailed.csv" | head -1)
        if [ -n "${DETAILED_CSV}" ]; then
            cp "${DETAILED_CSV}" "${OUTPUT_BASE}/run_$(printf "%03d" ${run}).csv"
        fi
    else
        echo -e "${RED}✗ Run ${run} failed${NC}"
        FAILED_RUNS=$((FAILED_RUNS + 1))
    fi

    echo ""
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Generating Heatmap${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Find all CSV files
CSV_FILES=$(find "${OUTPUT_BASE}" -name "run_*.csv" | sort)
CSV_COUNT=$(echo "${CSV_FILES}" | wc -l)

if [ ${CSV_COUNT} -lt 1 ]; then
    echo -e "${RED}Error: No CSV files found for heatmap generation${NC}"
    exit 1
fi

echo -e "${YELLOW}Found ${CSV_COUNT} evaluation runs${NC}"
echo -e "${YELLOW}Generating question vs metrics heatmap...${NC}"

# Generate heatmap using plot_stability.py
if uv run python scripts/plot_stability.py \
    --input-dir "${OUTPUT_BASE}" \
    --output-dir "${OUTPUT_BASE}/analysis"; then

    echo -e "${GREEN}✓ Heatmap generated${NC}"
else
    echo -e "${RED}✗ Heatmap generation failed${NC}"
fi

echo ""

# Generate summary statistics
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Total runs: ${NUM_RUNS}"
echo -e "Successful: ${GREEN}${SUCCESSFUL_RUNS}${NC}"
echo -e "Failed: ${RED}${FAILED_RUNS}${NC}"
echo ""
echo -e "Metrics evaluated (full suite):"
echo -e "  • custom:url_retrieval_eval (F1, MRR, ranking)"
echo -e "  • custom:keywords_eval (required facts)"
echo -e "  • custom:forbidden_claims_eval (regression detection)"
echo -e "  • ragas:context_precision_without_reference"
echo -e "  • ragas:context_relevance"
echo ""
echo -e "${GREEN}Output directory:${NC} ${OUTPUT_BASE}"
echo ""
echo -e "${GREEN}Generated files:${NC}"
if [ -d "${OUTPUT_BASE}/analysis" ]; then
    echo -e "  • Heatmap: ${OUTPUT_BASE}/analysis/*.png"
    echo -e "  • Metrics: ${OUTPUT_BASE}/run_*.csv"
fi
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. View heatmap:"
echo -e "     ${YELLOW}ls ${OUTPUT_BASE}/analysis/*.png${NC}"
echo ""
echo -e "  2. View detailed results:"
echo -e "     ${YELLOW}cat ${OUTPUT_BASE}/run_001/evaluation_*_summary.txt${NC}"
echo ""
echo -e "  3. Analyze URL retrieval stability:"
echo -e "     ${YELLOW}python scripts/analyze_url_retrieval_stability.py \\"
echo -e "       --input ${OUTPUT_BASE}/run_*/evaluation_*_detailed.csv \\"
echo -e "       --output ${OUTPUT_BASE}/url_stability${NC}"
echo ""
echo -e "  4. Compare with retrieval-only baseline:"
echo -e "     ${YELLOW}python scripts/compare_runs.py \\"
echo -e "       mcp_retrieval_output/suite_*/run_001.csv \\"
echo -e "       ${OUTPUT_BASE}/run_001.csv${NC}"
echo ""
echo -e "${GREEN}Done!${NC}"

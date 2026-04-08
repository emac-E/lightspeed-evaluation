#!/bin/bash
# Test the complete pattern-based fixing workflow
#
# This demonstrates:
# 1. Bootstrap: Extract tickets + discover patterns
# 2. Pattern analysis: List and review patterns
# 3. Pattern fixing: Fix entire pattern (all tickets at once)
# 4. Branching: Commits stacked on pattern branch (not main)
#
# Usage:
#   bash scripts/test_pattern_workflow.sh [--limit N]

set -e  # Exit on error

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Parse args
LIMIT=10  # Default: extract 10 tickets for testing
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--limit N] [--dry-run]"
            exit 1
            ;;
    esac
done

echo "================================================================================"
echo "PATTERN-BASED FIXING WORKFLOW TEST"
echo "================================================================================"
echo "Testing: Bootstrap → Pattern Discovery → Pattern-Based Fixing"
echo "Limit: ${LIMIT} tickets"
echo "Dry run: ${DRY_RUN}"
echo ""

# Create test output directory
TEST_OUTPUT="/tmp/pattern_workflow_test_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$TEST_OUTPUT"
echo "Test output: $TEST_OUTPUT"
echo ""

# ==============================================================================
# STAGE 1: BOOTSTRAP - Extract JIRA Tickets
# ==============================================================================

echo "================================================================================"
echo "STAGE 1: BOOTSTRAP - Extract JIRA Tickets"
echo "================================================================================"
echo ""
echo "Multi-agent verification (Linux Expert + Solr Expert)"
echo "Creates verified query/answer pairs with search intelligence"
echo ""

EXTRACTED_YAML="$TEST_OUTPUT/extracted_tickets.yaml"

if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would run: extract_jira_tickets.py --limit $LIMIT"
    # Create fake data for testing
    cat > "$EXTRACTED_YAML" << 'EOF'
metadata:
  generated_at: '2026-04-07T20:00:00'
  total_tickets: 5
tickets:
  - ticket_key: RSPEED-2482
    query: Can I run a RHEL 6 container on RHEL 9?
    pattern_id: null
  - ticket_key: RSPEED-2511
    query: Can I run a RHEL 7 container on RHEL 10?
    pattern_id: null
  - ticket_key: RSPEED-2520
    query: What is the minimum RHEL version for containers on RHEL 9?
    pattern_id: null
  - ticket_key: RSPEED-1234
    query: When does RHEL 7 reach EOL?
    pattern_id: null
  - ticket_key: RSPEED-1235
    query: When does RHEL 8 reach EOL?
    pattern_id: null
EOF
else
    uv run python scripts/extract_jira_tickets.py \
        --limit "$LIMIT" \
        --output "$EXTRACTED_YAML"
fi

if [ ! -f "$EXTRACTED_YAML" ]; then
    echo "❌ FAILED: Extraction did not create output YAML"
    exit 1
fi

TICKET_COUNT=$(grep -c "^  - ticket_key:" "$EXTRACTED_YAML" || echo "0")
echo ""
echo "✅ Stage 1 Complete: Extracted $TICKET_COUNT tickets"
echo ""

# ==============================================================================
# STAGE 2: BOOTSTRAP - Pattern Discovery
# ==============================================================================

echo "================================================================================"
echo "STAGE 2: BOOTSTRAP - Pattern Discovery"
echo "================================================================================"
echo ""
echo "Clusters tickets by: problem type, components, RHEL versions"
echo "Enables fixing 15 similar tickets as 1 pattern (15x efficiency)"
echo ""

if [ "$TICKET_COUNT" -lt 3 ]; then
    echo "⚠️  Only $TICKET_COUNT tickets extracted - need at least 3 for pattern discovery"
    echo "   Run with: --limit 10"
    exit 1
fi

TAGGED_YAML="$TEST_OUTPUT/tickets_with_patterns.yaml"
PATTERN_REPORT="$TEST_OUTPUT/patterns_report.json"

if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would run: discover_ticket_patterns.py"
    # Create fake pattern data
    cat > "$PATTERN_REPORT" << 'EOF'
{
  "generated_at": "2026-04-07T20:00:00",
  "summary": {
    "total_tickets": 5,
    "patterns_found": 2,
    "tickets_grouped": 5,
    "tickets_ungrouped": 0
  },
  "patterns": [
    {
      "pattern_id": "EOL_CONTAINER_COMPATIBILITY",
      "description": "RHEL 6/7 containers unsupported on RHEL 9/10 hosts",
      "ticket_count": 3,
      "representative_tickets": ["RSPEED-2482", "RSPEED-2511"],
      "matched_tickets": ["RSPEED-2482", "RSPEED-2511", "RSPEED-2520"],
      "common_problem_type": "EOL_UNSUPPORTED",
      "common_components": ["containers"],
      "version_pattern": ">2 major versions",
      "verification_queries": [
        {"query": "RHEL container compatibility", "context": "version support"}
      ]
    },
    {
      "pattern_id": "RHEL_EOL_DATES",
      "description": "Questions about RHEL version EOL dates",
      "ticket_count": 2,
      "representative_tickets": ["RSPEED-1234"],
      "matched_tickets": ["RSPEED-1234", "RSPEED-1235"],
      "common_problem_type": "EOL_UNSUPPORTED",
      "common_components": ["lifecycle"],
      "version_pattern": "RHEL 7/8",
      "verification_queries": [
        {"query": "RHEL EOL dates", "context": "lifecycle"}
      ]
    }
  ]
}
EOF
    cp "$EXTRACTED_YAML" "$TAGGED_YAML"
    # Add pattern IDs to tickets
    sed -i 's/pattern_id: null/pattern_id: EOL_CONTAINER_COMPATIBILITY/' "$TAGGED_YAML" || true
else
    uv run python scripts/discover_ticket_patterns.py \
        --input "$EXTRACTED_YAML" \
        --output-tagged "$TAGGED_YAML" \
        --output-report "$PATTERN_REPORT" \
        --min-pattern-size 2
fi

if [ ! -f "$PATTERN_REPORT" ]; then
    echo "❌ FAILED: Pattern discovery did not create report"
    exit 1
fi

PATTERN_COUNT=$(jq '.patterns | length' "$PATTERN_REPORT" 2>/dev/null || echo "0")
echo ""
echo "✅ Stage 2 Complete: Discovered $PATTERN_COUNT patterns"
echo ""

# Copy to repo root for pattern agent to find
cp "$PATTERN_REPORT" "$REPO_ROOT/patterns_report.json"
cp "$TAGGED_YAML" "$REPO_ROOT/config/tickets_with_patterns.yaml"

# ==============================================================================
# STAGE 3: PATTERN ANALYSIS
# ==============================================================================

echo "================================================================================"
echo "STAGE 3: PATTERN ANALYSIS"
echo "================================================================================"
echo ""

# List all patterns
echo "📋 Listing all patterns:"
echo ""
uv run python scripts/okp_mcp_pattern_agent.py list-patterns

# Show details of first pattern
FIRST_PATTERN=$(jq -r '.patterns[0].pattern_id' "$PATTERN_REPORT" 2>/dev/null || echo "")

if [ -n "$FIRST_PATTERN" ]; then
    echo ""
    echo "📊 Showing details for: $FIRST_PATTERN"
    echo ""
    uv run python scripts/okp_mcp_pattern_agent.py show-pattern "$FIRST_PATTERN"
fi

# ==============================================================================
# STAGE 4: PATTERN FIXING (PREVIEW)
# ==============================================================================

echo "================================================================================"
echo "STAGE 4: PATTERN FIXING (PREVIEW)"
echo "================================================================================"
echo ""
echo "This would:"
echo "  1. Create branch: fix/pattern-${FIRST_PATTERN,,}"
echo "  2. Iterate to fix ALL tickets in pattern (not one-by-one)"
echo "  3. Stack commits on pattern branch"
echo "  4. Pass only when ALL tickets pass (or >80% with --threshold 0.8)"
echo ""

if [ -n "$FIRST_PATTERN" ]; then
    echo "To fix this pattern, run:"
    echo ""
    echo "  uv run python scripts/okp_mcp_pattern_agent.py fix-pattern $FIRST_PATTERN \\"
    echo "    --max-iterations 10 \\"
    echo "    --threshold 0.8"
    echo ""
    echo "Or validate current state:"
    echo ""
    echo "  uv run python scripts/okp_mcp_pattern_agent.py validate-pattern $FIRST_PATTERN"
    echo ""
fi

# ==============================================================================
# SUMMARY
# ==============================================================================

echo "================================================================================"
echo "WORKFLOW SUMMARY"
echo "================================================================================"
echo ""
echo "✅ Bootstrap complete:"
echo "   - Extracted tickets: $TICKET_COUNT"
echo "   - Patterns discovered: $PATTERN_COUNT"
echo "   - Knowledge artifacts created"
echo ""

if [ "$PATTERN_COUNT" -gt 0 ]; then
    echo "📊 Pattern efficiency vs single-ticket:"
    jq -r '.patterns[] | "   - \(.pattern_id): \(.ticket_count) tickets → 1 fix (saves \(.ticket_count - 1) iterations)"' "$PATTERN_REPORT" 2>/dev/null || true
    echo ""
fi

echo "🌲 Branching strategy:"
echo "   - Each pattern gets its own branch: fix/pattern-<pattern-id>"
echo "   - Commits stack on pattern branch (not main)"
echo "   - Merge to main after pattern validated"
echo ""

echo "📁 Created files:"
echo "   - $PATTERN_REPORT"
echo "   - $TAGGED_YAML"
echo "   - $REPO_ROOT/patterns_report.json (copied for pattern agent)"
echo "   - $REPO_ROOT/config/tickets_with_patterns.yaml (copied for pattern agent)"
echo ""

echo "🚀 Next steps:"
echo "   1. Review patterns: cat $PATTERN_REPORT | jq '.patterns'"
echo "   2. Fix a pattern: uv run python scripts/okp_mcp_pattern_agent.py fix-pattern <PATTERN_ID>"
echo "   3. Validate pattern: uv run python scripts/okp_mcp_pattern_agent.py validate-pattern <PATTERN_ID>"
echo ""

echo "================================================================================"
echo "TEST OUTPUT: $TEST_OUTPUT"
echo "================================================================================"

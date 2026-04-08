#!/bin/bash
# Test the complete bootstrap → coding agent workflow
#
# Usage:
#   bash scripts/test_bootstrap_workflow.sh [--limit N]
#
# This tests:
# 1. Bootstrap Step: Extract tickets + discover patterns
# 2. Knowledge artifacts created
# 3. Ready for coding agent to consume

set -e  # Exit on error

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Parse args
LIMIT=5  # Default: extract 5 tickets for testing
while [[ $# -gt 0 ]]; do
    case $1 in
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--limit N]"
            exit 1
            ;;
    esac
done

echo "================================================================================"
echo "BOOTSTRAP WORKFLOW TEST"
echo "================================================================================"
echo "Testing: Extract → Pattern Discovery → Knowledge Artifacts"
echo "Limit: ${LIMIT} tickets"
echo ""

# Create test output directory
TEST_OUTPUT="/tmp/bootstrap_test_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$TEST_OUTPUT"
echo "Test output: $TEST_OUTPUT"
echo ""

# Stage 1: Extract tickets with multi-agent verification
echo "================================================================================"
echo "STAGE 1: Extract JIRA Tickets (Multi-Agent Verification)"
echo "================================================================================"
echo ""

EXTRACTED_YAML="$TEST_OUTPUT/extracted_tickets.yaml"

uv run python scripts/extract_jira_tickets.py \
    --limit "$LIMIT" \
    --output "$EXTRACTED_YAML"

if [ ! -f "$EXTRACTED_YAML" ]; then
    echo "❌ FAILED: Extraction did not create output YAML"
    exit 1
fi

# Check what we extracted
TICKET_COUNT=$(grep -c "^  - ticket_key:" "$EXTRACTED_YAML" || echo "0")
echo ""
echo "✅ Stage 1 Complete: Extracted $TICKET_COUNT tickets"
echo ""

# Stage 2: Discover patterns
echo "================================================================================"
echo "STAGE 2: Pattern Discovery"
echo "================================================================================"
echo ""

if [ "$TICKET_COUNT" -lt 3 ]; then
    echo "⚠️  Only $TICKET_COUNT tickets extracted - need at least 3 for pattern discovery"
    echo "   Skipping pattern discovery (requires --min-pattern-size=3)"
else
    TAGGED_YAML="$TEST_OUTPUT/tickets_with_patterns.yaml"
    PATTERN_REPORT="$TEST_OUTPUT/patterns_report.json"

    uv run python scripts/discover_ticket_patterns.py \
        --input "$EXTRACTED_YAML" \
        --output-tagged "$TAGGED_YAML" \
        --output-report "$PATTERN_REPORT" \
        --min-pattern-size 2  # Lower threshold for testing

    if [ -f "$PATTERN_REPORT" ]; then
        PATTERN_COUNT=$(jq '.patterns | length' "$PATTERN_REPORT" 2>/dev/null || echo "0")
        echo ""
        echo "✅ Stage 2 Complete: Discovered $PATTERN_COUNT patterns"
        echo ""
    else
        echo "⚠️  No patterns discovered (may need more diverse tickets)"
        echo ""
    fi
fi

# Stage 3: Verify knowledge artifacts
echo "================================================================================"
echo "STAGE 3: Knowledge Artifacts Verification"
echo "================================================================================"
echo ""

echo "📦 Created Artifacts:"
echo ""

# 1. Extracted tickets YAML
if [ -f "$EXTRACTED_YAML" ]; then
    echo "✅ extracted_tickets.yaml"
    echo "   - Verified query/answer pairs from Linux + Solr Expert"
    echo "   - Tickets: $TICKET_COUNT"
    echo "   - Location: $EXTRACTED_YAML"
fi

# 2. Pattern-tagged YAML (if created)
if [ -f "$TAGGED_YAML" ]; then
    echo "✅ tickets_with_patterns.yaml"
    echo "   - Tickets tagged with pattern_id"
    echo "   - Enables batch fixing (1 pattern → N tickets)"
    echo "   - Location: $TAGGED_YAML"
fi

# 3. Pattern report (if created)
if [ -f "$PATTERN_REPORT" ]; then
    echo "✅ patterns_report.json"
    echo "   - Pattern analysis and grouping"
    echo "   - Location: $PATTERN_REPORT"

    # Show pattern summary
    echo ""
    echo "   Pattern Summary:"
    jq -r '.patterns[] | "   - \(.pattern_id): \(.ticket_count) tickets (\(.common_problem_type))"' "$PATTERN_REPORT" 2>/dev/null || true
fi

# 4. Search intelligence database
SEARCH_DB=".claude/search_intelligence"
if [ -d "$SEARCH_DB" ]; then
    DB_SIZE=$(du -sh "$SEARCH_DB" 2>/dev/null | cut -f1)
    SEARCH_COUNT=$(find "$SEARCH_DB" -name "*.json" 2>/dev/null | wc -l)
    echo "✅ search_intelligence database"
    echo "   - Logs of successful Solr searches"
    echo "   - Used by coding agent to optimize retrieval"
    echo "   - Size: $DB_SIZE ($SEARCH_COUNT searches logged)"
    echo "   - Location: $SEARCH_DB"
fi

echo ""
echo "================================================================================"
echo "BOOTSTRAP COMPLETE"
echo "================================================================================"
echo ""
echo "Knowledge artifacts ready for coding agent consumption."
echo ""
echo "Next steps:"
echo "  1. Review extracted tickets:"
echo "     cat $EXTRACTED_YAML"
echo ""

if [ -f "$PATTERN_REPORT" ]; then
    echo "  2. Review patterns:"
    echo "     cat $PATTERN_REPORT | jq '.patterns'"
    echo ""
    echo "  3. Fix tickets using patterns:"
    echo "     python scripts/okp_mcp_agent.py fix <pattern_representative> --max-iterations 10"
    echo ""
fi

echo "  4. Check search intelligence:"
echo "     ls -lh $SEARCH_DB/"
echo ""

echo "================================================================================"
echo "TEST OUTPUT: $TEST_OUTPUT"
echo "================================================================================"

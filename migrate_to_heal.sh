#!/bin/bash
# HEAL Migration Helper Script
# Automates some of the tedious migration tasks

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SOURCE_DIR="/home/emackey/Work/lightspeed-core/lightspeed-evaluation"
DEST_BASE="$HOME/Work/rhel-lightspeed"
DEST_DIR="$DEST_BASE/HEAL"
ARCHIVE_DIR="$HOME/heal_migration_archive"

echo -e "${GREEN}=== HEAL Migration Helper ===${NC}\n"

# Check we're in the right directory
if [ ! -d "okp_mcp_agent" ]; then
    echo -e "${RED}Error: Must run from lightspeed-evaluation repository root${NC}"
    exit 1
fi

# Check we're on the right branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "okp-mcp-integration" ]; then
    echo -e "${YELLOW}Warning: Not on okp-mcp-integration branch (current: $CURRENT_BRANCH)${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Menu
echo "Select migration phase:"
echo "  1) Security scan (detect secrets)"
echo "  2) Archive sensitive files"
echo "  3) Create destination directory structure"
echo "  4) Copy and rename files"
echo "  5) Run quality checks"
echo "  6) Full automated migration (steps 2-4)"
echo "  0) Exit"
echo
read -p "Enter choice [0-6]: " choice

case $choice in
    1)
        echo -e "\n${GREEN}Running security scan...${NC}"
        make detect-secrets || echo -e "${YELLOW}Note: Fix any secrets before proceeding${NC}"

        echo -e "\n${GREEN}Scanning for hardcoded sensitive patterns...${NC}"
        grep -rn "api[_-]key\|secret\|password\|token" okp_mcp_agent/ \
            --include="*.py" --include="*.md" --include="*.yaml" \
            | grep -v "# Example\|TODO\|FIXME\|# For\|export" || echo "No patterns found"
        ;;

    2)
        echo -e "\n${GREEN}Creating archive directory...${NC}"
        mkdir -p "$ARCHIVE_DIR"

        echo -e "${GREEN}Copying sensitive/large files to archive (for reference)...${NC}"
        echo -e "${YELLOW}Note: Files are COPIED, not moved. Original files remain in place.${NC}"
        echo -e "${YELLOW}You can manually delete them from okp_mcp_agent/ after verifying migration.${NC}\n"

        # Copy large log files
        find okp_mcp_agent/artifacts -name "*.log" -exec cp {} "$ARCHIVE_DIR/" \; 2>/dev/null || true

        # Copy internal planning docs
        [ -f "okp_mcp_agent/plans_04032026.txt" ] && cp okp_mcp_agent/plans_04032026.txt "$ARCHIVE_DIR/"
        [ -f "okp_mcp_agent/IMPORT_FIXES_NEEDED.md" ] && cp okp_mcp_agent/IMPORT_FIXES_NEEDED.md "$ARCHIVE_DIR/"
        [ -f "okp_mcp_agent/PATTERN_FIX_REVIEW.md" ] && cp okp_mcp_agent/PATTERN_FIX_REVIEW.md "$ARCHIVE_DIR/"
        [ -f "okp_mcp_agent/MULTI_STAGE_TESTING_PLAN.md" ] && cp okp_mcp_agent/MULTI_STAGE_TESTING_PLAN.md "$ARCHIVE_DIR/"

        echo -e "${GREEN}Copied files to: $ARCHIVE_DIR${NC}"
        ls -lh "$ARCHIVE_DIR"

        # Create a cleanup script for later
        cat > "$ARCHIVE_DIR/cleanup_source.sh" << 'CLEANUP_EOF'
#!/bin/bash
# Run this AFTER verifying the migration succeeded
# This will delete the archived files from the original location

echo "This will DELETE the following from okp_mcp_agent/:"
echo "  - *.log files in artifacts/"
echo "  - plans_04032026.txt"
echo "  - IMPORT_FIXES_NEEDED.md"
echo "  - PATTERN_FIX_REVIEW.md"
echo "  - MULTI_STAGE_TESTING_PLAN.md"
echo ""
read -p "Are you sure? (yes/no) " -r
if [[ $REPLY == "yes" ]]; then
    find okp_mcp_agent/artifacts -name "*.log" -delete
    rm -f okp_mcp_agent/plans_04032026.txt
    rm -f okp_mcp_agent/IMPORT_FIXES_NEEDED.md
    rm -f okp_mcp_agent/PATTERN_FIX_REVIEW.md
    rm -f okp_mcp_agent/MULTI_STAGE_TESTING_PLAN.md
    echo "Cleanup complete!"
else
    echo "Cleanup cancelled"
fi
CLEANUP_EOF
        chmod +x "$ARCHIVE_DIR/cleanup_source.sh"
        echo -e "\n${YELLOW}To cleanup source files later, run: $ARCHIVE_DIR/cleanup_source.sh${NC}"
        ;;

    3)
        echo -e "\n${GREEN}Creating HEAL directory structure...${NC}"
        mkdir -p "$DEST_BASE"

        if [ -d "$DEST_DIR" ]; then
            echo -e "${YELLOW}Warning: $DEST_DIR already exists${NC}"
            read -p "Remove and recreate? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                rm -rf "$DEST_DIR"
            else
                echo "Exiting to avoid overwriting"
                exit 1
            fi
        fi

        mkdir -p "$DEST_DIR"
        cd "$DEST_DIR"

        # Initialize git
        git init
        git branch -m main

        # Create .gitignore
        cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/

# Virtual environments
venv/
.venv

# IDE
.vscode/
.idea/
*.swp

# Testing
.pytest_cache/
.coverage
htmlcov/

# Outputs
output/
.caches/
*.log

# Sensitive
.env
*.key
*.pem
credentials*.json

# Artifacts
artifacts/bootstrap_*/
EOF

        echo -e "${GREEN}Created: $DEST_DIR${NC}"
        ;;

    4)
        echo -e "\n${GREEN}Copying and renaming files...${NC}"

        if [ ! -d "$DEST_DIR" ]; then
            echo -e "${RED}Error: Destination directory doesn't exist. Run option 3 first.${NC}"
            exit 1
        fi

        cd "$SOURCE_DIR"

        # Copy main code with src/ layout
        echo "Copying okp_mcp_agent/ -> src/heal/"
        mkdir -p "$DEST_DIR/src"
        cp -r okp_mcp_agent "$DEST_DIR/src/heal"

        # Reorganize structure
        cd "$DEST_DIR"

        echo "Reorganizing directory structure..."

        # Move tests to top level
        [ -d "src/heal/tests" ] && mv src/heal/tests ./

        # Move docs to top level
        [ -d "src/heal/docs" ] && mv src/heal/docs ./

        # Extract config
        mkdir -p config
        [ -d "src/heal/config/test_suites" ] && cp -r src/heal/config/test_suites config/
        [ -d "src/heal/config/patterns_v2" ] && cp -r src/heal/config/patterns_v2 config/patterns
        [ -d "src/heal/config" ] && rm -rf src/heal/config

        # Rename imports
        echo "Renaming module references (okp_mcp_agent -> heal)..."
        find . -name "*.py" -type f -exec sed -i 's/from okp_mcp_agent/from heal/g' {} +
        find . -name "*.py" -type f -exec sed -i 's/import okp_mcp_agent/import heal/g' {} +

        # Update docs
        find docs -name "*.md" -type f -exec sed -i 's/okp_mcp_agent/heal/g' {} + 2>/dev/null || true

        # Ensure __init__.py files exist
        echo "Creating __init__.py files..."
        find src/heal -type d -exec touch {}/__init__.py \; 2>/dev/null || true

        echo -e "${GREEN}Files copied and renamed${NC}"
        ;;

    5)
        echo -e "\n${GREEN}Running quality checks...${NC}"

        cd "$SOURCE_DIR"

        # Format
        echo "Formatting code..."
        make black-format

        # Lint
        echo "Running linters..."
        make ruff || echo -e "${YELLOW}Fix linting issues before migration${NC}"

        # Type check
        echo "Type checking..."
        make check-types || echo -e "${YELLOW}Fix type issues before migration${NC}"

        echo -e "${GREEN}Quality checks complete${NC}"
        ;;

    6)
        echo -e "\n${GREEN}Running full automated migration...${NC}"
        echo -e "${YELLOW}This will run steps 2, 3, and 4${NC}\n"
        read -p "Continue? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 0
        fi

        # Run steps 2, 3, 4
        $0 << EOF
2
3
4
0
EOF

        echo -e "\n${GREEN}=== Migration Complete ===${NC}"
        echo -e "Next steps:"
        echo "  1. Review files in: $DEST_DIR"
        echo "  2. Create pyproject.toml (see HEAL_MIGRATION_GUIDE.md Phase 5)"
        echo "  3. Create README.md (see HEAL_MIGRATION_GUIDE.md Phase 5)"
        echo "  4. Set up uv: cd $DEST_DIR && uv sync --group dev"
        echo "  5. Test imports: uv run python -c 'import heal'"
        echo "  6. Run tests: uv run pytest tests/"
        echo "  7. Create GitHub repository and push"
        ;;

    0)
        echo "Exiting"
        exit 0
        ;;

    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo -e "\n${GREEN}Done!${NC}"

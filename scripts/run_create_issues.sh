#!/bin/bash
#
# Helper script to create GitHub issues from security scanning alerts
#
# Usage:
#   ./scripts/run_create_issues.sh [--live]
#
# By default, runs in dry-run mode. Use --live to actually create issues.
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration - can be overridden via environment variables
OWNER="${GITHUB_REPOSITORY_OWNER:-rhamenator}"
REPO="${GITHUB_REPOSITORY_NAME:-ai-scraping-defense}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="${SCRIPT_DIR}/create_issues_from_alerts.py"

# Parse arguments
DRY_RUN="--dry-run"
if [[ "${1:-}" == "--live" ]]; then
    DRY_RUN=""
fi

# Helper functions
print_header() {
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     Create GitHub Issues from Security Alerts               ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found. Please install Python 3."
        exit 1
    fi
    print_success "Python 3 found: $(python3 --version)"
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3 not found. Please install pip."
        exit 1
    fi
    print_success "pip3 found"
    
    # Check required packages
    # Note: PyGithub package is imported as 'github' in Python
    local packages_ok=true
    if ! python3 -c "import requests" 2>/dev/null; then
        packages_ok=false
    fi
    if ! python3 -c "from github import Github" 2>/dev/null; then
        packages_ok=false
    fi
    
    if [ "$packages_ok" = false ]; then
        print_warning "Required Python packages not found"
        print_info "Installing required packages..."
        pip3 install requests PyGithub
    fi
    print_success "Required packages found"
    
    # Check GitHub token
    if [[ -z "${GITHUB_TOKEN:-}" ]]; then
        print_error "GITHUB_TOKEN environment variable not set"
        echo ""
        echo "Create a token at: https://github.com/settings/tokens/new"
        echo "Required scopes: repo, security_events"
        echo ""
        echo "Then set it:"
        echo "  export GITHUB_TOKEN=\"your_token_here\""
        exit 1
    fi
    print_success "GitHub token found"
    
    # Check script exists
    if [[ ! -f "$SCRIPT_PATH" ]]; then
        print_error "Script not found: $SCRIPT_PATH"
        exit 1
    fi
    print_success "Script found"
    
    echo ""
}

# Display configuration
display_config() {
    print_info "Configuration:"
    echo "  Repository: ${OWNER}/${REPO}"
    if [[ -n "$DRY_RUN" ]]; then
        echo "  Mode: ${YELLOW}DRY RUN${NC} (no issues will be created)"
    else
        echo "  Mode: ${RED}LIVE${NC} (issues will be created)"
    fi
    echo ""
}

# Confirm live mode
confirm_live_mode() {
    if [[ -z "$DRY_RUN" ]]; then
        print_warning "You are about to create GitHub issues in LIVE mode!"
        echo ""
        read -p "Are you sure you want to continue? (yes/no): " -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            print_info "Aborted by user"
            exit 0
        fi
    fi
}

# Run the script
run_script() {
    print_info "Starting issue creation from security alerts..."
    echo ""
    
    python3 "$SCRIPT_PATH" \
        --owner "$OWNER" \
        --repo "$REPO" \
        $DRY_RUN
    
    local exit_code=$?
    echo ""
    
    if [[ $exit_code -eq 0 ]]; then
        print_success "Script completed successfully"
        
        if [[ -n "$DRY_RUN" ]]; then
            echo ""
            print_info "This was a dry-run. No issues were created."
            print_info "To actually create issues, run:"
            echo "  ./scripts/run_create_issues.sh --live"
        fi
    else
        print_error "Script failed with exit code $exit_code"
        exit $exit_code
    fi
}

# Main execution
main() {
    print_header
    check_prerequisites
    display_config
    confirm_live_mode
    run_script
}

main

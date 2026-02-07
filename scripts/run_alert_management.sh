#!/bin/bash

# Alert Management Helper Script
# This script simplifies running the alert management tool

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
OWNER="${GITHUB_REPOSITORY_OWNER:-rhamenator}"
REPO="${GITHUB_REPOSITORY_NAME:-ai-scraping-defense}"
DRY_RUN="true"

# Function to print colored messages
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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Print banner
echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║     Security Alert, Issue, and PR Management Tool            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check Python installation
print_info "Checking prerequisites..."
if ! command_exists python3; then
    print_error "Python 3 is not installed. Please install Python 3.7 or higher."
    exit 1
fi
print_success "Python 3 found: $(python3 --version)"

# Check pip installation
if ! command_exists pip3; then
    print_error "pip3 is not installed. Please install pip."
    exit 1
fi
print_success "pip3 found"

# Check if required packages are installed
print_info "Checking Python packages..."
if ! python3 -c "import requests, github" 2>/dev/null; then
    print_warning "Required packages not found. Installing..."
    pip3 install requests PyGithub
    if [ $? -eq 0 ]; then
        print_success "Packages installed successfully"
    else
        print_error "Failed to install packages. Please run: pip3 install requests PyGithub"
        exit 1
    fi
else
    print_success "Required packages found"
fi

# Check for GitHub token
if [ -z "$GITHUB_TOKEN" ]; then
    print_error "GITHUB_TOKEN environment variable is not set"
    echo ""
    echo "Please set your GitHub Personal Access Token:"
    echo "  export GITHUB_TOKEN=\"your_token_here\""
    echo ""
    echo "Your token needs these scopes:"
    echo "  - repo"
    echo "  - security_events"
    echo "  - admin:org (for org-level features)"
    echo ""
    echo "Create a token at: https://github.com/settings/tokens/new"
    exit 1
fi
print_success "GitHub token found"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --owner)
            OWNER="$2"
            shift 2
            ;;
        --repo)
            REPO="$2"
            shift 2
            ;;
        --live)
            DRY_RUN="false"
            shift
            ;;
        --help)
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --owner OWNER    GitHub repository owner (default: rhamenator)"
            echo "  --repo REPO      GitHub repository name (default: ai-scraping-defense)"
            echo "  --live           Run in live mode (default: dry-run)"
            echo "  --help           Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  GITHUB_TOKEN     GitHub Personal Access Token (required)"
            echo ""
            echo "Examples:"
            echo "  # Dry run (no changes)"
            echo "  $0"
            echo ""
            echo "  # Live run (makes changes)"
            echo "  $0 --live"
            echo ""
            echo "  # Different repository"
            echo "  $0 --owner myuser --repo myrepo"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SCRIPT_PATH="$SCRIPT_DIR/manage_alerts_issues_prs.py"

# Check if the script exists
if [ ! -f "$SCRIPT_PATH" ]; then
    print_error "Script not found: $SCRIPT_PATH"
    exit 1
fi

# Print configuration
echo ""
print_info "Configuration:"
echo "  Repository: $OWNER/$REPO"
if [ "$DRY_RUN" = "true" ]; then
    echo "  Mode: ${YELLOW}DRY RUN${NC} (no changes will be made)"
else
    echo "  Mode: ${RED}LIVE${NC} (changes WILL be made)"
fi
echo ""

# Confirm if live mode
if [ "$DRY_RUN" = "false" ]; then
    print_warning "You are about to run in LIVE mode. Changes will be made to:"
    echo "  - Security alerts (code scanning, secret scanning, Dependabot)"
    echo "  - Issues"
    echo "  - Pull requests"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        print_info "Operation cancelled"
        exit 0
    fi
fi

# Build command
CMD="python3 $SCRIPT_PATH --owner $OWNER --repo $REPO"
if [ "$DRY_RUN" = "true" ]; then
    CMD="$CMD --dry-run"
fi

# Run the script
print_info "Starting alert management..."
echo ""

$CMD

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    print_success "Alert management completed successfully"
    echo ""
    print_info "Report file: alert_management_report_*.txt"

    if [ "$DRY_RUN" = "true" ]; then
        echo ""
        print_info "This was a DRY RUN. No changes were made."
        print_info "To apply changes, run with --live flag:"
        echo "  $0 --live"
    fi
else
    print_error "Alert management failed with exit code $EXIT_CODE"
    exit $EXIT_CODE
fi

echo ""

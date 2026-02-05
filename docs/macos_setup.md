# macOS Setup Guide

This guide explains how to run the AI Scraping Defense system on macOS using the provided zsh helper scripts.

## Prerequisites
- macOS with [Homebrew](https://brew.sh/) installed
- [Docker Desktop](https://www.docker.com/products/docker-desktop) running
- Python 3.10 or newer (`brew install python`)

## Clone the Repository
```bash
git clone https://github.com/your-username/ai-scraping-defense.git
cd ai-scraping-defense
```

## Prepare the Virtual Environment
Use the `reset_venv.zsh` script to create a fresh virtual environment and install dependencies:
```zsh
./reset_venv.zsh
source .venv/bin/activate
```
The script verifies Homebrew, installs required XML libraries (`libxml2` and `libxslt`), and installs project requirements inside `.venv/`.

## Start the Stack
With Docker Desktop running, launch the development stack:
```zsh
./scripts/macos/quickstart_dev.zsh
```
After the containers start, open <http://localhost:5002> to access the Admin UI.

## Install Security Tools
`security_setup.zsh` installs macOS-compatible binaries of Trivy, Gitleaks, and Grype. Run it once to fetch the tools:
```zsh
./security_setup.zsh
```

## Run Security Scans
After installing the tools, `security_scan.zsh` can audit the repository and Docker images:
```zsh
./security_scan.zsh
```
The script runs Trivy, Gitleaks, and Grype scans and stores reports in the `security_scan_reports/` directory.

## Additional Helper Scripts
- `quick_deploy.zsh` – deploy the stack to a Kubernetes cluster.
- `quick_proxy.zsh` – start the stack with a reverse proxy.
- `quick_takeover.zsh` – stop local web servers and expose the stack on port 80.
- `setup_fake_website.zsh` – launch a fake backend site for testing.
- `post_takeover_test_site.zsh` – attach a sample site after running `quick_takeover.zsh`.

## Updating Dependencies
Re-run `./reset_venv.zsh` whenever Python dependencies change. To update security tools, run `./security_setup.zsh` again.

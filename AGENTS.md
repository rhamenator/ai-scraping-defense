# Repo Guidelines for Codex Agents

This repository contains multiple microservices written mostly in Python. Use the following guidelines when making automated changes.

## Development Workflow

1. **Run Pre-commit Hooks**
   - Format and lint modified files with:
     ```bash
     pre-commit run --files <file1> [file2 ...]
     ```
   - The project uses `black`, `isort`, and `flake8`.

2. **Run Tests**
   - Execute the unit tests when Python code or tests are modified:
     ```bash
     python -m pytest
     ```
   - Tests live in the `test/` directory.

3. **Commit Messages**
   - Use short, present‑tense summaries (e.g., `Update architecture overview`).
   - Separate unrelated changes into separate commits.

4. **Pull Requests**
   - Summarize the change and include test results.
   - Refer to `.github/PULL_REQUEST_TEMPLATE.md` for optional checklist items.

## Repository Structure

- `src/` – Python microservices and shared modules.
- `scripts/` – Helper scripts for setup and maintenance.
- `test/` – Unit tests.
- `docker-compose.yaml` – Service composition for local development.

Consult `CONTRIBUTING.md` and `README.md` for more details about the project.

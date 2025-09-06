#!/usr/bin/env bash
set -euo pipefail

# Simple, idempotent autofix helper used by CI workflows.
# Usage: .github/tools/autofix.sh [category]

CATEGORY="${1:-code-quality}"

echo "[autofix] Category: ${CATEGORY}"

# Python formatters and linters
if compgen -G "**/*.py" > /dev/null; then
  echo "[autofix] Running Python formatters (black, isort, ruff)"
  command -v black >/dev/null 2>&1 && black . || true
  command -v isort >/dev/null 2>&1 && isort . || true
  command -v ruff  >/dev/null 2>&1 && ruff --fix . || true
  command -v docformatter >/dev/null 2>&1 && docformatter -r -i . || true
fi

# Pre-commit hooks if configured
if [ -f .pre-commit-config.yaml ] && command -v pre-commit >/dev/null 2>&1; then
  echo "[autofix] Running pre-commit hooks"
  pre-commit run --all-files || true
fi

# JavaScript/TypeScript + Markdown formatting
if [ -f package.json ]; then
  echo "[autofix] Running JS formatters (prettier, eslint --fix)"
  npx --yes prettier -w . || true
  npx --yes eslint . --ext .js,.jsx,.ts,.tsx --fix || true
  if command -v markdownlint >/dev/null 2>&1; then
    echo "[autofix] Running markdownlint --fix"
    markdownlint "**/*.md" --fix || true
  fi
fi

# Shell formatting
if compgen -G "**/*.sh" > /dev/null && command -v shfmt >/dev/null 2>&1; then
  echo "[autofix] Formatting shell scripts with shfmt"
  shfmt -w . || true
fi

# Go formatting
if compgen -G "**/*.go" > /dev/null; then
  echo "[autofix] Running gofmt and goimports"
  command -v gofmt >/dev/null 2>&1 && gofmt -s -w . || true
  command -v goimports >/dev/null 2>&1 && goimports -w . || true
fi

# Rust formatting
if [ -f Cargo.toml ] || compgen -G "**/Cargo.toml" > /dev/null; then
  echo "[autofix] Running cargo fmt"
  command -v cargo >/dev/null 2>&1 && cargo fmt --all || true
fi

# Terraform formatting
if compgen -G "**/*.tf" > /dev/null; then
  echo "[autofix] Running terraform fmt"
  command -v terraform >/dev/null 2>&1 && terraform fmt -recursive || true
fi

# Lua formatting
if compgen -G "**/*.lua" > /dev/null && command -v stylua >/dev/null 2>&1; then
  echo "[autofix] Running stylua"
  stylua . || true
fi

# C/C++ formatting
if compgen -G "**/*.c" > /dev/null || compgen -G "**/*.h" > /dev/null || compgen -G "**/*.cpp" > /dev/null; then
  if command -v clang-format >/dev/null 2>&1; then
    echo "[autofix] Running clang-format"
    find . -type f \( -name "*.c" -o -name "*.h" -o -name "*.cpp" \) -print0 | xargs -0 -r clang-format -i || true
  fi
fi

# TOML formatting
if compgen -G "**/*.toml" > /dev/null && command -v taplo >/dev/null 2>&1; then
  echo "[autofix] Formatting TOML with taplo"
  taplo fmt || true
fi

echo "[autofix] Completed autofix steps."

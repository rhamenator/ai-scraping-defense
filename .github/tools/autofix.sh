#!/usr/bin/env bash
set -euo pipefail
shopt -s globstar nullglob

echo "::group::Python fixes"
if compgen -G "**/*.py" >/dev/null; then
  ruff check . --fix || true
  black . || true
  isort . || true
fi
echo "::endgroup::"

echo "::group::Shell fixes"
if compgen -G "**/*.sh" >/dev/null; then
  shfmt -w . || true
fi
echo "::endgroup::"

echo "::group::Lua fixes"
if compgen -G "**/*.lua" >/dev/null; then
  luacheck . || true
  if command -v stylua >/dev/null 2>&1; then stylua . || true; fi
fi
echo "::endgroup::"

echo "::group::JS/TS fixes"
if [ -f package.json ] || compgen -G "**/*.{js,jsx,ts,tsx}" >/dev/null; then
  npx --yes prettier -w . || true
  npx --yes eslint . --ext .js,.jsx,.ts,.tsx --fix || true
fi
echo "::endgroup::"

echo "::group::Docker/K8s checks (non-fatal)"
if compgen -G "**/Dockerfile" >/dev/null; then
  (for f in **/Dockerfile; do hadolint "$f" || true; done)
fi
kubeconform -ignore-missing-schemas -summary $(git ls-files '*.yaml' '*.yml' | tr '\n' ' ') || true
echo "::endgroup::"

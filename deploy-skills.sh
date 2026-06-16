#!/usr/bin/env bash
# Deploy updated skills to Hermes skills directory.
# Run from repo root: ./deploy-skills.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="${HOME}/.hermes/skills"

echo "=== Deploying raindrop-categorize ==="
cp "${REPO_DIR}/raindrop-categorize/scripts/"*.py "${SKILLS_DIR}/raindrop-categorize/scripts/"
cp "${REPO_DIR}/raindrop-categorize/references/raindrop-rules.json" "${SKILLS_DIR}/raindrop-categorize/references/raindrop-rules.json"

echo "=== Deploying raindrop-linter ==="
cp "${REPO_DIR}/raindrop-linter/scripts/"*.py "${SKILLS_DIR}/raindrop-linter/scripts/"

echo "=== Deploying shared module ==="
mkdir -p "${SKILLS_DIR}/shared/"
cp "${REPO_DIR}/shared/raindrop_common.py" "${SKILLS_DIR}/shared/raindrop_common.py"
cp "${REPO_DIR}/shared/__init__.py" "${SKILLS_DIR}/shared/__init__.py"

echo "=== Done ==="

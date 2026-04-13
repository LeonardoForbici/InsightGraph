#!/bin/sh
# InsightGraph — Install git hooks into the current repo.
# Run once from the repo root: sh scripts/install-hooks.sh

set -e

HOOKS_DIR="$(git rev-parse --git-dir)/hooks"
SCRIPTS_DIR="$(git rev-parse --show-toplevel)/scripts"

echo "[InsightGraph] Installing git hooks into $HOOKS_DIR"

cp "$SCRIPTS_DIR/post-commit" "$HOOKS_DIR/post-commit"
chmod +x "$HOOKS_DIR/post-commit"

echo "[InsightGraph] post-commit hook installed."
echo ""
echo "Every commit will now automatically trigger an architecture scan."
echo "Set INSIGHTGRAPH_API env var to point to your backend (default: http://localhost:8000)"

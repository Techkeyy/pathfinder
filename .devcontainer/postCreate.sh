#!/usr/bin/env bash
# One-time Codespace setup. Runs after the container is created.
# Keeps two isolated Python environments so DataHub's heavy dependency tree
# never collides with Pathfinder's:
#   * base env      -> Pathfinder (editable install)
#   * ~/.dh venv    -> acryl-datahub (the `datahub` CLI + REST emitter for seeding)
set -euo pipefail

echo "== Pathfinder: installing package (editable) =="
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

echo "== DataHub CLI: isolated venv at ~/.dh =="
python -m venv "$HOME/.dh"
"$HOME/.dh/bin/python" -m pip install --upgrade pip
"$HOME/.dh/bin/python" -m pip install "acryl-datahub[datahub-rest]"

echo
echo "✅ Setup complete."
echo "   Next:  bash demo/up.sh      # boots DataHub + seeds the ML lineage demo"
echo "   Then:  pathfinder doctor    # confirms the live GraphQL lineage schema"

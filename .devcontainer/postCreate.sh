#!/usr/bin/env bash
# One-time Codespace setup (runs after the container is built).
# A single venv at ~/.dh holds BOTH the DataHub CLI/emitter and Pathfinder, and
# is put on PATH — this mirrors the exact sequence proven to work by hand, and
# avoids the recovery-container's pip-less system python.
set -uo pipefail   # deliberately not -e: report problems, don't half-exit silently

echo "== Pathfinder Codespace setup =="
PY="$(command -v python3 || command -v python)"
echo "using python: $PY ($("$PY" --version 2>&1))"

"$PY" -m venv "$HOME/.dh"
"$HOME/.dh/bin/pip" install --upgrade pip
"$HOME/.dh/bin/pip" install "acryl-datahub[datahub-rest]"
"$HOME/.dh/bin/pip" install -e ".[dev]"

# Make datahub / pathfinder / python resolve to this venv in every future shell.
grep -q '.dh/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.dh/bin:$PATH"' >> "$HOME/.bashrc"

echo
echo "✅ Setup complete (pathfinder + DataHub CLI installed in ~/.dh, on PATH)."
echo "   Next:  bash demo/up.sh      # boots DataHub + seeds the ML lineage demo"
echo "   Then:  pathfinder doctor"

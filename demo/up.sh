#!/usr/bin/env bash
# Stand up a local DataHub and seed the demo stack.
# Requires Docker. See https://docs.datahub.com/docs/quickstart
set -euo pipefail

echo "==> Installing DataHub CLI (if needed)"
python -m pip install --quiet 'acryl-datahub[datahub-rest]'

echo "==> Starting DataHub (Docker quickstart) — first run pulls images, be patient"
datahub docker quickstart

echo "==> Seeding the demo stack (datasets + dashboards + ML feature/model/deployment + lineage)"
python "$(dirname "$0")/seed.py"

echo "==> Done. DataHub UI: http://localhost:9002  (GMS: http://localhost:8080)"
echo "    Next: pathfinder doctor"

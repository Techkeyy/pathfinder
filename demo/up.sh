#!/usr/bin/env bash
# Boot a local DataHub and seed the Pathfinder demo (tables -> feature -> model
# -> deployment ML lineage). Designed for the Codespace devcontainer, but works
# on any Linux host with Docker.
set -euo pipefail

DH="${DH_PY:-$HOME/.dh/bin/python}"
DH_CLI="${DH_CLI:-$HOME/.dh/bin/datahub}"
GMS="${DATAHUB_GMS_URL:-http://localhost:8080}"

# Fall back to the ambient python/datahub if the isolated venv is absent
# (e.g. running outside the devcontainer).
[ -x "$DH" ] || DH="python"
[ -x "$DH_CLI" ] || DH_CLI="datahub"

echo "== Waiting for the Docker daemon =="
for i in $(seq 1 20); do docker info >/dev/null 2>&1 && { echo "docker ready"; break; }; sleep 3; done
if ! docker info >/dev/null 2>&1; then
  echo "❌ Docker daemon not reachable. In the universal image it auto-starts;"
  echo "   if this persists, run:  sudo dockerd > /tmp/dockerd.log 2>&1 &   then re-run this script."
  exit 1
fi

echo "== Booting DataHub (this pulls images on first run; ~5-10 min) =="
"$DH_CLI" docker quickstart

echo "== Waiting for GMS at $GMS/health =="
for i in $(seq 1 60); do
  if curl -fsS "$GMS/health" >/dev/null 2>&1; then
    echo "DataHub GMS healthy after ~$((i*5))s"
    break
  fi
  sleep 5
done

echo "== Seeding demo metadata (ML lineage chain) =="
"$DH" "$(dirname "$0")/seed.py"

echo
echo "✅ DataHub is up and seeded."
echo "   UI       : forwarded port 9002  (login datahub / datahub)"
echo "   GraphQL  : $GMS/api/graphql"
echo
echo "   Now run:  pathfinder doctor"
echo "   Then    :  pathfinder run --before demo/changes/orders_before.sql \\"
echo "                            --after  demo/changes/orders_after.sql --dataset orders --dry-run"

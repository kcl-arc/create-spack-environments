#!/usr/bin/env bash
set -euo pipefail

# Refresh feature mappings and generated environment artifacts from live Slurm state.
# Run this on the cluster head/login node where scontrol is available.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_FEATURES_FILE="${TMPDIR:-/tmp}/er-spack-features.$$.txt"

cleanup() {
  rm -f "$TMP_FEATURES_FILE"
}
trap cleanup EXIT

cd "$REPO_ROOT"

if ! command -v scontrol >/dev/null 2>&1; then
  echo "Error: scontrol not found in PATH. Run this script on a Slurm-enabled host." >&2
  exit 1
fi

echo "Collecting feature sets from Slurm..."
scontrol show nodes | grep -o 'Features=[^ ]*' > "$TMP_FEATURES_FILE"

echo "Updating matrix/features_to_family.yaml..."
python3 scripts/update_features_to_family.py --input "$TMP_FEATURES_FILE"

echo "Regenerating environments/index..."
python3 scripts/generate_envs.py

echo "Refreshing root install queue..."
python3 scripts/export_root_install_queue.py

echo "Done. Review changes with: git status --short"

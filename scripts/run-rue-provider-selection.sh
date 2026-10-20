#!/usr/bin/env bash
set -euo pipefail

out="target/evidence/RUE-PROV-001"
rm -rf "$out"
mkdir -p "$out"

python -m scripts.select_rue_provider \
  --provider "Provider B" \
  --json > "$out/provider-b-selection.json"

# Unknown selections must fail closed rather than silently choosing a default.
if python -m scripts.select_rue_provider --provider "Provider Z" > "$out/unexpected-provider.txt" 2>&1; then
  echo "unknown provider selection unexpectedly succeeded" >&2
  exit 1
fi
rm -f "$out/unexpected-provider.txt"

cat "$out/provider-b-selection.json"

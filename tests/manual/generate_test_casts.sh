#!/usr/bin/env bash
# Run from project root
set -euo pipefail
SPECS_DIR="tests/manual"
mkdir -p tests/manual/casts
for spec in iterm2 kitty sixel; do
    echo "Generating cast for protocol: $spec"
    uv run gen_asciicast.py "$SPECS_DIR/test_${spec}_protocol.yaml"
done
echo "Done. Casts in tests/manual/casts/"

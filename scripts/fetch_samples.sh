#!/usr/bin/env bash
# Download a small CC0 sample starter set into assets/samples/.
# Only CC0 / public-domain one-shots. Edit the URLs to point at your own pack.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SMP="$ROOT/assets/samples"

echo "assets/samples exists: $(test -d "$SMP" && echo yes || echo no)"

# The engine works entirely offline and self-contains; this script is a
# convenience placeholder. Point SAMPLE_URL at a tar/zip of CC0 one-shots, e.g.
#   SAMPLE_URL=https://example.com/pack.tar.gz ./scripts/fetch_samples.sh
# and it will extract guitars, keys, strings, etc. into the folders above.

if [ -n "${SAMPLE_URL:-}" ]; then
  echo "Downloading $SAMPLE_URL ..."
  curl -fL "$SAMPLE_URL" -o /tmp/samples.tar.gz
  tar -xzf /tmp/samples.tar.gz -C "$SMP"
  echo "Extracted. Restart the backend to pick up the samples."
else
  echo "No SAMPLE_URL set. Either set it, or drop your own royalty-free"
  echo "one-shots in manually. See assets/samples/README.md."
fi
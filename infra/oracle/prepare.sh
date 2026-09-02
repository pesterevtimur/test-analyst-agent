#!/usr/bin/env bash
# Fetch the Sales History sample data into infra/oracle/vendor/.
#
# Why not vendor it in git: sales.csv alone is 71 MB. The repo stays small and
# the data stays traceable to its upstream release.
#
# Run once before the first `docker compose up`. Idempotent.

set -euo pipefail

REPO="https://github.com/oracle-samples/db-sample-schemas.git"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR="$HERE/vendor"
TARGET="$VENDOR/sales_history"

if [ -d "$TARGET" ] && [ -f "$TARGET/sh_create.sql" ]; then
    echo "Sales History data already present at $TARGET"
    exit 0
fi

mkdir -p "$VENDOR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Cloning $REPO (sales_history only)..."
git clone --depth 1 --filter=blob:none --sparse "$REPO" "$TMP/repo" >/dev/null 2>&1
git -C "$TMP/repo" sparse-checkout set sales_history >/dev/null 2>&1

if [ ! -f "$TMP/repo/sales_history/sh_create.sql" ]; then
    echo "ERROR: sales_history not found in the upstream repo - layout changed?" >&2
    exit 1
fi

SHA="$(git -C "$TMP/repo" rev-parse --short HEAD)"
cp -R "$TMP/repo/sales_history" "$TARGET"
printf 'source: %s\ncommit: %s\nfetched: %s\n' "$REPO" "$SHA" "$(date -Iseconds)" > "$VENDOR/PROVENANCE.txt"

echo "Fetched sales_history at $SHA into $TARGET"
du -sh "$TARGET"

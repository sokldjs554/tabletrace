#!/usr/bin/env bash
# Mirror the project into the chartwire checkout (visible in the Claude app) and refresh the
# full-history bundle. Used because this session could not push to any GitHub remote.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST="${1:-/home/user/chartwire}"
mkdir -p "$DST/tabletrace"
cd "$SRC"
find "$DST/tabletrace" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
tar --exclude='./.git' --exclude='./.venv' --exclude='./models' --exclude='./data/raw' --exclude='./experiments/*/model' \
    --exclude='./_site' --exclude='./dist' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' -cf - . | tar -C "$DST/tabletrace" -xf -
git bundle create "$DST/tabletrace-history.bundle" --all
echo "mirrored to $DST/tabletrace ($(du -sh "$DST/tabletrace" | cut -f1)); bundle $(du -h "$DST/tabletrace-history.bundle" | cut -f1); HEAD $(git rev-parse --short HEAD)"

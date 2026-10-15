#!/usr/bin/env bash
# Install the yq binary. Requires curl.
# Usage: install_yq.sh [DIR]   (default DIR: this tools/ directory)

set -euo pipefail

DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
DEST="$DIR/yq"

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)        ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *)             echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

URL="https://github.com/mikefarah/yq/releases/latest/download/yq_${OS}_${ARCH}"

mkdir -p "$DIR"
echo "Downloading yq (${OS}/${ARCH})..."
curl -fsSL "$URL" -o "$DEST"
chmod +x "$DEST"
echo "Installed: $DEST"
"$DEST" --version

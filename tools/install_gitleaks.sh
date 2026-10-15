#!/usr/bin/env bash
# Install the gitleaks binary. Detects platform automatically; requires curl and tar.
# Usage: install_gitleaks.sh [DIR]   (default DIR: this tools/ directory)

set -euo pipefail

VERSION="8.30.1"
DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
DEST="$DIR/gitleaks"

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  ARCH="x64" ;;
    aarch64) ARCH="arm64" ;;
    arm64)   ARCH="arm64" ;;
    *)       echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

URL="https://github.com/gitleaks/gitleaks/releases/download/v${VERSION}/gitleaks_${VERSION}_${OS}_${ARCH}.tar.gz"

mkdir -p "$DIR"
echo "Downloading gitleaks ${VERSION} (${OS}/${ARCH})..."
curl -fsSL "$URL" | tar -xz -C "$DIR" gitleaks
chmod +x "$DEST"
echo "Installed: $DEST"
"$DEST" version

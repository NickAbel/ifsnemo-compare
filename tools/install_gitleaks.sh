#!/usr/bin/env bash
# Install the gitleaks binary into this tools/ directory.
# Detects platform automatically; requires curl and tar.

set -euo pipefail

VERSION="8.30.1"
DEST="$(cd "$(dirname "$0")" && pwd)/gitleaks"

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  ARCH="x64" ;;
    aarch64) ARCH="arm64" ;;
    arm64)   ARCH="arm64" ;;
    *)       echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

URL="https://github.com/gitleaks/gitleaks/releases/download/v${VERSION}/gitleaks_${VERSION}_${OS}_${ARCH}.tar.gz"

echo "Downloading gitleaks ${VERSION} (${OS}/${ARCH})..."
curl -fsSL "$URL" | tar -xz -C "$(dirname "$DEST")" gitleaks
chmod +x "$DEST"
echo "Installed: $DEST"
"$DEST" version

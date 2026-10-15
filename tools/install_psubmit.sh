#!/usr/bin/env bash
# Install psubmit (https://github.com/a-v-medvedev/psubmit). Requires git.
# Usage: install_psubmit.sh [DIR]   (default DIR: tools/psubmit next to this script)
# psubmit.sh finds its sibling scripts relative to itself, so they must stay together in DIR.

set -euo pipefail

DIR="${1:-$(cd "$(dirname "$0")" && pwd)/psubmit}"

echo "Cloning psubmit..."
git clone -q --depth=1 https://github.com/a-v-medvedev/psubmit.git "$DIR"
echo "Installed: $DIR"

#!/usr/bin/env bash
# Install codebase-memory-mcp build Termux (auto-detect arsitektur).
#   curl -fsSL https://raw.githubusercontent.com/FgsiDev/codebase-memory-mcp-termux/main/install-termux.sh | bash
# Env opsional: CBM_REPO=owner/repo  CBM_DIR=~/.local/bin  CBM_TAG=termux-0.12.1-281-gxxxx
set -euo pipefail

REPO="${CBM_REPO:-FgsiDev/codebase-memory-mcp-termux}"
DIR="${CBM_DIR:-$HOME/.local/bin}"
TAG="${CBM_TAG:-}"

case "$(uname -m)" in
  aarch64|arm64)        ARCH=arm64 ;;
  armv7l|armv8l|arm*)   ARCH=arm ;;
  x86_64|amd64)         ARCH=x86_64 ;;
  i386|i486|i586|i686)  ARCH=x86 ;;
  *) echo "error: arsitektur tidak didukung: $(uname -m)" >&2; exit 1 ;;
esac

NAME="codebase-memory-mcp-termux-${ARCH}.tar.gz"
if [ -n "$TAG" ]; then
  BASE="https://github.com/${REPO}/releases/download/${TAG}"
else
  BASE="https://github.com/${REPO}/releases/latest/download"
fi

echo "arch:   $ARCH"
echo "source: $BASE/$NAME"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"

curl -fL --progress-bar -o "$NAME" "$BASE/$NAME"
curl -fsSL -o "$NAME.sha256" "$BASE/$NAME.sha256"
sha256sum -c "$NAME.sha256"

tar xzf "$NAME"
mkdir -p "$DIR"
install -m 755 codebase-memory-mcp "$DIR/codebase-memory-mcp"

echo "terpasang: $DIR/codebase-memory-mcp"
case ":$PATH:" in
  *":$DIR:"*) ;;
  *) echo "tambahkan ke PATH:  export PATH=\"$DIR:\$PATH\"" ;;
esac
"$DIR/codebase-memory-mcp" --version || echo "peringatan: binary gagal dijalankan"

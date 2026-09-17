#!/bin/bash
# One-time macOS setup. Run once, then use the Desktop icon.
#
# The Windows side ships its own interpreter through the installer; on
# macOS we use the system python, so the pinned requirements must be
# installable there. requirements.txt targets 3.10+, so fall back to
# unpinned versions when only 3.9 is available.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "Installing Réduire PDF…"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null

if ! .venv/bin/pip install -q -r requirements.txt 2>/dev/null; then
    echo "Pinned versions need Python 3.10+; installing the newest that fit…"
    .venv/bin/pip install -q pikepdf pypdfium2 pillow numpy scipy flask zstandard
fi

# Optional, but black-and-white scans compress far better with it.
if command -v brew >/dev/null 2>&1 && ! command -v jbig2 >/dev/null 2>&1; then
    echo "Installing jbig2enc (optional)…"
    brew install jbig2enc || echo "jbig2enc not installed; scans will compress less."
fi

cp "scripts/Réduire PDF.command" "$HOME/Desktop/Réduire PDF.command"
chmod +x "$HOME/Desktop/Réduire PDF.command"
echo "Done. Double-click « Réduire PDF » on your Desktop."

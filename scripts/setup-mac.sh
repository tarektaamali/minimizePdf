#!/bin/bash
# One-time macOS setup. Run once, then use the Desktop icon.
#
# The Windows side ships its own Python 3.12 through the installer; macOS
# uses the system interpreter. requirements.txt carries a pin for each,
# selected by environment marker, so this needs no special case.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "Installing Réduire PDF…"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null

.venv/bin/pip install -q -r requirements.txt

# Optional, but black-and-white scans compress far better with it.
if command -v brew >/dev/null 2>&1 && ! command -v jbig2 >/dev/null 2>&1; then
    echo "Installing jbig2enc (optional)…"
    brew install jbig2enc || echo "jbig2enc not installed; scans will compress less."
fi

cp "scripts/Réduire PDF.command" "$HOME/Desktop/Réduire PDF.command"
chmod +x "$HOME/Desktop/Réduire PDF.command"
echo "Done. Double-click « Réduire PDF » on your Desktop."

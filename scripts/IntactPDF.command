#!/bin/bash
# Double-clicking opens Terminal in the user's home, so locate the project
# from this script's own path rather than the working directory.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$HERE"
[ -d "$PROJECT/pdfshrink" ] || PROJECT="$HERE/.."
[ -d "$PROJECT/pdfshrink" ] || PROJECT="$HOME/Desktop/Ghassen"

cd "$PROJECT" || { echo "Project folder not found."; read -r; exit 1; }

if [ ! -x .venv/bin/python ]; then
    echo "First run - installing…"
    bash scripts/setup-mac.sh || { echo "Install failed."; read -r; exit 1; }
fi

# Match the Windows launcher: U+202F in sizes needs a UTF-8 console.
export PYTHONUTF8=1
exec .venv/bin/python -m pdfshrink.web

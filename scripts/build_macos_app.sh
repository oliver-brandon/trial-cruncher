#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$(uname -s)" == Darwin ]] || { echo "This build requires macOS." >&2; exit 1; }
python_bin="${PYTHON_BIN:-python3}"
venv="${root}/.build-venv"
[[ -x "$venv/bin/python" ]] || "$python_bin" -m venv "$venv"
"$venv/bin/python" -m pip install -e "$root[build]"
"$venv/bin/python" -c 'from PySide6.QtWebEngineWidgets import QWebEngineView'
"$venv/bin/python" -m PyInstaller --noconfirm --distpath "$root/dist" --workpath "$root/build/macos" "$root/packaging/macos/TrialCruncher.spec"

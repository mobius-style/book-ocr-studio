#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
umask 077
if [[ $# -gt 1 ]]; then echo "Use one option only; see --help." >&2; exit 2; fi
case "${1:-}" in
  --help|-h)
    echo 'Usage: bash install.sh [--skip-model | --yomitoku]'
    echo 'Creates an isolated .venv; --yomitoku creates .venv-yomitoku instead.'
    echo 'Python 3.10 or 3.11 required; choose with BOOK_OCR_PYTHON.'
    echo 'Default: downloads missing Gemma 12B weights using preinstalled Ollama. --skip-model installs Python only. No sudo or browser installation.'
    exit 0;;
  '') target=.venv; requirements=requirements.txt; prepare_model=1;;
  --skip-model) target=.venv; requirements=requirements.txt; prepare_model=0;;
  --yomitoku) target=.venv-yomitoku; requirements=requirements-yomitoku.txt; prepare_model=0;;
  *) echo 'Unknown option; use --help' >&2; exit 2;;
esac
python="${BOOK_OCR_PYTHON:-python3}"
"$python" -c 'import sys; assert sys.platform == "linux", "Linux required"; assert (3,10) <= sys.version_info[:2] < (3,12), "Use Python 3.10 or 3.11"'
if [[ -e "$target" ]]; then
  echo "$target already exists; refusing to modify it. Move it aside deliberately or use a fresh directory." >&2
  exit 1
fi
if [[ "$prepare_model" == 1 ]] && ! command -v ollama >/dev/null 2>&1; then
  echo 'Install Ollama first (https://ollama.com/download/linux), or use --skip-model.' >&2
  exit 1
fi
"$python" -m venv "$target"
"$target/bin/python" -m pip install --upgrade pip
constraints=()
if [[ "$target" == .venv ]] && "$target/bin/python" -c 'import sys; sys.exit(sys.version_info[:2] != (3,10))'; then
  constraints=(-c constraints-linux-py310.txt)
fi
"$target/bin/python" -m pip install -r "$requirements" "${constraints[@]}"
"$target/bin/python" -m pip check
if [[ "$target" == .venv ]]; then
  "$target/bin/python" scripts/check_install.py
else
  "$target/bin/python" -c 'from yomitoku import DocumentAnalyzer; import cv2, torch; print("Optional engine imports OK; models not loaded")'
fi
if [[ "$prepare_model" == 1 ]]; then
  "$target/bin/python" scripts/setup_models.py
fi
echo 'Installation finished. Read INSTALL.md for drivers and Chrome. C1 OCR review is included in the application.' 

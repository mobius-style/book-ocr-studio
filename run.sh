#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
umask 077
if [[ ! -x .venv/bin/python ]]; then
  echo "Environment missing. Run bash install.sh first; see INSTALL.md." >&2
  exit 1
fi
exec .venv/bin/python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port "${BOOK_OCR_PORT:-8507}" --browser.gatherUsageStats false --server.maxUploadSize 200

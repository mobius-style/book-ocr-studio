# Linux installation

This beta targets Linux x86-64, Python 3.10 or 3.11, NVIDIA CUDA GPUs,
Google Chrome and Ollama. It is not a hosted OCR service. Model downloads
can require many gigabytes; model weights are not inside the source ZIP.
The standard installer prepares Gemma 12B automatically. The OCR-specific
C1 prompt and review workflow are already included in the application.
Install [Ollama](https://ollama.com/download/linux) before running the standard installer.

## 1. Python environment

Install Python with its `venv` support using your operating system's package
manager. Extract the source archive to a writable directory. Then run:

```bash
bash install.sh
```

If your default Python is newer, select an installed supported interpreter:

```bash
BOOK_OCR_PYTHON=python3.11 bash install.sh
```

The installer creates `.venv` without inheriting system Python packages. It
refuses to modify an existing environment. A failed attempt may leave a
partial `.venv`; move that directory aside before retrying. It does not
install operating-system packages, Chrome or Ollama. After Python checks pass,
it downloads missing Gemma 12B weights using your installed Ollama executable.
Use `bash install.sh --skip-model` for Python dependencies only.
`requirements.txt` pins direct dependencies. On Python 3.10, the installer
also applies the tested transitive version snapshot in
`constraints-linux-py310.txt`. It is not an artifact-hash lock. Python 3.11
resolves transitive dependencies with pip and has not been installation-tested
for this release. The optional YomiToku environment resolves separately.

## 2. CUDA and models

Install a compatible NVIDIA driver and check `nvidia-smi`. The installer
uses PyTorch 2.10.0 from PyPI. Confirm CUDA actually works:

```bash
.venv/bin/python scripts/check_install.py
```

If CUDA is unavailable, resolve the driver/PyTorch combination before OCR.
This build has not been qualified for CPU-only, AMD or Apple GPUs.

The standard installer invokes `scripts/setup_models.py`, which starts its own
short-lived loopback Ollama server and obtains `gemma4:12b-it-qat`. It does not
run inference or stop your existing Ollama server. Download progress is shown.
Existing matching tags in the chosen store are reused; their digest is recorded.
Tags can change upstream, so these are not permanently pinned weight artifacts.

Weights default to `models/` inside the extracted application directory.
`model-settings.json` records the resolved path and model digests; workers read
the same settings. Both are private and excluded from public packages.

If the download fails or you used `--skip-model`, retry just the model step:

```bash
.venv/bin/python scripts/setup_models.py
```

Do not rerun the full installer against an existing `.venv`. Dependencies remain
installed after a failed model step. Retry can reuse Ollama's cached download data.

To add 26B (optional; does not change the UI's 12B default):

```bash
.venv/bin/python scripts/setup_models.py --model gemma4:26b-a4b-it-qat
```

Select 26B in the app when needed. See [BENCHMARKS.md](BENCHMARKS.md) for the
limited historical comparison; there is no guaranteed whole-job speedup.

To reuse a different model store, set `BOOK_OCR_MODELS` to its directory before
running setup. The setup records that directory for subsequent workers. An
explicit environment override takes precedence. It must be readable and, for
new downloads, writable; no permissions are changed on an existing store.
Do not make model directories world-writable. For old installations without
settings, workers retain the legacy system-store fallback.

Read [third-party terms](THIRD_PARTY_NOTICES.md) before downloading. Each exact
model retains its own license. Marker obtains its own weights on first OCR use;
those weights are separate from the Gemma setup step. C1 here is an OCR-specific
application workflow, not a new or fine-tuned model weight release.

## 3. Start

```bash
bash run.sh
```

Open `http://127.0.0.1:8507/`. Use `BOOK_OCR_PORT` to change the UI port.
The optional extension opens port 8507 by default. The bridge uses port 8508.

For a synthetic source/export smoke test (no models):

```bash
.venv/bin/python -m unittest discover -s public_tests -v
```

## 4. Kindle: dedicated Chrome or optional extension

Install Google Chrome separately. The **Open Chrome for Kindle** button uses
that browser through Playwright; it does not install another browser. Sign
in to Amazon in the opened window. The default profile is private local
`captures/chrome-profile/`, with no migration of any older profile. A fresh
installation therefore requires login again. Supported reader hosts are
`read.amazon.co.jp` and `read.amazon.com`; layouts may still need adaptation.

To connect an existing regular Chrome instead:

1. Run `.venv/bin/python setup_chrome_bridge.py` locally.
2. Open `chrome://extensions`, enable Developer mode and load the
   `chrome-extension/` directory. Review the debugger permission.
3. In the app, expand **Connect your regular Chrome (optional)** and click
   **Enable local Chrome bridge**. Alternatively set
   `BOOK_OCR_ENABLE_BRIDGE=1` before launching the app.
4. Open one Kindle book in Chrome, then start capture in the app.

The bridge is not started for PDF-only use by default. Once enabled it runs
as a background process, including after the browser tab closes. To stop a
manually started bridge, use Ctrl+C; for an app-started bridge, identify the
exact `chrome_bridge.py` process in your process manager and terminate only
that process. Never use a broad command that kills all Python or Chrome
processes. Do not operate competing debugger extensions on the same tab.

The generated `.chrome-bridge-key` and `chrome-extension/config.js` are
private and excluded from the public package. Every fresh installation
generates its own key. To rotate it, stop the bridge, remove those two local
files, rerun setup and reload the extension. No key is supplied by this release.

## Optional YomiToku

Read its CC BY-NC-SA terms and commercial licensing options in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) first. If your use is permitted:

```bash
bash install.sh --yomitoku
```

This creates a separate `.venv-yomitoku`. Select YomiToku explicitly in the
UI. Its weights are obtained separately. The default remains Marker.

## Privacy and troubleshooting

Keep `jobs/`, `captures/`, browser profiles, logs and generated credentials
private. Use a source-only release builder when publishing modifications;
do not upload your working directory. Output to another AI service is a
separate user-controlled action.

When reporting an error, provide software versions and a synthetic
reproduction. Remove book text, screenshots, paths containing personal
details, cookies and secrets from logs before sharing.

## Optional vision API instead of local Gemma

Gemma 4 remains the recommended default. To use a user-selected vision model
through the optional OpenAI-compatible connector, follow [CONNECTORS.md](CONNECTORS.md).
For this route, `bash install.sh --skip-model` skips Gemma preparation; local
OCR dependencies are still installed. You must prepare your chosen server
separately. A remote endpoint receives the page images and OCR text after
explicit enablement and may charge fees. API compatibility is not a quality
or completion guarantee.

## GPU process lifetime

The app terminates its dedicated OCR and local Gemma processes after work or
on error. An independent supervisor watches an ownership pipe and cleans up the
owned process group if its caller disappears. This was tested with SIGKILL of
the caller, not SIGKILL of the supervisor itself or an unrecoverable driver fault.
Other applications and user-managed API servers are never stopped by this mechanism.
Closing the browser tab alone does not cancel an active background job; use the
job Stop control. Model review may finish its current request before stopping.

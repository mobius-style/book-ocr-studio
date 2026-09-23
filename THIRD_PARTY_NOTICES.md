# Licenses and source

Book OCR Studio original application code is licensed under **AGPL-3.0-only**; see `LICENSE`. You may use, modify and redistribute it under those terms. No warranty is provided. The license does not grant rights in books, brands, third-party code or model weights. Source is supplied with the application; operators of modified network-accessible versions must review AGPL section 13 and provide the required corresponding source.

The original application license is a project choice for the present dependency stack, not a claim that all dependencies have been relicensed or that every commercial use is cleared.

| Component checked | Code terms | Model / other terms |
| --- | --- | --- |
| PyMuPDF 1.28.2 | AGPL-3.0 or Artifex commercial license | Used for PDF processing/export; its upstream terms remain applicable |
| Marker 1.10.2 | GPL-3.0-or-later | Modified AI Pubs Open RAIL-M model terms; separate eligibility/use conditions |
| Surya 0.17.1 | GPL-3.0-or-later | Modified AI Pubs Open RAIL-M model terms; separate eligibility/use conditions |
| YomiToku 0.15.0 (optional) | CC BY-NC-SA 4.0 | Associated weights also CC BY-NC-SA 4.0; commercial use requires a suitable separate license |
| Gemma `gemma4:12b-it-qat`, `gemma4:26b-a4b-it-qat` | Served by separately installed Ollama | These exact local tags report Apache-2.0 in `ollama show --license`; recheck the exact artifact when obtaining weights |
| Streamlit 1.47.0 | Apache-2.0 | Application UI |
| markdown2 2.5.5 | MIT (installed metadata) | Build-time static documentation rendering |
| Requests 2.32.4 | Apache-2.0 | Loopback HTTP client |
| Pillow 10.4.0 | HPND | Image processing |
| PyTorch 2.10.0 | BSD-3-Clause | GPU runtime; bundled CUDA components have separate vendor terms |
| Torchvision 0.25.0 | BSD (installed metadata) | Vision utilities; preserve the installed license |
| Transformers 4.57.6 | Apache-2.0 | Model execution utilities; does not license model weights |
| OpenCV Python headless 4.11.0.86 | Apache-2.0 (installed metadata) | Binary wheels include additional third-party notices |
| Playwright 1.63.0 | Apache-2.0 | Python browser automation used by the dedicated Chrome capture path; browser binaries have their own notices |

This is a focused inventory, not a complete transitive dependency SBOM. Follow upstream notices and preserve required attribution. We do not bundle third-party environments or model weights. Separate installation does not waive their use conditions or automatically resolve license compatibility.

**Marker is not a blanket commercial-use replacement for YomiToku.** Its versioned documentation describes additional model-weight conditions; verify the actual downloaded weights and your intended use before commercial deployment. YomiToku is not automatically selected merely because it is installed. Optional integration is retained for permitted local use; it is not a legal opinion that CC BY-NC-SA and AGPL form a distributable combined work.

YomiToku integration uses a separate `.venv-yomitoku` Python environment and a child process launched by `worker.py`; job configuration, page images and OCR results are exchanged through files. The adapter is `yomitoku_worker.py`. The intended source-only release excludes the YomiToku environment and weights; these exist separately in the local development setup. These execution facts do not determine the legal classification of a combined distribution.

Primary sources:
- [Playwright upstream license](https://github.com/microsoft/playwright-python/blob/main/LICENSE) (installed 1.63.0 metadata and packaged LICENSE also checked)
- [PyMuPDF licensing](https://pymupdf.readthedocs.io/en/latest/about.html)
- [Marker 1.10.2 terms](https://github.com/datalab-to/marker/blob/v1.10.2/README.md#commercial-usage)
- [Surya 0.17.1 terms](https://github.com/datalab-to/surya/blob/v0.17.1/README.md)
- [YomiToku license and commercial options](https://github.com/kotaro-kinoshita/yomitoku/blob/master/README_EN.md#license)

Do not publish purchased-book text/images, credentials, browser profiles or private processing records with the software. Only process content you are entitled to use under applicable law and service terms. Book OCR Studio is not affiliated with Amazon. Software licensing does not authorize redistribution of exported books.

See `docs/legal/PUBLIC_SCOPE.md` for release scope and unresolved checks. Inventory checked on 2026-09-23.

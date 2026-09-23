# Publishing this source package on Hugging Face

Create a **Space with the Static SDK**. Upload the contents of the release
directory at repository root, including hidden `.gitignore`. Do not upload
its parent directory or a live application workspace.

`README.md` contains `sdk: static` and `app_file: index.html`. This is a
static distribution page: it does not run `app.py`, request a cloud GPU,
connect to a visitor's Chrome, or receive books. The downloadable
`book-ocr-studio-source.zip` contains the same allowlisted application source.
OCR runs after local installation on the visitor's Linux computer.

Do not choose a model repository: this release is application source,
not fine-tuned Gemma weights. No model weights or inference service are
included. HF access tokens are never required by the release builder.

Before upload:

```bash
python3 scripts/verify_public.py .
```

Review `RELEASE_NOTES.md`, `THIRD_PARTY_NOTICES.md`, `LICENSE`, and
`BUILD_MANIFEST.json`. The manifest hashes every copied payload file;
`ARCHIVE_SHA256.txt` records the source ZIP hash. These checks detect
accidental changes, not authenticity against a malicious replacement of
the entire package. All inspection records describe their tested scope.

Official HF format references:
- https://huggingface.co/docs/hub/spaces-sdks-static
- https://huggingface.co/docs/hub/spaces-config-reference

Creating the local package does not publish it. Public release remains a
separate owner action after reviewing the exact package.

## Rebuilding a modified source package

In an installed development checkout, update the Markdown originals, then run:

```bash
.venv/bin/python scripts/render_public_docs.py
.venv/bin/python scripts/build_public.py /path/to/a/new-release-directory
```

The builder requires the pinned markdown2 dependency and rejects stale generated
HTML. It never modifies an existing release directory. Keep prior review hashes
with the prior release; a revised ZIP has a different hash. Models downloaded
by local setup and model-settings.json must not be added to the allowlist.

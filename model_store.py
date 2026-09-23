"""Shared model-store selection for setup and GPU workers; no network actions."""
import json
import os
from pathlib import Path

DEFAULT_MODEL = 'gemma4:12b-it-qat'
OPTIONAL_MODEL = 'gemma4:26b-a4b-it-qat'

def model_directory(root, *, setup=False):
    root = Path(root)
    if os.environ.get('BOOK_OCR_MODELS'):
        return Path(os.environ['BOOK_OCR_MODELS']).expanduser().resolve()
    settings = root/'model-settings.json'
    if settings.exists():
        data = json.loads(settings.read_text(encoding='utf-8'))
        value = data.get('models_directory')
        if not isinstance(value, str) or not value or not Path(value).is_absolute():
            raise ValueError('Invalid model-settings.json: models_directory must be an absolute path')
        return Path(value)
    # Preserve the old installation path only for existing, unconfigured workers.
    legacy = Path('/usr/share/ollama/.ollama/models')
    if not setup and legacy.is_dir():
        return legacy
    return (root/'models').resolve()

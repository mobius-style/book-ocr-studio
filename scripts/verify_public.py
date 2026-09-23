"""Verify the source package; unknown files, symlinks or changed bytes fail."""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

GENERATED = {'BUILD_MANIFEST.json', 'book-ocr-studio-source.zip', 'ARCHIVE_SHA256.txt'}

def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'BUILD_MANIFEST.json').read_text())['files']
    allowlist = {line.strip() for line in (root/'public-release-files.txt').read_text().splitlines()
                 if line.strip() and not line.startswith('#')}
    assert set(manifest) == allowlist, 'Manifest differs from allowlist'
    paths = list(root.rglob('*'))
    assert not any(p.is_symlink() for p in paths), 'Symlink in package'
    actual = {p.relative_to(root).as_posix() for p in paths if p.is_file()}
    # Extracted source ZIPs omit the outer archive/checksum, but retain the manifest.
    expected = allowlist | {'BUILD_MANIFEST.json'}
    if (root/'book-ocr-studio-source.zip').exists():
        expected |= {'book-ocr-studio-source.zip', 'ARCHIVE_SHA256.txt'}
    assert actual == expected, 'Unexpected or missing files: '+str(actual ^ expected)
    for name, record in manifest.items():
        rel = Path(name)
        assert not rel.is_absolute() and '..' not in rel.parts
        assert not set(rel.parts) & {'jobs', 'captures', 'backups', '.git', '.venv', '.venv-yomitoku', '__pycache__', 'evidence', 'models', '.connector-profiles'}
        assert rel.name not in {'config.js', '.chrome-bridge-key', 'environment.json', 'gpu-profile.json', 'model-settings.json'}
        data = (root/name).read_bytes()
        assert len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'], name
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError('Binary payload rejected by text-only release policy: '+name) from exc
        # Local user paths, common token forms and PEM private keys are not source assets.
        assert not re.search(r'/home/' + r'[^/\s]+/', text), 'Personal path: '+name
        assert not re.search(r'\b(?:hf_' + r'[A-Za-z0-9]{20,}|sk-' + r'[A-Za-z0-9]{24,})\b', text), 'Token: '+name
        assert '-----BEGIN ' + 'PRIVATE KEY-----' not in text, 'Private key: '+name
    if (root/'book-ocr-studio-source.zip').exists():
        archive = root/'book-ocr-studio-source.zip'
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == (root/'ARCHIVE_SHA256.txt').read_text().split()[0]
        with zipfile.ZipFile(archive) as package:
            assert len(package.namelist()) == len(set(package.namelist()))
            assert set(package.namelist()) == allowlist | {'BUILD_MANIFEST.json'}
            for name in package.namelist():
                assert package.read(name) == (root/name).read_bytes(), 'Archive mismatch: '+name
    print('PASS source package:', len(manifest), 'allowlisted files; hashes and exclusions checked')

if __name__ == '__main__':
    sys.dont_write_bytecode = True
    verify(sys.argv[1] if len(sys.argv)>1 else '.')

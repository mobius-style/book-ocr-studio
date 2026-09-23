"""Build a new, source-only directory from an explicit reviewed allowlist."""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Destination already exists; use a new release directory')
    names = [line.strip() for line in (ROOT/'public-release-files.txt').read_text().splitlines()
             if line.strip() and not line.startswith('#')]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate allowlist entry')
    from render_public_docs import PAGES, render
    for original, generated in PAGES.items():
        if (ROOT/generated).read_text(encoding='utf-8') != render(original):
            raise ValueError('Stale HTML; run scripts/render_public_docs.py: '+generated)
    payload = {}
    secret_file = ROOT/'.chrome-bridge-key'
    private_key = secret_file.read_bytes().strip() if secret_file.exists() else b''
    private_keys = [private_key] if private_key else []
    for profile in (ROOT/'.connector-profiles').glob('*.json'):
        secret = json.loads(profile.read_text()).get('api_key', '')
        if secret:private_keys.append(secret.encode())
    for name in names:
        rel = Path(name)
        source = ROOT/rel
        if rel.is_absolute() or '..' in rel.parts or source.is_symlink() or not source.is_file():
            raise ValueError('Invalid allowlist entry: '+name)
        if not source.resolve().is_relative_to(ROOT):
            raise ValueError('Source escapes project')
        data = source.read_bytes()
        if any(secret in data for secret in private_keys):
            raise ValueError('Local credential found in allowlisted file: '+name)
        payload[name] = data
    destination.mkdir(parents=True)
    for name, data in payload.items():
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o755 if name.endswith('.sh') else 0o644)
    manifest = {'format': 1, 'scope': 'source-only', 'files': {
        name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        for name, data in sorted(payload.items())}}
    (destination/'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n')
    archive = destination/'book-ocr-studio-source.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for name in sorted([*payload, 'BUILD_MANIFEST.json']):
            output.write(destination/name, name)
    (destination/'ARCHIVE_SHA256.txt').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    from verify_public import verify
    verify(destination)
    print('Built', destination)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 scripts/build_public.py NEW_DESTINATION')
    build(sys.argv[1])

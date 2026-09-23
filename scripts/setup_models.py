"""Prepare local Gemma weights via an owned Ollama server; never run inference."""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import requests
from model_store import DEFAULT_MODEL, OPTIONAL_MODEL, model_directory

def prepare(root, model, *, executable=None):
    if model not in {DEFAULT_MODEL, OPTIONAL_MODEL}:
        raise ValueError('Unsupported model')
    executable = executable or shutil.which('ollama')
    if not executable:
        raise RuntimeError('Install Ollama first: https://ollama.com/download/linux; then rerun scripts/setup_models.py')
    root = Path(root)
    directory = model_directory(root, setup=True)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    host = f'127.0.0.1:{port}'
    env = os.environ.copy()
    env.update(OLLAMA_HOST=host, OLLAMA_MODELS=str(directory), OLLAMA_NO_CLOUD='1')
    print(f'Preparing {model} in {directory}. Missing weights require a multi-GB download.', flush=True)
    log_path = root/'model-setup.log'
    with log_path.open('ab') as log:
        process = subprocess.Popen([executable, 'serve'], env=env, stdout=log, stderr=log)
        try:
            with requests.Session() as client:
                client.trust_env = False  # Loopback must not pass through proxy environment variables.
                url = f'http://{host}/api/tags'
                models = None
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError('Owned Ollama server exited; inspect model-setup.log')
                    try:
                        response = client.get(url, timeout=1)
                        response.raise_for_status()
                        models = response.json()['models']
                        break
                    except requests.RequestException:
                        time.sleep(0.25)
                if models is None:
                    raise RuntimeError('Ollama startup timed out; inspect model-setup.log')
                if not any(item.get('name') == model for item in models):
                    subprocess.run([executable, 'pull', model], env=env, check=True)
                response = client.get(url, timeout=10)
                response.raise_for_status()
                found = next((item for item in response.json()['models'] if item.get('name') == model), None)
                if not found or not found.get('digest'):
                    raise RuntimeError('Download did not produce the requested model and digest')
                settings = root/'model-settings.json'
                data = json.loads(settings.read_text()) if settings.exists() else {}
                previous = data.get('models', {}) if data.get('models_directory') == str(directory) else {}
                data = dict(models_directory=str(directory), models={**previous, model: found['digest']})
                temporary = settings.with_name(settings.name+'.tmp-'+uuid.uuid4().hex)
                try:
                    with temporary.open('x', encoding='utf-8') as stream:
                        temporary.chmod(0o600)
                        json.dump(data, stream, indent=2)
                        stream.write('\n')
                    temporary.replace(settings)
                finally:
                    temporary.unlink(missing_ok=True)
                print(f'Ready: {model}; C1 OCR profile is supplied by the application.', flush=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=[DEFAULT_MODEL, OPTIONAL_MODEL], default=DEFAULT_MODEL)
    args = parser.parse_args()
    try:
        prepare(ROOT, args.model)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, requests.RequestException) as exc:
        print(f'Model setup incomplete: {exc}\nPython dependencies are retained. Rerun this command to retry.', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    os.umask(0o077)
    raise SystemExit(main())

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model_store import DEFAULT_MODEL, OPTIONAL_MODEL, model_directory
spec = importlib.util.spec_from_file_location('setup_models', ROOT/'scripts/setup_models.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

class SetupTests(unittest.TestCase):
    def exercise(self, initial, final, *, failure=False):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=False):
            os.environ.pop('BOOK_OCR_MODELS', None)
            root = Path(tmp)
            client = MagicMock()
            client.get.return_value.json.side_effect = [{'models': initial}, {'models': final}]
            with patch.object(setup.requests, 'Session') as session, patch.object(setup.subprocess, 'Popen') as popen, patch.object(setup.subprocess, 'run') as pull:
                session.return_value.__enter__.return_value = client
                popen.return_value.poll.return_value = None
                if failure:
                    pull.side_effect = subprocess.CalledProcessError(1, 'synthetic-pull')
                    with self.assertRaises(subprocess.CalledProcessError):
                        setup.prepare(root, DEFAULT_MODEL, executable='synthetic-ollama')
                    self.assertFalse((root/'model-settings.json').exists())
                elif not final:
                    with self.assertRaises(RuntimeError):
                        setup.prepare(root, DEFAULT_MODEL, executable='synthetic-ollama')
                    self.assertFalse((root/'model-settings.json').exists())
                else:
                    setup.prepare(root, DEFAULT_MODEL, executable='synthetic-ollama')
                    data = json.loads((root/'model-settings.json').read_text())
                    self.assertEqual(data['models'][DEFAULT_MODEL], 'synthetic-digest')
                    self.assertEqual(model_directory(root), root/'models')
                    self.assertEqual((root/'model-settings.json').stat().st_mode & 0o777, 0o600)
                if initial:
                    pull.assert_not_called()
                else:
                    self.assertEqual(pull.call_args.args[0], ['synthetic-ollama', 'pull', DEFAULT_MODEL])
                self.assertEqual(popen.call_args.kwargs['env']['OLLAMA_MODELS'], str(root/'models'))
                self.assertTrue(popen.call_args.kwargs['env']['OLLAMA_HOST'].startswith('127.0.0.1:'))
                popen.return_value.terminate.assert_called_once()

    def test_default_download_and_record(self):
        self.exercise([], [{'name': DEFAULT_MODEL, 'digest': 'synthetic-digest'}])

    def test_existing_model_reused(self):
        model = {'name': DEFAULT_MODEL, 'digest': 'synthetic-digest'}
        self.exercise([model], [model])

    def test_failed_download_has_no_success_record(self):
        self.exercise([], [], failure=True)

    def test_missing_model_after_pull_has_no_success_record(self):
        self.exercise([], [])

    def test_corrupt_configuration_does_not_silently_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=False):
            os.environ.pop('BOOK_OCR_MODELS', None)
            root = Path(tmp)
            (root/'model-settings.json').write_text('{}')
            with self.assertRaises(ValueError):
                model_directory(root)
            os.environ['BOOK_OCR_MODELS'] = str(root/'override')
            self.assertEqual(model_directory(root), root/'override')

    def test_optional_model_does_not_change_default(self):
        self.assertEqual(DEFAULT_MODEL, 'gemma4:12b-it-qat')
        self.assertEqual(OPTIONAL_MODEL, 'gemma4:26b-a4b-it-qat')

if __name__ == '__main__':
    unittest.main()

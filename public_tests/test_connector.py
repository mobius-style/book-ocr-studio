"""Local HTTP contract tests; no external service, books, model or GPU required."""
import base64
import io
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import review_connector as connector

class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.requests = []
        self.failure = 0
        self.choice_override = None
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.requests.append((self.path, data, self.headers.get('Authorization')))
                if owner.failure:
                    self.send_response(owner.failure); self.end_headers()
                    self.wfile.write(b'Provider error: synthetic-secret-do-not-export')
                    return
                text = '\n'.join(m['content'] if isinstance(m['content'], str) else
                                 '\n'.join(c.get('text', '') for c in m['content']) for m in data['messages'])
                if 'six-character uppercase code' in text:
                    result = {'code': 'AAAAAA'}
                elif 'Alternative A:' in text:
                    result = {'choice': 'A' if "Alternative A: 'hello'" in text else 'B', 'evidence': 'Visible synthetic glyphs'}
                else:
                    result = {'corrections': [{'before': 'he1lo', 'after': 'hello', 'reason': 'Visible letter'}], 'notes': []}
                body = owner.choice_override or {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}]}
                self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(json.dumps(body).encode())
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.cfg = dict(base_url=f'http://127.0.0.1:{self.server.server_port}/v1', model='synthetic-vision',
                        api_key='synthetic-secret-do-not-export', format='json_schema', token_field='max_tokens', consent=True)
        self.root_patch = patch.object(connector, 'ROOT', self.root); self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop(); self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def profile(self):
        with patch.object(connector.secrets, 'choice', return_value='A'):
            return connector.test_and_save(self.cfg)

    def test_probe_vision_format_and_secret_boundary(self):
        ident = self.profile()
        self.assertEqual(connector.model_for(ident), 'synthetic-vision')
        path, body, header = self.requests[0]
        self.assertEqual(path, '/v1/chat/completions')
        self.assertEqual(header, 'Bearer '+self.cfg['api_key'])
        self.assertNotIn('AAAAAA', json.dumps(body))
        parts = body['messages'][-1]['content']
        self.assertTrue(parts[1]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertEqual(body['response_format']['type'], 'json_schema')
        self.assertNotIn('think', body)
        self.assertEqual((self.root/'.connector-profiles'/f'{ident}.json').stat().st_mode & 0o777, 0o600)

    def test_refusal_consent_redirect_and_bad_probe(self):
        with self.assertRaises(ValueError): connector.test_and_save(dict(self.cfg, consent=False))
        self.assertEqual(len(self.requests), 0)
        for url in ['http://example.com/v1', 'https://user:secret@example.com/v1', 'https://example.com/v1?key=hidden']:
            with self.assertRaises(ValueError): connector.validate(dict(self.cfg, base_url=url))
        self.failure = 302
        with self.assertRaisesRegex(RuntimeError, 'HTTP 302'): self.profile()
        self.failure = 0
        self.choice_override = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"code":"WRONG"}'}}]}
        with self.assertRaisesRegex(ValueError, 'vision/JSON'): self.profile()
        self.assertFalse((self.root/'.connector-profiles').exists())

    def test_json_modes_length_and_error_redaction(self):
        payload = dict(model='synthetic-vision', format={'type': 'object'}, options={'num_predict': 512}, messages=[dict(role='user', content='JSON test')])
        for mode in ['json_object', 'prompt']:
            connector._completion(dict(self.cfg, format=mode, token_field='max_completion_tokens'), payload, (1, 2))
            sent = self.requests[-1][1]
            self.assertEqual(sent['max_completion_tokens'], 512)
            self.assertEqual('response_format' in sent, mode != 'prompt')
        self.failure = 401
        with self.assertRaises(RuntimeError) as error: connector._completion(self.cfg, payload, (1, 2))
        self.assertNotIn(self.cfg['api_key'], str(error.exception))
        self.failure = 0
        self.choice_override = {'choices': [{'finish_reason': 'length', 'message': {'content': self.cfg['api_key']}}]}
        result = connector._completion(self.cfg, payload, (1, 2))
        self.assertEqual(result['done_reason'], 'length')
        self.assertEqual(result['message']['content'], '[REDACTED]')

    def run_job(self, fail=False):
        from PIL import Image
        import core, worker
        ident = self.profile()
        image = Image.new('RGB', (200, 80), 'white'); data = io.BytesIO(); image.save(data, format='PNG')
        with patch.object(core, 'JOBS', self.root/'jobs'):
            job = core.new_job([('synthetic.png', data.getvalue())], spec='', model='synthetic-vision', review_connector=ident)
        # Deterministic OCR subprocess fixture exercises the actual worker subprocess path.
        (self.root/'marker_worker.py').write_text("import sys,json\nfrom pathlib import Path\np=Path(sys.argv[1])/'page-00001'\n(p/'original.md').write_text('he1lo')\n(p/'marker.json').write_text('{}')\n")
        if fail: self.failure = 401
        with patch.object(worker, 'ROOT', self.root), patch.object(worker, 'gpu_plan', return_value={'mode': 'sequential', 'ocr_gpu': 0, 'gemma_gpu': 0}), patch('calibrate_gpu.calibrate', return_value={}), patch.object(worker, 'LocalGemma', side_effect=AssertionError('External review must not start Gemma')):
            worker.run(job)
        self.assertEqual(core.read(job/'status.json')['state'], 'partial' if fail else 'done')
        self.assertEqual((job/'page-00001/original.md').read_text(), 'he1lo')
        self.assertTrue((job/'delivery.json').exists())
        if not fail:
            self.assertEqual((job/'page-00001/candidate.md').read_text(), 'hello')
            review = core.read(job/'page-00001/review.json')
            self.assertEqual(review['status'], 'candidate_unverified')
            self.assertEqual(review['prompt_profile'], 'c1_ocr_v3')
        for file in job.rglob('*'):
            if file.is_file(): self.assertNotIn(self.cfg['api_key'].encode(), file.read_bytes())
        archive = core.bundle(job)
        self.assertNotIn(self.cfg['api_key'].encode(), archive)

    def test_worker_completion_with_c1_and_preserved_original(self): self.run_job()
    def test_worker_retains_partial_results_on_provider_failure(self): self.run_job(fail=True)

    def test_optional_reasoning_and_exact_json_fence(self):
        payload = dict(model='synthetic-vision', format={'type': 'object'}, messages=[dict(role='user', content='JSON')])
        self.choice_override = {'choices': [{'finish_reason': 'stop', 'message': {'content': '```json\n{"code":"AAAAAA"}\n```'}}]}
        result = connector._completion(dict(self.cfg, reasoning_effort='none'), payload, (1, 2))
        self.assertEqual(self.requests[-1][1]['reasoning_effort'], 'none')
        self.assertEqual(json.loads(result['message']['content']), {'code':'AAAAAA'})
        self.profile()
        self.assertNotIn('reasoning_effort', self.requests[-1][1])
        self.choice_override['choices'][0]['message']['content'] = 'Commentary\n```json\n{"code":"AAAAAA"}\n```'
        with self.assertRaisesRegex(ValueError, 'vision/JSON'): self.profile()
        self.choice_override['choices'][0]['finish_reason'] = 'length'
        with self.assertRaisesRegex(ValueError, 'output-token limit'): self.profile()

    def test_missing_profile_fails_without_fallback(self):
        ident = self.profile()
        (self.root/'.connector-profiles'/f'{ident}.json').unlink()
        with self.assertRaises(ValueError):
            connector.chat_response('compat:'+ident, {}, (1, 2))
        self.assertEqual(len(self.requests), 1)

    def test_ui_requires_probe_again_after_settings_change(self):
        from streamlit.testing.v1 import AppTest
        ident = self.profile()
        from core import save
        capture = self.root/'capture'; (capture/'commands').mkdir(parents=True)
        save(capture/'settings.json', dict(headless=False))
        save(capture/'state.json', dict(phase='login', message='Ready', count=0))
        with patch('connector_ui.test_and_save', return_value=ident), patch('importlib.reload', side_effect=lambda module: module), patch('kindle_ui.active_session', return_value=capture), patch('kindle_ui.running', return_value=True):
            app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=25).run()
            app.selectbox(key='review_provider').select('Advanced: OpenAI-compatible API').run()
            self.assertFalse(app.exception)
            starts = lambda: [b for b in app.button if b.label in {'Start conversion', 'Start — Save book as MD'}]
            self.assertGreaterEqual(len(starts()), 2)
            self.assertTrue(all(b.disabled for b in starts()))
            app.text_input(key='connector_model').input('synthetic-vision').run()
            app.checkbox(key='connector_consent').check().run()
            next(b for b in app.button if b.label == 'Test vision connection and enable').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.session_state['review_ready'])
            self.assertTrue(all(not b.disabled for b in starts()))
            self.assertEqual(app.session_state['active_review_options']['review_connector'], ident)
            app.text_input(key='connector_model').input('changed-model').run()
            self.assertTrue(all(b.disabled for b in starts()))
            app.selectbox(key='review_provider').select('Recommended: Local Gemma 4').run()
            self.assertTrue(app.session_state['review_ready'])
            self.assertIsNone(app.session_state['active_review_options']['review_connector'])

    def test_capture_options_propagate_provider(self):
        from capture_options import apply_options
        from core import read, save
        ident = self.profile()
        capture = self.root/'captures/session'; capture.mkdir(parents=True)
        job = self.root/'job'; job.mkdir()
        save(capture/'conversion-options.json', dict(model='synthetic-vision', ocr_engine='marker', review_connector=ident))
        cfg = apply_options(job, {'autopilot': {'source_capture': str(capture)}}, self.root, read, save)
        self.assertEqual(cfg['review_connector'], ident)
        self.assertEqual(cfg['model'], 'synthetic-vision')

if __name__ == '__main__': unittest.main()

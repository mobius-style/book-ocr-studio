"""Synthetic tests: no purchased text, model downloads or GPU inference."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class ReleaseTests(unittest.TestCase):
    def test_capture_profile_is_private_local(self):
        from kindle_capture import PROFILE, CAPTURES, validate_reader_url
        self.assertEqual(PROFILE, CAPTURES/'chrome-profile')
        self.assertTrue(PROFILE.is_relative_to(ROOT))
        self.assertEqual(validate_reader_url('https://read.amazon.com/'), 'https://read.amazon.com/')
        with self.assertRaises(ValueError):
            validate_reader_url('https://example.com/')

    def test_ui_bridge_is_explicit(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ, {}, clear=False), patch('chrome_job.ensure_bridge') as bridge:
            os.environ.pop('BOOK_OCR_ENABLE_BRIDGE', None)
            app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=25).run()
            self.assertFalse(app.exception)
            bridge.assert_not_called()
            button = next(b for b in app.button if b.label == 'Enable local Chrome bridge')
            button.click().run()
            self.assertFalse(app.exception)
            bridge.assert_called_once()

    def test_offline_exports_preserve_synthetic_source(self):
        from PIL import Image, ImageDraw
        import pymupdf
        from core import save
        from delivery import ensure_delivery
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp)
            folder = job/'page-00001'
            folder.mkdir()
            text = 'Synthetic garden notes\nThree green leaves.\n合成テスト：葉は三枚です。'
            (folder/'original.md').write_text(text, encoding='utf-8')
            image = Image.new('RGB', (700, 400), 'white')
            ImageDraw.Draw(image).text((30, 30), 'Synthetic garden notes. Three green leaves.', fill='black')
            image.save(folder/'source.png')
            save(job/'job.json', dict(title='Synthetic garden', author='Test author', kind='images',
                                      selected=[0], inputs=[dict(name='synthetic.png')]))
            (job/'original.md').write_text(text, encoding='utf-8')
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
            with patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')):
                result = ensure_delivery(job, include_html=True, include_pdf=True, include_epub=True)
            self.assertEqual(Path(result['path']).name, 'Synthetic garden_Test author.md')
            self.assertIn('Three green leaves.', Path(result['path']).read_text())
            with pymupdf.open(result['pdf_path']) as document:
                self.assertGreaterEqual(len(document), 2)
                self.assertIn('Three green leaves.', ''.join(page.get_text() for page in document))
            with zipfile.ZipFile(result['epub_path']) as archive:
                self.assertEqual(archive.infolist()[0].filename, 'mimetype')
                self.assertEqual(archive.read('EPUB/images/screen-00001.png'), (folder/'source.png').read_bytes())
                for name in archive.namelist():
                    if name.endswith(('.xml', '.opf', '.xhtml')):
                        ET.fromstring(archive.read(name))
                self.assertIn('葉は三枚', archive.read('EPUB/screen-00001.xhtml').decode())
            for name, digest in before.items():
                self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(), digest)

if __name__ == '__main__':
    unittest.main()

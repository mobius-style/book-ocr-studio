"""Prepare extension configuration. Installation/permission grant remains a browser action."""
import json
from chrome_bridge import key,ROOT
path=ROOT/'chrome-extension/config.js'
path.write_text('const BOOK_OCR_KEY='+json.dumps(key())+';\n');path.chmod(0o600)
print('Chrome bridge extension prepared at',path.parent)

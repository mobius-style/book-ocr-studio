"""Opt-in vision Chat Completions transport. Credentials never enter jobs."""
import base64
import io
import ipaddress
import json
import os
import re
import secrets
import uuid
from pathlib import Path
from urllib.parse import urlsplit
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent

def validate(settings):
    data = dict(settings)
    base = str(data.get('base_url', '')).strip().rstrip('/')
    parsed = urlsplit(base)
    try:
        loopback = parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = False
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Use a base URL without credentials, query parameters or fragments')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and loopback):
        raise ValueError('HTTPS is required except for loopback servers')
    if base.endswith('/chat/completions'):
        raise ValueError('Enter the API base URL, usually ending in /v1, not /chat/completions')
    model = str(data.get('model', '')).strip()
    if not model or len(model) > 200 or any(ord(c) < 32 for c in model):
        raise ValueError('Enter a valid vision model identifier')
    if data.get('format') not in {'json_schema', 'json_object', 'prompt'}:
        raise ValueError('Invalid JSON response mode')
    if data.get('token_field') not in {'max_tokens', 'max_completion_tokens'}:
        raise ValueError('Invalid output-token parameter')
    effort = data.get('reasoning_effort', 'server_default')
    if effort not in {'server_default', 'none', 'minimal', 'low', 'medium', 'high'}:
        raise ValueError('Invalid reasoning effort')
    key = str(data.get('api_key', ''))
    if any(ord(c) < 32 for c in key):
        raise ValueError('Invalid API key')
    return dict(base_url=base, model=model, format=data['format'], token_field=data['token_field'],
                api_key=key, consent=data.get('consent') is True, reasoning_effort=effort)

def load_profile(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise ValueError('Invalid connector profile')
    try:
        raw = json.loads((ROOT/'.connector-profiles'/f'{identifier}.json').read_text())
        result = validate(raw)
    except (OSError, ValueError, TypeError):
        raise ValueError('Connector profile is missing or invalid; configure and test again') from None
    if not result['consent'] or raw.get('vision_test_passed') is not True:
        raise ValueError('Connector requires consent and a successful synthetic vision test')
    return result

def model_for(identifier):
    return load_profile(identifier)['model']

def _completion(settings, payload, timeout):
    cfg = validate(settings)
    if not cfg['consent']:
        raise ValueError('Sending to this endpoint has not been enabled')
    messages = []
    for message in payload['messages']:
        content = message['content']
        if message.get('images'):
            content = [{'type': 'text', 'text': content}] + [
                {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,'+image}}
                for image in message['images']]
        messages.append(dict(role=message['role'], content=content))
    schema = payload.get('format', {})
    messages.insert(0, dict(role='system', content='Return only JSON matching this schema: '+json.dumps(schema)))
    request = dict(model=cfg['model'], messages=messages, stream=False)
    request[cfg['token_field']] = payload.get('options', {}).get('num_predict', 4096)
    if cfg['reasoning_effort'] != 'server_default':
        request['reasoning_effort'] = cfg['reasoning_effort']
    if cfg['format'] == 'json_schema':
        request['response_format'] = dict(type='json_schema', json_schema=dict(name='ocr_review', strict=True, schema=schema))
    elif cfg['format'] == 'json_object':
        request['response_format'] = dict(type='json_object')
    headers = {'Authorization': 'Bearer '+cfg['api_key']} if cfg['api_key'] else {}
    # No redirects, automatic retries, provider response dumps or ambient proxy credentials.
    with requests.Session() as client:
        client.trust_env = False
        try:
            response = client.post(cfg['base_url']+'/chat/completions', json=request,
                                   headers=headers, timeout=timeout, allow_redirects=False)
        except requests.RequestException:
            raise RuntimeError('Connector network/timeout failure. Saved results are preserved.') from None
        if response.status_code != 200:
            raise RuntimeError(f'Connector HTTP {response.status_code}; check endpoint, credentials, model and response mode. Provider error body is not saved.')
        try:
            choice = response.json()['choices'][0]
            message = choice['message']
            content = message['content']
            if message.get('refusal') or not isinstance(content, str):
                raise ValueError()
            finish = choice.get('finish_reason')
            if finish not in {'stop', 'length'}:
                raise ValueError()
        except (ValueError, KeyError, TypeError, IndexError):
            raise RuntimeError('Connector returned an unsupported response or refusal; original OCR is preserved.') from None
    # Some compatible servers wrap otherwise valid JSON in one Markdown fence.
    # Accept only an entire fenced JSON value, never extract JSON from prose.
    fenced = re.fullmatch(r'\s*```(?:json)?[ \t]*\n(.*?)\n```\s*', content, re.S | re.I)
    if fenced:
        try: json.loads(fenced[1])
        except ValueError: pass
        else: content = fenced[1]
    if cfg['api_key']:
        content = content.replace(cfg['api_key'], '[REDACTED]')
    return dict(message=dict(content=content), done_reason=finish)

def test_and_save(settings):
    cfg = validate(settings)
    code = ''.join(secrets.choice('23456789ABCDEFGHJKLMNPQRSTUVWXYZ') for _ in range(6))
    image = Image.new('RGB', (600, 150), 'white')
    ImageDraw.Draw(image).text((25, 25), code, fill='black', font=ImageFont.load_default(size=72))
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    schema = dict(type='object', properties={'code': {'type': 'string'}}, required=['code'], additionalProperties=False)
    body = _completion(cfg, dict(format=schema, options={'num_predict': 256}, messages=[dict(role='user',
        content='Read the six-character uppercase code in this image. Return JSON with exactly the key code.',
        images=[base64.b64encode(buffer.getvalue()).decode()])]), (10, 90))
    if body['done_reason'] == 'length':
        raise ValueError('Synthetic test reached the output-token limit. Try a lower reasoning effort if your server supports it; no book data was sent')
    try:
        answer = json.loads(body['message']['content'])
    except (ValueError, KeyError, TypeError):
        raise ValueError('Synthetic vision/JSON test failed; no book data was sent') from None
    if body['done_reason'] != 'stop' or answer != {'code': code}:
        raise ValueError('Synthetic vision/JSON test failed; no book data was sent')
    identifier = uuid.uuid4().hex
    directory = ROOT/'.connector-profiles'; directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    target = directory/f'{identifier}.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(dict(cfg, vision_test_passed=True), stream)
    return identifier

class _Response:
    status_code = 200
    def __init__(self, body): self.body = body
    def raise_for_status(self): pass
    def json(self): return self.body

def chat_response(endpoint, payload, timeout):
    if endpoint.startswith('compat:'):
        cfg = load_profile(endpoint.removeprefix('compat:'))
        if cfg['model'] != payload['model']:
            raise ValueError('Connector model differs from the saved job')
        return _Response(_completion(cfg, payload, timeout))
    return requests.post(endpoint+'/api/chat', json=payload, timeout=timeout)

"""Download names derived from explicit fields or local PDF metadata."""
import re
from pathlib import Path
import fitz

def book_details(job, cfg):
    title, author = cfg.get('title', ''), cfg.get('author', '')
    if not title and cfg.get('autopilot',{}).get('source_capture'):
        import json,html
        capture=Path(cfg['autopilot']['source_capture'])
        if (capture/'capture.json').exists():
            value=json.loads((capture/'capture.json').read_text()).get('title','').strip()
            if value and value.lower()!='kindle':title=value
        if not title and (capture/'start-ui.json').exists():
            header=json.loads((capture/'start-ui.json').read_text()).get('header','')
            matches=re.findall(r'<ion-title\b[^>]*>([^<]+)</ion-title>',header)
            if len(matches)==1:title=html.unescape(matches[0]).strip()

    if cfg.get('kind') == 'pdf':
        try:
            with fitz.open(Path(job)/'inputs'/cfg['inputs'][0]['file']) as doc:
                metadata = doc.metadata or {}
                title = title or metadata.get('title', '')
                author = author or metadata.get('author', '')
        except Exception:
            pass
    if not author:
        author = author_from_front_back(job)
    title = str(title or '').strip()
    author = str(author or '').strip()
    return title or Path(cfg['inputs'][0]['name']).stem, author

def markdown_name(title, author='', override=''):
    def safe(value):
        return re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]', '_', str(value)).strip(' .')
    def limit(value, budget):
        return value.encode('utf-8')[:budget].decode('utf-8',errors='ignore').rstrip(' .')
    if override.strip():
        name=override.strip()
        if name.lower().endswith('.md'):name=name[:-3]
        name=limit(safe(name),240)
    else:
        author=limit(safe(author),110)
        suffix='_'+author if author else ''
        name=limit(safe(title),240-len(suffix.encode('utf-8')))+suffix
    return (name or 'document')+'.md'


def author_from_front_back(job):
    """Extract only an explicit author label in front/back OCR, never publisher credits."""
    pages=sorted(Path(job).glob('page-*/original.md'))
    sources=list(dict.fromkeys(pages[:3]+pages[-3:]))
    candidates=set()
    for path in sources:
        text=path.read_text(encoding='utf-8')
        for match in re.finditer(r'(?m)^[# \t]*著[ \t　]*者[ \t　]*[:：]?[ \t　]*(?:\n(?:[ \t　]*\n)*)?([^\n]+)',text):
            value=match[1].strip().strip('#').strip()
            if 1<len(value)<=80 and not re.search(r'^(発行|編集|出版|製作|著作権|Copyright|©)',value,re.I):
                candidates.add(value)
    return next(iter(candidates)) if len(candidates)==1 else ''

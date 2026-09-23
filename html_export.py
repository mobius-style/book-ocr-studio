"""Self-contained review HTML. OCR text is escaped, never executed."""
import base64,html,json
from pathlib import Path
from display_language import english_message

def render(job,cfg):
    esc=lambda s:html.escape(str(s),quote=True)
    from context_export import page_context
    sections=[]
    for idx in cfg['selected']:
        folder=Path(job)/f'page-{idx+1:05d}'
        if not (folder/'source.png').exists():continue
        image=base64.b64encode((folder/'source.png').read_bytes()).decode()
        error=json.loads((folder/'review-error.json').read_text()).get('error','') if (folder/'review-error.json').exists() else ''
        status='Suggestions available; approve or reject in the app' if (folder/'review.json').exists() else 'Not reviewed by Gemma'
        blocks=[]
        if (folder/'regions.json').exists():
            regions=json.loads((folder/'regions.json').read_text())['regions']
            for r in regions:
                blocks.append(f'<article><small>{esc(r["role"])} · Region {r["id"]+1} · Coordinates {esc(r["box"])}</small><pre>{esc(r["text"])}</pre></article>')
        else:
            text=(folder/'original.md').read_text() if (folder/'original.md').exists() else 'OCR incomplete'
            blocks=[f'<p>No region data; using the saved OCR reading order.</p><pre>{esc(text)}</pre>']
        context=page_context(folder)
        blocks.insert(0,'<article><h3>Text for model input</h3><p>'+esc(context['status'])+'</p><pre>'+esc(context['text'])+'</pre><h4>Applied changes</h4><pre>'+esc(json.dumps(context['edits'],ensure_ascii=False,indent=2))+'</pre><h4>Suggestions requiring review; not applied to the text</h4><pre>'+esc(json.dumps(context['pending'],ensure_ascii=False,indent=2))+'</pre><p>Unverified model notes: '+esc(' / '.join(context['notes']))+'</p></article>')
        sections.append(f'<section><h2>Page {idx+1}</h2><p>{esc(english_message(error or status))}</p><div class="pair"><img alt="Source page {idx+1}" src="data:image/png;base64,{image}"><div>{"".join(blocks)}</div></div></section>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>OCR review document</title><style>body{font:16px/1.7 sans-serif;margin:2rem;background:#f5f5f5;color:#222}.pair{display:grid;grid-template-columns:1fr 1fr;gap:2rem}.pair img{width:100%;position:sticky;top:1rem;align-self:start}article{background:white;padding:1rem;margin-bottom:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}small{color:#555}@media(max-width:800px){.pair{display:block}}</style><h1>Model input text, suggestions and source images</h1><p>Region order is detected automatically. Check it against the images. Original OCR is preserved. Model input text is original OCR or approved content. Unapproved suggestions are listed separately for review.</p>'+''.join(sections)+'</html>'

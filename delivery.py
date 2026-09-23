"""One named MD/HTML delivery for both upload and capture UIs."""
import hashlib,json,os,uuid
from pathlib import Path
from download_names import book_details,markdown_name
from html_export import render
from context_export import render as render_context, VERSION
from portable_export import VERSION as PORTABLE_VERSION, write_pdf, write_epub

def ensure_delivery(job, *, include_html=False, include_pdf=False, include_epub=False):
    import fcntl
    with (Path(job)/'delivery.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _ensure_delivery(job,include_html=include_html,include_pdf=include_pdf,include_epub=include_epub)

def _ensure_delivery(job, *, include_html=False, include_pdf=False, include_epub=False):
    from core import read,save
    job=Path(job).resolve();cfg=read(job/'job.json')
    title,author=book_details(job,cfg)
    name=markdown_name(title,author,cfg.get('download_name',''))
    files=[job/'original.md',job/'job.json']
    for p in sorted(job.glob('page-*')):
        for n in ('source.png','original.md','candidate.md','decision.json','regions.json','review.json','review-error.json'):
            if (p/n).exists():files.append(p/n)
    stamp=hashlib.sha256(json.dumps(dict(version=VERSION,portable_version=PORTABLE_VERSION,title=title,author=author,name=name,files=[(str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in files]),ensure_ascii=False).encode()).hexdigest()
    record=job/'delivery.json'
    def publish(result):
        if (job/'output.json').exists():
            output=read(job/'output.json');output.update({k:result.get(k) for k in ('path','html_path','pdf_path','epub_path')})
            save(job/'output.json',output)
        return result
    def with_formats(result):
        for suffix,requested in [('html',include_html),('pdf',include_pdf),('epub',include_epub)]:
            key=suffix+'_path'
            if requested and not result.get(key):
                target=Path(result['path']).with_suffix('.'+suffix)
                temp=target.with_name('.tmp-'+uuid.uuid4().hex)
                try:
                    if suffix=='html':temp.write_text(render(job,cfg),encoding='utf-8')
                    elif suffix=='pdf':write_pdf(job,cfg,temp)
                    else:write_epub(job,cfg,temp)
                    os.replace(temp,target)
                finally:temp.unlink(missing_ok=True)
                result[key]=str(target)
                save(record,result)
        return publish(result)
    if record.exists():
        prior=read(record)
        if prior.get('stamp')==stamp and all(Path(prior[k]).is_file() for k in ('path','original_path')):
            for key in ('html_path','pdf_path','epub_path'):
                if prior.get(key) and not Path(prior[key]).is_file():prior[key]=None
            return with_formats(prior)
    if record.exists():
        prior=read(record)
        archive=job/'delivery-history'/prior.get('stamp','legacy')
        archive.mkdir(parents=True,exist_ok=True)
        for key in ('path','html_path','pdf_path','epub_path'):
            if not prior.get(key):continue
            source=Path(prior[key]);target=archive/source.name
            if source.exists() and not target.exists():
                with target.open('xb') as f:f.write(source.read_bytes())
    out=job/'delivery';out.mkdir(exist_ok=True)
    md=out/name;html=out/(name[:-3]+'.html')
    def write(path,text):
        temp=path.with_name('.tmp-'+uuid.uuid4().hex)
        temp.write_text(text,encoding='utf-8');os.replace(temp,path)
    context,manifest=render_context(job,cfg)
    raw=out/'OCR-original.md'
    write(raw,(job/'original.md').read_text(encoding='utf-8'))
    write(md,context)
    save(out/'context-manifest.json',manifest)
    result=dict(path=str(md),html_path=None,pdf_path=None,epub_path=None,original_path=str(raw),context_version=VERSION,title=title,author=author,stamp=stamp)
    save(record,result)
    return with_formats(result)

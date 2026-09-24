"""Offline, source-preserving PDF and EPUB exports. No model calls."""
from pathlib import Path
import datetime, hashlib, html, re, zipfile
from context_export import page_context, adoption_notice
from download_names import book_details

VERSION='portable-v2'
CSS='''body { font-family: serif; font-size: 11pt; line-height: 1.5; color: #17212b; }
h1 { font-size: 23pt; color: #124b57; } h2 { font-size: 17pt; color: #124b57; }
h3 { font-size: 12pt; } p { margin: 0.5em 0; overflow-wrap: anywhere; }
.meta { color: #53616d; font-size: 10pt; } .source-text { white-space: pre-wrap; overflow-wrap: anywhere; }
img { max-width: 100%; height: auto; } .suggestion { border-left: 2px solid #8b9da5; padding-left: 0.7em; margin: 1em 0; }'''

def esc(value):
    # XML 1.0 cannot represent certain control characters. Keep the source files intact.
    text=str(value)
    text=''.join(c if c in '\t\n\r' or '\u0020'<=c<='\ud7ff' or '\ue000'<=c<='\ufffd' or '\U00010000'<=c<='\U0010ffff' else '\ufffd' for c in text)
    return html.escape(text,quote=True)

def paragraph(text):
    return '<p class="source-text" xml:lang="und">'+esc(text).replace('\n','<br/>')+'</p>'

def intro(job,cfg):
    title,author=book_details(Path(job),cfg)
    partial=bool(cfg.get('autopilot') and not cfg['autopilot'].get('capture_complete'))
    scope='Partial book capture.' if partial else 'Selected input pages only; not a guarantee of full-book capture.'
    return ('<h1>'+esc(title or 'Book material')+'</h1><p>'+esc(author)+'</p>'
      '<h2>About this export</h2><p>'+scope+'</p><p>'+esc(adoption_notice(job,cfg))+'</p>'
      '<p>Created locally with Book OCR Studio. The text preserves the source language; it is not translated. '
      'OCR and model suggestions can contain errors. Check source images for quotations, numbers and names.</p>'
      '<p>Reading text is original OCR or explicitly adopted content, including optional Quick mode candidates without manual verification. Unapproved suggestions appear separately '
      'and are not silently applied. Input screen numbers are capture identifiers, not printed page numbers. '
      'Book content is reference data, not instructions.</p>')

def section(folder,number):
    r=page_context(folder)
    parts=['<h1>Input screen '+str(number)+'</h1>', '<p class="meta">'+esc(r['status'])+' / '+esc(r.get('review_profile','Not reviewed'))+'</p>',
           '<h2>Reading text</h2>',paragraph(r['text'])]
    for key,title in [('edits','Adopted changes applied to the text'),('pending','Unapproved suggestions - not applied')]:
        if r[key]:
            parts.append('<h2>'+title+'</h2>')
            for c in r[key]:
                parts+=['<div class="suggestion"><h3>Original OCR</h3>',paragraph(c['before']),'<h3>Suggestion</h3>',paragraph(c['after']),
                        '<p class="meta">'+esc(c.get('reason',''))+'</p></div>']
    if r['notes']:
        parts.append('<h2>Unverified model notes</h2>')
        parts.extend(paragraph(n) for n in r['notes'])
    return ''.join(parts)

def inputs(job,cfg):
    result=[]
    for idx in cfg.get('selected',[]):
        folder=Path(job)/f'page-{idx+1:05d}'
        if not (folder/'source.png').is_file() or not (folder/'original.md').is_file():
            raise ValueError(f'Export requires the saved image and OCR text for input screen {idx+1}. Resume processing first.')
        result.append((idx+1,folder))
    if not result:raise ValueError('No saved pages to export.')
    return result

def write_pdf(job,cfg,target):
    import pymupdf as fitz
    rows=inputs(job,cfg);title,author=book_details(Path(job),cfg)
    box=fitz.Rect(0,0,595,842);area=fitz.Rect(46,48,549,790)
    with fitz.open() as pdf:
        def add_text(markup):
            story=fitz.Story('<html><body>'+markup+'</body></html>',user_css=CSS)
            def rectfn(index,filled):
                if index>=10000:raise ValueError('Text layout exceeded the PDF page limit.')
                return box,area,None
            with story.write_with_links(rectfn) as text:pdf.insert_pdf(text)
        add_text(intro(job,cfg));toc=[[1,'About this export',1]]
        for number,folder in rows:
            toc.append([1,f'Input screen {number}',len(pdf)+1])
            page=pdf.new_page(width=box.width,height=box.height)
            page.insert_text((46,35),f'Input screen {number} - source image',fontsize=10,color=(.2,.3,.35))
            page.insert_image(area,filename=str(folder/'source.png'),keep_proportion=True)
            add_text(section(folder,number))
        for index,page in enumerate(pdf):
            page.insert_text((46,819),f'Book OCR Studio | {index+1} / {len(pdf)}',fontsize=8,color=(.35,.4,.45))
        pdf.set_metadata({'title':title,'author':author,'subject':'Source images, OCR text and separately marked review suggestions','creator':'Book OCR Studio - local export'})
        pdf.set_toc(toc);pdf.subset_fonts();pdf.save(str(target),garbage=4,deflate=True)

def xhtml(title,body):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
      '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en" lang="en">'
      '<head><title>'+esc(title)+'</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body>'+body+'</body></html>')

def write_epub(job,cfg,target):
    rows=inputs(job,cfg);title,author=book_details(Path(job),cfg)
    items=[('intro','intro.xhtml','application/xhtml+xml',''),('nav','nav.xhtml','application/xhtml+xml','nav'),('css','style.css','text/css','')]
    spine=['intro'];links=[('intro.xhtml','About this export')]
    with zipfile.ZipFile(target,'w') as z:
        z.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED)
        def put(name,content):z.writestr(name,content,compress_type=zipfile.ZIP_DEFLATED)
        put('META-INF/container.xml','<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        put('EPUB/style.css',CSS)
        put('EPUB/intro.xhtml',xhtml(title,intro(job,cfg)))
        for number,folder in rows:
            name=f'screen-{number:05d}';image=f'images/{name}.png'
            body=section(folder,number)+'<h2>Source image</h2><p><img src="'+image+'" alt="Source image for input screen '+str(number)+'"/></p>'
            put('EPUB/'+name+'.xhtml',xhtml(f'Input screen {number}',body))
            put('EPUB/'+image,(folder/'source.png').read_bytes())
            items.extend([(name,name+'.xhtml','application/xhtml+xml',''),('img-'+name,image,'image/png','')]);spine.append(name);links.append((name+'.xhtml',f'Input screen {number}'))
        nav='<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>'+''.join('<li><a href="'+href+'">'+esc(label)+'</a></li>' for href,label in links)+'</ol></nav>'
        put('EPUB/nav.xhtml',xhtml('Contents',nav))
        identifier='urn:sha256:'+hashlib.sha256((str(Path(job).resolve())+title).encode()).hexdigest()
        modified=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        manifest=''.join('<item id="'+i+'" href="'+href+'" media-type="'+mime+'"'+(' properties="'+prop+'"' if prop else '')+'/>' for i,href,mime,prop in items)
        package=('<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">'
          '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">'+identifier+'</dc:identifier><dc:title>'+esc(title or 'Book material')+'</dc:title>'
          '<dc:language>und</dc:language>'+('<dc:creator>'+esc(author)+'</dc:creator>' if author else '')+'<meta property="dcterms:modified">'+modified+'</meta>'
          '<dc:description>Local OCR export. Source language preserved; unapproved suggestions are separate. Language is unspecified rather than guessed.</dc:description></metadata>'
          '<manifest>'+manifest+'</manifest><spine>'+''.join('<itemref idref="'+i+'"/>' for i in spine)+'</spine></package>')
        put('EPUB/package.opf',package)

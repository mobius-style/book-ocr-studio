"""Review bounded region images, checkpointing successful responses."""
import difflib, hashlib
from PIL import Image

def grouped(regions,original,locked=()):
    groups=[]
    for n,r in enumerate(regions):
        item=dict(r,first=n,last=n,legacy=n in locked)
        if groups:
            prev=groups[-1]
            same_kind=(prev.get('role')=='figure_text')==(r.get('role')=='figure_text')
            same_part=prev.get('part')==r.get('part')
            # Adjacent vertical columns may share a crop, but horizontal columns must not.
            pb=prev['box'];rb=r['box']
            vertical=(pb[3]-pb[1]>2*(pb[2]-pb[0]) and rb[3]-rb[1]>2*(rb[2]-rb[0]) and
                min(pb[3],rb[3])-max(pb[1],rb[1])>0.7*min(pb[3]-pb[1],rb[3]-rb[1]) and
                max(pb[0],rb[0])-min(pb[2],rb[2])<48 and max(pb[2],rb[2])-min(pb[0],rb[0])<400)
            # Preserve source order and paragraph separators, up to 700 chars.
            if not prev['legacy'] and not item['legacy'] and same_kind and same_part and r['end']-prev['start']<=700 and (vertical or min(prev['box'][2],r['box'][2])-max(prev['box'][0],r['box'][0])>0.5*min(prev['box'][2]-prev['box'][0],r['box'][2]-r['box'][0])):
                prev['end']=r['end'];prev['last']=n
                prev['text']=original[prev['start']:prev['end']]
                prev['box']=[min(prev['box'][0],r['box'][0]),min(prev['box'][1],r['box'][1]),max(prev['box'][2],r['box'][2]),max(prev['box'][3],r['box'][3])]
                continue
        groups.append(item)
    return groups

def review(folder,model,endpoint,review_one,read,save):
    from core import OCR_PROFILE
    original=(folder/'original.md').read_text()
    regions=read(folder/'regions.json')['regions']
    replacements=[];corrections=[];deferred=[];notes=[];last=0
    with Image.open(folder/'source.png') as source:
        locked=[]
        for n,r in enumerate(regions):
            a,b=r['start'],r['end']
            if a<last or original[a:b]!=r['text'].strip():raise ValueError('Region data does not match the original OCR')
            last=b
            x1,y1,x2,y2=r['box']
            if not (0<=x1<x2<=source.width and 0<=y1<y2<=source.height):raise ValueError('Region coordinates are outside the image')
            # Retain successful old per-region requests, without trusting stale text.
            old=folder/'review-regions'/f'{n:04d}'/'0000'
            if len(original[a:b])<=3000 and (old/'review.json').exists():
                meta=read(old/'review.json')
                import io
                buf=io.BytesIO();source.crop((x1,y1,x2,y2)).save(buf,format='PNG')
                if meta.get('prompt_profile')==OCR_PROFILE and meta.get('model')==model and meta.get('original_sha256')==hashlib.sha256(original[a:b].encode()).hexdigest() and meta.get('source_sha256')==hashlib.sha256(buf.getvalue()).hexdigest():locked.append(n)
        groups=grouped(regions,original,locked)
        save(folder/'review-plan.json',dict(original_regions=len(regions),groups=len(groups),legacy_cached=len(locked),model=model))
        for r in groups:
            a,b=r['start'],r['end'];x1,y1,x2,y2=r['box']
            part=(folder/'review-regions'/f'{r["first"]:04d}') if r['legacy'] else (folder/'review-groups'/f'{r["first"]:04d}-{r["last"]:04d}')
            part.mkdir(parents=True,exist_ok=True)
            chunk=original[a:b]
            # Split long text into bounded requests, retaining the same region image.
            for k,start in enumerate(range(0,len(chunk),3000)):
                if (folder.parent/'cancel').exists():raise RuntimeError('Stop requested. Completed region reviews are saved.')
                unit=part/f'{k:04d}';unit.mkdir(exist_ok=True)
                text=chunk[start:start+3000]
                sha=hashlib.sha256(text.encode()).hexdigest()
                image=source.crop((max(0,x1-12),max(0,y1-12),min(source.width,x2+12),min(source.height,y2+12)))
                if not r['legacy']:
                    # Keep vision work bounded and avoid degenerate skinny inputs.
                    image.thumbnail((1024,1024))
                    canvas=Image.new('RGB',(max(64,image.width,(image.height+3)//4),max(64,image.height,(image.width+3)//4)),'white')
                    canvas.paste(image,(0,0));image=canvas
                image.save(unit/'source.png')
                image_sha=hashlib.sha256((unit/'source.png').read_bytes()).hexdigest()
                cached=read(unit/'review.json') if (unit/'review.json').exists() else {}
                (unit/'original.md').write_text(text)
                if cached.get('prompt_profile')!=OCR_PROFILE or cached.get('original_sha256')!=sha or cached.get('source_sha256')!=image_sha or cached.get('model')!=model:
                    review_one(unit,model,endpoint)
                result=read(unit/'review.json')
                candidate=(unit/'candidate.md').read_text()
                if hashlib.sha256(candidate.encode()).hexdigest()!=result['candidate_sha256']:raise ValueError('Region candidate hash mismatch')
                replacements.append((a+start,a+start+len(text),candidate))
                corrections.extend(result['corrections']);deferred.extend(result.get('deferred_corrections',[]));notes.extend(result['notes'])
    candidate=original
    for a,b,text in reversed(replacements):candidate=candidate[:a]+text+candidate[b:]
    (folder/'candidate.md').write_text(candidate)
    (folder/'changes.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile='OCR',tofile='Gemma candidate')))
    digest=lambda b:hashlib.sha256(b).hexdigest()
    save(folder/'review.json',dict(corrections=corrections,notes=notes,model=model,
        original_sha256=digest(original.encode()),candidate_sha256=digest(candidate.encode()),
        source_sha256=digest((folder/'source.png').read_bytes()),status='candidate_unverified',deferred_corrections=deferred,prompt_version=2,prompt_profile=OCR_PROFILE,region_requests=len(replacements)))

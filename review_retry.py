"""Bounded, checkpointed subdivision after a model output limit failure."""
import hashlib, difflib

def split_review(folder, model, endpoint, review_one, read, save, reason):
    from core import OCR_PROFILE
    original=(folder/'original.md').read_text()
    source=(folder/'source.png').read_bytes()
    digest=lambda data:hashlib.sha256(data).hexdigest()
    cut=len(original)//2
    nearby=original.rfind('\n',max(1,len(original)//4),max(2,3*len(original)//4))
    if nearby>0:cut=nearby+1
    pieces=[original[:cut],original[cut:]]
    candidates=[];corrections=[];deferred=[];notes=[]
    for index,text in enumerate(pieces):
        unit=folder/'retry-parts'/str(index);unit.mkdir(parents=True,exist_ok=True)
        (unit/'original.md').write_text(text);(unit/'source.png').write_bytes(source)
        cached=read(unit/'review.json') if (unit/'review.json').exists() else {}
        if not (cached.get('prompt_profile')==OCR_PROFILE and cached.get('model')==model and cached.get('original_sha256')==digest(text.encode())
                and cached.get('source_sha256')==digest(source)):
            review_one(unit,model,endpoint)
        result=read(unit/'review.json');candidate=(unit/'candidate.md').read_text()
        if digest(candidate.encode())!=result['candidate_sha256']:raise ValueError('Split candidate hash mismatch')
        candidates.append(candidate);corrections.extend(result['corrections']);deferred.extend(result.get('deferred_corrections',[]));notes.extend(result['notes'])
    candidate=''.join(candidates)
    (folder/'candidate.md').write_text(candidate)
    (folder/'changes.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile='OCR',tofile='Gemma candidate')))
    save(folder/'review.json',dict(corrections=corrections,notes=notes,model=model,
         original_sha256=digest(original.encode()),source_sha256=digest(source),
         candidate_sha256=digest(candidate.encode()),status='candidate_unverified',deferred_corrections=deferred,
         prompt_profile=OCR_PROFILE,retry_reason=reason,retry_parts=2))

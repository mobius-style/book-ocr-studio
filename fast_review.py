"""Review queue based on artifact content, not the presence of a diff file."""
import hashlib
import json


def page_state(folder):
    def digest(data): return hashlib.sha256(data).hexdigest()
    try:
        original = (folder/'original.md').read_bytes()
        if (folder/'review-error.json').exists(): return 'error'
        if not (folder/'review.json').exists(): return 'waiting'
        review = json.loads((folder/'review.json').read_text())
        candidate = (folder/'candidate.md').read_bytes()
        if (review.get('original_sha256') != digest(original) or
                review.get('candidate_sha256') != digest(candidate) or
                review.get('source_sha256') != digest((folder/'source.png').read_bytes())):
            return 'stale'
        decision = json.loads((folder/'decision.json').read_text()) if (folder/'decision.json').exists() else {}
        if decision.get('candidate_sha256') == digest(candidate) and isinstance(decision.get('accepted'), bool):
            return 'approved' if decision['accepted'] else 'original kept'
        if review.get('deferred_corrections'): return 'deferred'
        return 'unchanged' if original == candidate else 'changed'
    except (OSError, ValueError, TypeError):
        return 'error'


def pending_pages(job, numbers):
    return [n for n in numbers if page_state(job/f'page-{n:05d}') not in {'unchanged','approved','original kept'}]


def render(st, job, numbers, running, accept):
    from core import read
    from difflib import unified_diff
    states = {n: page_state(job/f'page-{n:05d}') for n in numbers}
    queue = pending_pages(job, numbers)
    st.caption(f"Needs attention: {len(queue)} · Unchanged: {sum(v=='unchanged' for v in states.values())} · Decided: {sum(v in {'approved','original kept'} for v in states.values())}")
    st.caption('Unchanged pages retain original OCR without being marked approved. Deferred, failed and stale reviews remain visible. Tab to a button and press Enter or Space; decisions apply to the whole page. Decided includes Quick mode adoption, even when only deferred proposals existed; these remain in the handoff.')
    if not queue:
        st.info('No pending page decisions. This does not establish OCR accuracy.')
        return
    n = st.selectbox('Next page needing attention', queue, format_func=lambda n:f'{n} — {states[n]}',key='fast-page-'+job.name)
    folder=job/f'page-{n:05d}'
    left,right=st.columns(2)
    with left: st.image(str(folder/'source.png'),caption=f'Source page {n}',use_container_width=True)
    with right:
        original=(folder/'original.md').read_text()
        candidate=(folder/'candidate.md').read_text() if (folder/'candidate.md').exists() else original
        st.code(''.join(unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile='Original OCR',tofile='Candidate')) or 'No text changes',language='diff')
        if (folder/'review.json').exists():
            review=read(folder/'review.json')
            for note in review.get('notes',[]): st.caption(note)
            if review.get('deferred_corrections'):
                st.warning('Some proposals were deferred. Check these against the image; approving only accepts the candidate shown above.')
                st.json(review['deferred_corrections'])
        if states[n] in {'error','stale','waiting'}:
            st.warning('This page has no current valid review. Use the full page inspector to inspect or resume it.')
            return
        a,b=st.columns(2)
        def decide(value):
            # Recheck artifacts at action time, not only when the UI was rendered.
            if page_state(folder) not in {'changed','deferred','unchanged'}:
                st.error('Page changed since display. Reload before deciding.'); return
            accept(job,n,value)
        a.button('Approve page and next',key=f'fast-yes-{job.name}-{n}',disabled=running,on_click=decide,args=(True,))
        b.button('Keep original and next',key=f'fast-no-{job.name}-{n}',disabled=running,on_click=decide,args=(False,))


def adopt_pending(job, numbers):
    """Explicit bulk action; retain prior decisions and never mark human-verified."""
    import time
    from core import read, save, export
    eligible=[]
    for n in numbers:
        folder=job/f'page-{n:05d}'
        if page_state(folder) in {'changed','deferred'}:
            review=read(folder/'review.json')
            eligible.append((folder,review['candidate_sha256']))
    try:
        for folder,digest in eligible:
            if page_state(folder) not in {'changed','deferred'}:
                raise ValueError('Review changed during bulk adoption; reload before retrying.')
            if read(folder/'review.json')['candidate_sha256'] != digest:
                raise ValueError('Candidate changed during bulk adoption')
            save(folder/'decision.json',dict(accepted=True,candidate_sha256=digest,time=time.time(),method='bulk_model_adoption',human_verified=False))
    finally:
        # Persist readable exports even after a partial decision-write failure.
        export(job)
    return len(eligible)

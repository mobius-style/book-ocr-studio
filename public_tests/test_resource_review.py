import hashlib
import json
import pytest
from gpu_admission import wait_for_memory
from fast_review import page_state, pending_pages

def test_admission_waits_for_two_samples():
    samples=iter([9000,11000,9000,11000,11000]);events=[]
    assert wait_for_memory(0,10000,sample=lambda:[{'index':0,'memory.free':next(samples)}],observe=events.append,sleep=lambda _:None)==11000
    assert len(events)==5

def test_admission_refuses_busy_missing_and_cancelled():
    with pytest.raises(RuntimeError,match='Out of VRAM'):
        wait_for_memory(0,10000,timeout=0,sample=lambda:[{'index':0,'memory.free':9000}])
    with pytest.raises(RuntimeError,match='unavailable'): wait_for_memory(0,10000,sample=lambda:[])
    with pytest.raises(RuntimeError,match='cancelled'): wait_for_memory(0,10000,cancelled=lambda:True)
    with pytest.raises(OSError): wait_for_memory(0,10000,sample=lambda:(_ for _ in ()).throw(OSError()))

def page(tmp_path, candidate=b'original', deferred=None):
    f=tmp_path/'page-00001';f.mkdir()
    for name,data in [('original.md',b'original'),('candidate.md',candidate),('source.png',b'image')]: (f/name).write_bytes(data)
    review={k:hashlib.sha256((f/v).read_bytes()).hexdigest() for k,v in [('original_sha256','original.md'),('candidate_sha256','candidate.md'),('source_sha256','source.png')]}
    review['deferred_corrections']=deferred or []
    (f/'review.json').write_text(json.dumps(review));return f

def test_unchanged_is_skipped_not_approved(tmp_path):
    f=page(tmp_path)
    assert page_state(f)=='unchanged' and pending_pages(tmp_path,[1])==[]
    assert not (f/'decision.json').exists()
    (f/'source.png').write_bytes(b'changed image')
    assert page_state(f)=='stale' and pending_pages(tmp_path,[1])==[1]

def test_deferred_identical_is_not_hidden(tmp_path):
    f=page(tmp_path,deferred=[{'before':'original','after':'new'}])
    assert page_state(f)=='deferred' and pending_pages(tmp_path,[1])==[1]

def test_decision_must_match_current_candidate(tmp_path):
    f=page(tmp_path,b'new');assert page_state(f)=='changed'
    (f/'decision.json').write_text(json.dumps({'accepted':False,'candidate_sha256':'stale'}))
    assert page_state(f)=='changed'
    (f/'decision.json').write_text(json.dumps({'accepted':False,'candidate_sha256':hashlib.sha256(b'new').hexdigest()}))
    assert page_state(f)=='original kept'
    (f/'review-error.json').write_text('{}');assert page_state(f)=='error'

def test_worker_handoff_orders_exit_admission_and_llm(tmp_path,monkeypatch):
    import worker, gpu_admission
    events=[]
    class Process:
        pid=999999999;returncode=0
        def poll(self): events.append('ocr-exit');return 0
    class Model:
        def __init__(self,*a,**kw): pass
        def __enter__(self): events.append('llm-start');return 'local'
        def __exit__(self,*a): events.append('llm-stop')
    monkeypatch.setattr(worker,'OwnedPopen',lambda *a,**kw:Process())
    monkeypatch.setattr(worker,'stop',lambda p:events.append('stop'))
    monkeypatch.setattr(worker,'LocalGemma',Model)
    monkeypatch.setattr(worker,'review_ready',lambda *a,**kw:[])
    monkeypatch.setattr(worker,'export',lambda *a:None)
    monkeypatch.setattr(worker,'status',lambda *a,**kw:None)
    monkeypatch.setattr(gpu_admission,'wait_for_memory',lambda *a,**kw:events.append('admit'))
    worker.attempt(tmp_path,{'gemma':True,'model':'gemma4:12b-it-qat'}, {'mode':'sequential','ocr_gpu':0,'gemma_gpu':0},'python','ocr.py')
    assert events[:5]==['admit','ocr-exit','stop','admit','llm-start']

def test_fast_review_ui_advances(tmp_path):
    from streamlit.testing.v1 import AppTest
    from PIL import Image
    f=page(tmp_path,b'new');Image.new('RGB',(30,30),'white').save(f/'source.png')
    r=json.loads((f/'review.json').read_text());r['source_sha256']=hashlib.sha256((f/'source.png').read_bytes()).hexdigest();(f/'review.json').write_text(json.dumps(r))
    script='''
import streamlit as st
from pathlib import Path
from fast_review import render
import json
job=Path(JOB)
def accept(job,n,value):
    f=job/f'page-{n:05d}'
    r=json.loads((f/'review.json').read_text())
    (f/'decision.json').write_text(json.dumps(dict(accepted=value,candidate_sha256=r['candidate_sha256'])))
@st.fragment
def body(): render(st,job,[1],False,accept)
body()
'''.replace('JOB',repr(str(tmp_path)))
    at=AppTest.from_string(script).run()
    assert not at.exception
    assert len(at.button)==2
    at.button[0].click().run()
    assert not at.exception
    assert page_state(f)=='approved'
    assert not at.button

def test_bulk_adoption_preserves_original_and_records_provenance(tmp_path,monkeypatch):
    import core
    from fast_review import adopt_pending
    f=page(tmp_path,b'new')
    monkeypatch.setattr(core,'export',lambda job:None)
    assert adopt_pending(tmp_path,[1])==1
    d=json.loads((f/'decision.json').read_text())
    assert d['accepted'] and d['human_verified'] is False and d['method']=='bulk_model_adoption'
    assert (f/'original.md').read_bytes()==b'original'
    assert adopt_pending(tmp_path,[1])==0

def test_bulk_excludes_invalid_and_preserves_rejection(tmp_path,monkeypatch):
    import core
    from fast_review import adopt_pending
    f=page(tmp_path,b'new');monkeypatch.setattr(core,'export',lambda job:None)
    (f/'candidate.md').write_bytes(b'tampered')
    assert adopt_pending(tmp_path,[1])==0
    assert not (f/'decision.json').exists()

def test_frontier_contains_failed_and_missing_pages_without_process_secrets(tmp_path):
    import io,zipfile
    from frontier_export import build
    f=page(tmp_path,b'candidate')
    (f/'review-error.json').write_text('{"error":"secret-token"}')
    (tmp_path/'job.json').write_text(json.dumps({'selected':[0,1],'review_connector':'private-endpoint'}))
    (tmp_path/'worker.log').write_text('secret-token')
    with zipfile.ZipFile(io.BytesIO(build(tmp_path))) as z:
        text=z.read('CONTEXT.md').decode()
        assert 'Input screen 1' in text and 'Input screen 2' in text
        assert 'Review failed: True' in text and '[Missing' in text
        assert 'candidate' in text and 'original' in text
        assert 'page-00001/source.png' in z.namelist()
        assert 'secret-token' not in text and 'worker.log' not in z.namelist()
        assert len(json.loads(z.read('manifest.json'))['pages'])==2

@pytest.mark.parametrize('model,budget',[('gemma4:12b-it-qat',10000),('gemma4:26b-a4b-it-qat',15300)])
def test_dual_admits_both_gpus_before_load(tmp_path,monkeypatch,model,budget):
    import worker,gpu_admission
    events=[]
    class Process:
        returncode=0
        def wait(self,timeout=None): pass
    class Model:
        def __init__(self,*a,**k): pass
        def __enter__(self): events.append('load');return 'local'
        def __exit__(self,*a): pass
    monkeypatch.setattr(worker,'LocalGemma',Model)
    monkeypatch.setattr(worker,'OwnedPopen',lambda *a,**k:Process())
    monkeypatch.setattr(worker,'stop',lambda *a:None)
    monkeypatch.setattr(worker,'review_ready',lambda *a,**k:[])
    monkeypatch.setattr(worker,'export',lambda *a:None)
    monkeypatch.setattr(worker,'status',lambda *a,**k:None)
    monkeypatch.setattr(gpu_admission,'wait_for_memory',lambda gpu,minimum,*a:events.append((gpu,minimum)))
    worker.attempt(tmp_path,{'gemma':True,'model':model},{'mode':'dual','ocr_gpu':1,'gemma_gpu':0},'python','ocr.py')
    assert events[:3]==[(1,10000),(0,budget),'load']


def test_admission_final_sufficient_sample_gets_confirmation():
    samples=iter([15834,15834]);sleeps=[]
    assert wait_for_memory(0,10000,timeout=0,sample=lambda:[{'index':0,'memory.free':next(samples)}],sleep=sleeps.append)==15834
    assert sleeps==[.5]
    samples=iter([15834,9000])
    with pytest.raises(RuntimeError,match='9000MiB'):
        wait_for_memory(0,10000,timeout=0,sample=lambda:[{'index':0,'memory.free':next(samples)}],sleep=lambda _:None)


def export_fixture(tmp_path):
    from PIL import Image
    f=page(tmp_path,b'new')
    Image.new('RGB',(40,40),'white').save(f/'source.png')
    r=json.loads((f/'review.json').read_text());r.update(source_sha256=hashlib.sha256((f/'source.png').read_bytes()).hexdigest(),corrections=[],notes=[])
    (f/'review.json').write_text(json.dumps(r));(f/'marker.json').write_text('{}')
    cfg=dict(selected=[0],total_pages=1,inputs=[{'name':'Synthetic.txt'}],title='Synthetic',author='Test')
    (tmp_path/'job.json').write_text(json.dumps(cfg));return f,cfg


def test_bulk_provenance_in_actual_reading_exports(tmp_path):
    import zipfile,pymupdf
    from fast_review import adopt_pending
    from html_export import render
    from portable_export import write_pdf,write_epub
    f,cfg=export_fixture(tmp_path)
    adopt_pending(tmp_path,[1])
    assert 'Quick mode: 1 pages' in (tmp_path/'reviewed.md').read_text()
    report=json.loads((tmp_path/'report.json').read_text())['pages'][0]
    assert report['method']=='bulk_model_adoption' and report['human_verified'] is False
    assert 'Quick mode: 1 pages' in render(tmp_path,cfg)
    write_pdf(tmp_path,cfg,tmp_path/'out.pdf')
    with pymupdf.open(tmp_path/'out.pdf') as pdf:
        assert 'Quick mode: 1 pages' in ''.join(p.get_text() for p in pdf)
    write_epub(tmp_path,cfg,tmp_path/'out.epub')
    with zipfile.ZipFile(tmp_path/'out.epub') as z:
        assert b'Quick mode: 1 pages' in z.read('EPUB/intro.xhtml')
    assert (f/'original.md').read_bytes()==b'original'


def test_partial_bulk_failure_regenerates_exports(tmp_path,monkeypatch):
    import core,shutil
    from fast_review import adopt_pending
    f,cfg=export_fixture(tmp_path)
    shutil.copytree(f,tmp_path/'page-00002');cfg['selected']=[0,1];cfg['total_pages']=2
    (tmp_path/'job.json').write_text(json.dumps(cfg))
    save=core.save
    def fail_second(path,data):
        if path.parent.name=='page-00002' and path.name=='decision.json':raise OSError('simulated write failure')
        save(path,data)
    monkeypatch.setattr(core,'save',fail_second)
    with pytest.raises(OSError,match='simulated'):adopt_pending(tmp_path,[1,2])
    report=json.loads((tmp_path/'report.json').read_text())['pages']
    assert report[0]['accepted'] and not report[1]['accepted']
    assert 'Quick mode: 1 pages' in (tmp_path/'reviewed.md').read_text()

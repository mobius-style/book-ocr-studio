import os,sys,subprocess,time,uuid,fcntl
from pathlib import Path
from core import ROOT,save,read

def connected():
    p=ROOT/'chrome-bridge-status.json'
    return p.exists() and time.time()-read(p).get('seen',0)<45

def ensure_bridge():
    import requests
    try:
        r=requests.get('http://127.0.0.1:8508/health',timeout=1)
        if r.ok and r.json().get('service')=='book-ocr-chrome':return
        return
    except requests.RequestException:pass
    with (ROOT/'chrome-bridge.log').open('ab') as log:
        subprocess.Popen([sys.executable,str(ROOT/'chrome_bridge.py')],cwd=ROOT,stdout=log,stderr=log,start_new_session=True)

def start(model='gemma4:12b-it-qat',ocr_engine='marker',review_connector=None):
    from kindle_capture import CAPTURES
    folder=CAPTURES/('session-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);folder.mkdir(parents=True,mode=0o700)
    (folder/'commands').mkdir()
    save(folder/'conversion-options.json',dict(model=model,ocr_engine=ocr_engine,review_connector=review_connector))
    save(folder/'settings.json',dict(headless=False,backend='chrome-extension'))
    save(folder/'state.json',dict(phase='starting',message='Connecting to the book open in Chrome',count=0))
    with (folder/'capture.log').open('ab') as log:
        subprocess.Popen([sys.executable,str(Path(__file__).resolve()),str(folder)],stdout=log,stderr=log,cwd=ROOT,start_new_session=True)
    return folder

def run(folder):
    from chrome_bridge import ChromePage,call
    from kindle_capture import state
    from oneclick import run_book
    with (folder/'session.lock').open('a') as lock, (ROOT/'chrome-capture.lock').open('a') as shared:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            state(folder,'attention','Another book is being captured. Start after it finishes.');return
        try:run_book(ChromePage(),folder)
        except Exception as exc:state(folder,'attention',str(exc))
        finally:
            try:call('disconnect')
            except Exception:pass
if __name__=='__main__':
    os.umask(0o077);run(Path(sys.argv[1]).resolve())

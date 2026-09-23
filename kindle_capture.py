"""Non-blocking Chrome capture session controlled by the local Streamlit UI."""
import fcntl, io, os, subprocess, sys, time, uuid
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from core import ROOT, save, read, sha, new_job, launch
CAPTURES=ROOT/'captures'
PROFILE=CAPTURES/'chrome-profile'

def active_session():
    if not CAPTURES.exists():return None
    for folder in sorted(CAPTURES.glob('session-*'),reverse=True):
        if (folder/'settings.json').exists() and read(folder/'settings.json').get('headless'):continue
        if running(folder):return folder
    return None

def running(folder):
    try:
        with (folder/'session.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return True
            return False
    except OSError:return False

def validate_reader_url(url):
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in {'read.amazon.co.jp','read.amazon.com'} or parsed.username or parsed.password or parsed.port not in {None,443}:
        raise ValueError('Enter an HTTPS URL for Kindle Web Reader')
    return url

def create_session(url='https://read.amazon.co.jp/',headless=False,profile=None):
    validate_reader_url(url)
    CAPTURES.mkdir(exist_ok=True,mode=0o700)
    with (CAPTURES/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        requested=str(profile or PROFILE)
        for existing in sorted(CAPTURES.glob('session-*'),reverse=True):
            config=existing/'settings.json';statusfile=existing/'state.json'
            if not config.exists() or not statusfile.exists():continue
            settings=read(config)
            if settings.get('profile')!=requested:continue
            pending=read(statusfile).get('phase')=='starting' and time.time()-statusfile.stat().st_mtime<30
            if running(existing) or pending:return existing
        return _create_session(url,headless,profile)


def _create_session(url='https://read.amazon.co.jp/',headless=False,profile=None):
    CAPTURES.mkdir(exist_ok=True,mode=0o700)
    folder=CAPTURES/('session-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);folder.mkdir(mode=0o700)
    (folder/'commands').mkdir()
    save(folder/'settings.json',dict(url=url,headless=headless,profile=str(profile or PROFILE),device_scale_factor=2))
    save(folder/'state.json',dict(phase='starting',message='Opening Chrome',count=0))
    with (folder/'capture.log').open('ab') as log:
        subprocess.Popen([sys.executable,str(Path(__file__).resolve()),str(folder)],stdout=log,stderr=log,start_new_session=True,cwd=ROOT)
    return folder

def command(folder,action,**params):
    ident=str(time.time_ns())+'-'+uuid.uuid4().hex[:6]
    if action in {'auto','snapshot','reset','test','capture','convert','oneclick'}:
        state(folder,{'auto':'detecting','snapshot':'detecting','reset':'updating','test':'capturing','capture':'capturing','convert':'updating','oneclick':'capturing'}[action],'Processing')
    save(folder/'commands'/(ident+'.json'),dict(action=action,**params))
    return ident

def state(folder,phase,message,**extra):
    old=read(folder/'state.json') if (folder/'state.json').exists() else {}
    old.update(phase=phase,message=message,updated=time.time(),**extra);save(folder/'state.json',old)

def difference(a,b):
    a,b=[Image.open(io.BytesIO(x)).convert('L') for x in (a,b)]
    if a.size!=b.size:return 255
    return ImageStat.Stat(ImageChops.difference(a,b)).mean[0]

def stable(page,clip,folder,previous=None,timeout=18):
    from reader_detection import clean_reader_capture
    with clean_reader_capture(page):
        end=time.monotonic()+timeout;last=None;count=0
        while time.monotonic()<end:
            if (folder/'stop').exists():raise InterruptedError('Capture stopped')
            image=page.screenshot(clip=clip,animations='disabled')
            changed=previous is None or difference(previous,image)>.01
            count=count+1 if changed and last is not None and difference(last,image)<.05 else 0
            if count>=2:return image
            last=image;page.wait_for_timeout(400)
        raise RuntimeError('The page did not advance or the screen did not stabilize. Check whether this is the last page and verify the arrow position.')

def validate_selection(value,width=1280,height=900):
    clip=value.get('clip');target=value.get('next')
    if not isinstance(clip,dict) or set(clip)!={'x','y','width','height'}:raise ValueError('Select the text area')
    if any(type(v) not in (int,float) for v in clip.values()):raise ValueError('Invalid text-area coordinates')
    if not (clip['x']>=0 and clip['y']>=0 and clip['width']>=80 and clip['height']>=80 and clip['x']+clip['width']<=width and clip['y']+clip['height']<=height):raise ValueError('Select a larger text area within the screen')
    if not isinstance(target,list) or len(target)!=2 or any(type(v) not in (int,float) for v in target):raise ValueError('Click the next-page arrow')
    if not (0<=target[0]<width and 0<=target[1]<height):raise ValueError('The next-page arrow is outside the screen')
    return clip,target

def pick_page(context):
    alive=[p for p in context.pages if not p.is_closed()]
    if not alive:raise RuntimeError('Chrome was closed. Use Open Chrome to start again.')
    readers=[p for p in alive if p.url.startswith(('https://read.amazon.','http://127.0.0.1:','http://localhost:'))]
    return (readers or alive)[-1]

def capture_pages(page,folder,selection,limit,test=False):
    clip,target=validate_selection(selection)
    if type(limit)!=int or not 1<=limit<=2000:raise ValueError('Set the capture count between 1 and 2000')
    manifest=read(folder/'capture.json') if (folder/'capture.json').exists() else dict(pages=[],clip=clip,next=target,status='capturing')
    if manifest['pages'] and (clip!=manifest['clip'] or target!=manifest['next']):raise ValueError('The capture area cannot change during capture. Start a new capture session.')
    existing=len(manifest['pages']);current=stable(page,clip,folder)
    if existing:
        last=(folder/manifest['pages'][-1]['image']).read_bytes()
        if difference(current,last)>.5:raise ValueError('The screen differs from the last saved image. Return Chrome to the last saved position before resuming.')
        page.mouse.click(*target);page.mouse.move(0,0);page.wait_for_timeout(900)
        current=stable(page,clip,folder,previous=last)
    fingerprints={p['sha256'] for p in manifest['pages']}
    manifest.update(clip=clip,next=target,status='capturing');save(folder/'capture.json',manifest)
    try:
        for i in range(limit):
            if (folder/'stop').exists():raise InterruptedError('Capture stopped')
            if sha(current) in fingerprints:raise RuntimeError('Stopped after detecting a repeated screen. Saved images are preserved.')
            name=f"page-{len(manifest['pages'])+1:05d}.png"
            if (folder/name).exists():raise RuntimeError('An unregistered image already exists. Start a separate capture session.')
            (folder/name).write_bytes(current);fingerprints.add(sha(current))
            manifest['pages'].append(dict(image=name,sha256=sha(current)));save(folder/'capture.json',manifest)
            state(folder,'capturing',f"{len(manifest['pages'])} screens saved",count=len(manifest['pages']))
            if i+1<limit:
                previous=current;page.mouse.click(*target);page.mouse.move(0,0);page.wait_for_timeout(900)
                current=stable(page,clip,folder,previous=previous)
        manifest['status']='requested_count_reached_not_full_book_verified';save(folder/'capture.json',manifest)
        state(folder,'test_ready' if test else 'captured','Two test screens captured. Check the text area and page navigation.' if test else 'Finished capturing the requested number of screens.',count=len(manifest['pages']))
    except Exception:
        manifest['status']='stopped_needs_review';save(folder/'capture.json',manifest);raise

def convert_saved(folder,gemma=True,autopilot=None):
    old=read(folder/'state.json')
    if old.get('job'):return Path(old['job'])
    manifest=read(folder/'capture.json');files=[]
    for item in manifest['pages']:
        path=(folder/item['image']).resolve()
        if path.parent!=folder.resolve():raise ValueError('Invalid image path')
        data=path.read_bytes()
        if sha(data)!=item['sha256']:raise ValueError('Saved image integrity check failed')
        files.append((path.name,data))
    options=read(folder/'conversion-options.json') if (folder/'conversion-options.json').exists() else {}
    job=new_job(files,spec='',gemma=gemma,mode='auto',model=options.get('model','gemma4:12b-it-qat'),ocr_engine=options.get('ocr_engine','marker'),review_connector=options.get('review_connector'))
    if autopilot:
        cfg=read(job/'job.json');cfg['autopilot']=autopilot
        title=manifest.get('title','').strip()
        if title and title.lower()!='kindle':
            cfg['title']=title;cfg['title_source']='kindle_reader_header'
        if cfg['ocr_engine']=='yomitoku':
            direction=manifest.get('reading_direction')
            splits={};last=0
            for idx,item in enumerate(manifest['pages']):
                pos=(item.get('position') or {}).get('current')
                if pos and last and pos-last==2 and direction in {'rtl','ltr'}:splits[str(idx)]=direction
                if pos:last=pos
            cfg['capture_splits']=splits
        save(job/'job.json',cfg)
    state(folder,'converting','Conversion started. See the results below.',job=str(job));launch(job);return job

def serve(folder):
    from playwright.sync_api import sync_playwright
    with (folder/'session.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        try:
            settings=read(folder/'settings.json')
            Path(settings['profile']).mkdir(parents=True,exist_ok=True,mode=0o700)
            with sync_playwright() as pw:
                context=pw.chromium.launch_persistent_context(settings['profile'],channel='chrome',headless=settings['headless'],viewport={'width':1280,'height':900},device_scale_factor=settings.get('device_scale_factor',2),locale='ja-JP',args=['--disable-features=Translate'])
                try:
                    page=context.pages[0] if context.pages else context.new_page();page.goto(settings['url'])
                    state(folder,'login','Sign in and open a book in the Chrome window, then press Start in the app.')
                    while context.pages:
                        if (folder/'close').exists():break
                        pending=sorted((folder/'commands').glob('*.json'))
                        if not pending:
                            try:pick_page(context).wait_for_timeout(300)
                            except Exception:break
                            continue
                        item=pending[0];req=read(item);item.unlink()
                        try:
                            page=pick_page(context)
                            if req['action']=='oneclick':
                                import oneclick,importlib
                                importlib.reload(oneclick)
                                oneclick.run_book(page,folder,gemma=req.get('gemma',True),max_screens=req.get('max_screens',5000))
                            elif req['action'] in {'snapshot','auto'}:
                                detection=None
                                if req['action']=='auto':
                                    from reader_detection import fit_and_detect
                                    detection=fit_and_detect(page)
                                    save(folder/'detection.json',detection)
                                page.mouse.move(5,450);page.wait_for_timeout(300)
                                page.screenshot(path=str(folder/'preview.png'))
                                state(folder,'select',detection['reason'] if detection else 'Select the text area in the image below, then click the next-page arrow.',preview_token=uuid.uuid4().hex,detection=detection)
                            elif req['action'] in {'test','capture'}:
                                if read(folder/'state.json').get('job'):raise ValueError('A capture cannot be modified after conversion starts. Start a new capture session.')
                                (folder/'stop').unlink(missing_ok=True)
                                selected=req['selection']
                                if selected.get('token') and selected['token']!=read(folder/'state.json').get('preview_token'):raise ValueError('The display has changed. Check the latest selection.')
                                save(folder/'selection.json',selected)
                                capture_pages(page,folder,selected,2 if req['action']=='test' else req['limit'],req['action']=='test')
                                if req['action']=='capture' and req.get('convert',True):convert_saved(folder,req.get('gemma',True))
                            elif req['action']=='reset':
                                if read(folder/'state.json').get('job'):raise ValueError('A capture cannot be modified after conversion starts')
                                archive=folder/'attempts'/uuid.uuid4().hex;archive.mkdir(parents=True)
                                for old in list(folder.glob('page-*.png'))+[folder/'capture.json']:
                                    if old.exists():old.rename(archive/old.name)
                                state(folder,'select','Previous test images archived. Check the selection and try another test capture.',count=0)
                            elif req['action']=='convert':convert_saved(folder,req.get('gemma',True))
                        except Exception as exc:
                            state(folder,'attention',str(exc))
                finally:context.close()
            state(folder,'closed','Capture Chrome closed. Saved images are preserved.')
        except Exception as exc:
            msg=str(exc)
            if 'Singleton' in msg or 'ProcessSingleton' in msg or 'Opening in existing browser session' in msg:msg='A previous capture Chrome window is still open. Close it before opening another.'
            state(folder,'error',msg[-1500:])

if __name__=='__main__':
    os.umask(0o077);serve(Path(sys.argv[1]).resolve())

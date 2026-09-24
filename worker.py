import fcntl, os, signal, subprocess, sys, time, traceback, uuid
from pathlib import Path
from core import ROOT, read, save, prepare, review_page, status, export
from gpu_server import LocalGemma
from owned_process import OwnedPopen

from scheduler import gpu_plan, learn
from gpu_fallback import execute, is_oom

def stop(proc):
    if proc:
        try:os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        # Includes children left behind after the process leader exits.
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass

def ocr_failure(proc):
    path=getattr(proc,'ocr_log_path',None)
    detail=''
    if path and path.exists():
        with path.open('rb') as f:
            f.seek(max(0,path.stat().st_size-16000));detail=f.read().decode(errors='replace')
    if is_oom(detail):raise RuntimeError('OCR ran out of VRAM (CUDA out of memory)')
    raise RuntimeError('The OCR process failed. Check the OCR attempt log.')

def review_ready(job, cfg, endpoint, proc=None, gpu=None):
    errors=[]
    for idx in cfg['selected']:
        folder=job/f'page-{idx+1:05d}'
        while not (folder/'marker.json').exists():
            if (job/'cancel').exists(): return errors
            if proc is None or proc.poll() is not None:
                if proc is not None and proc.returncode:ocr_failure(proc)
                raise RuntimeError(f'OCR did not finish for page {idx+1}. Check the log.')
            status(job,'parallel','Waiting for OCR pages',page=idx+1)
            time.sleep(.2)
        if (job/'cancel').exists(): return errors
        if (folder/'review.json').exists(): continue
        status(job,'parallel' if proc and proc.poll() is None else 'gemma',f"{'External model' if cfg.get('review_connector') else 'Gemma'} is reviewing page {idx+1} (stop takes effect after the response)")
        try:
            started=time.time()
            review_page(folder,cfg['model'],endpoint)
            (folder/'review-error.json').unlink(missing_ok=True)
            save(folder/'gemma-timing.json',dict(start=started,end=time.time(),endpoint=endpoint,gpu=gpu))
        except Exception as exc:
            error=dict(error=str(exc),page=idx+1)
            save(folder/'review-error.json',error);errors.append(error)
            if is_oom(exc):raise
        export(job)
    return errors

def attempt(job,cfg,plan,ocr_python,ocr_script):
    proc=None;errors=[]
    save(job/'execution.json',plan)
    env=os.environ.copy();env['CUDA_VISIBLE_DEVICES']=str(plan['ocr_gpu']);env['TORCH_DEVICE']='cuda'
    log_path=job/('ocr-attempt-'+uuid.uuid4().hex+'.log')
    def launch_ocr():
        with log_path.open('ab') as log:
            child=OwnedPopen([ocr_python,ocr_script,str(job)],env=env,stdout=log,stderr=log,start_new_session=True)
        child.ocr_log_path=log_path
        return child
    def admit(gpu, minimum, stage):
        from gpu_admission import wait_for_memory
        def observe(event):
            save(job/'gpu-admission.json',dict(stage=stage,time=time.time(),**event))
            status(job,'waiting_gpu',f"Waiting for GPU {gpu}: {event['free_mib']}MiB free / {minimum}MiB required ({stage})")
        wait_for_memory(gpu,minimum,lambda:(job/'cancel').exists(),observe)
    try:
        # Fresh admission after planning/preparation, and again at the sequential handoff.
        admit(plan['ocr_gpu'],14500 if plan['mode']=='shared' else 10000,'OCR')
        status(job,'ocr',f"{plan['mode']} mode: running OCR and review")
        if cfg['gemma'] and not cfg.get('review_connector') and plan['mode'] in {'dual','shared'}:
            if plan['mode']=='dual':
                admit(plan['gemma_gpu'],10000 if cfg['model']=='gemma4:12b-it-qat' else 15300,'Gemma (dual)')
            with LocalGemma(plan['gemma_gpu'],job,model=cfg['model']) as endpoint:
                proc=launch_ocr()
                try:
                    errors=review_ready(job,cfg,endpoint,proc,gpu=plan['gemma_gpu'])
                    if not (job/'cancel').exists():proc.wait(timeout=30)
                finally:stop(proc)
        else:
            proc=launch_ocr()
            while proc.poll() is None:
                if (job/'cancel').exists():stop(proc);return errors
                time.sleep(.2)
        if (job/'cancel').exists():return errors
        if proc.returncode:ocr_failure(proc)
        if cfg['gemma'] and plan['mode']=='sequential':
            stop(proc)  # OCR exits and releases allocations before loading Gemma.
            if not cfg.get('review_connector'):
                admit(plan['gemma_gpu'],10000 if cfg['model']=='gemma4:12b-it-qat' else 15300,'Gemma after OCR exit')
            if cfg.get('review_connector'):
                errors=review_ready(job,cfg,'compat:'+cfg['review_connector'])
            else:
                with LocalGemma(plan['gemma_gpu'],job,model=cfg['model']) as endpoint:
                    errors=review_ready(job,cfg,endpoint,gpu=plan['gemma_gpu'])
        return errors
    finally:
        stop(proc)
        export(job)

def run(job):
    proc=None
    with (job/'run.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return
        try:
            with (ROOT/'pipeline.lock').open('a') as shared:
                status(job,'queued','Queued for processing')
                while True:
                    try: fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                    except BlockingIOError:
                        if (job/'cancel').exists():status(job,'cancelled','Stopped');return
                        time.sleep(1)
                cfg=read(job/'job.json')
                from capture_options import apply_options
                cfg=apply_options(job,cfg,ROOT,read,save)
                external=bool(cfg.get('review_connector'))
                if external:
                    from review_connector import model_for
                    if model_for(cfg['review_connector'])!=cfg['model']:raise ValueError('Connector model mismatch')
                engine=cfg.get('ocr_engine','marker')
                if engine not in {'marker','yomitoku'}:raise RuntimeError('Unknown OCR engine')
                ocr_python=str(ROOT/'.venv-yomitoku/bin/python') if engine=='yomitoku' else sys.executable
                ocr_script=str(ROOT/('yomitoku_worker.py' if engine=='yomitoku' else 'marker_worker.py'))
                if not Path(ocr_python).exists():raise RuntimeError('YomiToku environment not found')
                from calibrate_gpu import calibrate
                status(job,'calibrating','Checking transfer bandwidth on available GPUs')
                save(job/'calibration.json',calibrate())
                history_kind=cfg['kind']+(':yomitoku' if engine=='yomitoku' else '')+(':'+cfg['model'] if cfg['model']!='gemma4:26b-a4b-it-qat' else '')
                plan=gpu_plan('sequential' if external else cfg.get('mode','auto'),cfg['gemma'] and not external,len(cfg['selected']),history_kind,model=cfg['model']);save(job/'execution.json',plan)
                status(job,'preparing','Saving source pages')
                prepare(job)
                if (job/'cancel').exists():status(job,'cancelled','Stopped');return
                def select(mode):
                    # Owned processes have exited before fresh GPU inventory is read.
                    return gpu_plan('sequential' if external else mode,cfg['gemma'] and not external,len(cfg['selected']),history_kind,model=cfg['model'])
                def record(event):
                    path=job/'fallback.json'
                    history=read(path) if path.exists() else []
                    history.append(dict(time=time.time(),**event));save(path,history)
                    status(job,'switching',f"VRAM fallback: {event['event']} → {event.get('mode')}")
                errors,plan=execute(plan,lambda p:attempt(job,cfg,p,ocr_python,ocr_script),select,record,lambda:(job/'cancel').exists())
                if (job/'cancel').exists():status(job,'cancelled','Stopped. You can resume from saved pages.');return
                export(job)
                from delivery import ensure_delivery
                ensure_delivery(job)
                if not external and engine=='marker' and cfg['model']=='gemma4:26b-a4b-it-qat':learn(job,plan)
                status(job,'partial' if errors else 'done','OCR complete. Some model reviews failed.' if errors else 'Processing complete. Suggestions have not been approved.',errors=errors)
        except Exception as exc:
            stop(proc);traceback.print_exc()
            try:export(job)
            except Exception:pass
            if (job/'cancel').exists():status(job,'cancelled','Stopped. Saved results are preserved.')
            else:status(job,'error',str(exc))
        finally:stop(proc)
if __name__=='__main__':
    os.umask(0o077)
    run(Path(sys.argv[1]).resolve())

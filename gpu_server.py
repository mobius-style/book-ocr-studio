"""Start an owned loopback-only Ollama server, with a single visible GPU."""
import os, signal, socket, subprocess, time
from pathlib import Path
import requests
from core import ROOT, MODEL
from model_store import model_directory
from owned_process import OwnedPopen

class LocalGemma:
    def __init__(self,gpu,job=None,model=MODEL): self.gpu=gpu; self.job=job; self.model=model; self.process=None; self.log=None; self.url=None
    def __enter__(self):
        # Let the OS choose an available port; startup failures never attach to someone else's server.
        with socket.socket() as s:
            s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
        self.url=f'http://127.0.0.1:{port}'
        model_path=str(model_directory(ROOT))
        if not Path(model_path).is_dir(): raise RuntimeError('Ollama model directory not found. Set BOOK_OCR_MODELS.')
        env=os.environ.copy()
        gpu_uuid=subprocess.check_output(['nvidia-smi','-i',str(self.gpu),'--query-gpu=uuid','--format=csv,noheader'],text=True).strip()
        env.update(CUDA_VISIBLE_DEVICES=gpu_uuid,OLLAMA_VULKAN='false',OLLAMA_HOST=f'127.0.0.1:{port}',OLLAMA_MODELS=model_path,
                   OLLAMA_CONTEXT_LENGTH='8192',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',
                   OLLAMA_FLASH_ATTENTION='1',OLLAMA_KV_CACHE_TYPE='q8_0',OLLAMA_NO_CLOUD='1')
        log_dir=ROOT/'backups'/'runtime-logs'
        log_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.log=(log_dir/f'ollama-gpu{self.gpu}.log').open('ab')
        self.process=OwnedPopen(['ollama','serve'],env=env,stdout=self.log,stderr=self.log,start_new_session=True)
        try:
            for _ in range(60):
                if self.process.poll() is not None: raise RuntimeError('Failed to start the dedicated Ollama process. Check the log.')
                try:
                    r=requests.get(self.url+'/api/tags',timeout=1);r.raise_for_status()
                    if self.model not in [m['name'] for m in r.json()['models']]: raise RuntimeError(f'{self.model} is not available')
                    load_start=time.time()
                    load=requests.post(self.url+'/api/generate',json={'model':self.model,'prompt':'','stream':False,'keep_alive':'2m','options':{'num_ctx':8192}},timeout=(5,600))
                    if load.status_code>=400 and 'out of memory' in load.text.lower():
                        raise RuntimeError('Out of VRAM while loading Gemma')
                    load.raise_for_status()
                    if self.job:
                        from core import save
                        ps=requests.get(self.url+'/api/ps',timeout=5).json()
                        save(self.job/'gemma-load.json',dict(start=load_start,end=time.time(),gpu=self.gpu,models=ps))
                    return self.url
                except requests.RequestException: time.sleep(.5)
            raise RuntimeError('Timed out while starting the dedicated Ollama process')
        except BaseException:
            self.__exit__(None,None,None); raise
    def __exit__(self,*args):
        if self.process:
            try:os.killpg(self.process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid,signal.SIGKILL);self.process.wait()
            try:os.killpg(self.process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        if self.log:self.log.close()

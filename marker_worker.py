"""Dedicated process: release Marker CUDA allocations at exit."""
import os, sys, time
from pathlib import Path
os.environ.setdefault('TORCH_DEVICE','cuda')
os.environ.setdefault('RECOGNITION_BATCH_SIZE','4')
os.environ.setdefault('DETECTOR_BATCH_SIZE','2')
from core import read, save

def run(job):
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import save_output
    cfg=read(job/'job.json')
    todo=[job/f'page-{idx+1:05d}' for idx in cfg['selected'] if not (job/f'page-{idx+1:05d}'/'marker.json').exists()]
    if not todo: return
    load_start=time.time()
    converter=PdfConverter(artifact_dict=create_model_dict(),config={'force_ocr':cfg['force_ocr'],'use_llm':False})
    save(job/'marker-load.json',dict(start=load_start,end=time.time(),gpu=os.environ.get('CUDA_VISIBLE_DEVICES')))
    for folder in todo:
        # Bound the OCR lead to four pages while the second GPU consumes them.
        parallel=(job/'execution.json').exists() and read(job/'execution.json')['mode']=='dual'
        while parallel and cfg['gemma']:
            pending=sum((p/'marker.json').exists() and not ((p/'review.json').exists() or (p/'review-error.json').exists()) for p in job.glob('page-*'))
            if pending<4 or (job/'cancel').exists(): break
            time.sleep(1)
        if (job/'cancel').exists(): break
        print('Marker:',folder.name,flush=True)
        source=folder/'source.pdf' if (folder/'source.pdf').exists() else folder/'source.png'
        started=time.time()
        result=converter(str(source))
        save_output(result,str(folder),'original')
        if not (folder/'original.md').exists(): raise RuntimeError('Marker output not found')
        save(folder/'marker.json',dict(engine='marker-pdf',version='1.10.2',source=source.name,start=started,end=time.time(),gpu=os.environ.get('CUDA_VISIBLE_DEVICES')))
if __name__=='__main__': run(Path(sys.argv[1]).resolve())

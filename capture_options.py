"""Resolve the model selected before capture, including long-lived capture workers."""
from pathlib import Path

def apply_options(job,cfg,root,read,save):
    if cfg.get('capture_options_applied'):return cfg
    source=cfg.get('autopilot',{}).get('source_capture')
    if not source:return cfg
    boundary=(Path(root)/'captures').resolve();folder=Path(source).resolve()
    if not folder.is_relative_to(boundary):raise ValueError('Capture source is outside the storage directory')
    while folder!=boundary:
        path=folder/'conversion-options.json'
        if path.exists():
            options=read(path)
            model=options['model']
            engine=options.get('ocr_engine',cfg.get('ocr_engine','marker'))
            if engine not in {'marker','yomitoku'}:raise ValueError('Invalid capture OCR engine')
            connector=options.get('review_connector')
            if connector:
                from review_connector import model_for
                if model!=model_for(connector):raise ValueError('Connector model mismatch')
            elif model not in {'gemma4:12b-it-qat','gemma4:26b-a4b-it-qat'}:raise ValueError('Invalid capture review model')
            cfg.update(model=model,ocr_engine=engine,review_connector=connector,capture_options_applied=True,capture_options_source=str(path));save(Path(job)/'job.json',cfg)
            break
        folder=folder.parent
    if not cfg.get('capture_options_applied'):
        cfg['capture_options_applied']=True;save(Path(job)/'job.json',cfg)
    return cfg

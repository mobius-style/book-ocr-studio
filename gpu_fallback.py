"""Bounded, observable mode degradation after GPU memory exhaustion."""
def is_oom(error):
    text=str(error).lower()
    return any(s in text for s in ('out of vram','vram不足','cuda out of memory','cuda error: out of memory','torch.outofmemoryerror','cuda_error_out_of_memory'))

def remaining_modes(mode):
    return {'shared':['dual','sequential'],'dual':['sequential'],'sequential':[]}.get(mode,[])

def execute(plan,attempt,select,record,cancelled):
    while True:
        if cancelled():return None,plan
        try:return attempt(plan),plan
        except Exception as exc:
            if not is_oom(exc) or cancelled():raise
            old=plan;plan=None
            for mode in remaining_modes(old['mode']):
                try:plan=select(mode)
                except RuntimeError as unavailable:
                    record(dict(event='unavailable',mode=mode,reason=str(unavailable)))
                    continue
                record(dict(event='switch',previous=old['mode'],mode=mode,reason=str(exc),ocr_gpu=plan['ocr_gpu'],gemma_gpu=plan['gemma_gpu']))
                break
            if plan is None:
                record(dict(event='stopped',mode=old['mode'],reason=str(exc)))
                raise RuntimeError('Out of VRAM: all available execution modes were tried. Processing stopped with saved results preserved.') from exc

"""Explainable GPU assignment: topology first; conservative measured makespan when available."""
import json, math, statistics, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROFILE=ROOT/'gpu-profile.json'
FIELDS=['index','uuid','pci.bus_id','pcie.link.gen.current','pcie.link.gen.max','pcie.link.width.current','memory.total','memory.free','utilization.gpu']

def inventory():
    raw=subprocess.check_output(['nvidia-smi','--query-gpu='+','.join(FIELDS),'--format=csv,noheader,nounits'],text=True)
    out=[]
    for line in raw.strip().splitlines():
        parts=[x.strip() for x in line.split(',')]
        if len(parts)!=len(FIELDS):raise RuntimeError('Unexpected GPU inventory format')
        row=dict(zip(FIELDS,parts))
        for k in FIELDS:
            if k not in {'uuid','pci.bus_id'}:
                try:row[k]=int(row[k])
                except ValueError:row[k]=None
        if row['memory.free'] is None or row['index'] is None:continue
        # Current lane width reflects wiring; max GPU width does not. Gen can downclock at idle.
        gen=row['pcie.link.gen.max'];width=row['pcie.link.width.current']
        row['link_gbps_estimate']=({1:.250,2:.500,3:.985,4:1.969,5:3.938,6:7.563}.get(gen,0)*width) if width else None
        out.append(row)
    return out

def profile():
    return json.loads(PROFILE.read_text()) if PROFILE.exists() else {'schema':1,'cards':{}}

def bandwidth(card,profiles):
    measurement=profiles.get('cards',{}).get(card['uuid'],{}).get('transfer',{})
    if (time.time()-measurement.get('time',0)<7*86400 and measurement.get('width')==card['pcie.link.width.current'] and measurement.get('gen')==card['pcie.link.gen.max']):
        return measurement['h2d_gbps'],'measured_h2d'
    return card['link_gbps_estimate'] or 1.,'pcie_theoretical'

def med_seconds(card,engine,profiles,kind):
    values=[x['seconds'] for x in profiles.get('cards',{}).get(card['uuid'],{}).get(engine,[]) if x.get('kind')==kind and x['seconds']>0]
    return statistics.median(values) if len(values)>=3 else None

def choose(cards,mode='auto',gemma=True,count=1,kind='pdf',profiles=None,llm_min=15300):
    profiles=profiles if profiles is not None else profile()
    ocr=[c for c in cards if c['memory.free']>=10000]
    llm=[c for c in cards if c['memory.free']>=llm_min]
    pairs=[(a,b) for a in ocr for b in llm if a['uuid']!=b['uuid']]
    if not gemma:
        if not ocr:raise RuntimeError('OCR requires at least 10GB of free GPU memory')
        fastest=max(ocr,key=lambda c:bandwidth(c,profiles)[0])
        return dict(mode='sequential',ocr_gpu=fastest['index'],gemma_gpu=fastest['index'],reason='OCR only. Selected by free VRAM and transfer bandwidth.',inventory=cards,estimated=False)
    ranked=[]
    for a,b in pairs:
        ab,ak=bandwidth(a,profiles);bb,bk=bandwidth(b,profiles)
        ot=med_seconds(a,'ocr',profiles,kind);gt=med_seconds(b,'gemma',profiles,kind)
        # No invented page timings. If history is incomplete, use a stated bandwidth heuristic.
        ol=med_seconds(a,'ocr_load',profiles,kind);gl=med_seconds(b,'gemma_load',profiles,kind)
        measured=all(t is not None for t in (ot,gt,ol,gl))
        score=(ot+gt+(count-1)*max(ot,gt)+ol+gl) if measured else None
        ranked.append(dict(ocr_gpu=a['index'],gemma_gpu=b['index'],score_seconds=score,
             measured_pages=measured,ocr_seconds=ot,gemma_seconds=gt,
             gemma_bandwidth=bb,ocr_bandwidth=ab,bandwidth_basis=[ak,bk]))
    if mode!='sequential' and ranked:
        # Comparing measured vs unmeasured as if exact would bias towards whichever happened to run.
        all_measured=all(c['measured_pages'] for c in ranked)
        ranked.sort(key=(lambda c:c['score_seconds']) if all_measured else (lambda c:(-c['gemma_bandwidth'],-c['ocr_bandwidth'])))
        best=ranked[0]
        reason=('Selected using estimated pipeline completion time from recent median page timings on each GPU' if all_measured else
                'Insufficient measurements for both assignments. Tentatively placing Gemma on the higher-bandwidth GPU and OCR on the other.')
        # For tiny jobs, measured sequential cost can beat loading a second engine concurrently.
        if mode=='auto' and all_measured:
            options=[]
            for c in llm:
                ot=med_seconds(c,'ocr',profiles,kind);gt=med_seconds(c,'gemma',profiles,kind)
                ol=med_seconds(c,'ocr_load',profiles,kind);gl=med_seconds(c,'gemma_load',profiles,kind)
                if all(t is not None for t in (ot,gt,ol,gl)):
                    options.append((count*(ot+gt)+ol+gl,c))
            if options:
                cost,card=min(options,key=lambda p:p[0])
                if cost<best['score_seconds']*.9:
                    return dict(mode='sequential',ocr_gpu=card['index'],gemma_gpu=card['index'],reason='Measurements estimate sequential processing to be at least 10% faster for this short document',inventory=cards,estimated=True,candidates=ranked)
        return dict(mode='dual',ocr_gpu=best['ocr_gpu'],gemma_gpu=best['gemma_gpu'],reason=reason,
                    inventory=cards,estimated=True,candidates=ranked,
                    bottleneck='gemma' if best['gemma_seconds'] and best['ocr_seconds'] and best['gemma_seconds']>best['ocr_seconds'] else 'unknown')
    if mode=='dual':raise RuntimeError(f'Insufficient free VRAM across two GPUs. OCR requires 10000MiB and Gemma requires {llm_min}MiB. Other processes will not be stopped.')
    if not llm:raise RuntimeError(f'Gemma requires at least {llm_min}MiB of free GPU memory. Resume after other processes finish.')
    fastest=max(llm,key=lambda c:bandwidth(c,profiles)[0])
    return dict(mode='sequential',ocr_gpu=fastest['index'],gemma_gpu=fastest['index'],reason='Parallel requirements not met, or sequential mode selected. Using the available higher-bandwidth GPU.',inventory=cards,estimated=True,candidates=ranked)

def gpu_plan(mode,gemma,count=1,kind='pdf',model=None):
    if mode=='shared':
        if model!='gemma4:12b-it-qat' or ':yomitoku' not in kind or not gemma:
            raise RuntimeError('Single-GPU parallel mode requires YomiToku + Gemma 12B review')
        cards=inventory();available=[c for c in cards if c['memory.free']>=14500]
        if not available:raise RuntimeError('Single-GPU parallel mode requires at least 14.5GB of free VRAM')
        card=max(available,key=lambda c:bandwidth(c,profile())[0])
        return dict(mode='shared',ocr_gpu=card['index'],gemma_gpu=card['index'],inventory=cards,estimated=True,reason='YomiToku + 12B share one GPU, requiring at least 14.5GB free. Peak usage and speed depend on the input.')
    minimum=10000 if model=='gemma4:12b-it-qat' else 15300
    return choose(inventory(),mode,gemma,count,kind,llm_min=minimum)

def learn(job,plan):
    # Called under the app pipeline lock. Keep only successful stage measurements.
    from core import read,save
    cfg=read(job/'job.json');p=profile()
    lookup={c['index']:c['uuid'] for c in plan['inventory']}
    for idx in cfg['selected']:
        folder=job/f'page-{idx+1:05d}'
        for engine,file,gpu in [('ocr','marker.json',plan['ocr_gpu']),('gemma','gemma-timing.json',plan['gemma_gpu'])]:
            if not (folder/file).exists():continue
            t=read(folder/file)
            if not {'start','end'}<=t.keys():continue
            key=f'{job.name}/{idx}/{engine}'
            actual_gpu=int(t.get('gpu',gpu))
            card=p['cards'].setdefault(lookup[actual_gpu],{})
            samples=card.setdefault(engine,[])
            if not any(s['key']==key for s in samples):
                samples.append(dict(key=key,seconds=t['end']-t['start'],kind=cfg['kind'],time=time.time()))
                card[engine]=samples[-30:]
    for engine,file,gpu in [('ocr_load','marker-load.json',plan['ocr_gpu']),('gemma_load','gemma-load.json',plan['gemma_gpu'])]:
        if not (job/file).exists(): continue
        t=read(job/file);actual_gpu=int(t.get('gpu',gpu));key=f'{job.name}/{engine}'
        samples=p['cards'].setdefault(lookup[actual_gpu],{}).setdefault(engine,[])
        if not any(s['key']==key for s in samples):
            samples.append(dict(key=key,seconds=t['end']-t['start'],kind=cfg['kind'],time=time.time()))
            del samples[:-30]
    save(PROFILE,p)

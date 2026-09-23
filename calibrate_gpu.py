import fcntl,json,os,subprocess,sys,time
from scheduler import ROOT,PROFILE,profile,inventory
from core import save

def calibrate():
 p=profile();results=[]
 for card in inventory():
  old=p['cards'].get(card['uuid'],{}).get('transfer',{})
  if time.time()-old.get('time',0)<7*86400 and old.get('width')==card['pcie.link.width.current'] and old.get('gen')==card['pcie.link.gen.max']:continue
  if card['utilization.gpu'] is None or card['utilization.gpu']>5 or card['memory.free']<card['memory.total']*.94:
   results.append({'gpu':card['index'],'status':'busy_skipped'});continue
  env=os.environ.copy();env['CUDA_VISIBLE_DEVICES']=card['uuid']
  r=subprocess.run([sys.executable,str(ROOT/'transfer_probe.py')],env=env,capture_output=True,text=True,timeout=45)
  if r.returncode:
   results.append({'gpu':card['index'],'status':'probe_failed','error':r.stderr[-500:]});continue
  data=json.loads(r.stdout.strip().splitlines()[-1]);data.update(time=time.time(),width=card['pcie.link.width.current'],gen=card['pcie.link.gen.max'])
  p['cards'].setdefault(card['uuid'],{})['transfer']=data
  results.append({'gpu':card['index'],'status':'measured',**data})
 save(PROFILE,p)
 return results
if __name__=='__main__':
 with (ROOT/'pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  print(json.dumps(calibrate(),ensure_ascii=False,indent=2))

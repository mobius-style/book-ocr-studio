"""Small pinned-memory PCIe probe, launched only on idle GPUs by calibrate_gpu.py."""
import json,time,statistics
import torch
n=32*1024*1024
host=torch.empty(n,dtype=torch.uint8,pin_memory=True);host.fill_(1)
device=torch.empty(n,dtype=torch.uint8,device='cuda')
for _ in range(3):device.copy_(host,non_blocking=True);torch.cuda.synchronize()
results={}
for name in ['h2d','d2h']:
 values=[]
 for _ in range(8):
  start=time.perf_counter()
  if name=='h2d':device.copy_(host,non_blocking=True)
  else:host.copy_(device,non_blocking=True)
  torch.cuda.synchronize();values.append(n/(time.perf_counter()-start)/1e9)
 results[name+'_gbps']=statistics.median(values)
print(json.dumps(results))

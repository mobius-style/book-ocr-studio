"""Japanese/English image OCR in an isolated YomiToku environment."""
import json,os,sys,time,uuid
from pathlib import Path
from layout_regions import ordered,assemble

def read(path):return json.loads(path.read_text())
def save(path,data):
 temp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex);temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.replace(path)

def run(job):
 import cv2
 from yomitoku import DocumentAnalyzer
 cfg=read(job/'job.json');start=time.time()
 analyzer=DocumentAnalyzer(device='cuda',visualize=False,reading_order='auto')
 save(job/'marker-load.json',dict(engine='yomitoku',start=start,end=time.time(),gpu=os.environ.get('CUDA_VISIBLE_DEVICES')))
 for idx in cfg['selected']:
  folder=job/f'page-{idx+1:05d}'
  if (folder/'marker.json').exists():continue
  while cfg['gemma'] and read(job/'execution.json')['mode'] in {'dual','shared'}:
   pending=sum((p/'marker.json').exists() and not ((p/'review.json').exists() or (p/'review-error.json').exists()) for p in job.glob('page-*'))
   if pending<4 or (job/'cancel').exists():break
   time.sleep(1)
  if (job/'cancel').exists():break
  started=time.time();image=cv2.imread(str(folder/'source.png'))
  if image is None:raise RuntimeError('Source image cannot be read')
  split=cfg.get('capture_splits',{}).get(str(idx))
  if split:
   mid=image.shape[1]//2;left=image[:,:mid];right=image[:,mid:]
   parts=[('right',right),('left',left)] if split=='rtl' else [('left',left),('right',right)]
  else:parts=[('whole',image)]
  outputs=[];regions=[]
  for name,img in parts:
   cv2.imwrite(str(folder/f'ocr-{name}.png'),img)
   result,_,_=analyzer(img)
   save(folder/f'layout-{name}.json',result.model_dump(mode='json'))
   out=folder/f'ocr-{name}.md'
   result.to_markdown(str(out),img=img,export_figure=False,export_figure_letter=True,ignore_line_break=True,encoding='utf-8')
   outputs.append(out.read_text())
   from yomitoku.export.export_markdown import paragraph_to_md,table_to_md
   offset=mid if name=='right' else 0
   def region(element,text,role):
    x1,y1,x2,y2=element.box
    return dict(box=[x1+offset,y1,x2+offset,y2],text=text,role=role,order=element.order,part=name)
   main=[region(p,paragraph_to_md(p,False)['md'].replace('<br>','\n'),p.role or 'body') for p in result.paragraphs if p.contents]
   main += [region(t,table_to_md(t,False)['md'],'table') for t in result.tables]
   rtl=sum(p.direction=='vertical' for p in result.paragraphs)>len(result.paragraphs)/2
   regions.extend(ordered(main,rtl))
   # Figure text must not disappear when figure images are disabled.
   for figure in sorted(result.figures,key=lambda f:f.order or 0):
    for p in sorted(figure.paragraphs,key=lambda p:p.order or 0):
     if p.contents:regions.append(region(p,paragraph_to_md(p,False)['md'].replace('<br>','\n'),'figure_text'))
  (folder/'raw-engine.md').write_text('\n\n'.join(outputs),encoding='utf-8')
  original,regions=assemble(regions)
  (folder/'original.md').write_text(original,encoding='utf-8')
  save(folder/'regions.json',dict(version=1,ordering='gutter-cuts; figure text separate',regions=regions))
  save(folder/'marker.json',dict(engine='yomitoku',version='0.15.0',source='source.png',parts=[n for n,_ in parts],start=started,end=time.time(),gpu=os.environ.get('CUDA_VISIBLE_DEVICES')))
if __name__=='__main__':run(Path(sys.argv[1]).resolve())

"""Inspect rendered reader geometry and explicitly labelled page navigation."""
import math

SCAN=r'''() => {
 const visible = el => {const r=el.getBoundingClientRect(),s=getComputedStyle(el);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
 const surfaces=[...document.querySelectorAll('canvas,img')].filter(visible).map(el=>{
 const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,tag:el.tagName};
 }).filter(r=>r.width>=200&&r.height>=200);
 const next=[...document.querySelectorAll('button,[role="button"],a')].filter(visible).map(el=>{
 const name=[el.getAttribute('aria-label'),el.getAttribute('title'),el.textContent].filter(Boolean).join(' ').trim();const r=el.getBoundingClientRect();
 return {name:name.slice(0,160),x:r.x+r.width/2,y:r.y+r.height/2,disabled:el.disabled||el.getAttribute('aria-disabled')==='true'};
 }).filter(b=>!b.disabled&&(/next\s*page|次のページ|次ページ|ページを進む|ページをめくる/i.test(b.name)));
 return {surfaces,next,width:innerWidth,height:innerHeight};
}'''

def detect(page):
    view=page.viewport_size;surfaces=[];buttons=[]
    for frame in page.frames:
        try:
            info=frame.evaluate(SCAN);ox=oy=0;sx=sy=1
            if frame!=page.main_frame:
                box=frame.frame_element().bounding_box()
                if not box:continue
                ox,oy=box['x'],box['y'];sx=box['width']/info['width'];sy=box['height']/info['height']
            for item in info['surfaces']:
                item.update(x=ox+item['x']*sx,y=oy+item['y']*sy,width=item['width']*sx,height=item['height']*sy)
                if item['x']<view['width'] and item['y']<view['height'] and item['x']+item['width']>0 and item['y']+item['height']>0:surfaces.append(item)
            for b in info['next']:
                b.update(x=ox+b['x']*sx,y=oy+b['y']*sy)
                if 0<=b['x']<view['width'] and 0<=b['y']<view['height']:buttons.append(b)
        except Exception:continue
    if not surfaces:return dict(selection=None,reason='Could not identify the text area. Refresh the reader or select it manually.',clipped=False)
    largest=max(s['width']*s['height'] for s in surfaces)
    substantial=[s for s in surfaces if s['width']*s['height']>=largest*.45]
    x=min(s['x'] for s in substantial);y=min(s['y'] for s in substantial)
    right=max(s['x']+s['width'] for s in substantial);bottom=max(s['y']+s['height'] for s in substantial)
    clipped=x < -2 or y < -2 or right>view['width']+2 or bottom>view['height']+2
    clip=dict(x=max(0,math.floor(x)),y=max(0,math.floor(y)),width=0,height=0)
    clip['width']=min(view['width'],math.ceil(right))-clip['x'];clip['height']=min(view['height'],math.ceil(bottom))-clip['y']
    # Ambiguous navigation stays manual; never silently guess RTL vs LTR.
    unique={(round(b['x']),round(b['y'])):b for b in buttons}
    nxt=list(next(iter(unique))) if len(unique)==1 else None
    return dict(selection=dict(clip=clip,next=nxt),reason='Detected the text area and page navigation.' if nxt else 'Detected the text area. Select the next-page arrow in the image.',clipped=clipped,surface_count=len(substantial))

def fit_and_detect(page):
    # Browser keyboard zoom is not reliable through automation. Apply reversible layout zoom
    # to the document root, then re-measure the rendered surfaces after every change.
    page.bring_to_front()
    page.evaluate("() => {document.documentElement.style.zoom='1';}")
    page.wait_for_timeout(400)
    result=detect(page);steps=0;zoom=1.0
    while result['clipped'] and steps<4:
        zoom*=.8
        page.evaluate("z => {document.documentElement.style.zoom=String(z);window.dispatchEvent(new Event('resize'));}",zoom)
        page.wait_for_timeout(500);steps+=1;result=detect(page)
    result['zoom_out_steps']=steps;result['layout_zoom']=zoom
    if result['clipped']:result['reason']='The whole page does not fit yet. Choose the full-page view in Kindle display settings.'
    return result


from contextlib import contextmanager

@contextmanager
def clean_reader_capture(page):
    """Temporarily remove observed Kindle overlay chrome; preserve position text."""
    token = page.evaluate("""() => {
      const elements = [...document.querySelectorAll('#reader-header, #kr-scrubber-bar, ion-footer.reader-footer, .bookmark[role="checkbox"]')];
      const saved = elements.map(e => ({selector: e.id ? '#'+e.id : e.tagName.toLowerCase()+'.'+(e.classList.contains('reader-footer')?'reader-footer':'bookmark'), value:e.style.getPropertyValue('opacity'), priority:e.style.getPropertyPriority('opacity')}));
      elements.forEach(e => e.style.setProperty('opacity','0','important'));
      return saved;
    }""")
    try:
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        yield
    finally:
        page.evaluate("""saved => {for(const item of saved) {
          const e=document.querySelector(item.selector);if(!e)continue;
          if(item.value)e.style.setProperty('opacity',item.value,item.priority);
          else e.style.removeProperty('opacity');
        }}""", token)

"""One command capture. Boundary proof is required; unchanged pages are not EOF."""
import time
import re
from core import read,save,sha

NAV=r'''() => {
 const visible=e=>{let r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
 return [...document.querySelectorAll('button,[role="button"],a')].filter(visible).map(e=>{
 let r=e.getBoundingClientRect();return {name:[e.getAttribute('aria-label'),e.getAttribute('title'),e.textContent].filter(Boolean).join(' ').trim(),x:r.x+r.width/2,y:r.y+r.height/2,disabled:!!e.disabled||e.getAttribute('aria-disabled')==='true'};});
}'''

def position_from_text(text):
    """Accept one unambiguous rendered Kindle position, never a slider value."""
    matches = {(int(a), int(b)) for a, b in re.findall(
        r'(?:位置|Location)\s*([0-9,]+)\s*/\s*([0-9,]+)',
        text.replace(',', ''), re.I)}
    if not matches:
        # Reflowable books can expose only progress, not stable location numbers.
        percentages={int(p) for p in re.findall(r'(?:●|•)\s*(\d{1,3})%',text)}
        if len(percentages)==1 and 0<=next(iter(percentages))<=100:
            return dict(current=next(iter(percentages)),total=100,unit='percent')
        return None
    if len(matches) != 1:
        return None
    current, total = next(iter(matches))
    if not 1 <= current <= total:
        return None
    return dict(current=current, total=total)


def reader_position(page):
    # innerText reflects the displayed UI, not hidden application state.
    values = []
    for frame in page.frames:
        try:
            value = position_from_text(frame.evaluate("() => document.body.innerText"))
            if value:
                values.append(value)
        except Exception:
            pass
    unique = {(v['current'], v['total']) for v in values}
    return values[0] if len(unique) == 1 else None


def navigation(page,direction,cover_position=None):
    import re
    pattern=r'next\s*page|次のページ|次ページ|ページを進む' if direction=='next' else r'previous\s*page|前のページ|前ページ|ページを戻る'
    found=[]
    for frame in page.frames:
        try:
            items=frame.evaluate(NAV)
            for item in items:
                if not re.search(pattern,item['name'],re.I):continue
                if frame!=page.main_frame:
                    box=frame.frame_element().bounding_box()
                    if not box:continue
                    item['x']+=box['x'];item['y']+=box['y']
                found.append(item)
        except Exception:continue
    unique={(round(b['x']),round(b['y'])):b for b in found}
    if not unique:
        position = reader_position(page)
        boundary = (position and
                    (((position['current'] == (0 if position.get('unit')=='percent' else 1)) or position == cover_position) if direction == 'previous'
                     else position['current'] == position['total']))
        if boundary:
            return dict(disabled=True, evidence='displayed_position', position=position)
    if len(unique)!=1:raise RuntimeError(f'{direction} page navigation could not be uniquely identified. Stopped with saved images preserved.')
    return next(iter(unique.values()))

def dismiss_reading_sync(page):
    """Decline only Kindle's observed last-read-position prompt."""
    if not hasattr(page,'locator'):return False
    dialog=page.locator('ion-alert[role="alertdialog"][header="前回読んでいたページ"]')
    if dialog.count()==1 and dialog.is_visible():
        no=dialog.get_by_role('button',name='いいえ',exact=True)
        if no.count()==1:
            no.click(timeout=3000)
            dialog.wait_for(state='hidden',timeout=3000)
            return True
    return False


def jump_to_cover(page):
    """Try the explicit cover anchor, otherwise the labelled slider endpoint."""
    if not hasattr(page,'locator'):return None
    dismiss_reading_sync(page)
    toc=page.locator('[data-testid="top_menu_table_of_contents"]')
    used_cover=False
    if toc.count()==1 and toc.is_visible():
        if 'active' not in (toc.get_attribute('class') or '').split():toc.click()
        try:
            cover=page.get_by_text(re.compile(r'^(表紙|Cover)$',re.I),exact=True)
            try:cover.wait_for(state='visible',timeout=1500)
            except Exception:pass
            if cover.count()==1 and cover.is_visible():
                cover.click();used_cover=True;page.wait_for_timeout(800)
        finally:
            if 'active' in (toc.get_attribute('class') or '').split():toc.click()
    if not used_cover:
        slider=page.locator('#kr-scrubber-bar')
        if slider.count()!=1:raise RuntimeError('Could not identify the cover entry or location slider')
        nxt=navigation(page,'next')
        if 'x' in nxt:
            rtl=nxt['x']<page.viewport_size['width']/2
        else:
            prev=navigation(page,'previous')
            if 'x' not in prev:raise RuntimeError('Could not determine the reading direction')
            rtl=prev['x']>page.viewport_size['width']/2
        key='End' if rtl else 'Home'
        slider.locator('[role="slider"]').press(key)
        # Ionic versions can ignore Home/End. Click the observed track endpoint;
        # the host padding keeps this inside the range while clamping to min/max.
        track=slider.locator('.range-slider').bounding_box()
        if not track:raise RuntimeError('Could not determine the location slider bounds')
        page.mouse.click(track['x']+track['width']+2 if rtl else track['x']-2,track['y']+track['height']/2)
        page.mouse.move(0,0);page.wait_for_timeout(800)
    for _ in range(30):
        position=reader_position(page)
        if position:return position
        page.wait_for_timeout(200)
    raise RuntimeError('Moved to the beginning, but could not confirm the location indicator')


def book_identity(url):
    from urllib.parse import urlsplit, parse_qs
    u=urlsplit(url);asin=parse_qs(u.query).get('asin')
    return (u.hostname,asin[0]) if asin else url


def resume_manifest(folder,url):
    path=folder/'capture.json'
    if not path.exists():return None
    m=read(path)
    if m.get('status') not in {'partial','capturing'} or not m.get('pages'):return None
    if book_identity(m.get('url',''))!=book_identity(url):return None
    if not all(p.get('position') for p in m['pages']):return None
    if any(p['position'].get('unit')=='percent' for p in m['pages']):return None # Percent cannot identify an exact resume screen.
    for item in m['pages']:
        source=(folder/item['image']).resolve()
        if source.parent!=folder.resolve() or sha(source.read_bytes())!=item['sha256']:
            raise RuntimeError('Resume image integrity check failed.')
    return m


def capture_identity(digest, position):
    """An exact displayed location distinguishes repeated printed pages.

    Percent progress is too coarse, so it cannot disambiguate identical images.
    """
    if position and position.get('unit') != 'percent':
        return (digest, position['current'], position['total'])
    return digest


def run_book(page,folder,gemma=True,max_screens=5000):
    from kindle_capture import stable,difference,state as write_state,convert_saved
    from reader_detection import fit_and_detect
    from core import is_running
    control=folder
    prior=read(folder/'state.json')
    candidate=__import__('pathlib').Path(prior.get('active_run') or folder)
    manifest=resume_manifest(candidate,page.url)
    if manifest:
        folder=candidate
        if prior.get('job') and is_running(__import__('pathlib').Path(prior['job'])):
            raise RuntimeError('Saved images are being converted. Resume capture after conversion finishes.')
    elif (folder/'capture.json').exists() or prior.get('job'):
        import uuid
        folder=control/'books'/uuid.uuid4().hex
        folder.mkdir(parents=True,mode=0o700);save(folder/'state.json',{})
        if (control/'conversion-options.json').exists():save(folder/'conversion-options.json',read(control/'conversion-options.json'))
    def state(phase,message,**extra):
        write_state(folder,phase,message,**extra)
        if folder!=control:write_state(control,phase,message,active_run=str(folder),**extra)
    (control/'stop').unlink(missing_ok=True)
    write_state(control,'capturing','Preparing',job=None,count=len(manifest['pages']) if manifest else 0,active_run=str(folder))
    if folder!=control:write_state(folder,'capturing','Preparing',job=None)
    state('capturing','Detecting the capture area automatically')
    dismiss_reading_sync(page)
    detection=fit_and_detect(page);save(folder/'detection.json',detection)
    if detection.get('clipped') or not detection.get('selection'):raise RuntimeError(detection['reason'])
    clip=detection['selection']['clip'];page.mouse.move(0,0)
    current=stable(page,clip,control,timeout=60)
    if manifest:
        target=manifest['pages'][-1]['position']
        if clip!=manifest['clip']:raise RuntimeError('The capture area differs from the saved session. Restore the same display size.')
        for _ in range(max_screens):
            pos=reader_position(page)
            if not pos or pos['total']!=target['total']:raise RuntimeError('Could not confirm the resume location.')
            if pos==target:break
            direction='previous' if pos['current']>target['current'] else 'next'
            nav=navigation(page,direction)
            if nav['disabled']:raise RuntimeError('Could not return to the saved location.')
            state('capturing','Moving to the saved location')
            page.mouse.click(nav['x'],nav['y']);page.mouse.move(0,0)
            current=stable(page,clip,control,previous=current,timeout=60)
        else:raise RuntimeError('Reached the search limit for the resume location.')
        original=(folder/manifest['pages'][-1]['image']).read_bytes()
        if difference(original,current)>1:raise RuntimeError('The resume image does not match the saved image.')
        manifest.update(status='capturing');manifest.pop('error',None)
        save(folder/'capture.json',manifest)
        # The last saved screen is already durable. Advance exactly once.
        nav=navigation(page,'next')
        if nav['disabled']:manifest.update(status='complete',end_verified=True)
        else:
            page.mouse.click(nav['x'],nav['y']);page.mouse.move(0,0)
            current=stable(page,clip,control,previous=current,timeout=60)
    else:
        state('capturing','Jumping to the cover from the table of contents')
        if hasattr(page,'inner_text'):
            save(folder/'start-ui.json',dict(text=page.inner_text('body'),buttons=page.evaluate(NAV),header=page.locator('#reader-header').inner_html(),slider=page.locator('#kr-scrubber-bar').evaluate("e => e.outerHTML + (e.shadowRoot ? e.shadowRoot.innerHTML : '')")))
            page.screenshot(path=str(folder/'start-ui.png'))
        cover_position=jump_to_cover(page)
        if cover_position:
            current=stable(page,clip,control,timeout=60)
            save(folder/'start-anchor.json',dict(source='reader_start_anchor',position=cover_position))
        seen=set()
        for _ in range(max_screens):
            previous=navigation(page,'previous',cover_position=cover_position)
            if previous['disabled']:break
            digest=sha(current)
            if digest in seen:raise RuntimeError('Detected a loop while moving to the beginning.')
            seen.add(digest);state('capturing','Moving to the beginning of the book')
            page.mouse.click(previous['x'],previous['y']);page.mouse.move(0,0)
            current=stable(page,clip,control,previous=current,timeout=60)
        else:raise RuntimeError('Stopped because the beginning could not be confirmed.')
        next_point=detection['selection'].get('next')
        manifest=dict(pages=[],clip=clip,status='capturing',start_verified=True,end_verified=False,title=(page.locator('ion-title.top-chrome__book-title').inner_text().strip() if hasattr(page,'locator') and page.locator('ion-title.top-chrome__book-title').count()==1 else page.title()),url=page.url,
                      reading_direction=('rtl' if next_point[0]<page.viewport_size['width']/2 else 'ltr') if next_point else 'unknown')
        save(folder/'capture.json',manifest)
    fingerprints={capture_identity(p['sha256'],p.get('position')) for p in manifest['pages']}
    try:
        for _ in range(max_screens):
            if manifest.get('end_verified'):break
            pos=reader_position(page)
            if manifest['pages'] and pos and manifest['pages'][-1].get('position'):
                previous_position=manifest['pages'][-1]['position']
                comparable=pos.get('unit')==previous_position.get('unit') and pos['total']==previous_position['total']
                previous_pos=previous_position['current']
                if comparable and (pos['current']<previous_pos or (pos['current']==previous_pos and pos.get('unit')!='percent')):raise RuntimeError('The reading position is not advancing.')
                if capture_identity(sha(current),pos) in fingerprints:raise RuntimeError('Stopped after detecting a capture loop.')
            elif capture_identity(sha(current),pos) in fingerprints:raise RuntimeError('Stopped after detecting a capture loop.')
            name=f"page-{len(manifest['pages'])+1:05d}.png"
            if (folder/name).exists():raise RuntimeError('An image already exists at the destination.')
            (folder/name).write_bytes(current);fingerprints.add(capture_identity(sha(current),pos))
            manifest['pages'].append(dict(image=name,sha256=sha(current),position=pos));save(folder/'capture.json',manifest)
            state('capturing',f"{len(manifest['pages'])} screens saved",count=len(manifest['pages']))
            nxt=navigation(page,'next')
            if nxt['disabled']:manifest.update(status='complete',end_verified=True);break
            page.mouse.click(nxt['x'],nxt['y']);page.mouse.move(0,0)
            current=stable(page,clip,control,previous=current,timeout=60)
        else:raise RuntimeError('Capture limit reached. The end of the book has not been confirmed.')
    except Exception as exc:
        manifest.update(status='partial',error=str(exc))
        save(folder/'stop-diagnostic.json',dict(position=reader_position(page),image_sha256=sha(current),error=str(exc)))
    save(folder/'capture.json',manifest)
    if manifest['pages']:
        save(folder/'autopilot.json',dict(source_capture=str(folder),capture_complete=manifest['end_verified'],capture_error=manifest.get('error')))
        job=convert_saved(folder,gemma=gemma,autopilot=read(folder/'autopilot.json'))
        if folder!=control:write_state(control,'converting','Converting to text',job=str(job),count=len(manifest['pages']),active_run=str(folder))
        return job

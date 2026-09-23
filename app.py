from pathlib import Path
import os
os.umask(0o077)
import streamlit as st
from display_language import english_message, diagnostic_display
from core import JOBS, ROOT, new_job, launch, read, save, is_running, accept, bundle
from download_names import book_details, markdown_name

from chrome_job import ensure_bridge
if os.environ.get('BOOK_OCR_ENABLE_BRIDGE')=='1':
    st.cache_resource(ensure_bridge)()

st.set_page_config(page_title='Book OCR Studio',page_icon='📖',layout='wide')
st.markdown('''<style>[data-testid="stStatusWidget"]{display:none!important}.block-container{max-width:1500px;padding-top:2rem}h1{letter-spacing:-.04em}textarea:disabled{-webkit-text-fill-color:#334155!important;color:#334155!important;opacity:1!important}div[data-testid="stMetric"]{background:#f1f5f9;border-radius:10px;padding:12px}</style>''',unsafe_allow_html=True)
st.title('Book OCR Studio')
st.subheader('Local-first book OCR')
st.caption('Local processing by default. Import PDFs, images or Kindle captures; export MD, HTML, PDF and EPUB with Gemma review or an optional vision API.')
st.caption('Output preserves the language of the source; it is not translated. Recognition accuracy varies by language and layout.')
with st.sidebar:
    st.subheader('Local processing')
    st.write('Marker / YomiToku + Gemma 4 (12B default)')
    st.caption('Default Gemma review is local. The optional API connector sends images and OCR text to your selected endpoint only when enabled. Internet is needed for initial downloads and Kindle access.')
    st.divider()
    jobs=sorted(JOBS.glob('*/job.json'),reverse=True) if JOBS.exists() else []
    selected=st.selectbox('Saved jobs',['New job']+[p.parent.name for p in jobs])
    if selected!='New job': st.session_state['job']=str(JOBS/selected)
    st.caption('Original OCR is preserved. Model suggestions enter the reviewed version only after approval.')

if not st.session_state.get('c1_12b_default_applied'):
    st.session_state['shared_model']='gemma4:12b-it-qat'
    st.session_state['c1_12b_default_applied']=True
model=st.selectbox('Gemma review model — Möbius Custom C1 for OCR',['gemma4:12b-it-qat','gemma4:26b-a4b-it-qat'],key='shared_model')
st.caption('Review profile: Möbius Custom C1 for OCR (PDF, images and Kindle). 12B is the default; 26B uses the same profile.')
st.caption('12B + YomiToku supports parallel OCR and review on one GPU. A 16GB or larger card is recommended, with at least 14.5GB free VRAM. Select One GPU, parallel in GPU mode; speed gains depend on the input.')
st.caption('Timing: on one 16GB GPU, 26B runs OCR and review sequentially. This may take longer than 12B in single-GPU parallel mode. Timing varies with text volume and free VRAM; the end-to-end ratio has not been measured.')
from connector_ui import render as render_connector
review_options=render_connector(model)
engines=['Marker']
if (ROOT/'.venv-yomitoku/bin/python').exists():engines.append('YomiToku')
engine=st.selectbox('OCR engine (PDF, images and Kindle)',engines,key='shared_ocr_engine',help='Marker is the default. YomiToku is optional and has non-commercial terms unless separately licensed.')
if engine=='YomiToku':
    st.warning('YomiToku 0.15.0 code and weights: CC BY-NC-SA 4.0. Use only when your use is permitted by those terms or covered by a separate commercial license. Selecting it does not grant a license.')
else:
    st.caption('Marker 1.10.2 / Surya 0.17.1: GPL code; model weights have separate modified AI Pubs Open RAIL-M conditions. Marker is not an unrestricted commercial-use alternative. See Licenses and source below.')
with st.expander('Licenses and source'):
    st.markdown((ROOT/'THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8'))
    st.download_button('Application license (AGPL-3.0-only)',(ROOT/'LICENSE').read_bytes(),file_name='LICENSE.txt',key='license-download')
upload_tab, kindle_tab=st.tabs(['PDF / Images','Kindle capture'])
with upload_tab:
    page_scope=st.radio('Pages to process',['Select a page range','All pages'],horizontal=True)
    all_pages=page_scope=='All pages'
    with st.form('upload'):
        uploads=st.file_uploader('One PDF or multiple page images',type=['pdf','png','jpg','jpeg','webp'],accept_multiple_files=True)
        a,b,c=st.columns(3)
        with a: spec=st.text_input('Page range','1-3',disabled=all_pages,help='Page numbers start at 1, for example 1-3,5. This field is ignored for All pages. Images are sorted by filename.')
        with b: mode=st.selectbox('GPU mode',['Automatic','Two GPUs in parallel','One GPU, sequential','One GPU, parallel (12B + YomiToku)'])
        with c:
            gemma=st.checkbox('Review against images with selected model',value=True)
            force=st.checkbox('Force OCR on text-based PDFs',value=False)
        st.caption('All input pages will be processed.' if all_pages else 'Only the selected pages will be processed, for example 1-3,5.')
        submitted=st.form_submit_button('Start conversion',type='primary',disabled=not st.session_state.get('review_ready',True))
    if submitted:
        try:
            files=sorted([(u.name,u.getvalue()) for u in uploads],key=lambda x:x[0])
            job=new_job(files,'' if all_pages else spec,gemma,force,{'Automatic':'auto','Two GPUs in parallel':'dual','One GPU, sequential':'sequential','One GPU, parallel (12B + YomiToku)':'shared'}[mode],ocr_engine=engine.lower(),**review_options)
            st.session_state['job']=str(job);launch(job)
        except Exception as exc:st.error(str(exc))
with kindle_tab:
    import kindle_ui,importlib
    importlib.reload(kindle_ui)
    kindle_ui.render_kindle()

from ui_refresh import adaptive_fragment,job_pending

@adaptive_fragment(3,lambda: job_pending(st.session_state.get('job')))
def show_job():
    if 'job' not in st.session_state:return
    job=Path(st.session_state['job']);cfg=read(job/'job.json');s=read(job/'status.json')
    st.divider();st.subheader(cfg['inputs'][0]['name'])
    st.caption(f'Saved to: {job}')
    st.caption(f"OCR engine: {cfg.get('ocr_engine','marker')}")
    st.caption(f"Review model: {cfg.get('model')} · Provider: {'OpenAI-compatible API' if cfg.get('review_connector') else 'Local Gemma'}")
    st.info(english_message(s['message']))
    if (job/'fallback.json').exists():
        with st.expander('VRAM fallback history'):
            for event in read(job/'fallback.json'):
                st.write(f"{event['event']} → {event['mode']}: {english_message(event['reason'])}")
    if (job/'execution.json').exists():
        execution=read(job/'execution.json')
        st.caption(f"Execution mode: {execution['mode']} / OCR: GPU {execution['ocr_gpu']} / Gemma: GPU {execution['gemma_gpu']}")
        st.caption(english_message(execution.get('reason','')))
        with st.expander('GPU assignment details'):
            st.json(diagnostic_display(execution))
    complete=sum((job/f'page-{i+1:05d}'/'marker.json').exists() for i in cfg['selected'])
    checked=sum((job/f'page-{i+1:05d}'/'review.json').exists() for i in cfg['selected'])
    a,b,c=st.columns(3)
    a.metric('OCR completed',f"{complete} / {len(cfg['selected'])}");b.metric('Gemma reviewed',checked);c.metric('Total input pages',cfg['total_pages'])
    st.caption('Progress covers the selected input only. It does not confirm full-book capture or error-free text.')
    running=is_running(job)
    if running:
        if st.button('Stop after current request',key='cancel'+job.name):
            (job/'cancel').touch();st.warning('Processing will stop after the current Gemma response.')
    elif s['state'] not in {'done'}:
        resume_models=['gemma4:12b-it-qat','gemma4:26b-a4b-it-qat']
        resume_model=st.selectbox('Review model for resume',resume_models,index=resume_models.index(cfg['model']),key='resumemodel'+job.name)
        shared_resume=st.checkbox('Resume in single-GPU parallel mode (12B + YomiToku only)',value=cfg.get('mode')=='shared',key='resumeshared'+job.name)
        st.caption('Completed reviews are preserved. Changing the model means completed and remaining pages may use different models.')
        if st.button('Resume from saved progress',key='resume'+job.name):
            if shared_resume and (resume_model!='gemma4:12b-it-qat' or cfg.get('ocr_engine')!='yomitoku'):
                st.error('Select YomiToku and 12B for single-GPU parallel mode.')
            else:
                cfg['model']=resume_model
                cfg['mode']='shared' if shared_resume else ('auto' if cfg.get('mode')=='shared' else cfg.get('mode','auto'))
                save(job/'job.json',cfg);launch(job)
    ready=[i+1 for i in cfg['selected'] if (job/f'page-{i+1:05d}'/'marker.json').exists()]
    if ready:
        num=st.selectbox('Page to inspect',ready,key='page'+job.name)
        folder=job/f'page-{num:05d}'
        left,right=st.columns([1,1])
        with left:st.image(str(folder/'source.png'),caption=f'Source page {num}',use_container_width=True)
        with right:
            original=(folder/'original.md').read_text()
            t1,t2,t3=st.tabs(['Original OCR','Gemma suggestions','Changes'])
            with t1:st.text_area('Original text (saved)',original,height=430,disabled=True,key=f'original{job.name}{num}')
            with t2:
                if (folder/'review.json').exists():
                    review=read(folder/'review.json');candidate=(folder/'candidate.md').read_text()
                    st.caption(f"Review model for this page: {review.get('model','Unknown')}")
                    st.text_area('Suggested text from Gemma',candidate,height=330,disabled=True,key=f'candidate{job.name}{num}')
                    for correction in review['corrections']:st.write(correction)
                    for note in review['notes']:st.caption(note)
                    decision=read(folder/'decision.json') if (folder/'decision.json').exists() else {}
                    st.caption('Approved' if decision.get('accepted') else 'Not approved')
                    if not running:
                        x,y=st.columns(2)
                        if x.button('Approve suggestions for this page',key=f'accept{job.name}{num}'):accept(job,num,True);st.rerun(scope='fragment')
                        if y.button('Restore original OCR',key=f'reject{job.name}{num}'):accept(job,num,False);st.rerun(scope='fragment')
                elif (folder/'review-error.json').exists():st.error(english_message(read(folder/'review-error.json')['error']))
                else:st.caption('Waiting for review, or Gemma review is disabled.')
            with t3:
                st.code((folder/'changes.diff').read_text() if (folder/'changes.diff').exists() else 'No changes to display yet',language='diff')
        if not running and (job/'original.md').exists():
            title,author=book_details(job,cfg)
            name_key=job.name+str((job/'job.json').stat().st_mtime_ns)
            with st.expander('Download filename settings'):
                title=st.text_input('Book title',value=title,key='booktitle'+name_key)
                author=st.text_input('Author',value=author,key='bookauthor'+name_key)
                override=st.text_input('Filename (optional)',value=cfg.get('download_name',''),key='downloadname'+name_key,help='Leave blank for Book title_Author.md. If the author is unknown, only the title is used.')
                st.caption('PDF title and author metadata are used when available. Otherwise, the input filename provides the title.')
                if st.button('Save title, author and filename',key='savename'+job.name):
                    cfg.update(title=title,author=author,download_name=override);save(job/'job.json',cfg)
                    from delivery import ensure_delivery
                    ensure_delivery(job)
                    st.rerun()
            filename=markdown_name(title,author,override)
            st.caption(f'Download filename: {filename}')
            x,y,z=st.columns(3)
            x.download_button('Original OCR MD',data=(job/'original.md').read_bytes(),file_name=filename,key='download1'+job.name)
            y.download_button('Reviewed MD',data=(job/'reviewed.md').read_bytes(),file_name=filename,key='download2'+job.name)
            z.download_button('Images, suggestions and records ZIP',data=bundle(job),file_name=job.name+'.zip',key='download3'+job.name)
            from delivery_ui import output_buttons
            output_buttons(job,'job-'+job.name)
            st.caption('The reviewed version uses suggestions only on approved pages; all other pages retain the original OCR.')
    with st.expander('Processing log'):
        st.code(english_message((job/'worker.log').read_text(errors='replace')[-6000:]) if (job/'worker.log').exists() else 'No log available yet')
show_job()

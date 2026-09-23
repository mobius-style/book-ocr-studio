import base64
from pathlib import Path
import streamlit as st
from display_language import english_message
import streamlit.components.v1 as components
from core import ROOT,read,save,is_running
from kindle_capture import create_session,active_session,running,command,validate_selection,convert_saved
picker=components.declare_component('kindle_capture_picker',path=str(ROOT/'components/capture_picker'))

from ui_refresh import adaptive_fragment,capture_pending

@adaptive_fragment(2,capture_pending)
def render_kindle():
    st.subheader('Kindle capture')
    review_options=st.session_state.get('active_review_options',dict(model=st.session_state.get('shared_model','gemma4:12b-it-qat'),review_connector=None))
    review_ready=st.session_state.get('review_ready',True)
    st.caption('Not affiliated with Amazon. Process only content you are entitled to use; check applicable law and service terms. Buying a book does not grant redistribution rights.')
    st.write('Select a book in the connected Chrome window, then press Start to save Markdown. HTML can be created separately from the results.')
    if 'capture_session' not in st.session_state:
        current=active_session()
        if current:st.session_state['capture_session']=str(current)
    folder=Path(st.session_state['capture_session']) if st.session_state.get('capture_session') else None
    alive=folder is not None and running(folder)
    if not alive and (folder is None or not read(folder/'state.json').get('job')):
        current=active_session()
        if current:
            folder=current;st.session_state['capture_session']=str(folder);alive=True
    starting=folder is not None and read(folder/'state.json').get('phase')=='starting'
    from chrome_job import connected,start,ensure_bridge
    with st.expander('Connect your regular Chrome (optional)'):
        st.caption('Dedicated capture Chrome works without this bridge. For regular Chrome, generate the local extension configuration and install the extension first; see INSTALL.md.')
        if st.button('Enable local Chrome bridge'):
            ensure_bridge()
            st.session_state['bridge_enabled']=True
        if st.session_state.get('bridge_enabled'):
            st.caption('Local bridge enabled on 127.0.0.1:8508. It remains active until stopped; see INSTALL.md.')
    external=connected()
    managed=alive and read(folder/'settings.json').get('backend')!='chrome-extension'
    current_state=read(folder/'state.json') if folder else {}
    active_work=alive and current_state.get('phase') in {'starting','capturing','detecting','updating'}
    active_work=active_work or bool(current_state.get('job') and is_running(Path(current_state['job'])))
    with st.expander('Capture limit for testing'):
        capture_limit=st.number_input('Screens to capture (0 = entire book)',min_value=0,max_value=5000,value=0,step=1,key='capture_limit')
        st.caption('A capture limit produces a partial book. Leave this at 0 for normal use.')
    if st.button('Start — Save book as MD',type='primary',disabled=active_work or not (managed or external) or not review_ready):
        requested_model=review_options['model']
        if managed:
            save(folder/'conversion-options.json',dict(**review_options,ocr_engine=st.session_state.get('shared_ocr_engine','Marker').lower()))
            command(folder,'oneclick',gemma=True,max_screens=int(capture_limit) or 5000)
        else:
            folder=start(**review_options,ocr_engine=st.session_state.get('shared_ocr_engine','Marker').lower());st.session_state['capture_session']=str(folder)
        st.rerun()
    if managed:st.caption('Connected to capture Chrome. Select a book in that window and press Start above.')
    elif external:st.caption('Connected to your regular Chrome. Select a book and press Start above.')
    else:st.warning('Chrome is not connected. Open capture Chrome below or enable the connection extension.')
    st.caption(f"Model for the next run: {review_options['model']}")
    with st.expander('Use a book selected in another browser'):
        reader_url=st.text_input('Kindle book URL',value='https://read.amazon.co.jp/',help='Paste the URL of the open book. Close capture Chrome first, then reopen it with the button below.')
    x,y=st.columns([1,2])
    with x:
        if st.button('1. Open Chrome for Kindle',type='primary',disabled=alive or starting):
            try:
                folder=create_session(url=reader_url);st.session_state['capture_session']=str(folder);st.rerun()
            except ValueError as exc:st.error(str(exc))
    with y:st.caption('Sign in to Amazon in the opened Chrome window and select your book. The dedicated Chrome profile retains your login.')
    if folder is None:return
    s=read(folder/'state.json');phase=s['phase']
    if s.get('job') and (Path(s['job'])/'status.json').exists():
        job_status=read(Path(s['job'])/'status.json')
        st.info(f"Captured: {s.get('count',0)} screens / {english_message(job_status['message'])}")
    else:
        st.info(english_message(s['message']))
    busy=phase in {'starting','capturing','detecting','updating'} or bool(s.get('job') and is_running(Path(s['job'])))
    datafolder=Path(s.get('active_run') or folder)
    if (datafolder/'capture.json').exists():
        manifest=read(datafolder/'capture.json');images=manifest['pages']
        st.caption(f'Saved screens: {len(images)} (not book page numbers)')
        if images:
            with st.expander('Inspect captured screens',expanded=phase in {'test_ready','attention'}):
                cols=st.columns(2)
                for column,item in zip(cols,images[-2:]):
                    column.image(str(datafolder/item['image']),caption=item['image'],use_container_width=True)
            if not busy and not s.get('job'):
                if alive and st.button('Retry test capture (archive previous images)'):
                    command(folder,'reset');st.toast('Archiving the previous test capture')
                if st.button('Convert saved screens only',disabled=not review_ready):
                    save(folder/'conversion-options.json',dict(**review_options,ocr_engine=st.session_state.get('shared_ocr_engine','Marker').lower()))
                    if alive:command(folder,'convert',gemma=True)
                    else:convert_saved(folder,gemma=True)
                    st.rerun(scope='fragment')
    if alive:
        a,b=st.columns(2)
        if a.button('Stop capture',disabled=not busy):(folder/'stop').touch()
        if b.button('Close capture Chrome'):
            (folder/'stop').touch();(folder/'close').touch()
    if s.get('job') and (Path(s['job'])/'output.json').exists():
        output=read(Path(s['job'])/'output.json')
        path=Path(output['path'])
        if not is_running(Path(s['job'])) and (Path(s['job'])/'original.md').exists():
            from delivery import ensure_delivery
            delivered=ensure_delivery(Path(s['job']))
            path=Path(delivered['path'])
        if path.exists():
            complete=output['capture_complete'] and output['ocr_pages']==output['expected_pages']
            if complete:st.success('OCR has been saved.')
            else:st.warning('Partial Markdown has been saved. Full completion is not confirmed.')
            st.code(str(path),language=None)
            st.caption('Export OCR text together with separately marked, unapproved Gemma suggestions. HTML is optional; source images are always preserved.')
            if not is_running(Path(s['job'])):
                from delivery_ui import output_buttons
                output_buttons(Path(s['job']),'capture-'+folder.name)
            else:
                st.download_button('Download partial MD',path.read_bytes(),file_name=path.name,key='book-download-'+folder.name)
    if s.get('job'):
        if st.session_state.get('capture_adopted')!=s['job']:
            st.session_state['job']=s['job'];st.session_state['capture_adopted']=s['job'];st.rerun()
        st.success('Import complete. Conversion progress and results appear below.')
    if phase in {'error','attention'}:
        st.caption('Saved images are preserved. Check the reader, then detect again or resume.')

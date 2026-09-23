"""Shared provider selector for uploaded documents and Kindle capture."""
import hashlib
import json
import streamlit as st
from review_connector import test_and_save, load_profile

def render(local_model):
    provider = st.selectbox('Review provider', ['Recommended: Local Gemma 4', 'Advanced: OpenAI-compatible API'], key='review_provider')
    st.session_state['review_ready'] = provider == 'Recommended: Local Gemma 4'
    options = dict(model=local_model, review_connector=None)
    if provider == 'Advanced: OpenAI-compatible API':
        st.warning('A vision-capable model is required. OpenAI-compatible does not guarantee image support, JSON support, accuracy or successful completion. Gemma 4 remains the recommended tested configuration.')
        base = st.text_input('API base URL', 'http://127.0.0.1:1234/v1', key='connector_base')
        model = st.text_input('Vision model identifier', key='connector_model')
        key = st.text_input('API key (optional for local servers)', type='password', key='connector_key')
        response_mode = st.selectbox('JSON response mode', ['json_schema', 'json_object', 'prompt'], key='connector_format', help='Use JSON Schema when supported. Other modes retain local output validation.')
        token_field = st.selectbox('Output token parameter', ['max_tokens', 'max_completion_tokens'], key='connector_tokens')
        effort = st.selectbox('Reasoning effort (server dependent)', ['server_default', 'none', 'minimal', 'low', 'medium', 'high'], key='connector_effort', help='Server default omits this parameter. For thinking models, none can reserve the output budget for OCR JSON when supported.')
        consent = st.checkbox('I allow images and OCR text to be sent to this endpoint when I start a job.', key='connector_consent')
        st.caption('Remote endpoints can receive book content and may charge fees. Only a generated test image is sent by the test button. Keys are stored in a private local profile, outside job exports. OCR finishes before external review; this app does not manage the endpoint server or its GPU memory.')
        settings = dict(base_url=base, model=model, api_key=key, format=response_mode, token_field=token_field, consent=consent, reasoning_effort=effort)
        fingerprint = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
        if st.button('Test vision connection and enable', disabled=not consent):
            try:
                with st.spinner('Testing a synthetic image and JSON response…'):
                    identifier = test_and_save(settings)
                st.session_state['tested_connector'] = (fingerprint, identifier)
            except Exception as exc:
                st.session_state.pop('tested_connector', None)
                st.error(str(exc))
        tested = st.session_state.get('tested_connector')
        if tested and tested[0] == fingerprint and consent:
            try:
                cfg = load_profile(tested[1])
                options = dict(model=cfg['model'], review_connector=tested[1])
                st.session_state['review_ready'] = True
                st.success('Synthetic vision/JSON test passed. This is not a quality guarantee.')
                st.caption('Destination: '+cfg['base_url']+' · Model: '+cfg['model'])
            except ValueError as exc:
                st.error(str(exc))
        else:
            st.info('Configure and pass the synthetic test before starting. Changing any setting requires a new test.')
    st.session_state['active_review_options'] = options
    return options

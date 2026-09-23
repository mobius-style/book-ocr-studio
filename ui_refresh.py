"""Poll only while asynchronous work needs UI updates."""
from functools import wraps
from pathlib import Path
import streamlit as st
from core import read,is_running

def job_pending(path):
    if not path:return False
    folder=Path(path)
    if not (folder/'status.json').exists():return False
    return is_running(folder) or read(folder/'status.json').get('state') in {'ready','queued'}

def capture_pending():
    from kindle_capture import running
    path=st.session_state.get('capture_session')
    if not path:return False
    folder=Path(path)
    s=read(folder/'state.json')
    # Child process may not have acquired its lock yet; still poll startup.
    if s.get('phase')=='starting':return True
    if not running(folder):return job_pending(s.get('job'))
    return (any((folder/'commands').glob('*.json')) or
            s.get('phase') in {'starting','capturing','detecting','updating'} or
            (folder/'close').exists() or job_pending(s.get('job')))

def adaptive_fragment(seconds,pending):
    def decorate(fn):
        @wraps(fn)
        def render(*args,**kwargs):
            polling=bool(pending())
            @st.fragment(run_every=seconds if polling else None)
            def body():
                fn(*args,**kwargs)
                if bool(pending())!=polling:
                    st.rerun()  # Register or remove timer after a state transition.
            return body()
        return render
    return decorate

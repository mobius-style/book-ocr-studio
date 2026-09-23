"""Linux subprocess supervisor: release owned descendants when the caller exits.

A private pipe, not a PID/name scan, defines ownership. Closing the caller's
write end (including SIGKILL) asks the independent supervisor to stop its group.
Normal child exit and SIGTERM also clean up remaining group members.
"""
import json
import os
import select
import signal
import subprocess
import sys
import time
import weakref
from pathlib import Path


def _close(fd):
    try: os.close(fd)
    except OSError: pass


class OwnedPopen(subprocess.Popen):
    def __init__(self, args, **kwargs):
        if os.name != 'posix' or not sys.platform.startswith('linux'):
            raise RuntimeError('Owned process supervision requires Linux')
        if kwargs.pop('shell', False) or kwargs.get('preexec_fn') or kwargs.get('pass_fds'):
            raise ValueError('OwnedPopen requires direct argv without preexec_fn/pass_fds')
        reader, writer = os.pipe2(os.O_CLOEXEC)
        self._pipe_finalizer = None
        try:
            kwargs['start_new_session'] = True
            kwargs['pass_fds'] = (reader,)
            super().__init__([sys.executable, str(Path(__file__).resolve()), '--watch',
                              str(reader), json.dumps([os.fspath(a) for a in args])], **kwargs)
            self._pipe_finalizer = weakref.finalize(self, _close, writer)
        except BaseException:
            _close(writer)
            raise
        finally:
            _close(reader)

    def wait(self, timeout=None):
        result = super().wait(timeout=timeout)
        finalizer = getattr(self, '_pipe_finalizer', None)
        if finalizer: finalizer()
        return result


def _watch(reader, args):
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    child = None
    result = 1
    try:
        # Avoid starting a model if the caller already vanished during spawn.
        if select.select([reader], [], [], 0)[0] and not os.read(reader, 1):
            return 125
        child = subprocess.Popen(args, start_new_session=True, close_fds=True)
        while not stopping:
            code = child.poll()
            if code is not None:
                result = code if code >= 0 else 128-code
                break
            if select.select([reader], [], [], .1)[0] and not os.read(reader, 1):
                stopping = True
        if stopping: result = 143
    finally:
        if child:
            # Only the process group created above is signalled. External API
            # servers and other applications are never selected by name.
            try: os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: child.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
            # The leader may exit before a model runner/grandchild does.
            time.sleep(.1)
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait()
        _close(reader)
    return result


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] != '--watch':
        raise SystemExit('Internal owned-process supervisor')
    raise SystemExit(_watch(int(sys.argv[2]), json.loads(sys.argv[3])))

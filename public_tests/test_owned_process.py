"""Actual subprocess lifecycle tests, including a killed owner and stubborn children."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from owned_process import OwnedPopen


def alive(pid):
    try: return (Path('/proc')/str(pid)/'stat').read_text().split(') ', 1)[1].split()[0] != 'Z'
    except FileNotFoundError: return False


def until(condition, timeout=8):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        if condition(): return
        time.sleep(.05)
    raise AssertionError('Timed out waiting for process state')


class OwnedProcessTests(unittest.TestCase):
    def exercise(self, mode):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d); record = tmp/'child.json'
            child = tmp/'child.py'
            child.write_text("""import os,sys,json,signal,subprocess,time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
p=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])
time.sleep(.2)
Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid]))
if sys.argv[2]=='normal':raise SystemExit(7)
time.sleep(60)
""")
            unrelated = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(60)'])
            owner = None; proc = None; pids = []
            try:
                if mode == 'owner_kill':
                    code = "from owned_process import OwnedPopen;import sys,time;p=OwnedPopen(sys.argv[1:]);print(p.pid,flush=True);time.sleep(60)"
                    owner = subprocess.Popen([sys.executable, '-c', code, sys.executable, str(child), str(record), mode], cwd=ROOT, stdout=subprocess.PIPE, text=True)
                    supervisor = int(owner.stdout.readline())
                else:
                    proc = OwnedPopen([sys.executable, str(child), str(record), mode]); supervisor = proc.pid
                until(record.exists); pids = json.loads(record.read_text())
                if mode == 'owner_kill': owner.kill(); owner.wait()
                elif mode == 'terminate': proc.terminate()
                if proc:
                    result = proc.wait(timeout=8)
                    self.assertEqual(result, 7 if mode == 'normal' else 143)
                until(lambda: all(not alive(p) for p in [supervisor, *pids]))
                self.assertIsNone(unrelated.poll())
            finally:
                if owner and owner.poll() is None: owner.kill(); owner.wait()
                if owner and owner.stdout: owner.stdout.close()
                if proc and proc.poll() is None: proc.terminate(); proc.wait(timeout=8)
                for pid in pids:
                    if alive(pid): os.kill(pid, signal.SIGKILL)
                unrelated.terminate(); unrelated.wait()

    def test_normal_exit_reaps_stubborn_descendant(self): self.exercise('normal')
    def test_terminate_reaps_stubborn_group(self): self.exercise('terminate')
    def test_killed_owner_releases_group(self): self.exercise('owner_kill')
    def test_missing_executable_reports_failure(self):
        p=OwnedPopen(['/nonexistent-synthetic-test-executable'], stderr=subprocess.DEVNULL)
        self.assertNotEqual(p.wait(timeout=5), 0)

if __name__ == '__main__': unittest.main()

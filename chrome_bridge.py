"""Authenticated loopback bridge for the user's existing Chrome window."""
import base64,fcntl,json,queue,secrets,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from core import ROOT,read,save
PORT=8508
KEY=ROOT/'.chrome-bridge-key'
def key():
    if not KEY.exists():
        try:
            with KEY.open('x') as f:f.write(secrets.token_urlsafe(32))
            KEY.chmod(0o600)
        except FileExistsError:pass
    return KEY.read_text().strip()

def call(action,**args):
    import requests
    r=requests.post(f'http://127.0.0.1:{PORT}/rpc',json=dict(action=action,**args),headers={'X-Book-OCR-Key':key()},timeout=75)
    r.raise_for_status();data=r.json()
    if data.get('error'):raise RuntimeError(data['error'])
    return data.get('result')

class Mouse:
    def click(self,x,y):call('click',x=x,y=y)
    def move(self,x,y):call('move',x=x,y=y)
class ChromePage:
    def __init__(self):
        info=call('connect');self.viewport_size=dict(width=info['width'],height=info['height']);self.url=info['url'];self._title=info['title']
        self.frames=[self];self.main_frame=self;self.mouse=Mouse()
    def evaluate(self,script,arg=None):return call('evaluate',script=script,arg=arg)
    def bring_to_front(self):pass
    def wait_for_timeout(self,ms):time.sleep(ms/1000)
    def title(self):return self._title
    def screenshot(self,clip=None,animations=None,**kw):
        data=base64.b64decode(call('screenshot',clip=clip))
        if kw.get('path'):Path(kw['path']).write_bytes(data)
        return data

def run():
    requests_q=queue.Queue();pending={};lock=threading.Lock()
    class H(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_GET(self):
            if self.path!='/health':self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"service":"book-ocr-chrome"}')
        def do_POST(self):
            if self.headers.get('X-Book-OCR-Key')!=key():self.send_error(403);return
            if int(self.headers.get('Content-Length',0))>20_000_000:self.send_error(413);return
            try:
                data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
                if self.path=='/poll':
                    save(ROOT/'chrome-bridge-status.json',dict(connected=True,seen=time.time()))
                    try:result=requests_q.get(timeout=1)
                    except queue.Empty:result=None
                elif self.path=='/reply':
                    with lock:entry=pending.get(data['id'])
                    if entry:entry['data']=data;entry['event'].set()
                    result={}
                elif self.path=='/rpc':
                    if data.get('action') not in {'connect','evaluate','click','move','screenshot','disconnect'}:self.send_error(400);return
                    ident=uuid.uuid4().hex;entry=dict(event=threading.Event())
                    with lock:pending[ident]=entry
                    requests_q.put(dict(id=ident,deadline=time.time()+65,**data))
                    ok=entry['event'].wait(66)
                    with lock:pending.pop(ident,None)
                    result=entry['data'] if ok else dict(error='Cannot connect to the Chrome extension. Check the extension and Kindle tab.')
                else:self.send_error(404);return
                body=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception as exc:self.send_error(500,str(exc))
    ThreadingHTTPServer(('127.0.0.1',PORT),H).serve_forever()
if __name__=='__main__':run()

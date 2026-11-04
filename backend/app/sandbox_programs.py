"""Trusted programs copied into a microVM; never imported/executed on the API host."""

RUNNER = r'''
import json, os, selectors, signal, subprocess, sys, time, resource, shutil
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
def limit():
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (4194304, 4194304))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
command = list(sys.argv[1:])
command[0] = shutil.which(command[0]) or command[0]
process = subprocess.Popen(command, cwd='/vercel/sandbox/workspace', stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, preexec_fn=limit, env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','LANG':'C.UTF-8'})
selector = selectors.DefaultSelector()
selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
logs = {'stdout': bytearray(), 'stderr': bytearray()}
start = time.monotonic()
reason = ''
try:
    while selector.get_map():
        if time.monotonic()-start > 25:
            reason = 'Execution stopped after 25 seconds.'
            break
        for key, _ in selector.select(0.1):
            chunk = os.read(key.fileobj.fileno(), 4096)
            if not chunk:
                selector.unregister(key.fileobj)
                continue
            logs[key.data].extend(chunk)
            if sum(len(v) for v in logs.values()) > 65536:
                reason = 'Execution stopped at the 64 KB output limit.'
                break
        if reason:
            break
finally:
    try: os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError: pass
    process.wait()
    selector.close()
print(json.dumps({'stdout':bytes(logs['stdout'])[:65536].decode('utf-8','replace'),'stderr':bytes(logs['stderr'])[:65536].decode('utf-8','replace'),'exit_code':124 if reason else process.returncode,'reason':reason}))
'''

PREVIEW_SERVER = r'''
import functools, http.server, os, secrets, sys, urllib.parse
token = sys.argv[1]
root = '/vercel/sandbox/previews'
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=root, **kwargs)
    def do_GET(self):
        parsed=urllib.parse.urlsplit(self.path)
        parts=parsed.path.split('/')
        if len(parts)<3 or not secrets.compare_digest(parts[1],token):
            self.send_error(404)
            return
        self.path='/'+'/'.join(parts[2:])
        super().do_GET()
    def do_HEAD(self):
        self.do_GET()
    def list_directory(self, path):
        self.send_error(404)
        return None
    def translate_path(self, path):
        resolved=super().translate_path(path)
        if os.path.commonpath([os.path.realpath(root),os.path.realpath(resolved)]) != os.path.realpath(root):
            return '/nonexistent'
        return resolved
    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; form-action 'none'; base-uri 'self'; worker-src 'none'")
        super().end_headers()
    def log_message(self, *args):
        pass
http.server.ThreadingHTTPServer(('0.0.0.0',3000),Handler).serve_forever()
'''

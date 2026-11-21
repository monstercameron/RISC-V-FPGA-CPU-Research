"""Local connection between the visualizer and the real RTL simulator.

Only serves this viewer and runs the fixed project build command. No arbitrary
shell commands, uploaded code, external bindings or third-party dependencies.
SPDX-License-Identifier: MIT
"""
from pathlib import Path
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import subprocess
import sys
import threading
import webbrowser
from urllib.parse import urlsplit, parse_qs
from program_catalog import PROGRAMS
from program_inputs import validate_inputs

ROOT=Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=0,help='0 selects an available local port')
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args()
    token=secrets.token_urlsafe(32)
    lock=threading.Lock()
    state={'running':False,'run':0,'status':'ready','log':[],'last_success':0}
    origin=f'http://127.0.0.1:{args.port}'

    def build(program,inputs):
        try:
            request_path=ROOT/'build/cpu/visualizer/request-inputs.json'
            request_path.parent.mkdir(parents=True,exist_ok=True)
            request_path.write_text(json.dumps(inputs),encoding='utf-8')
            process=subprocess.Popen([sys.executable,'-u','-B','sim/cpu/build_visualizer.py','--program',program,'--inputs-json',str(request_path)],
                cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                encoding='utf-8',errors='replace')
            for line in process.stdout:
                with lock:
                    state['log'].append(line.rstrip())
                    state['log']=state['log'][-30:]
            code=process.wait()
            with lock:
                state['status']='passed' if code==0 else 'failed'
                if code==0: state['last_success']=state['run']
        except Exception as exc:
            with lock:
                state['status']='failed';state['log'].append(str(exc))
        finally:
            with lock: state['running']=False

    class Handler(BaseHTTPRequestHandler):
        def respond(self,code,data,kind='application/json; charset=utf-8'):
            if not isinstance(data,bytes): data=json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.end_headers()
            self.wfile.write(data)
        def valid_host(self):
            return self.headers.get('Host')==f'127.0.0.1:{args.port}'
        def do_GET(self):
            if not self.valid_host(): return self.respond(403,{'error':'Use the printed loopback URL.'})
            route=self.path.split('?',1)[0]
            if route=='/api/status':
                with lock: snapshot=dict(state);snapshot['log']=list(state['log'])
                snapshot['token']=token
                snapshot['project']=str(ROOT)
                return self.respond(200,snapshot)
            if route=='/api/program':
                query=parse_qs(urlsplit(self.path).query,keep_blank_values=True)
                program=query.get('program',[None])[0]
                if set(query)!={'program'} or len(query['program'])!=1 or program not in PROGRAMS:
                    return self.respond(400,{'error':'Choose one built-in program.'})
                saved=ROOT/'build/cpu/programs'/program/'viewer-data.json'
                if not saved.is_file():
                    return self.respond(404,{'error':'No saved run yet. Click Run simulation to build this lesson.'})
                return self.respond(200,saved.read_bytes())
            paths={'/':('cpu/cpu-visualizer.html','text/html; charset=utf-8'),
                   '/cpu-visualizer.html':('cpu/cpu-visualizer.html','text/html; charset=utf-8'),
                   '/api/capture':('build/cpu/visualizer/viewer-data.json','application/json'),
                   '/core-explainer.html':('cpu/core-explainer.html','text/html; charset=utf-8'),
                   '/README.md':('cpu/README.md','text/plain; charset=utf-8'),
                   '/architecture.md':('cpu/architecture.md','text/plain; charset=utf-8'),
                   '/verification.json':('cpu/verification.json','application/json'),
                   '/rtl/cpu/rv64_core.sv':('rtl/cpu/rv64_core.sv','text/plain; charset=utf-8')}
            if route=='/favicon.ico': return self.respond(204,b'','image/x-icon')
            if route not in paths: return self.respond(404,{'error':'Unknown route'})
            name,kind=paths[route]
            path=ROOT/name
            if not path.is_file(): return self.respond(404,{'error':'Build the viewer first: python -B sim/cpu/build_visualizer.py'})
            self.respond(200,path.read_bytes(),kind)
        def do_POST(self):
            if (not self.valid_host() or self.headers.get('Origin')!=origin or
                self.headers.get('X-CPU-Token')!=token):
                return self.respond(403,{'error':'Run requests must come from this viewer.'})
            parsed=urlsplit(self.path)
            if parsed.path!='/api/run': return self.respond(404,{'error':'Unknown route'})
            choices=parse_qs(parsed.query,keep_blank_values=True)
            if set(choices)-{'program'} or len(choices.get('program',['demo']))!=1:
                return self.respond(400,{'error':'Choose one built-in program.'})
            program=choices.get('program',['demo'])[0]
            if program not in PROGRAMS: return self.respond(400,{'error':'Unknown program'})
            try:
                if self.headers.get('Transfer-Encoding'): raise ValueError('Chunked requests are unsupported.')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<=length<=8192: raise ValueError('Input request must be at most 8192 bytes.')
                inputs=None
                if length:
                    if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
                        raise ValueError('Send input values as JSON.')
                    self.connection.settimeout(5)
                    payload=json.loads(self.rfile.read(length))
                    if not isinstance(payload,dict) or set(payload)!={'inputs'} or payload['inputs'] is None:
                        raise ValueError('Provide an inputs object.')
                    inputs=payload['inputs']
                inputs=validate_inputs(program,inputs)
            except (ValueError,UnicodeError,OSError,RecursionError) as exc:
                return self.respond(400,{'error':str(exc)})
            with lock:
                if state['running']: return self.respond(409,{'error':'A simulation is already running.'})
                state.update(running=True,run=state['run']+1,status='running',program=program,inputs=inputs,log=['Compiling C, then simulating the CPU…'])
            threading.Thread(target=build,args=(program,inputs),daemon=True).start()
            self.respond(202,{'status':'running'})
        def log_message(self,*args): pass

    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    args.port=server.server_address[1]
    origin=f'http://127.0.0.1:{args.port}'
    print(f'CPU visualizer connected to this project: {ROOT}',flush=True)
    print(origin,flush=True)
    print('Use Run simulation in the viewer. Ctrl+C stops the local connection.',flush=True)
    if not args.no_open: webbrowser.open(origin)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__': main()

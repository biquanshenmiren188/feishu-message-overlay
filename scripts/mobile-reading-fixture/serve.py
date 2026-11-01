"""Serve an inspected graph plus optional candidate; inject synthetic APIs/recorder only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import argparse, mimetypes, json, re, time

p=argparse.ArgumentParser()
p.add_argument('--baseline',type=Path,default=Path(__file__).resolve().parents[3]/'mobile-reading-live-baseline')
p.add_argument('--overlay',type=Path)
p.add_argument('--port',type=int,default=8099)
p.add_argument('--out',type=Path,help='Local synthetic reports only; defaults beside the baseline')
a=p.parse_args();here=Path(__file__).resolve().parent
roots=[r.resolve() for r in [a.overlay,a.baseline] if r]
evidence=(a.out or a.baseline.resolve().parent/'mobile-reading-fixture-evidence').resolve()/str(a.port)
def find(name):
    for root in roots:
        file=(root/name).resolve()
        if file.is_relative_to(root) and file.is_file(): return file

entry=find('robot-push/index.html');assert entry,'Missing baseline BOT entry'
html=entry.read_text(encoding='utf-8')
modules=re.findall(r'<script[^>]+type="module"[^>]+src="([^"]+)"',html)
gate=None
for module in modules:
    file=find(module.split('?')[0].removeprefix('/radar/'))
    if file:
        text=file.read_text(encoding='utf-8')
        match=re.search(r'from\s*["\']([^"\']*mobile-scroll[^"\']*)["\']',text)
        if match: gate=match.group(1);break
assert gate,'Inspected entry must import a mobile-scroll module'
injection='<script>window.__fixtureProvenance='+json.dumps({'baseline':str(roots[-1]),'overlay':str(roots[0]) if a.overlay else None,'gateURL':gate})+'</script><script src="/__diagnostic/production-boot.js"></script>'
html=html.replace('<head>','<head>'+injection,1)

class Handler(BaseHTTPRequestHandler):
    # A long-lived tool subprocess may have a small undrained stdout pipe.
    # Routine asset logs must not block responses during repeated reloads.
    def log_message(self,*args):pass

    def do_POST(self):
        if urlparse(self.path).path!='/__fixture-report':self.send_error(404);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=10*1024*1024:self.send_error(413);return
            value=json.loads(self.rfile.read(length))
            assert value.get('syntheticOnly') is True and value.get('kind') in ['case','suite-progress','suite']
            report=value['report'];assert isinstance(report,dict)
            if value['kind']=='case':assert report.get('productionGraph') is True and report.get('syntheticData') is True
            else:assert isinstance(report.get('reports'),list) and all(r.get('syntheticData') is True for r in report['reports'])
            scenario=re.sub(r'[^A-Za-z0-9_-]','_',str(report.get('scenario',value['kind'])))[:70]
            evidence.mkdir(parents=True,exist_ok=True)
            file=evidence/(str(time.time_ns())+'-'+scenario+'.json')
            with file.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False)
            body=json.dumps({'saved':str(file)}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
            print(json.dumps({'report':file.name}),flush=True)
        except (ValueError,KeyError,AssertionError,TypeError):self.send_error(400,'Expected a synthetic diagnostic report')
    def do_GET(self):
        url=urlparse(self.path).path
        if url in ['/','/radar/robot-push/','/radar/robot-push/index.html']:
            body=html.encode();mime='text/html'
        elif url=='/__diagnostic/production-boot.js':
            body=(here/'production-boot.js').read_bytes();mime='text/javascript'
        else:
            relative=url.removeprefix('/radar/').lstrip('/')
            if relative=='push-test/manifest.webmanifest': relative='pwa-public/manifest.webmanifest'
            file=find(relative)
            if not file:self.send_error(404);return
            body=file.read_bytes();mime='text/javascript' if file.suffix in ['.js','.mjs'] else mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
        self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"connect-src 'self'; worker-src 'none'; img-src 'self' data:; media-src 'none'")
        self.end_headers();self.wfile.write(body)

print(f'Inspected graph, SYNTHETIC data only: http://127.0.0.1:{a.port}/radar/robot-push/',flush=True)
print(json.dumps({'syntheticEvidenceDirectory':str(evidence)}),flush=True)
ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()

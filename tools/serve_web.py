#!/usr/bin/env python3
"""Local-only CVCC workbench. Compilation stays on this machine."""
import argparse
import io
import zipfile
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from workspace_store import WorkspaceStore, Conflict
from rom_exports import exports
from cartridge import profiles
from project_source import read_project, validate_files, file_bytes

ROOT = Path(__file__).resolve().parents[1]
BUILD_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def send(self, status, data, content_type='application/json'):
        if isinstance(data, dict):
            data = json.dumps(data).encode()
        if isinstance(data, str):
            data = data.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        origin = self.headers.get('Origin')
        return self.headers.get('Host') in hosts and (not origin or origin in {f'http://{h}' for h in hosts})

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': 'Local origin required'})
        route = urlsplit(self.path).path
        if route == '/api/config':
            examples = [{'id': name, 'files': read_project(ROOT / 'examples' / name)} for name in ('square', 'counter', 'patrol', 'masks', 'logic', 'states', 'functions', 'banks')]
            if self.server.local_example:
                examples.append(dict(id=self.server.local_example.stem, files={'main.cvc':self.server.local_example.read_text()}, local=True))
            if self.server.project:
                examples.append(dict(id=self.server.project.name, files=read_project(self.server.project), local=True))
            return self.send(200, dict(examples=examples, cartridges=profiles(ROOT/'build/cvcc'), player_available=all((self.server.player / f).is_file() for f in ('core.js', 'core.wasm'))))
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/workspace.js': ('workspace.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8'),
                 '/player.js': ('player.js', 'text/javascript; charset=utf-8')}
        if route in files:
            name, mime = files[route]
            return self.send(200, (ROOT / 'web' / name).read_bytes(), mime)
        if route in ('/player/core.js', '/player/core.wasm'):
            path = self.server.player / route.rsplit('/', 1)[-1]
            if path.is_file():
                return self.send(200, path.read_bytes(), 'application/wasm' if path.suffix == '.wasm' else 'text/javascript')
        return self.send(404, {'error': 'Not found'})

    def workspace_request(self, action):
        if self.headers.get_content_type() != 'application/json':
            return self.send(415, {'error': 'JSON required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2 * 1024 * 1024:
                return self.send(413, {'error': 'Request too large'})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict): raise ValueError('Expected JSON object')
            result = self.server.workspaces.dispatch(action, payload)
            return self.send(200, result)
        except Conflict as exc:
            return self.send(409, {'error': str(exc)})
        except KeyError:
            return self.send(409, {'error': 'Sessione scaduta: riapri il progetto da Recenti. La bozza resta nel browser.'})
        except (ValueError, OSError, TypeError) as exc:
            return self.send(400, {'error': str(exc)})
        except subprocess.TimeoutExpired:
            return self.send(504, {'error': 'Operazione scaduta. Controlla la destinazione prima di riprovare.'})

    def do_POST(self):
        if not self.allowed():
            return self.send(403, {'error': 'Local origin required'})
        route = urlsplit(self.path).path
        if route.startswith('/api/workspace/'):
            return self.workspace_request(route.rsplit('/', 1)[-1])
        if route not in ('/api/compile', '/api/project-download'):
            return self.send(404, {'error': 'Not found'})
        if self.headers.get_content_type() != 'application/json':
            return self.send(415, {'error': 'JSON required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 2 * 1024 * 1024:
                return self.send(413, {'error': 'Source exceeds request limit'})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict): raise ValueError('Expected JSON object')
            if 'files' in payload:
                files = validate_files(payload['files'])
                if 'main.cvc' not in files: raise ValueError('Project requires main.cvc')
            else:
                files = validate_files({'main.cvc':payload.get('source')})
        except (ValueError, AttributeError) as exc:
            return self.send(400, {'error': str(exc)})
        if route == '/api/project-download':
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for name,source in files.items(): z.writestr(name,file_bytes(source))
            return self.send(200,archive.getvalue(),'application/zip')
        if not BUILD_LOCK.acquire(blocking=False):
            return self.send(409, {'error': 'Another build is running'})
        owns_build_lock = True
        def finish(status, payload):
            nonlocal owns_build_lock
            # Release before the client sees completion and sends its next build.
            if owns_build_lock:
                BUILD_LOCK.release()
                owns_build_lock = False
            return self.send(status, payload)
        try:
            started = time.perf_counter()
            with tempfile.TemporaryDirectory(prefix='request-', dir=ROOT / '.work/web') as tmp:
                work = Path(tmp)
                project=work/'project';project.mkdir()
                for name,source in files.items():
                    file=project/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(file_bytes(source))
                path = project / 'main.cvc'
                out = work / 'result'
                result = subprocess.run([sys.executable, str(ROOT / 'tools/build_rom.py'), str(path), '--out-dir', str(out)], cwd=ROOT, capture_output=True, text=True, timeout=30)
                if result.returncode:
                    message = (result.stderr or result.stdout).replace(str(project)+'/', '')
                    match = re.search(r'([^\n:]+\.(?:cvc|h)):(\d+):(\d+): error: (.+)', message)
                    return finish(422, dict(error=message.strip(), file=match[1] if match else None, line=int(match[2]) if match else None, column=int(match[3]) if match else None))
                metadata = json.loads((out / 'build.json').read_text())
                symbols = dict((name, int(address,16)) for name,address in re.findall(r'^(\S+): EQU 0x([0-9A-F]+)$', (out/'program.sym').read_text(), re.M))
                rom = (out/'program.sg').read_bytes()
                code_bytes = symbols.get('ROM_END', 0)
                return finish(200, dict(rom=base64.b64encode(rom).decode(),
                    exports=exports(rom, code_bytes, backend=metadata["backend"], cartridge=metadata["cartridge"]),
                    backend=metadata["backend"], cartridge=metadata["cartridge"], bank_data_bytes=metadata["bank_data_bytes"],
                    basic=(out/'program.bas').read_text() if metadata['backend']=='legacy' else '', assembly=(out/'program.sj.asm').read_text(),
                    log=(out/'build.log').read_text(), elapsed_ms=round((time.perf_counter()-started)*1000),
                    rom_bytes=metadata['rom_bytes'], sha256=metadata['rom_sha256'],
                    ram_bytes=symbols.get('RAM_END',0)-symbols.get('RAM_START',0),
                    code_bytes=symbols.get('ROM_END',0)))
        except subprocess.TimeoutExpired:
            finish(504, {'error': 'Build timeout (30 seconds)'})
        except (OSError, ValueError) as exc:
            finish(500, {'error': str(exc)})
        finally:
            if owns_build_lock: BUILD_LOCK.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8844)
    parser.add_argument('--player-dist', type=Path, required=True, help='Existing GearSC3000 web dist; served read-only, never copied')
    parser.add_argument('--local-example', type=Path, help='Optional local .cvc example; source is served only by this local workbench')
    parser.add_argument('--project', type=Path, help='Local project folder containing main.cvc and headers')
    args = parser.parse_args()
    if args.project:
        read_project(args.project)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',args.project.name) or args.project.name in ('square','counter','patrol','masks','logic','states','functions'):
            parser.error('project folder must have a unique simple name')
    if args.project and args.local_example: parser.error('use either --project or --local-example')
    if args.local_example and (args.local_example.suffix != '.cvc' or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', args.local_example.stem) or args.local_example.stem in ('square','counter','patrol','masks','logic','states','functions') or not args.local_example.is_file()):
        parser.error('local example must be an existing .cvc file with a unique simple name')
    if not (ROOT/'build/cvcc').is_file():
        raise SystemExit('Build the frontend first: ./tools/build_frontend.sh')
    (ROOT/'.work/web').mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.workspaces = WorkspaceStore()
    server.player = args.player_dist.resolve()
    server.project = args.project.resolve() if args.project else None
    server.local_example = args.local_example.resolve() if args.local_example else None
    print(f'CVCC Workbench: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

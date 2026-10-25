#!/usr/bin/env python3
"""Local-only CVCC workbench. Compilation stays on this machine."""
import argparse
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
            examples = [{'id': name, 'source': (ROOT / 'examples' / f'{name}.cvc').read_text()} for name in ('square', 'counter')]
            return self.send(200, dict(examples=examples, player_available=all((self.server.player / f).is_file() for f in ('core.js', 'core.wasm'))))
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
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

    def do_POST(self):
        if not self.allowed():
            return self.send(403, {'error': 'Local origin required'})
        if urlsplit(self.path).path != '/api/compile':
            return self.send(404, {'error': 'Not found'})
        if self.headers.get_content_type() != 'application/json':
            return self.send(415, {'error': 'JSON required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 2 * 1024 * 1024:
                return self.send(413, {'error': 'Source exceeds request limit'})
            payload = json.loads(self.rfile.read(length))
            source = payload.get('source')
            if not isinstance(source, str) or len(source.encode()) > 1024 * 1024:
                return self.send(400, {'error': 'Expected source text, at most 1 MiB'})
        except (ValueError, AttributeError):
            return self.send(400, {'error': 'Invalid JSON request'})
        if not BUILD_LOCK.acquire(blocking=False):
            return self.send(409, {'error': 'Another build is running'})
        try:
            started = time.perf_counter()
            with tempfile.TemporaryDirectory(prefix='request-', dir=ROOT / '.work/web') as tmp:
                work = Path(tmp)
                path = work / 'sketch.cvc'
                path.write_text(source)
                out = work / 'result'
                result = subprocess.run([sys.executable, str(ROOT / 'tools/build_rom.py'), str(path), '--out-dir', str(out)], cwd=ROOT, capture_output=True, text=True, timeout=30)
                if result.returncode:
                    message = (result.stderr or result.stdout).replace(str(path), 'sketch.cvc')
                    match = re.search(r'sketch.cvc:(\d+):(\d+): error: (.+)', message)
                    return self.send(422, dict(error=message.strip(), line=int(match[1]) if match else None, column=int(match[2]) if match else None))
                metadata = json.loads((out / 'build.json').read_text())
                symbols = dict((name, int(address,16)) for name,address in re.findall(r'^(\S+): EQU 0x([0-9A-F]+)$', (out/'program.sym').read_text(), re.M))
                return self.send(200, dict(rom=base64.b64encode((out/'program.sg').read_bytes()).decode(),
                    basic=(out/'program.bas').read_text(), assembly=(out/'program.sj.asm').read_text(),
                    log=(out/'build.log').read_text(), elapsed_ms=round((time.perf_counter()-started)*1000),
                    rom_bytes=metadata['rom_bytes'], sha256=metadata['rom_sha256'],
                    ram_bytes=symbols.get('RAM_END',0)-symbols.get('RAM_START',0),
                    code_bytes=symbols.get('ROM_END',0)))
        except subprocess.TimeoutExpired:
            self.send(504, {'error': 'Build timeout (30 seconds)'})
        except (OSError, ValueError) as exc:
            self.send(500, {'error': str(exc)})
        finally:
            BUILD_LOCK.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8844)
    parser.add_argument('--player-dist', type=Path, required=True, help='Existing GearSC3000 web dist; served read-only, never copied')
    args = parser.parse_args()
    if not (ROOT/'build/cvcc').is_file():
        raise SystemExit('Build the frontend first: ./tools/build_frontend.sh')
    (ROOT/'.work/web').mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.player = args.player_dist.resolve()
    print(f'CVCC Workbench: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

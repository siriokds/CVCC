"""Integration checks against a running local workbench (default port 8844)."""
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get('CVCC_WEB_TEST_PORT', '8844'))


class WebTests(unittest.TestCase):
    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', PORT, timeout=40)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_compile_real_rom(self):
        source = (ROOT / 'examples/counter.cvc').read_text()
        status, body = self.request('POST', '/api/compile', json.dumps({'source': source}), {'Content-Type':'application/json'})
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        rom = base64.b64decode(result['rom'])
        self.assertEqual(len(rom), 32768)
        self.assertEqual(hashlib.sha256(rom).hexdigest(), '2f6b8572cb4f2a82383661587be1c5e845be0ecc975dea1455c0f4f1c73c66b8')
        self.assertEqual(result['sha256'], hashlib.sha256(rom).hexdigest())
        self.assertIn('IF v0 < 100', result['basic'])

    def test_diagnostics_no_rom(self):
        status, body = self.request('POST', '/api/compile', json.dumps({'source':'void setup(){noSuchCall();}\nvoid loop(){}'}), {'Content-Type':'application/json'})
        result = json.loads(body)
        self.assertEqual(status, 422)
        self.assertEqual(result['line'], 1)
        self.assertNotIn('rom', result)
        self.assertIn('unsupported function call', result['error'])

    def test_no_arbitrary_files_or_cross_origin(self):
        self.assertEqual(self.request('GET', '/../../.git/config')[0],404)
        self.assertEqual(self.request('GET', '/api/config',headers={'Origin':'https://example.invalid'})[0],403)
        self.assertEqual(self.request('GET', '/api/config',headers={'Host':'example.invalid'})[0],403)
        self.assertEqual(self.request('POST','/api/compile','source=x',{'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('POST','/api/compile','[]',{'Content-Type':'application/json'})[0],400)


if __name__ == '__main__':
    unittest.main(verbosity=2)

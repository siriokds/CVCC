"""Integration checks against a running local workbench (default port 8844)."""
import base64
import hashlib
import http.client
import json
import io
import zipfile
import tempfile
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
        source = (ROOT / 'examples/counter/main.cvc').read_text()
        status, body = self.request('POST', '/api/compile', json.dumps({'source': source}), {'Content-Type':'application/json'})
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        rom = base64.b64decode(result['rom'])
        self.assertEqual(len(rom), 8192)
        self.assertEqual(result['backend'], 'z80')
        self.assertEqual(result['sha256'], hashlib.sha256(rom).hexdigest())
        self.assertEqual(result['basic'], '')
        self.assertIn('cvcc_var_counter', result['assembly'])
        self.assertEqual([item['size'] for item in result['exports']], [8192,16384,32768,49152])
        for item in result['exports']:
            exported=base64.b64decode(item['rom'])
            self.assertEqual(len(exported),item['size'])
            self.assertEqual(exported[:result['code_bytes']],rom[:result['code_bytes']])
        self.assertEqual(base64.b64decode(result['exports'][0]['rom']),rom)

    def test_export_sizes_follow_payload(self):
        source='const uint8_t data[8192]={' + ','.join(['42']*8192) + '}; void setup(){} void loop(){waitFrame();}'
        status, body=self.request('POST','/api/compile',json.dumps({'source':source}),{'Content-Type':'application/json'})
        self.assertEqual(status,200,body)
        result=json.loads(body)
        self.assertGreater(result['code_bytes'],8192)
        self.assertEqual([item['size'] for item in result['exports']],[16384,32768,49152])

    def test_cartridge_metadata_banked_rom_and_zip(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools'))
        from project_source import read_project
        files=read_project(ROOT/'examples/banks')
        status,body=self.request('POST','/api/compile',json.dumps({'files':files}),{'Content-Type':'application/json'})
        self.assertEqual(status,200,body)
        result=json.loads(body)
        self.assertEqual(result['cartridge']['web_mapper'],4)
        self.assertEqual(result['cartridge']['ram_kib'],16)
        self.assertEqual(result['rom_bytes'],65536)
        self.assertEqual(result['exports'],[])
        rom=base64.b64decode(result['rom'])
        self.assertEqual(rom[32768:32800],(ROOT/'examples/banks/assets/square.bin').read_bytes())
        status,body=self.request('POST','/api/project-download',json.dumps({'files':files}),{'Content-Type':'application/json'})
        self.assertEqual(status,200,body)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(archive.read('cartridge.json').decode(),files['cartridge.json'])
        files['cartridge.json']='{"mapper":"sc3000","banks":{"2":"assets/square.bin"}}'
        status,body=self.request('POST','/api/compile',json.dumps({'files':files}),{'Content-Type':'application/json'})
        self.assertEqual(status,422,body)
        self.assertNotIn('rom',json.loads(body))

    def test_diagnostics_no_rom(self):
        status, body = self.request('POST', '/api/compile', json.dumps({'source':'void setup(){noSuchCall();}\nvoid loop(){}'}), {'Content-Type':'application/json'})
        result = json.loads(body)
        self.assertEqual(status, 422)
        self.assertEqual(result['line'], 1)
        self.assertNotIn('rom', result)
        self.assertIn('unsupported function call', result['error'])

    def test_project_headers_diagnostics_and_zip(self):
        files={'main.cvc':'#include "data/value.h"\nuint8_t x; void setup(){x=VALUE;} void loop(){waitFrame();}',
               'data/value.h':'#pragma once\nconst uint8_t VALUE=7;'}
        status,body=self.request('POST','/api/compile',json.dumps({'files':files}),{'Content-Type':'application/json'})
        self.assertEqual(status,200,body)
        status,body=self.request('POST','/api/project-download',json.dumps({'files':files}),{'Content-Type':'application/json'})
        self.assertEqual(status,200,body)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual({name:archive.read(name).decode() for name in archive.namelist()},files)
        files['data/value.h']='const uint8_t VALUE=7;\nvoid broken(){unknown=1;}'
        status,body=self.request('POST','/api/compile',json.dumps({'files':files}),{'Content-Type':'application/json'})
        self.assertEqual(status,422,body)
        result=json.loads(body);self.assertEqual(result['file'],'data/value.h');self.assertEqual(result['line'],2)
        files['../escape.h']=''
        self.assertEqual(self.request('POST','/api/project-download',json.dumps({'files':files}),{'Content-Type':'application/json'})[0],400)

    def test_binary_compile_and_zip(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools'))
        from project_source import read_project
        files=read_project(ROOT/'examples/functions')
        status,body=self.request('POST','/api/compile',json.dumps({'files':files}),{'Content-Type':'application/json'})
        self.assertEqual(status,200,body)
        result=json.loads(body)
        self.assertEqual(result['backend'],'z80')
        self.assertEqual(result['sha256'],hashlib.sha256(base64.b64decode(result['rom'])).hexdigest())
        status,body=self.request('POST','/api/project-download',json.dumps({'files':files}),{'Content-Type':'application/json'})
        self.assertEqual(status,200,body)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(archive.read('square.bin'),(ROOT/'examples/functions/square.bin').read_bytes())
        files['square.bin']={'base64':'%%%'}
        self.assertEqual(self.request('POST','/api/compile',json.dumps({'files':files}),{'Content-Type':'application/json'})[0],400)

    def test_workspace_save_conflict_and_binary_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'project'
            def workspace(action, payload, **headers):
                status, body=self.request('POST','/api/workspace/'+action,json.dumps(payload),{'Content-Type':'application/json',**headers})
                return status,json.loads(body)
            files={'main.cvc':'void setup(){} void loop(){waitFrame();}', 'data/pattern.bin':{'base64':'AAEC/w=='}}
            status,project=workspace('create',{'path':str(path),'files':files})
            self.assertEqual(status,200,project)
            edited={**files,'main.cvc':files['main.cvc']+' // saved'}
            status,saved=workspace('save',{'id':project['id'],'revision':project['revision'],'files':edited})
            self.assertEqual(status,200,saved)
            self.assertEqual((path/'main.cvc').read_text(),edited['main.cvc'])
            self.assertEqual((path/'data/pattern.bin').read_bytes(),bytes([0,1,2,255]))
            status,_=workspace('save',{'id':project['id'],'revision':project['revision'],'files':files})
            self.assertEqual(status,409)
            self.assertEqual((path/'main.cvc').read_text(),edited['main.cvc'])
            status,_=workspace('open',{'kind':'local','path':str(path)},Origin='https://example.invalid')
            self.assertEqual(status,403)
            status,_=workspace('save',{'id':'expired','files':files,'revision':'old'})
            self.assertEqual(status,409)

    def test_no_arbitrary_files_or_cross_origin(self):
        self.assertEqual(self.request('GET', '/../../.git/config')[0],404)
        self.assertEqual(self.request('GET', '/api/config',headers={'Origin':'https://example.invalid'})[0],403)
        self.assertEqual(self.request('GET', '/api/config',headers={'Host':'example.invalid'})[0],403)
        self.assertEqual(self.request('POST','/api/compile','source=x',{'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('POST','/api/compile','[]',{'Content-Type':'application/json'})[0],400)


if __name__ == '__main__':
    unittest.main(verbosity=2)

from pathlib import Path
import base64
import sys,tempfile,unittest,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from toolchain.project_source import expand,validate_files,read_project,remap,file_bytes
ROOT=Path(__file__).resolve().parents[1]
class Projects(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def write(self,name,text):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p
    def test_nested_once_comments_and_map(self):
        self.write('main.cvc','// #include "missing.h"\n#include "data/a.h"\n#include "data/a.h"\nvoid setup(){}\nvoid loop(){}\n')
        self.write('data/a.h','#pragma once\n#include "b.h" /* comment\n ignored */\nuint8_t x;\n')
        self.write('data/b.h','const uint8_t y=3;')
        source,mapping,inputs=expand(self.root)
        self.assertEqual(source.count('uint8_t x;'),1)
        p=self.write('flat.cvc',source)
        result=subprocess.run([ROOT/'compiler/build/cvcc',p],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        row=source.splitlines().index('const uint8_t y=3;')+1
        self.assertIn('data/b.h:1:7:',remap(f'{p}:{row}:7: error: invalid',p,mapping))
        self.assertEqual(len(inputs),3)
    def test_cycle_missing_escape_and_directives(self):
        for body in ['#include "main.cvc"','#include "missing.h"','#include "../outside.h"','#include <stdio.h>','#define X 2','/* unclosed']:
            with self.subTest(body=body):
                self.write('main.cvc',body)
                with self.assertRaises((ValueError,OSError)):expand(self.root)
    def test_symlink_escape(self):
        self.write('main.cvc','#include "escape.h"')
        (self.root/'escape.h').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):expand(self.root)
        with self.assertRaises(ValueError):read_project(self.root)
    def test_request_paths_and_limits(self):
        for name in ['../x.h','/tmp/x.h','a/../x.h','a//x.h','a\\x.h','x.json']:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):validate_files({'main.cvc':'',name:''})
        with self.assertRaises(ValueError):validate_files({'main.cvc':'x'*(1024*1024+1)})
    def test_binary_expansion_and_manifest(self):
        self.write('main.cvc','#include "data/sprite.h"\nvoid setup(){} void loop(){}')
        self.write('data/sprite.h','const uint8_t data[256]={\n#incbin "sprite.bin"\n};')
        data=bytes(range(256));(self.root/'data/sprite.bin').write_bytes(data)
        source,mapping,inputs=expand(self.root)
        self.assertEqual(file_bytes(inputs['data/sprite.bin']),data)
        self.assertEqual(file_bytes(read_project(self.root)['data/sprite.bin']),data)
        self.assertIn(','.join(map(str,range(16)))+',',source)
        result=subprocess.run([ROOT/'compiler/build/cvcc',self.write('flat.cvc',source)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(mapping[1],(str((self.root/'data/sprite.h').resolve()),2))
    def test_invalid_binaries(self):
        self.write('main.cvc','const uint8_t data[1]={\n#incbin "data.bin"\n};')
        for data in (b'',b'x'*8193):
            (self.root/'data.bin').write_bytes(data)
            with self.assertRaisesRegex(ValueError,'main.cvc:2:1: error: Binary must'):expand(self.root)
        (self.root/'data.bin').unlink();(self.root/'data.bin').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError,'escapes'):expand(self.root)
        for value in ('text',{'base64':'@@@'},{'base64':42}):
            with self.assertRaises(ValueError):validate_files({'main.cvc':'','data.bin':value})
        with self.assertRaises(ValueError):validate_files({'main.cvc':'','data.bin':{'base64':base64.b64encode(b'x'*(1024*1024+1)).decode()}})
    def test_header_diagnostic(self):
        self.write('main.cvc','#include "data/bad.h"\nvoid setup(){} void loop(){}')
        self.write('data/bad.h','uint8_t x;\nvoid helper(){ missing=1; }\n')
        result=subprocess.run([sys.executable,ROOT/'toolchain/build_rom.py',self.root,'--out-dir',self.root/'out'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('data/bad.h:2:',result.stderr)
        self.assertFalse((self.root/'out/program.sg').exists())
if __name__=='__main__':unittest.main(verbosity=2)

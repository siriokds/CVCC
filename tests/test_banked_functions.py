"""Explicit function placement: parser diagnostics, layout, stack and real Z80 execution."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class BankedFunctions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'output'

    def build(self, source, mapper='asc16l', **config):
        (self.root/'main.cvc').write_text(source)
        (self.root/'cartridge.json').write_text(json.dumps(dict(mapper=mapper,**config)))
        return subprocess.run([sys.executable,ROOT/'toolchain/build_rom.py',self.root,'--out-dir',self.out],capture_output=True,text=True)

    def test_tag_parsing_and_diagnostics(self):
        source='// __bank(99)\n/* __bank(88) */\n__bank(/* page */ 0x03)\nuint16_t f(uint16_t n){return n+1;}\nvoid setup(){f(1);printAt(0,"__bank(77)");}\nvoid loop(){waitFrame();}'
        result=self.build(source)
        self.assertEqual(result.returncode,0,result.stderr)
        metadata=json.loads((self.out/'build.json').read_text())
        self.assertEqual(metadata['cartridge']['code_banks'],[3])
        self.assertEqual(metadata['cartridge']['bank_count'],4)
        for tag in ('__bank(0)','__bank(1)','__bank(256)','__bank(-2)','__bank(03)',
                    '__bank(2+1)','__bank(n)','__bank(2,3)','__bank()', '__bank(2u)', '__bank(2) __bank(3)'):
            with self.subTest(tag=tag):
                result=self.build(tag+' void f(){} void setup(){} void loop(){}')
                self.assertNotEqual(result.returncode,0)
        for source in ('__bank(2) void setup(){} void loop(){}',
                       'void setup(){} __bank(2) void loop(){}',
                       '__bank(2) uint8_t n; void setup(){} void loop(){}',
                       'void setup(){__bank(2) waitFrame();} void loop(){}'):
            self.assertNotEqual(self.build(source).returncode,0)
        self.assertNotEqual(self.build('__bank(2) void f(){} void setup(){} void loop(){}','sg1000').returncode,0)
        (self.root/'part.h').write_text('__bank(3)\nvoid bad(){\n missing=1;\n}\n')
        result=self.build('#include "part.h"\nvoid setup(){} void loop(){}')
        self.assertIn('part.h:3:',result.stderr)
        source=self.root/'raw.cvc';source.write_text('__bank(2) void f(){} void setup(){} void loop(){}')
        result=subprocess.run([ROOT/'compiler/build/cvcc','--basic',source],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,'')

    def test_layout_collision_overflow_and_preservation(self):
        source='__bank(2) uint16_t a(){return 1234;} __bank(7) uint16_t b(){return a()+9;} void setup(){b();} void loop(){}'
        result=self.build(source)
        self.assertEqual(result.returncode,0,result.stderr)
        rom=(self.out/'program.sg').read_bytes()
        self.assertEqual(len(rom),8*16384)
        symbols={name:int(value,16) for name,value in re.findall(r'^(\S+): EQU 0x([0-9A-F]+)$',(self.out/'program.sym').read_text(),re.M)}
        for name in ('a','b'):
            self.assertLess(symbols['cvcc_fn_'+name],32768)
            self.assertTrue(32768<=symbols['cvcc_body_'+name]<49152)
        self.assertGreater(json.loads((self.out/'build.json').read_text())['bank_code_bytes'],0)
        replay=subprocess.run(['sjasmplus','-Wno-fileorg','program.sj.asm'],cwd=self.out,capture_output=True,text=True)
        self.assertEqual(replay.returncode,0,replay.stderr)
        self.assertEqual((self.out/'program.sg').read_bytes(),rom)
        (self.root/'data.bin').write_bytes(b'X')
        result=self.build(source,banks={'2':'data.bin'})
        self.assertIn('Code and binary data share bank(s): 2',result.stderr)
        self.assertEqual((self.out/'program.sg').read_bytes(),rom)
        # A single function cannot straddle a physical page.
        result=self.build('__bank(2) void huge(){'+'vramPoke(0,1);'*2400+'} void setup(){huge();} void loop(){}')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('bank 2 overflow after huge',result.stderr)
        self.assertEqual((self.out/'program.sg').read_bytes(),rom)
        result=self.build('__bank(2) void a(){b();} __bank(3) void b(){a();} void setup(){a();} void loop(){}')
        self.assertIn('recursive calls are unsupported',result.stderr)

    def test_nested_thunks_are_included_in_stack_budget(self):
        functions=''.join('__bank(%d) void f%d(){%s}'%(2+i%2,i,'f%d();'%(i+1) if i<59 else '') for i in range(60))
        result=self.build('void setup(){f0();} void loop(){}'+functions)
        self.assertEqual(result.returncode,0,result.stderr)
        symbols=(self.out/'program.sym').read_text()
        stack=int(re.search(r'STACK_BYTES: EQU 0x([0-9A-F]+)',symbols)[1],16)
        self.assertGreaterEqual(stack,60*6+32)
        # Fits under the old 256-byte reservation, exceeds the real call chain.
        result=self.build('uint8_t data[7800]; void setup(){f0();} void loop(){}'+functions,ram_kib=8)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('RAM_END+STACK_BYTES',result.stderr)

    @unittest.skipUnless(os.environ.get('CVCC_WEB_CORE'),'set CVCC_WEB_CORE to GearSF7000 Web core.js')
    def test_banked_calls_data_access_irq_and_reset_in_web_core(self):
        cases=[]
        for color in (2,4,6):
            result=self.build(f'void setup(){{screenDisable();vdpWrite(7,{color});}} void loop(){{waitFrame();}}','sg1000')
            self.assertEqual(result.returncode,0,result.stderr)
            path=self.root/f'color{color}.sg';path.write_bytes((self.out/'program.sg').read_bytes())
            cases.append(dict(path=str(path),mapper=7,ram=16,label=f'color{color}'))
        (self.root/'data.bin').write_bytes(bytes([7])*16384)
        source=(ROOT/'tests/fixtures/banked_functions/main.cvc').read_text()
        for mapper,ram,index in (('asc16l',8,4),('asc16l',16,4),('sega-dahjee-b',None,14)):
            result=self.build(source,mapper,banks={'5':'data.bin'},**({'ram_kib':ram} if ram else {}))
            self.assertEqual(result.returncode,0,result.stderr)
            path=self.root/f'{mapper}-{ram}.sg';path.write_bytes((self.out/'program.sg').read_bytes())
            cases.append(dict(path=str(path),mapper=index,ram=ram or 16,label=path.stem,heartbeat=True))
        path=self.root/'cases.json';path.write_text(json.dumps(cases))
        result=subprocess.run(['node',ROOT/'tests/web_core_cartridges.cjs',os.environ['CVCC_WEB_CORE'],path],capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main(verbosity=2)

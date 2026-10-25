"""Physical memory, bank packaging and optional real GearSF7000 Web execution.
CVCC_WEB_CORE=/absolute/path/to/core.js enables the WebAssembly tests in Node.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from toolchain.cartridge import load, profiles
from toolchain.project_source import read_project
from toolchain.rom_exports import exports


class Cartridges(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root/'out'

    def tearDown(self):
        self.temp.cleanup()

    def build(self, mapper, source, **config):
        (self.root/'main.cvc').write_text(source)
        (self.root/'cartridge.json').write_text(json.dumps(dict(mapper=mapper, **config)))
        return subprocess.run([sys.executable, ROOT/'toolchain/build_rom.py', self.root,
                               '--out-dir', self.out], capture_output=True, text=True)

    def test_ram_and_rom_capacity(self):
        for profile in profiles(ROOT/'compiler/build/cvcc'):
            capacity = profile['ram_end']-profile['ram_start']
            # Split arrays because the frontend intentionally limits each to 8192 elements.
            def arrays(size):
                return ''.join(f'uint8_t data{i}[{min(8192,size-i*8192)}];' for i in range((size+8191)//8192))
            with self.subTest(mapper=profile['id']):
                good = self.build(profile['id'], arrays(capacity-512)+'void setup(){} void loop(){waitFrame();}')
                self.assertEqual(good.returncode, 0, good.stderr)
                saved = (self.out/'program.sg').read_bytes()
                bad = self.build(profile['id'], arrays(capacity)+'void setup(){} void loop(){}')
                self.assertNotEqual(bad.returncode, 0)
                self.assertEqual((self.out/'program.sg').read_bytes(), saved)
        source = ''.join(f'const uint8_t data{i}[8192]={{'+','.join(['42']*8192)+'};' for i in range(4))+'void setup(){} void loop(){}'
        for mapper in ('sg1000', 'dahjee-b'):
            result = self.build(mapper, source)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.out/'program.sg').stat().st_size, 49152)
        for mapper in ('sc3000', 'sc3000-16k', 'asc16l', 'sega-dahjee-b'):
            self.assertNotEqual(self.build(mapper, source).returncode, 0)

    def test_bank_payload_and_replay(self):
        (self.root/'a.bin').write_bytes(bytes(range(256))*64)
        (self.root/'b.bin').write_bytes(b'last bank')
        result = self.build('asc16l', 'void setup(){vramWriteBank(0,5,0,9);} void loop(){waitFrame();}', banks={'2':'a.bin','5':'b.bin'})
        self.assertEqual(result.returncode, 0, result.stderr)
        rom = (self.out/'program.sg').read_bytes()
        self.assertEqual(len(rom), 98304)
        self.assertEqual(rom[32768:49152], (self.root/'a.bin').read_bytes())
        self.assertEqual(rom[49152:81920], b'\xff'*32768)
        self.assertEqual(rom[81920:], b'last bank'+b'\xff'*(16384-9))
        result = subprocess.run(['sjasmplus','-Wno-fileorg','program.sj.asm'], cwd=self.out, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.out/'program.sg').read_bytes(), rom)
        files = read_project(self.root)
        self.assertIn('cartridge.json', files)
        self.assertEqual(base64.b64decode(files['a.bin']['base64']), rom[32768:49152])
        profile = load(self.root, ROOT/'compiler/build/cvcc')[0]
        self.assertEqual(exports(rom, 2000, backend='z80', cartridge=profile), [])

    def test_invalid_banks_and_ram(self):
        (self.root/'a.bin').write_bytes(b'X')
        for config in ({'mapper':'unknown'}, {'mapper':'sc3000','ram_kib':8},
                       {'mapper':'asc16l','ram_kib':True}, {'mapper':'asc16l','ram_kib':None}, {'mapper':'asc16l','ram_kib':32},
                       {'mapper':'dahjee-b','banks':{'2':'a.bin'}},
                       {'mapper':'asc16l','banks':{'1':'a.bin'}},
                       {'mapper':'asc16l','banks':{'02':'a.bin'}},
                       {'mapper':'asc16l','banks':{'256':'a.bin'}},
                       {'mapper':'asc16l','banks':{'2':'../a.bin'}}):
            with self.subTest(config=config):
                self.assertNotEqual(self.build(source='void setup(){} void loop(){}', **config).returncode, 0)
        for code in ('bankRead(1,0);', 'bankRead(3,0);', 'bankRead(2,16384);',
                     'vramWriteBank(0,2,16380,8);', 'vramWriteBank(16380,2,0,8);', 'vramWriteBank(0,2,0,0);'):
            self.assertNotEqual(self.build('asc16l', 'void setup(){'+code+'} void loop(){}').returncode, 0)
        self.assertNotEqual(self.build('sc3000', 'void setup(){bankRead(2,0);} void loop(){}').returncode, 0)
        self.assertEqual(self.build('sc3000', 'void setup(){} void loop(){}').returncode, 0)
        profile = load(self.root, ROOT/'compiler/build/cvcc')[0]
        self.assertEqual([x['size'] for x in exports(b'X'+b'\xff'*8191, 1, backend='z80', cartridge=profile)], [8192,16384,32768])

    @unittest.skipUnless(os.environ.get('CVCC_WEB_CORE'), 'set CVCC_WEB_CORE to GearSF7000 Web core.js')
    def test_real_web_core_ram_banks_vram_and_reset(self):
        cases = []
        # Establish the pass pixel with the same renderer, independent of palette changes.
        for color in (2,6):
            self.assertEqual(self.build('sg1000', f'void setup(){{screenDisable();vdpWrite(7,{color});}} void loop(){{waitFrame();}}').returncode, 0)
            target = self.root/f'color{color}.sg';target.write_bytes((self.out/'program.sg').read_bytes())
            cases.append(dict(path=str(target), mapper=7, ram=16, label=f'color{color}'))
        for p in profiles(ROOT/'compiler/build/cvcc'):
            for ram in ((8,16) if p['id']=='asc16l' else (None,)):
                capacity = ram*1024 if ram else p['ram_end']-p['ram_start']
                declarations, writes, checks = ['uint8_t buffer[16];uint8_t ticks;'], [], []
                remaining = capacity-512
                for i in range((remaining+8191)//8192):
                    size = min(8192,remaining-i*8192)
                    declarations.append(f'uint8_t data{i}[{size}];')
                    for j in sorted({0, size-1, *range(0,size,512)}):
                        value = 10+i*40+j//512
                        writes.append(f'data{i}[{j}]={value};')
                        checks.append(f'data{i}[{j}]!={value}')
                config = {'ram_kib':ram} if ram else {}
                if p['banked']:
                    for bank in (2,3,5):
                        (self.root/f'bank{bank}.bin').write_bytes(bytes([bank*10])*16384)
                    config['banks'] = {str(b):f'bank{b}.bin' for b in (2,3,5)}
                    writes += ['vramWriteBank(0x3000,5,16124,260);', 'vramRead(0x30f4,buffer,0,16);']
                    checks += ['buffer[0]!=50', 'buffer[15]!=50', 'bankRead(2,0)!=20',
                               'bankRead(3,16383)!=30', 'bankRead(5,256)!=50', 'bankRead(4,0)!=255',
                               'bankRead(2,bankRead(3,0))!=20', 'bankRead(2,0)+bankRead(3,0)!=50']
                source = ''.join(declarations)+'void setup(){screenDisable();'+''.join(writes)+'} void loop(){waitFrame();ticks++;if('+(' || '.join(checks))+'){vdpWrite(7,6);}else{vdpWrite(7,2);}}'
                result = self.build(p['id'], source, **config)
                self.assertEqual(result.returncode, 0, result.stderr)
                target = self.root/f'{p["id"]}-{ram}.sg';target.write_bytes((self.out/'program.sg').read_bytes())
                cases.append(dict(path=str(target), mapper=p['web_mapper'], ram=ram or 16, label=target.stem))
        manifest = self.root/'cases.json';manifest.write_text(json.dumps(cases))
        result = subprocess.run(['node', ROOT/'tests/web_core_cartridges.cjs', os.environ['CVCC_WEB_CORE'], manifest], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)

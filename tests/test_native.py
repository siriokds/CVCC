"""Original Z80 backend: builds require no CVBasic checkout or executable."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeBuildTests(unittest.TestCase):
    def build(self, source, dest, *options):
        return subprocess.run([sys.executable, str(ROOT/'toolchain/build_rom.py'), str(source),
                               '--out-dir', str(dest), *options], capture_output=True, text=True)

    def test_all_fixtures_and_public_examples(self):
        sources = list((ROOT/'tests/fixtures').glob('*.cvc')) + list((ROOT/'examples').glob('*/main.cvc'))
        with tempfile.TemporaryDirectory() as directory:
            for source in sources:
                with self.subTest(source=source):
                    dest = Path(directory)/source.parent.name/source.stem
                    result = self.build(source, dest)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    metadata = json.loads((dest/'build.json').read_text())
                    rom = (dest/'program.sg').read_bytes()
                    self.assertEqual(metadata['backend'], 'z80')
                    self.assertNotIn('CVBasic', metadata['dependencies'])
                    self.assertFalse((dest/'program.bas').exists())
                    profile=metadata['cartridge']
                    if profile['banked']:self.assertEqual(len(rom),profile['bank_count']*16384)
                    else:self.assertIn(len(rom), (8192,16384,32768,49152))
                    self.assertEqual(hashlib.sha256(rom).hexdigest(), metadata['rom_sha256'])
                    result = subprocess.run(['sjasmplus','-Wno-fileorg','program.sj.asm'], cwd=dest, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((dest/'program.sg').read_bytes(), rom)

    def test_no_cvbasic_checkout_and_stale_artifacts_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);deps=root/'deps';deps.mkdir();dest=root/'out';dest.mkdir()
            for name in ('tree-sitter','tree-sitter-cpp'):
                (deps/name).symlink_to(ROOT/'compiler/.deps'/name, target_is_directory=True)
            for name in ('program.bas','program.gasm.asm'):(dest/name).write_text('old build')
            result=self.build(ROOT/'examples/square',dest,'--deps',str(deps))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((dest/'program.bas').exists())
            self.assertFalse((dest/'program.gasm.asm').exists())

    def test_failure_preserves_last_successful_rom(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'main.cvc';dest=root/'out'
            source.write_text('void setup(){} void loop(){waitVBlank();}')
            self.assertEqual(self.build(source,dest).returncode,0)
            rom=(dest/'program.sg').read_bytes()
            for invalid in ('void setup(){unknown();} void loop(){}',
                            'uint8_t large[800]; void setup(){} void loop(){}'):
                source.write_text(invalid)
                self.assertNotEqual(self.build(source,dest).returncode,0)
                self.assertEqual((dest/'program.sg').read_bytes(),rom)

    def test_deep_call_stack_is_accounted_for(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'main.cvc'
            helpers=''.join('void f%d(){%s}'%(i, 'f%d();'%(i+1) if i<119 else '') for i in range(120))
            source.write_text('uint8_t data[620]; void setup(){f0();} void loop(){}'+helpers)
            result=self.build(source,root/'out')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('RAM_END+STACK_BYTES',result.stderr)

    def test_cli_defaults_to_assembly(self):
        result=subprocess.run([str(ROOT/'compiler/build/cvcc'),str(ROOT/'examples/counter/main.cvc')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('call cvcc_wait',result.stdout)
        self.assertIn('INCLUDE "sg1000.asm"',result.stdout)


if __name__=='__main__':unittest.main(verbosity=2)

"""Semantic rejection tests and differential ROM checks; no network access."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
FRONTEND = BUILD / 'cvcc'
sys.path.insert(0, str(ROOT / 'tools'))
from gasm80_to_sjasmplus import adapt


def command(*args, cwd=ROOT):
    result = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr + result.stdout)
    return result


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=BUILD)
        self.path = Path(self.temp.name) / 'test.cpp'

    def tearDown(self):
        self.temp.cleanup()

    def compile(self, source):
        self.path.write_text(source)
        return subprocess.run([str(FRONTEND), str(self.path)], capture_output=True, text=True)

    def test_counter_golden(self):
        result = self.compile((ROOT / 'examples/counter.cpp').read_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = '\n'.join(line for line in result.stdout.splitlines() if not line.startswith("'")) + '\n'
        self.assertEqual(output, (ROOT / 'tests/fixtures/counter.bas').read_text())

    def test_case_sensitive_symbols_and_comments(self):
        result = self.compile('uint8_t x; uint8_t X; void setup(/*ok*/){x=2; X=3;} void loop(){ x=X+1; /* ok */ waitFrame(); }')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('v0 = (v1 + 1)', result.stdout)

    def test_while_decrement_parentheses(self):
        result = self.compile('uint8_t n=3; void setup(){while(n>0){--n;}} void loop(){if((n)){n=(n+1);}waitFrame();}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('WHILE v0 > 0\nv0 = v0 - 1\nWEND', result.stdout)

    def test_large_rom_data_uses_bounded_lines(self):
        source = 'const uint8_t data[256]={' + ','.join(['255']*256) + '}; void setup(){} void loop(){}'
        result = self.compile(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('DATA BYTE'),16)
        self.assertTrue(all(len(line)<900 for line in result.stdout.splitlines()))

    def test_rejections_have_locations_and_no_partial_output(self):
        cases = {
            'syntax': 'void setup(){ uint8_t x = ; } void loop(){}',
            'missing_loop': 'void setup(){}',
            'duplicate_setup': 'void setup(){} void setup(){} void loop(){}',
            'parameters': 'void setup(uint8_t x){} void loop(){}',
            'return_type': 'int setup(){} void loop(){}',
            'qualifiers': 'void setup() noexcept {} void loop(){}',
            'locals': 'void setup(){uint8_t x;} void loop(){}',
            'unknown_symbol': 'void setup(){x=1;} void loop(){}',
            'duplicate_symbol': 'uint8_t x; uint8_t x; void setup(){} void loop(){}',
            'builtin_shadow': 'uint8_t waitFrame; void setup(){} void loop(){}',
            'word_type': 'uint16_t x; void setup(){} void loop(){}',
            'pointer': 'uint8_t *x; void setup(){} void loop(){}',
            'initializer_range': 'uint8_t x=256; void setup(){} void loop(){}',
            'expression_range': 'uint8_t x; void setup(){x=256;} void loop(){}',
            'multiple_declarators': 'uint8_t x,y; void setup(){} void loop(){}',
            'volatile': 'volatile uint8_t x; void setup(){} void loop(){}',
            'mutable_array': 'uint8_t x[1]={0}; void setup(){} void loop(){}',
            'short_array': 'const uint8_t x[2]={0}; void setup(){} void loop(){}',
            'rom_write': 'const uint8_t x[1]={0}; void setup(){x=1;} void loop(){}',
            'rom_read': 'const uint8_t x[1]={0}; uint8_t y; void setup(){y=x;} void loop(){}',
            'logical_short_circuit': 'uint8_t x; void setup(){if(x && x){x=1;}} void loop(){}',
            'logical_not': 'uint8_t x; void setup(){if(!x){x=1;}} void loop(){}',
            'comparison_as_value': 'uint8_t x; void setup(){x=(x==1);} void loop(){}',
            'side_effect_expression': 'uint8_t x; void setup(){x=x++;} void loop(){}',
            'compound_assignment': 'uint8_t x; void setup(){x+=1;} void loop(){}',
            'call_arity': 'void setup(){waitFrame(1);} void loop(){}',
            'unknown_call': 'void setup(){foo();} void loop(){}',
            'string_escape': r'void setup(){printAt(0,"hello\n");} void loop(){}',
            'prefixed_string': 'void setup(){printAt(0,u8"hi");} void loop(){}',
            'string_position': 'void setup(){printAt(768,"hi");} void loop(){}',
            'sprite_size': 'const uint8_t a[1]={0}; void setup(){defineSprite(0,1,a);} void loop(){}',
            'function': 'void f(){} void setup(){} void loop(){}',
            'return': 'void setup(){return;} void loop(){}',
            'for': 'void setup(){for(;;){}} void loop(){}',
            'preprocessor': '#define X 1\nvoid setup(){} void loop(){}',
            'constexpr_if': 'void setup(){if constexpr(1){}} void loop(){}',
            'condition_declaration': 'void setup(){if(uint8_t x=1){}} void loop(){}',
            'float_literal': 'uint8_t x; void setup(){x=1.5;} void loop(){}',
            'suffix_literal': 'uint8_t x; void setup(){x=1u;} void loop(){}',
            'octal_literal': 'uint8_t x=010; void setup(){} void loop(){}',
            'deep_expression': 'uint8_t x; void setup(){x=' + '(' * 140 + '1' + ')' * 140 + ';} void loop(){}',
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                result = self.compile(source)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertRegex(result.stderr, r'test.cpp:\d+:\d+: error:')

    def test_adapter_rejects_other_targets_and_banking(self):
        for source in ['SG1000: equ 0\nCVBASIC_BANK_SWITCHING: equ 0', 'SG1000: equ 1\nCVBASIC_BANK_SWITCHING: equ 1']:
            with self.assertRaises(ValueError):
                adapt(source, 'test.sg')

    def test_adapter_preserves_strings(self):
        source = 'SG1000: equ 1\nCVBASIC_BANK_SWITCHING: equ 0\nlabel:\n.1: db "RB FORG .1 lower-case"\n jr .1\n'
        output = adapt(source, 'test.sg')
        self.assertIn('"RB FORG .1 lower-case"', output)
        self.assertIn('JR LABEL__CVCCLOCAL_1', output)


class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cvb = ROOT / '.work/deps/CVBasic'
        command('cc', '-O2', *[cvb / (name + '.c') for name in ('cvbasic', 'node', 'driver', 'cpuz80', 'cpu6502', 'cpu9900')], '-o', BUILD / 'reference-cvbasic')

    def test_counter_against_handwritten_basic(self):
        dest = BUILD / 'test-counter'
        command(sys.executable, ROOT / 'tools/build_rom.py', ROOT / 'examples/counter.cpp', '--out-dir', dest)
        cvb = ROOT / '.work/deps/CVBasic'
        command(BUILD / 'reference-cvbasic', '--sg1000', ROOT / 'tests/fixtures/counter.bas', dest / 'reference.asm', str(cvb) + '/')
        command('gasm80', dest / 'reference.asm', '-o', dest / 'reference.sg')
        self.assertEqual((dest / 'program.sg').read_bytes(), (dest / 'reference.sg').read_bytes())

    def test_happy_face_exact_upstream_rom(self):
        # Upstream artwork stays in ignored build output; nothing is vendored.
        cvb = ROOT / '.work/deps/CVBasic'
        original = (cvb / 'examples/happy_face.bas').read_text()
        rows = re.findall(r'BITMAP "([.X]+)"', original)
        self.assertEqual(len(rows), 16)
        data = [int(row[a:a+8].replace('.', '0').replace('X', '1'), 2) for a in (0, 8) for row in rows]
        source = (ROOT / 'examples/square.cpp').read_text()
        source = re.sub(r'const uint8_t square\[32\] = \{.*?\};', 'const uint8_t square[32] = {' + ','.join(map(str,data)) + '};', source, flags=re.S)
        source = source.replace('CVCC moving square', 'Happy face!')
        path = BUILD / 'happy_face.cpp'
        path.write_text(source)
        dest = BUILD / 'test-happy-face'
        command(sys.executable, ROOT / 'tools/build_rom.py', path, '--out-dir', dest)
        command(BUILD / 'reference-cvbasic', '--sg1000', cvb / 'examples/happy_face.bas', dest / 'reference.asm', str(cvb) + '/')
        command('gasm80', dest / 'reference.asm', '-o', dest / 'reference.sg')
        self.assertEqual((dest / 'program.sg').read_bytes(), (dest / 'reference.sg').read_bytes())
        self.assertEqual(len((dest / 'program.sg').read_bytes()), 32768)


if __name__ == '__main__':
    unittest.main(verbosity=2)

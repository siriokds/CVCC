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
        self.path = Path(self.temp.name) / 'test.cvc'

    def tearDown(self):
        self.temp.cleanup()

    def compile(self, source):
        self.path.write_text(source)
        return subprocess.run([str(FRONTEND), str(self.path)], capture_output=True, text=True)

    def test_counter_golden(self):
        result = self.compile((ROOT / 'examples/counter.cvc').read_text())
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
        self.assertIn('WHILE v0 > 0\nv0 = v0 - 1\ncvcc_continue0:\nWEND', result.stdout)

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
            'word_initializer_range': 'uint16_t x=65536; void setup(){} void loop(){}',
            'literal_range': 'uint16_t x; void setup(){x=65536;} void loop(){}',
            'missing_return': 'uint8_t f(uint8_t x){if(x){return 1;}} void setup(){} void loop(){}',
            'bare_return': 'uint16_t f(){return;} void setup(){} void loop(){}',
            'void_value': 'uint8_t x; void f(){} void setup(){x=f();} void loop(){}',
            'parameter_scope': 'void f(uint8_t x){} void setup(){x=1;} void loop(){}',
            'duplicate_parameter': 'void f(uint8_t x,uint16_t x){} void setup(){} void loop(){}',
            'array_parameter': 'void f(uint8_t x[2]){} void setup(){} void loop(){}',
            'pointer_parameter': 'void f(uint8_t *x){} void setup(){} void loop(){}',
            'default_parameter': 'void f(uint8_t x=1){} void setup(){} void loop(){}',
            'value_recursion': 'uint8_t f(uint8_t x){return g(x);} uint8_t g(uint8_t x){return f(x);} void setup(){} void loop(){}',
            'switch_missing_return': 'uint8_t f(uint8_t x){switch(x){case 0:if(x){break;}return 1;default:return 2;}} void setup(){} void loop(){}',
            'return_value': 'void f(){return 1;} void setup(){} void loop(){}',
            'recursive': 'void f(){f();} void setup(){} void loop(){}',
            'indirect_recursion': 'void f(){g();} void g(){f();} void setup(){} void loop(){}',
            'entry_call': 'void setup(){} void loop(){setup();}',
            'function_arguments': 'void f(){} void setup(){f(1);} void loop(){}',
            'duplicate_function': 'void f(){} void f(){} void setup(){} void loop(){}',
            'function_builtin': 'void waitFrame(){} void setup(){} void loop(){}',
            'function_symbol': 'void f(){} uint8_t f; void setup(){} void loop(){}',
            'function_symbol_reverse': 'uint8_t f; void f(){} void setup(){} void loop(){}',
            'array_bound': 'uint16_t a[2]; void setup(){a[2]=1;} void loop(){}',
            'array_multi_index': 'uint8_t a[2]; void setup(){a[0,1]=1;} void loop(){}',
            'scalar_index': 'uint8_t a; void setup(){a[0]=1;} void loop(){}',
            'array_no_index': 'uint8_t a[2]; void setup(){a=1;} void loop(){}',
            'rom_index_write': 'const uint16_t a[1]={256}; void setup(){a[0]++;} void loop(){}',
            'array_side_effect_index': 'uint8_t a[2]; uint8_t i; void setup(){a[i++]=1;} void loop(){}',
            'array_word_range': 'const uint16_t a[1]={65536}; void setup(){} void loop(){}',
            'array_empty': 'uint8_t a[0]; void setup(){} void loop(){}',
            'array_unsized': 'uint8_t a[]={1}; void setup(){} void loop(){}',
            'array_nested': 'uint8_t a[2][2]; void setup(){} void loop(){}',
            'ram_short_initializer': 'uint8_t a[2]={1}; void setup(){} void loop(){}',
            'const_missing': 'const uint16_t a; void setup(){} void loop(){}',
            'const_write': 'const uint16_t a=1; void setup(){a=2;} void loop(){}',
            'sprite_ram': 'uint8_t a[32]; void setup(){defineSprite(0,1,a);} void loop(){}',
            'sprite_word': 'const uint16_t a[1]={0}; void setup(){defineSprite(0,1,a);} void loop(){}',
            'pointer': 'uint8_t *x; void setup(){} void loop(){}',
            'initializer_range': 'uint8_t x=256; void setup(){} void loop(){}',
            'multiple_declarators': 'uint8_t x,y; void setup(){} void loop(){}',
            'volatile': 'volatile uint8_t x; void setup(){} void loop(){}',
            'short_array': 'const uint8_t x[2]={0}; void setup(){} void loop(){}',
            'rom_write': 'const uint8_t x[1]={0}; void setup(){x=1;} void loop(){}',
            'rom_read': 'const uint8_t x[1]={0}; uint8_t y; void setup(){y=x;} void loop(){}',
            'logical_as_value': 'uint8_t x; void setup(){x=x && 1;} void loop(){}',
            'logical_not_as_value': 'uint8_t x; void setup(){x=!x;} void loop(){}',
            'comparison_as_value': 'uint8_t x; void setup(){x=(x==1);} void loop(){}',
            'side_effect_expression': 'uint8_t x; void setup(){x=x++;} void loop(){}',
            'compound_assignment': 'uint8_t x; void setup(){x*=2;} void loop(){}',
            'vblank_arity': 'void setup(){waitVBlank(1,2);} void loop(){}',
            'vblank_range': 'void setup(){waitVBlank(65536);} void loop(){}',
            'vblank_string': 'void setup(){waitVBlank("1");} void loop(){}',
            'vblank_shadow': 'uint8_t waitVBlank; void setup(){} void loop(){}',
            'vblank_shadow_function': 'void waitVBlank(){} void setup(){} void loop(){}',
            'call_arity': 'void setup(){waitFrame(1);} void loop(){}',
            'unknown_call': 'void setup(){foo();} void loop(){}',
            'string_escape': r'void setup(){printAt(0,"hello\n");} void loop(){}',
            'prefixed_string': 'void setup(){printAt(0,u8"hi");} void loop(){}',
            'string_position': 'void setup(){printAt(768,"hi");} void loop(){}',
            'sprite_size': 'const uint8_t a[1]={0}; void setup(){defineSprite(0,1,a);} void loop(){}',
            'do_invalid_condition': 'void setup(){do {} while(missing);} void loop(){}',
            'do_bad_body': 'void setup(){do {uint8_t local;} while(0);} void loop(){}',
            'do_break_scope': 'void setup(){do {} while(0); break;} void loop(){}',
            'do_continue_scope': 'void setup(){do {} while(0); continue;} void loop(){}',
            'switch_duplicate': 'void setup(){switch(1){case 1:break;case 0x1:break;}} void loop(){}',
            'switch_const_duplicate': 'const uint8_t A=1; void setup(){switch(1){case A:break;case 1:break;}} void loop(){}',
            'switch_default_duplicate': 'void setup(){switch(1){default:break;default:break;}} void loop(){}',
            'switch_variable_case': 'uint8_t n; void setup(){switch(1){case n:break;}} void loop(){}',
            'switch_case_range': 'void setup(){switch(1){case 65536:break;}} void loop(){}',
            'switch_case_negative': 'void setup(){switch(1){case -1:break;}} void loop(){}',
            'switch_continue': 'void setup(){switch(1){case 1:continue;}} void loop(){}',
            'switch_break_scope': 'void setup(){switch(1){default:break;} break;} void loop(){}',
            'switch_init': 'uint8_t n; void setup(){switch(n=1;n){default:break;}} void loop(){}',
            'switch_declaration': 'void setup(){switch(uint8_t n=1){default:break;}} void loop(){}',
            'switch_prelude': 'void setup(){switch(1){waitFrame();case 1:break;}} void loop(){}',
            'case_outside': 'void setup(){case 1:break;} void loop(){}',
            'switch_bad_selector': 'void setup(){switch(missing){default:break;}} void loop(){}',
            'for_local': 'void setup(){for(uint8_t i=0;i<3;i++){}} void loop(){}',
            'for_comma': 'uint8_t i; uint8_t j; void setup(){for(i=0,j=0;i<3;i++){}} void loop(){}',
            'break_outside': 'void setup(){break;} void loop(){}',
            'continue_outside': 'void setup(){} void loop(){continue;}',
            'break_helper': 'void f(){break;} void setup(){while(1){f();}} void loop(){}',
            'for_bad_update': 'uint8_t i; void setup(){for(i=0;i<3;i*2){}} void loop(){}',
            'shift_byte_range': 'uint8_t i; void setup(){i=i<<8;} void loop(){}',
            'shift_word_range': 'uint16_t i; void setup(){i>>=16;} void loop(){}',
            'shift_negative': 'uint8_t i; void setup(){i=i<<-1;} void loop(){}',
            'shift_dynamic': 'uint8_t i; void setup(){i=i<<i;} void loop(){}',
            'shift_bad_left': 'uint8_t i; void setup(){i=(i==1)<<1;} void loop(){}',
            'dead_rhs_invalid': 'void setup(){if(1 || missing){}} void loop(){}',
            'logical_arithmetic': 'uint8_t i; void setup(){if((i && 1)+1){}} void loop(){}',
            'compound_rom': 'const uint8_t a[1]={0}; void setup(){a[0]|=1;} void loop(){}',
            'compound_side_effect': 'uint8_t a[2]; uint8_t i; void setup(){a[i++]^=1;} void loop(){}',
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
                self.assertRegex(result.stderr, r'test.cvc:\d+:\d+: error:')

    def test_functions_arrays_words(self):
        result = self.compile((ROOT / 'tests/fixtures/functions_arrays.cvc').read_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        for snippet in ['DIM #v4(3)', '#v4(v7) = #d1(v7)', 'GOSUB cvcc_fn3',
                        'DATA 6144,6400,65535', 'CONST #k2 = 6144', 'RETURN']:
            self.assertIn(snippet, result.stdout)

    def test_for_and_bitwise(self):
        result = self.compile((ROOT / 'tests/fixtures/for_bitwise.cvc').read_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        for snippet in ['WHILE #v0 <= 255', 'GOTO cvcc_continue5', 'GOTO cvcc_break5',
                        'v9 = (NOT v7)', '#v10 = (NOT #v8)',
                        'v11 = (1 OR (2 XOR (3 AND 4)))']:
            self.assertIn(snippet, result.stdout)

    def test_shifts_and_short_circuit(self):
        result = self.compile((ROOT / 'tests/fixtures/shifts_logic.cvc').read_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('AND 255) * 128) AND 255)', result.stdout)
        self.assertIn('AND 65535) / 32768) AND 65535)', result.stdout)
        # Guards branch before a potentially invalid dynamic array read.
        self.assertRegex(result.stdout, r'IF v10 < 3 THEN GOTO cvcc_bool\d+\nGOTO cvcc_bool\d+\ncvcc_bool\d+:\nIF v11\(v10\)')

    def test_wait_vblank_aliases_and_count(self):
        variants=[self.compile('void setup(){} void loop(){'+call+';}') for call in
                  ('waitFrame()', 'waitVBlank()', 'waitVBlank(1)', 'waitVBlank(0x1)')]
        for result in variants:
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,variants[0].stdout)
        zero=self.compile('void setup(){waitVBlank(0);} void loop(){}')
        self.assertEqual(zero.returncode,0,zero.stderr)
        self.assertNotIn('WAIT',zero.stdout)
        counted=self.compile('uint16_t n=300; void setup(){waitVBlank(n);waitVBlank(2);} void loop(){waitVBlank();}')
        self.assertEqual(counted.returncode,0,counted.stderr)
        self.assertEqual(counted.stdout.count('DIM #cvcc_wait_remaining'),1)
        self.assertIn('#cvcc_wait_remaining = #v0',counted.stdout)
        self.assertEqual(counted.stdout.count('WHILE #cvcc_wait_remaining > 0'),2)

    def test_do_while_control_flow(self):
        result=self.compile((ROOT/'tests/fixtures/do_while.cvc').read_text())
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('cvcc_do0:\nv0 = v0 + 1\ncvcc_continue0:\nIF 0 THEN GOTO cvcc_do0',result.stdout)
        self.assertIn('GOTO cvcc_continue1',result.stdout)
        self.assertIn('cvcc_continue1:\nIF v1 < 3 THEN GOTO cvcc_do1',result.stdout)
        self.assertIn('GOTO cvcc_break2',result.stdout)

    def test_switch_dispatch_and_fallthrough(self):
        result=self.compile((ROOT/'tests/fixtures/switch.cvc').read_text())
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.count('DIM #cvcc_switch_value'),1)
        self.assertIn('#cvcc_switch_value = #v1',result.stdout)
        self.assertIn('IF #cvcc_switch_value = 300 THEN GOTO cvcc_case0_0',result.stdout)
        self.assertIn('v2 = v2 + 1\n#v1 = 0\ncvcc_case0_1:',result.stdout)
        self.assertIn('GOTO cvcc_continue5',result.stdout)

    def test_video_vram(self):
        result=self.compile((ROOT/'tests/fixtures/video_vram.cvc').read_text())
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('DEFINE VRAM 12288,4,VARPTR d0(2)',result.stdout)
        self.assertIn('DEFINE VRAM READ 12288,4,VARPTR v1(3)',result.stdout)
        self.assertIn('SCREEN ENABLE\nVDP(1) = 224',result.stdout)

    def test_video_rejections(self):
        for call in ['videoMode(3)', 'videoMode(x)', 'screenEnable(1)',
                     'spriteFlicker(2)', 'vdpWrite(8,0)', 'vdpWrite(x,0)',
                     'vramPoke(16384,0)', 'vramPoke(0,256)',
                     'vramWrite(0,data,0,0)', 'vramWrite(0,data,1,2)',
                     'vramWrite(16383,data,0,2)', 'vramWrite(0,data,x,1)',
                     'vramRead(0,data,0,1)', 'vramWrite(0,words,0,1)',
                     'vramWrite(0,x,0,1)', 'vramWrite(0,data,0)']:
            with self.subTest(call=call):
                result=self.compile('const uint8_t data[2]={1,2}; uint16_t words[2]; uint8_t x; void setup(){'+call+';} void loop(){}')
                self.assertNotEqual(result.returncode,0)
                self.assertIn('error:',result.stderr)
                self.assertEqual(result.stdout,'')

    def test_parameters_and_return_values(self):
        result=self.compile((ROOT/'tests/fixtures/function_values.cvc').read_text())
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('cvcc_p0_0',result.stdout)
        self.assertIn('cvcc_r0',result.stdout)
        self.assertIn('cvcc_t',result.stdout)

    def test_function_epilogue_after_switch_return(self):
        result=self.compile('uint8_t state; void setup(){} void loop(){step();waitVBlank();} void step(){switch(state){case 0:state=1;break;default:return;}}')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('cvcc_break0:\nRETURN\nEND',result.stdout)

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
        command(sys.executable, ROOT / 'tools/build_rom.py', ROOT / 'examples/counter.cvc', '--out-dir', dest)
        cvb = ROOT / '.work/deps/CVBasic'
        command(BUILD / 'reference-cvbasic', '--sg1000', ROOT / 'tests/fixtures/counter.bas', dest / 'reference.asm', str(cvb) + '/')
        command('gasm80', dest / 'reference.asm', '-o', dest / 'reference.sg')
        self.assertEqual((dest / 'program.sg').read_bytes(), (dest / 'reference.sg').read_bytes())

    def test_functions_arrays_against_handwritten_basic(self):
        dest = BUILD / 'functions-arrays'
        command(sys.executable, ROOT / 'tools/build_rom.py', ROOT / 'tests/fixtures/functions_arrays.cvc', '--out-dir', dest)
        cvb = ROOT / '.work/deps/CVBasic'
        command(BUILD / 'reference-cvbasic', '--sg1000', ROOT / 'tests/fixtures/functions_arrays.bas', dest / 'reference.asm', str(cvb) + '/')
        command('gasm80', dest / 'reference.asm', '-o', dest / 'reference.sg')
        self.assertEqual((dest / 'program.sg').read_bytes(), (dest / 'reference.sg').read_bytes())

    def test_for_bitwise_rom(self):
        dest = BUILD / 'for-bitwise'
        command(sys.executable, ROOT / 'tools/build_rom.py', ROOT / 'tests/fixtures/for_bitwise.cvc', '--out-dir', dest)
        # Assemble the same CVBasic lowering with the independent assembler.
        cvb = ROOT / '.work/deps/CVBasic'
        command(BUILD / 'reference-cvbasic', '--sg1000', dest / 'program.bas', dest / 'reference.asm', str(cvb) + '/')
        command('gasm80', dest / 'reference.asm', '-o', dest / 'reference.sg')
        self.assertEqual((dest / 'program.sg').read_bytes(), (dest / 'reference.sg').read_bytes())

    def test_shifts_logic_rom(self):
        dest = BUILD / 'shifts-logic'
        command(sys.executable, ROOT / 'tools/build_rom.py', ROOT / 'tests/fixtures/shifts_logic.cvc', '--out-dir', dest)
        cvb = ROOT / '.work/deps/CVBasic'
        command(BUILD / 'reference-cvbasic', '--sg1000', dest / 'program.bas', dest / 'reference.asm', str(cvb) + '/')
        command('gasm80', dest / 'reference.asm', '-o', dest / 'reference.sg')
        self.assertEqual((dest / 'program.sg').read_bytes(), (dest / 'reference.sg').read_bytes())

    def test_wait_vblank_alias_rom(self):
        source=(ROOT/'examples/counter.cvc').read_text().replace('waitFrame()', 'waitVBlank()')
        path=BUILD/'counter-vblank.cvc';path.write_text(source)
        dest=BUILD/'counter-vblank'
        command(sys.executable,ROOT/'tools/build_rom.py',path,'--out-dir',dest)
        import hashlib
        self.assertEqual(hashlib.sha256((dest/'program.sg').read_bytes()).hexdigest(),
                         '2f6b8572cb4f2a82383661587be1c5e845be0ecc975dea1455c0f4f1c73c66b8')

    def test_do_while_rom(self):
        dest=BUILD/'do-while'
        command(sys.executable,ROOT/'tools/build_rom.py',ROOT/'tests/fixtures/do_while.cvc','--out-dir',dest)
        cvb=ROOT/'.work/deps/CVBasic'
        command(BUILD/'reference-cvbasic','--sg1000',dest/'program.bas',dest/'reference.asm',str(cvb)+'/')
        command('gasm80',dest/'reference.asm','-o',dest/'reference.sg')
        self.assertEqual((dest/'program.sg').read_bytes(),(dest/'reference.sg').read_bytes())

    def test_switch_rom(self):
        dest=BUILD/'switch'
        command(sys.executable,ROOT/'tools/build_rom.py',ROOT/'tests/fixtures/switch.cvc','--out-dir',dest)
        cvb=ROOT/'.work/deps/CVBasic'
        command(BUILD/'reference-cvbasic','--sg1000',dest/'program.bas',dest/'reference.asm',str(cvb)+'/')
        command('gasm80',dest/'reference.asm','-o',dest/'reference.sg')
        self.assertEqual((dest/'program.sg').read_bytes(),(dest/'reference.sg').read_bytes())

    def test_video_vram_rom(self):
        dest=BUILD/'video-vram'
        command(sys.executable,ROOT/'tools/build_rom.py',ROOT/'tests/fixtures/video_vram.cvc','--out-dir',dest)
        command('gasm80',dest/'program.gasm.asm','-o',dest/'reference.sg')
        self.assertEqual((dest/'program.sg').read_bytes(),(dest/'reference.sg').read_bytes())

    def test_function_values_rom(self):
        dest=BUILD/'function-values'
        command(sys.executable,ROOT/'tools/build_rom.py',ROOT/'tests/fixtures/function_values.cvc','--out-dir',dest)
        command('gasm80',dest/'program.gasm.asm','-o',dest/'reference.sg')
        self.assertEqual((dest/'program.sg').read_bytes(),(dest/'reference.sg').read_bytes())

    def test_states_function_exit_has_ret(self):
        dest=BUILD/'states'
        command(sys.executable,ROOT/'tools/build_rom.py',ROOT/'examples/states.cvc','--out-dir',dest)
        symbols=dict((key,int(address,16)) for key,address in re.findall(r'^(\S+): EQU 0x([0-9A-F]+)$',(dest/'program.sym').read_text(),re.M))
        rom=(dest/'program.sg').read_bytes()
        self.assertEqual(rom[symbols['CVB_CVCC_BREAK0']],0xC9)  # RET, not sprite data.

    def test_happy_face_exact_upstream_rom(self):
        # Upstream artwork stays in ignored build output; nothing is vendored.
        cvb = ROOT / '.work/deps/CVBasic'
        original = (cvb / 'examples/happy_face.bas').read_text()
        rows = re.findall(r'BITMAP "([.X]+)"', original)
        self.assertEqual(len(rows), 16)
        data = [int(row[a:a+8].replace('.', '0').replace('X', '1'), 2) for a in (0, 8) for row in rows]
        source = (ROOT / 'examples/square.cvc').read_text()
        source = re.sub(r'const uint8_t square\[32\] = \{.*?\};', 'const uint8_t square[32] = {' + ','.join(map(str,data)) + '};', source, flags=re.S)
        source = source.replace('CVCC moving square', 'Happy face!')
        path = BUILD / 'happy_face.cvc'
        path.write_text(source)
        dest = BUILD / 'test-happy-face'
        command(sys.executable, ROOT / 'tools/build_rom.py', path, '--out-dir', dest)
        command(BUILD / 'reference-cvbasic', '--sg1000', cvb / 'examples/happy_face.bas', dest / 'reference.asm', str(cvb) + '/')
        command('gasm80', dest / 'reference.asm', '-o', dest / 'reference.sg')
        self.assertEqual((dest / 'program.sg').read_bytes(), (dest / 'reference.sg').read_bytes())
        self.assertEqual(len((dest / 'program.sg').read_bytes()), 32768)


if __name__ == '__main__':
    unittest.main(verbosity=2)

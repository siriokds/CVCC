"""Behavioral Z80 tests with GearSF7000's headless MCP interface.
Set CVCC_EMULATOR to an isolated GearSF7000 executable; no game assets required.
"""
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
EMU=os.environ.get('CVCC_EMULATOR')


@unittest.skipUnless(EMU, 'set CVCC_EMULATOR to an isolated GearSF7000 binary')
class NativeEmulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'build').mkdir(parents=True, exist_ok=True)
        cls.log=(ROOT/'build/native-emulator.log').open('w')
        cls.process=subprocess.Popen([EMU,'--headless','--mcp-stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=cls.log,text=True)
        cls.replies=queue.Queue();cls.seq=0
        def reader():
            for line in cls.process.stdout:
                try:cls.replies.put(json.loads(line))
                except ValueError:pass
        threading.Thread(target=reader,daemon=True).start()
        cls.rpc('initialize',dict(protocolVersion='2025-11-25',capabilities={},clientInfo=dict(name='cvcc-native-tests',version='1')))
        cls.models=cls.call('get_system_options')['models']

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate();cls.process.wait(timeout=10)
        cls.process.stdin.close();cls.process.stdout.close();cls.log.close()

    @classmethod
    def rpc(cls,method,params):
        cls.seq+=1
        cls.process.stdin.write(json.dumps(dict(jsonrpc='2.0',id=cls.seq,method=method,params=params))+'\n');cls.process.stdin.flush()
        while True:
            reply=cls.replies.get(timeout=25)
            if reply.get('id')==cls.seq:
                if 'error' in reply:raise AssertionError(reply)
                return reply['result']

    @classmethod
    def call(cls,name,**arguments):
        result=cls.rpc('tools/call',dict(name=name,arguments=arguments))
        if result.get('isError'):raise AssertionError(result)
        return json.loads(result['content'][0]['text'])

    def build(self,name):
        directory=ROOT/'build'/('native-'+name)
        result=subprocess.run([sys.executable,str(ROOT/'toolchain/build_rom.py'),str(ROOT/'tests/fixtures'/(name+'.cvc')),'--out-dir',str(directory)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.symbols={k:int(v,16) for k,v in re.findall(r'^(\S+): EQU 0x([0-9A-F]+)$',(directory/'program.sym').read_text(),re.M)}
        return directory/'program.sg'

    def load(self,rom,model):
        entry=next(m for m in self.models if m['name']==model)
        self.call('set_system_options',model_id=entry['id'],mapper_mode='manual',mapper_type_id=0,video_option='default')
        self.call('load_rom',file_path=str(rom))
        self.step(120)

    def step(self,n):self.call('debug_step_frame',frames=n,mode='sync')
    def memory(self,area,addr,count):return bytes.fromhex(self.call('read_memory',area=area,offset=f'{addr:04X}',size=count)['data'])
    def read(self,name,size=1):return int.from_bytes(self.memory(0,self.symbols['cvcc_var_'+name],size),'little')

    def test_language_results_and_frame_cadence(self):
        cases=json.loads((ROOT/'tests/fixtures/native_expected.json').read_text())
        for name,expected in cases.items():
            rom=self.build(name)
            for model in ('SG-1000 Mark I/II','SC-3000 Export'):
                with self.subTest(fixture=name,model=model):
                    self.load(rom,model)
                    for symbol,(size,want) in expected.items():self.assertEqual(self.read(symbol,size),want,symbol)
                    counter='frame' if name=='function_values' else 'ticks'
                    before=self.read(counter);self.step(60)
                    self.assertEqual((self.read(counter)-before)%256,60)
                    if name=='function_values':
                        self.assertEqual(self.memory(0,self.symbols['cvcc_var_arr'],4),bytes([10,23,30,40]))
                    if name=='functions_arrays':
                        self.assertEqual(self.memory(0,self.symbols['cvcc_var_words'],6),bytes([0,24,1,25,0,0]))

    def test_vram_and_ordered_side_effects(self):
        rom=self.build('video_vram')
        for model in ('SG-1000 Mark I/II','SC-3000 Export'):
            with self.subTest(model=model):
                self.load(rom,model)
                self.assertEqual(self.memory(0,self.symbols['cvcc_var_buffer'],10),bytes([42,9,9,3,4,5,6,9,9,9]))
                self.assertEqual(self.read('calls'),1)
                self.assertEqual(self.read('address',2),0x3001)
                self.assertEqual(self.memory(3,0x3100,6),bytes([9,3,4,5,6,9]))

    def test_counted_wait_and_zero_wait(self):
        rom=self.build('wait_vblank')
        for model in ('SG-1000 Mark I/II','SC-3000 Export'):
            with self.subTest(model=model):
                self.load(rom,model);self.assertEqual(self.read('ready'),0)
                self.step(60);self.assertEqual(self.read('ready'),0)
                self.assertEqual(self.read('delay',2),260)
                self.step(240);self.assertEqual(self.read('ready'),1)
                before=self.read('ticks');self.step(60)
                self.assertEqual((self.read('ticks')-before)%256,20)

    def test_video_modes_sprite_rotation_and_both_controllers(self):
        rom=self.build('runtime_modes')
        for model in ('SG-1000 Mark I/II','SC-3000 Export'):
            with self.subTest(model=model):
                self.load(rom,model)
                for name in ('fontTop','fontMiddle','fontBottom'):
                    self.assertEqual(self.memory(0,self.symbols['cvcc_var_'+name],8),bytes([56,68,68,124,68,68,68,0]))
                self.assertEqual(self.memory(0,self.symbols['cvcc_var_bitmapNames'],16),bytes(list(range(248,256))+list(range(8))))
                before=self.memory(3,0x1B00,128);self.step(1);after=self.memory(3,0x1B00,128)
                self.assertNotEqual(before,after)
                self.assertIn(bytes([10,20,4,15]),[after[i:i+4] for i in range(0,128,4)])
                self.assertIn(bytes([100,30,8,10]),[after[i:i+4] for i in range(0,128,4)])
                for player in (1,2):
                    for button,mask in (('up',1),('right',2),('down',4),('left',8),('fire1',64),('fire2',128)):
                        self.call('controller_button',player=player,button=button,action='press');self.step(2)
                        self.assertEqual(self.read('pad'+str(player)),mask,(player,button))
                        self.call('controller_button',player=player,button=button,action='release');self.step(2)
                        self.assertEqual(self.read('pad'+str(player)),0)


if __name__=='__main__':unittest.main(verbosity=2)

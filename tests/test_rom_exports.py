"""Verify safe resizing and boundaries of the pinned SG-1000 image format."""
from pathlib import Path
import base64
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toolchain.rom_exports import exports, HEADER, SIZES


def image(end):
    rounded = min((end+8191)//8192*8192, 0x7ff0)
    return b'\x42'*end + b'\xff'*(rounded-end) + b'\x00'*(0x7ff0-rounded) + HEADER


class ExportTests(unittest.TestCase):
    def test_sizes_and_preservation(self):
        for end in (1, 8191, 8192, 8193, 16384, 16385, 0x7ff0):
            original = image(end)
            choices = exports(original, end)
            self.assertEqual([x['size'] for x in choices], [n for n in SIZES if n >= end])
            for item in choices:
                data = base64.b64decode(item['rom'])
                self.assertEqual(len(data), item['size'])
                self.assertEqual(data[:end], original[:end])
                self.assertEqual(data[:min(len(data),len(original))],original[:len(data)])
                if len(data)>len(original):
                    self.assertEqual(data[len(original):], b'\xff'*(len(data)-len(original)))

    def test_native_padding_and_boundaries(self):
        for end in (1,8192,8193,16384,16385,32768):
            rom=b'\x42'*end+b'\xff'*(next(size for size in SIZES if size>=end)-end)
            choices=exports(rom,end,backend='z80')
            self.assertEqual([c['size'] for c in choices],[s for s in SIZES if s>=end])
            for choice in choices:
                data=base64.b64decode(choice['rom'])
                self.assertEqual(data[:end],rom[:end])
                self.assertEqual(data[end:],b'\xff'*(choice['size']-end))
        self.assertEqual(exports(b'X'*8192,100,backend='z80'),[])
        self.assertEqual(exports(b'X'*8192,8192,backend='unknown'),[])

    def test_unknown_layout_is_not_trimmed(self):
        original=image(100)
        for rom,end in [(original,0),(original,32768),(original[:-1],100),
                        (original[:-1]+b'X',100),
                        (original[:9000]+b'X'+original[9001:],100),
                        (original[:200]+b'X'+original[201:],100)]:
            self.assertEqual(exports(rom,end), [])

if __name__=='__main__':
    unittest.main(verbosity=2)

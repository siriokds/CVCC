#!/usr/bin/env python3
"""Compatibility entry point; use toolchain/build_rom.py for new scripts."""
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if __name__ == '__main__':
    runpy.run_module('toolchain.build_rom', run_name='__main__')

#!/usr/bin/env python3
"""Compatibility entry point; use ide/run.sh for new scripts."""
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if __name__ == '__main__':
    runpy.run_module('ide.serve', run_name='__main__')

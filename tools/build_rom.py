#!/usr/bin/env python3
"""Development pipeline: Tree-sitter frontend -> CVBasic -> sjasmplus, SG-1000 only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from gasm80_to_sjasmplus import adapt
from project_source import expand, remap, file_bytes

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd=None):
    result = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout or f'{args[0]} failed')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--deps', type=Path, default=ROOT / '.work/deps')
    parser.add_argument('--frontend', type=Path, default=ROOT / 'build/cvcc')
    args = parser.parse_args()
    source, dest, deps = args.source.resolve(), args.out_dir.resolve(), args.deps.resolve()
    # Validate before touching the destination. Rejected input never yields a ROM.
    if source.is_dir(): source = source/'main.cvc'
    expanded, mapping, inputs = expand(source)
    with tempfile.TemporaryDirectory(prefix='cvcc-source-') as temporary:
        flattened = Path(temporary)/'main.cvc'
        flattened.write_text(expanded)
        compiled = subprocess.run([str(args.frontend.resolve()), str(flattened)], capture_output=True, text=True)
        if compiled.returncode:
            raise RuntimeError(remap(compiled.stderr or compiled.stdout, flattened, mapping))
        basic = compiled.stdout
    lock = json.loads((ROOT / 'dependencies.lock.json').read_text())
    for name, spec in lock.items():
        actual = run(['git', '-C', deps / name, 'rev-parse', 'HEAD']).stdout.strip()
        if actual != spec['commit']:
            raise RuntimeError(f'{name}: expected pinned commit {spec["commit"]}, got {actual}')
        if run(['git', '-C', deps / name, 'status', '--porcelain', '--untracked-files=no']).stdout:
            raise RuntimeError(f'{name}: tracked source modifications invalidate the baseline')
    assembler = shutil.which('sjasmplus')
    if not assembler:
        raise RuntimeError('sjasmplus is required for this development prototype')
    # Build in a sibling scratch directory and publish only after assembly succeeds.
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.cvcc-', dir=dest.parent) as temp:
        work = Path(temp)
        (work / 'program.bas').write_text(basic)
        cvbasic = deps / 'CVBasic'
        c_files = ['cvbasic', 'node', 'driver', 'cpuz80', 'cpu6502', 'cpu9900']
        run([os.environ.get('CC', 'cc'), '-O2', *[cvbasic / f'{f}.c' for f in c_files], '-o', work / 'cvbasic'])
        compilation = run([work / 'cvbasic', '--sg1000', work / 'program.bas', work / 'program.gasm.asm', str(cvbasic) + '/'])
        # A relative OUTPUT keeps the saved assembly reproducible after moving it.
        converted = adapt((work / 'program.gasm.asm').read_text(), 'program.sg')
        (work / 'program.sj.asm').write_text(converted)
        assembly = run([assembler, '-Wno-fileorg', '--sym=program.sym', '--lst=program.lst', 'program.sj.asm'], cwd=work)
        rom = (work / 'program.sg').read_bytes()
        if not rom or len(rom) > 32768:
            raise RuntimeError('prototype requires a nonempty ROM of at most 32 KiB')
        metadata = dict(source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                        project_files={name:hashlib.sha256(file_bytes(text)).hexdigest() for name,text in inputs.items()},
                        frontend_sha256=hashlib.sha256(args.frontend.resolve().read_bytes()).hexdigest(),
                        dependencies=lock, assembler=run([assembler, '--version']).stdout.strip(),
                        assembler_sha256=hashlib.sha256(Path(assembler).read_bytes()).hexdigest(),
                        rom_bytes=len(rom), rom_sha256=hashlib.sha256(rom).hexdigest())
        (work / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
        (work / 'build.log').write_text(compilation.stdout + compilation.stderr + assembly.stdout + assembly.stderr)
        dest.mkdir(parents=True, exist_ok=True)
        for name in ['program.bas', 'program.gasm.asm', 'program.sj.asm', 'program.sg', 'program.sym', 'program.lst', 'build.json', 'build.log']:
            shutil.copy2(work / name, dest / name)
        print(f'{dest / "program.sg"}: {len(rom)} bytes, SHA-256 {metadata["rom_sha256"]}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc))

"""Experimental adapter for pinned CVBasic, unbanked SG-1000 output only."""
import pathlib
import re
import sys


def adapt(source, output):
    if not re.search(r'^SG1000:\s*equ 1\s*$', source, re.M | re.I):
        raise ValueError('Only SG-1000 output is supported')
    if not re.search(r'^CVBASIC_BANK_SWITCHING:\s*equ 0\s*$', source, re.M | re.I):
        raise ValueError('Bank switching is not supported')
    if any(ch in str(output) for ch in ('"', '\n', '\r')):
        raise ValueError('Invalid output filename')
    lines = [f'\tOUTPUT "{output}"']
    scope = "CVCC_ROOT"
    for line in source.splitlines():
        label = re.match(r"^([A-Za-z_#][\w#]*):", line)
        if label:
            scope = label[1].upper()
        # Preserve strings, character literals and comments; normalize Gasm80 symbols.
        parts = re.split(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])\'|;.*$)', line)
        for i in range(0, len(parts), 2):
            code = parts[i].upper()
            code = re.sub(r'(?<![\w.])\.([A-Z_0-9]+)\b', lambda m: scope + '__CVCCLOCAL_' + m[1], code)
            parts[i] = code
        line = ''.join(parts)
        # RB advances the address without emitting RAM bytes into the ROM.
        line = re.sub(r'^(\s*(?:[A-Z_#][\w#]*:\s*)?)RB\s+([^;]+)', r'\1ORG $+(\2)', line)
        line = re.sub(r'^(\s*)FORG\b', r'\1FPOS', line)
        match = re.match(r'\s*TIMES\s+(.+?)\s+DB\s+([^;]+)(;.*)?$', line)
        if match:
            count, value, comment = match.groups()
            line = f'\tDEFS {count},{value} {comment or ""}'
        lines.append(line)
    return '\n'.join(lines) + '\n'

if __name__ == '__main__':
    src, dst, rom = map(pathlib.Path, sys.argv[1:])
    dst.write_text(adapt(src.read_text(), rom.resolve()))

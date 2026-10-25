"""Project cartridge configuration and explicit 16 KiB data banks."""
import base64
import json
from pathlib import Path, PurePosixPath
import subprocess
from project_source import BINARY_SUFFIXES, LIMIT


def profiles(frontend):
    result = subprocess.run([str(frontend), '--list-cartridges'], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def load(root, frontend):
    root = Path(root).resolve()
    path = root / 'cartridge.json'
    inputs, banks = {}, {}
    config = {}
    if path.exists():
        if not path.resolve().is_relative_to(root) or path.stat().st_size > 16384:
            raise ValueError('Invalid cartridge.json path or size')
        inputs['cartridge.json'] = path.read_text()
        config = json.loads(inputs['cartridge.json'])
    if not isinstance(config, dict) or set(config) - {'mapper', 'ram_kib', 'banks'}:
        raise ValueError('cartridge.json accepts mapper, ram_kib and banks only')
    profile = next((p for p in profiles(frontend) if p['id'] == config.get('mapper', 'sg1000')), None)
    if profile is None:
        raise ValueError('Unknown cartridge mapper')
    ram = config.get('ram_kib', 16 if profile['id'] == 'asc16l' else None)
    if ('ram_kib' in config or profile['id'] == 'asc16l') and (profile['id'] != 'asc16l' or type(ram) is not int or ram not in (8, 16)):
        raise ValueError('ram_kib is available only for ASC16L: 8 or 16')
    entries = config.get('banks', {})
    if not isinstance(entries, dict) or (entries and not profile['banked']):
        raise ValueError('Data banks require ASC16L or Sega 315-5208 + Dahjee B')
    for key, name in entries.items():
        if not key.isascii() or not key.isdecimal() or str(int(key)) != key or not 2 <= int(key) <= 255:
            raise ValueError('Data bank numbers must be 2..255; banks 0 and 1 contain fixed code')
        if not isinstance(name, str) or '\\' in name or any(p in ('', '.', '..') for p in name.split('/')):
            raise ValueError('Bank files must use project-relative paths')
        relative = PurePosixPath(name)
        binary = (root / name).resolve()
        if relative.is_absolute() or relative.suffix not in BINARY_SUFFIXES or not binary.is_relative_to(root):
            raise ValueError('Bank file escapes project or has an unsupported extension')
        if not 1 <= binary.stat().st_size <= 16384:
            raise ValueError('A data bank must contain 1..16384 bytes')
        banks[int(key)] = binary.read_bytes()
        inputs[name] = {'base64': base64.b64encode(banks[int(key)]).decode()}
        if sum(len(data) for data in banks.values()) > LIMIT:
            raise ValueError('Bank data exceeds 1 MiB')
    profile = dict(profile, ram_kib=ram, bank_count=max([2, *banks])+1 if profile['banked'] else 0)
    if profile['id'] == 'asc16l':
        profile['ram_end'] = profile['ram_start'] + ram*1024
    return profile, banks, inputs


def append_banks(work, profile, banks):
    """Keep assembly self-contained and replayable with sjasmplus."""
    published = []
    if not profile['banked']:
        return published
    assembly = work / 'program.sj.asm'
    prefix = assembly.read_text().split('; CVCC_DATA_BANKS\n')[0]
    with assembly.open('w') as out:
        out.write(prefix + '; CVCC_DATA_BANKS\n')
        for bank in range(2, profile['bank_count']):
            name = f'bank{bank}.bin'
            (work / name).write_bytes(banks.get(bank, b'').ljust(16384, b'\xff'))
            out.write(f'\n; Physical ROM bank {bank}; CPU window $8000-$BFFF\n ORG $8000\n INCBIN "{name}"\n')
            published.append(name)
    return published

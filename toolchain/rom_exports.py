"""Size choices for pinned, unbanked SG-1000 images (not arbitrary ROM files)."""
import base64

SIZES = (8192, 16384, 32768, 49152)
HEADER = b'TMR SEGA\x00\x00\x00\x00\x11\x78\x00\x4c'


def exports(rom, code_bytes, *, backend='legacy', cartridge=None):
    if backend == 'z80':
        if cartridge and cartridge['banked']:
            return []  # Bank numbering and payload must not change on export.
        limit = cartridge['rom_limit'] if cartridge else 49152
        if (not isinstance(code_bytes, int) or not 0 < code_bytes <= limit
                or len(rom) != next((size for size in SIZES if size >= code_bytes), 0)
                or rom[code_bytes:] != b'\xff'*(len(rom)-code_bytes)):
            return []
        return [dict(size=size, rom=base64.b64encode(rom[:code_bytes] + b'\xff'*(size-code_bytes)).decode())
                for size in SIZES if code_bytes <= size <= limit]
    if backend != 'legacy':
        return []
    # ROM_END measures executable code + ROM data, not the fixed Sega footer.
    # Small SG-1000 images do not need that optional identification footer.
    if (len(rom) != 32768 or rom[0x7ff0:] != HEADER
            or not isinstance(code_bytes, int) or not 0 < code_bytes <= 0x7ff0):
        return []
    rounded = (code_bytes + 8191) // 8192 * 8192
    padding_end = min(rounded, 0x7ff0)
    if rom[code_bytes:padding_end] != b'\xff' * (padding_end-code_bytes):
        return []
    if rom[padding_end:0x7ff0] != b'\x00' * (0x7ff0-padding_end):
        return []
    result = []
    for size in SIZES:
        if size < code_bytes:
            continue
        image = rom[:size] + b'\xff' * max(0, size-len(rom))
        result.append(dict(size=size, rom=base64.b64encode(image).decode()))
    return result

# Project-to-ROM toolchain

This component prepares projects and drives the external tools. It needs Python
3.10 or newer, the built CVCC compiler, pinned compiler dependency checkouts and
an installed `sjasmplus`. It does not need the IDE, a web server or an emulator.
Commands below are run from the repository root.

```sh
python3 toolchain/build_rom.py examples/square --out-dir build/square
# Equivalent package entry point:
python3 -m toolchain.build_rom examples/square --out-dir build/square
```

The default compiler is `compiler/build/cvcc`; dependency checks use
`compiler/.deps` and `compiler/dependencies.lock.json`. Override them with
`--frontend /path/to/cvcc --deps /path/to/checkouts`. Output is published only
when compilation and assembly succeed; failures preserve the previous ROM.

## Source layout

- `project_source.py`: project files, includes, binary assets and diagnostic mapping.
- `cartridge.py`: mapper configuration and code/data bank packaging.
- `build_rom.py`: compiler invocation, runtime assembly, output and provenance.
- `rom_exports.py`: ROM export sizing and validation.
- `gasm80_to_sjasmplus.py`: optional historical reference adapter, used only by legacy builds/tests.

sjasmplus remains an external assembler. Nothing in this directory builds or
redistributes its executable. `--backend legacy` is optional and needs the
separate checkouts in `tests/legacy-dependencies.lock.json`; pass `--deps` for
that development-only cache. The normal Z80 build never runs CVBasic.

## Projects and includes

A project is a folder with a `main.cvc` entry point. For example:

```text
airsea/
  main.cvc
  data/
    patterns.h
    sprites.h
    screen.h
    colors.h
    title.h
```

Use `#include "data/patterns.h"` to separate data or helper definitions.
Includes resolve relative to the including file and must remain inside the
project directory. Headers may use `#pragma once`; otherwise inclusion is
textual and repeated declarations are errors. Nested includes are supported;
cycles and missing files produce diagnostics. This is not a macro preprocessor:
angle-bracket includes, `#define` and conditional directives are not supported.

Use `#incbin "sprite.bin"` on its own line inside an array initializer:

```c
const uint8_t spriteData[32] = {
#incbin "sprite.bin"
};
```

CVCC inserts the binary's byte values in order (including zero bytes), with a
trailing comma, before parsing. Declare the exact array size. Paths resolve
relative to the containing source/header and stay within the project, including
symlinks. Supported binary extensions: `.bin`, `.chr`, `.pal`, `.map`, `.dat`;
each inclusion accepts 1..8192 bytes. No offset/length syntax yet.
The workbench displays binaries as read-only hex previews; file and project ZIP
downloads preserve the original bytes. `examples/functions` demonstrates this
with its own square sprite. Binary files count toward the 1 MiB project limit.

Build a folder with `python3 toolchain/build_rom.py examples/functions --out-dir build/functions`.
The build driver expands includes before Tree-sitter parsing and maps errors
back to the original file and line. The raw `compiler/build/cvcc` executable still accepts
one already-expanded source. Limits: 128 files, 32 include levels, 1 MiB source
and expanded text. Build metadata records hashes of all included files.

The workbench shows a compact, expandable project explorer with nested folders,
indentation guides and distinct source, header and binary icons. Editing/switching files
preserves browser drafts; **Compila e avvia** always builds `main.cvc` with all
current project files. Error navigation opens the relevant header. **↓ File**
downloads the current file; **↓ Progetto** downloads a ZIP preserving paths.
Browser edits do not silently overwrite the original files on disk.
Launch with `--project /absolute/path/airsea` to open a local project. Air-Sea's
project and original data remain in ignored local work directories.

## Cartridge profiles and data banks

Open **Cartuccia del progetto** above the player to choose the mapper. The choice
is stored as `cartridge.json` beside `main.cvc`, included in local/GitHub saves,
browser drafts and ZIP downloads. Compilation and the player use that same profile.
Projects without this file retain `sg1000`. The memory profiles are defined in
`compiler/src/cartridges.h`; `compiler/build/cvcc --list-cartridges` exposes them to the workbench.

| `mapper` | Fixed ROM | Usable physical RAM | Data banks |
| --- | --- | --- | --- |
| `sg1000` | Up to 48 KiB | `$C000–$C3FF`, 1 KiB | No |
| `sc3000` | Up to 32 KiB | `$C000–$C7FF`, 2 KiB | No |
| `sc3000-16k` | Up to 32 KiB | `$8000–$BFFF` cartridge + `$C000–$C7FF` console, 18 KiB | No |
| `asc16l` | 32 KiB | `$C000–$FFFF`, 16 KiB; optionally 8 KiB at `$C000–$DFFF` | 16 KiB at `$8000–$BFFF` |
| `dahjee-b` | Up to 48 KiB | `$C000–$DFFF`, 8 KiB | No |
| `sega-dahjee-b` | 32 KiB | `$C000–$DFFE`, 8 KiB minus one reserved byte | 16 KiB at `$8000–$BFFF` |

SC-3000 profiles require an SC-3000's physical 2 KiB console RAM. The Web player
uses that machine. All RAM budgets include globals, parameters, runtime state and
stack. ASC16L's 8 KiB option does not count its mirrored addresses twice. On Sega
315-5208, writing the bank latch at `$FFFF` also writes Dahjee B RAM at `$DFFF`;
the compiler excludes that byte from allocation and stack. No emulator sources
are incorporated into CVCC; these are original implementations of the memory maps.

Example `cartridge.json` (see `examples/banks`):

```json
{
  "mapper": "asc16l",
  "ram_kib": 16,
  "banks": {
    "2": "assets/square.bin",
    "3": "assets/positions.bin"
  }
}
```

`ram_kib` is optional and only valid for ASC16L (8 or 16, default 16). Bank keys
are physical 16 KiB page numbers, 2..255. Pages 0 and 1 contain untagged functions,
IRQ code and ordinary `const` arrays. Files contain 1..16384 bytes, padded with
`0xFF`; omitted pages are filled with `0xFF`. Paths stay inside the project.
The existing 1 MiB project limit still applies in the IDE. A banked image has
at least three pages (48 KiB); a six-page/96 KiB image is also valid.

```c
x = bankRead(3, offset);                // One byte from a data bank.
vramWriteBank(0x3800, 2, 0, 32);        // VRAM address, bank, offset, length.
```

Bank numbers are literals and must fit the generated image. `bankRead` accepts
an expression for the offset; dynamic offsets wrap within the 16 KiB page,
while out-of-range literal offsets are rejected. `vramWriteBank` requires literal
offset and nonzero length and rejects transfers crossing the page boundary.
Both APIs select the bank immediately before access, after evaluating expressions,
and restore the caller's bank before returning. They can be called from banked
functions. IRQ code stays fixed and does not change the bank.

### Explicit banked functions

On ASC16L and Sega 315-5208 + Dahjee B, put `__bank(n)` before a helper function:

```c
__bank(3)
uint16_t advance(uint16_t value, uint16_t limit) {
    value++;
    if (value == limit) { return 0; }
    return value;
}
```

Calls use the usual syntax: `tick = advance(tick, 408);`. Fixed-ROM call wrappers
save the current bank, select the function's page, and restore the previous bank
on every return, preserving the result. Nested calls between different banks,
functions sharing one bank, and calls through fixed helpers are supported.
Parameters still use static cells; recursion remains unsupported.

The tag takes a decimal or hexadecimal literal from 2 to 255. `setup()` and
`loop()` must remain untagged. Each code page holds up to 16 KiB, with functions
in source order; overflow is a build error naming the bank and function.
There is no automatic placement. Untagged helpers and ordinary constants stay
in the fixed 32 KiB. Code and binary data cannot occupy the same page: reserve
data pages through `cartridge.json`, code pages through tags. The image grows to
include the highest page used by either, filling gaps with `0xFF`.

Banked calls reserve six stack bytes rather than two for a fixed call, in addition
to the callee's own needs. The compiler includes this in its call-chain RAM budget.
The implementation remains portable C11, with tag parsing in `compiler/src/bank_tags.h`,
placement in `compiler/src/backend_banks.h`, and fixed-ROM helpers in `runtime/banking.asm`.
See `examples/banked-functions` for a 64 KiB project with movement/drawing in
bank 2, math in bank 3, and a regular `main.cvc`.

The build directory contains the generated assembly, runtime and padded bank
files; rerunning sjasmplus there reproduces the entire ROM. CLI lowering accepts
`--cartridge ID`, `--ram-kib 8|16`, and `--bank-count N`; without project assets
its data banks are empty. For normal builds use `toolchain/build_rom.py PROJECT`.
ROM identification signatures remain optional and are not injected: when opening
a downloaded ROM in a separate emulator, select its mapper manually. The CVCC
player selects it explicitly from build metadata.

Cartridge tests cover memory overflow, 48 KiB linear ROMs, bank payload/reassembly,
invalid configurations, and export limits. With the optional Web core they also
execute RAM alias checks, multiple bank switches (including 96 KiB images), VRAM
transfers and reset on every profile:

```sh
python3 tests/test_cartridges.py
CVCC_WEB_CORE=/absolute/path/to/GearSF7000/platforms/web/dist/core.js python3 tests/test_cartridges.py
python3 tests/test_banked_functions.py
CVCC_WEB_CORE=/absolute/path/to/GearSF7000/platforms/web/dist/core.js python3 tests/test_banked_functions.py
```

Banked-function execution tests cover byte/word arguments and results, nested
calls, data/VRAM access from code banks, VBlank interrupts, reset, and continued
execution on both banked mappers (including ASC16L's 8 and 16 KiB RAM options).

# Validation

Run commands from the repository root after `./compiler/build.sh`.
The suites cover the compiler, ROM toolchain and IDE as separate components.

```sh
python3 tests/test_build.py
python3 tests/test_frontend.py
python3 tests/test_native.py
python3 tests/test_banked_functions.py
python3 tests/test_cartridges.py
python3 tests/test_projects.py
python3 tests/test_rom_exports.py
python3 tests/test_workspaces.py
```

`test_build.py` copies only `compiler/` into an isolated directory, builds it
against external dependency checkouts, and uses it without the IDE or runtime.
The other suites test real builds, semantics, assembly replay, project files,
export sizes and workspace conflicts. GitHub writes are simulated in tests.

For real Z80 execution in the optional external Web core:

```sh
CVCC_WEB_CORE=/path/to/GearSF7000/platforms/web/dist/core.js python3 tests/test_cartridges.py
CVCC_WEB_CORE=/path/to/GearSF7000/platforms/web/dist/core.js python3 tests/test_banked_functions.py
```

## Original Z80 backend and validation

The expression ABI uses HL for full-width results, A for byte destinations,
static parameter cells and stack snapshots for left-to-right argument evaluation.
Recursion is rejected. ROM lookup tables of exactly 256 bytes are page-aligned
for cheaper byte indexing. Scalar and constant-index assignments avoid address
spills. Hardware APIs use dedicated register conventions. There is no SDCC or
external C compiler for the generated game.

The runtime provides reset/IM1 IRQ vectors, VBlank waits, a 32-entry sprite
shadow, optional sprite-order rotation, TMS9918 modes 0/1/2, VRAM read/write,
controller input and SN76489 tone/noise/volume. Bulk VRAM loops allow at least
30 Z80 T-states between data accesses. At least 256 bytes are reserved for the
stack; a conservative call/expression analysis increases that reservation when
necessary. Assembly rejects ROM or RAM plus stack beyond the selected cartridge's
physical capacity. RAM allocation is counted without wrapping at $FFFF.

```sh
python3 tests/test_frontend.py
python3 tests/test_native.py
python3 tests/test_projects.py
python3 tests/test_rom_exports.py
python3 tests/test_workspaces.py
CVCC_EMULATOR=/absolute/path/to/isolated/gearsf7000 python3 tests/test_native_emulator.py
# With the local workbench running:
python3 tests/test_web.py
```

Native build tests assemble every public example and language fixture, reassemble
saved outputs, check failure preservation and build with a dependency directory
containing only Tree-sitter and its grammar. Headless emulator tests cover nested
calls, parameters/results, side effects, loops, switches, byte/word arithmetic,
shifts, short-circuit logic, VRAM transfers and counted waits on SG-1000 and SC-3000.

The local Air-Sea port has also passed audio stream/PSG checks, dense scroll and
enemy-load frame cadence, damage/game-over/reset transitions, an entire 12,288-frame
two-player timer, and per-game high-score persistence checks. The port and its
assets remain ignored. These are emulator checks, not physical-hardware validation.
The new code generator intentionally does not produce the old ROM bytes or RAM layout.

The shared semantic admission pass currently produces and discards a temporary
BASIC representation internally; this code is CVCC's own and does not load or
execute CVBasic. Separating that validation from the reference emitter remains
an internal refactor. `--basic` exposes the old representation explicitly.

Optional historical reference tests require the separately pinned CVBasic checkout
from `tests/legacy-dependencies.lock.json` in `compiler/.deps/`, and Gasm80. Enable them with
`CVCC_TEST_LEGACY=1 python3 tests/test_frontend.py`; they are skipped by default.
The default toolchain and the native emulator suite do not require either tool.

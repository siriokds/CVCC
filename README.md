# CVCC

An experimental C/Arduino-like language for Z80 games, beginning with SG-1000
and SC-3000. The current prototype parses real C++ syntax with Tree-sitter,
validates a small CVCC subset, and builds a ROM with **sjasmplus**:

```text
source.cpp -> Tree-sitter C++ -> CVCC semantic checks -> generated CVBasic
           -> unmodified CVBasic -> assembly adapter -> sjasmplus -> program.sg
```

The generated BASIC is a temporary validation bridge. The intended architecture
will connect the frontend directly to CVBasic's Z80 engine. CVCC is **not** a
standard C/C++ compiler, and does not yet provide CVBasic feature parity.

## Phase 1 target: Air/Sea Attack

Phase 1 ends with a complete, playable CVCC port of
[Air/Sea Attack](https://github.com/siriokds/Air-Sea-Attack-CVBasic), starting from
`setup()` and `loop()` and building its ROM with sjasmplus. The initial target
remains SG-1000/SC-3000. The reference is commit
`5f61956c538b66d47ac2ad5109218ee39b439db5`; its ColecoVision and MSX versions
are additional references, not requirements for this first milestone.

The reference has 2,194 BASIC source lines, 66 procedures and a 21-state game
dispatcher. It sets the following implementation priorities:

1. Named constants, 16-bit values, mutable RAM arrays, indexed ROM byte/word
   tables, arithmetic and bitwise expressions.
2. User functions, returns, counted loops and loop exits, with explicit byte
   overflow semantics and predictable generated code.
3. Controller input, random values, screen/VDP configuration, 8x8 sprites,
   VRAM uploads and reads, RAM buffers and dynamic VRAM writes.
4. Tone/noise/volume control for the game's own audio sequencer, preserving its
   frame scheduling and the order of graphics updates.

Completion means playing through title and mode selection, single- and
two-player modes, collisions/explosions, scores, game over and restart. Validate
against the original under the same input sequences on SG-1000 NTSC and SC-3000
PAL, checking graphics, audio timing, frame cadence, ROM size and RAM use.
The workbench must compile and launch the port using its separate Web player.
Binary identity is useful for unchanged lowering paths; gameplay equivalence
and measured resource use are the criteria for the complete port.

The original BASIC already assembles through the current adapter and sjasmplus
to the **same 32 KiB ROM** as Gasm80 (SHA-256
`96dfdcbf21ef02f431ed3082f218250b954606f868703f9d7fb642d4a5d3c1b4`).
The pinned CVBasic reports **654 of 814 available RAM bytes** used. This verifies
the assembly path, not a CVCC port or gameplay validation. Game source, assets
and generated ROMs remain outside this repository. Completing this milestone
does not by itself establish full CVBasic feature parity.

## Development build

Currently tested on macOS. A C11 compiler, Python 3, Git and sjasmplus are needed
for this prototype; Gasm80 is needed only for differential tests. Self-contained
Windows/macOS/Linux packages and WebAssembly remain future work.

Clone the three dependencies below into `.work/deps/`, then check out each
repository at the exact commit in `dependencies.lock.json`:

```sh
mkdir -p .work/deps
git clone https://github.com/tree-sitter/tree-sitter.git .work/deps/tree-sitter
git clone https://github.com/tree-sitter/tree-sitter-cpp.git .work/deps/tree-sitter-cpp
git clone https://github.com/nanochess/CVBasic.git .work/deps/CVBasic
python3 - <<'PY'
import json, subprocess
from pathlib import Path
for name, dependency in json.loads(Path('dependencies.lock.json').read_text()).items():
    subprocess.run(['git', '-C', str(Path('.work/deps') / name),
                    'checkout', '--detach', dependency['commit']], check=True)
PY
./tools/build_frontend.sh
python3 tools/build_rom.py examples/square.cpp --out-dir build/square
```

Load `build/square/program.sg` in an SG-1000/SC-3000 emulator with the standard
SG-1000 cartridge mapper. The output directory also contains the intermediate
BASIC, both assembly dialects, symbols, listing, logs, and build fingerprints.
Reassemble the saved assembly from its output directory with
`sjasmplus -Wno-fileorg program.sj.asm`.

The frontend alone writes BASIC to stdout, with diagnostics on stderr:

```sh
build/cvcc examples/counter.cpp > build/counter.bas
python3 tests/test_frontend.py
```

Rejected input emits no BASIC. The ROM command leaves the last successful output
intact on compilation failure; a successful exit is required to use a new build.
`CVCC_DEPS_DIR`, `CVCC_BUILD_DIR` and `CC` customize the shell build. The ROM
command accepts `--deps` and `--frontend` explicitly.

## Local Web Workbench

A browser editor is available with syntax coloring, persistent local drafts,
compiler diagnostics with line navigation, assembly/BASIC output, ROM download,
and a separate GearSC3000 Web player. It uses no external JavaScript packages.

After building the native frontend, point the server at an existing Web player
build (the directory must contain `core.js` and `core.wasm`):

```sh
python3 tools/serve_web.py --player-dist /path/to/GearSF7000/platforms/web/dist
```

Open `http://127.0.0.1:8844`. The square example compiles and starts automatically.
Use **Compila e avvia** or Command/Ctrl+Enter after editing. Source drafts are
stored in the browser, not written over repository examples. The last successful
ROM remains available after an error and is labeled accordingly.

The browser sends source to a loopback-only Python service, which invokes the
native compiler pipeline. The returned ROM runs in the separate WebAssembly
player. **The compiler itself is not yet running in WebAssembly.** The editor,
compilation API and player adapter are separate components for a future desktop
or VS Code-style interface. This is a local development server, not a hosted
multi-user compilation service.

Only the two specified player artifacts are served from the external directory;
no emulator code, private game library or WebAssembly binary is copied into this
repository. The player adapter uses its published `_web_*` ABI (SG-1000 1 KiB
mapper, NTSC, RGB565 video, 48 kHz audio). The browser UI does not expose emulator
MCP/debugger controls.

With the workbench running, `python3 tests/test_web.py` verifies compilation,
errors, request origin checks and the static file allowlist. Set
`CVCC_WEB_TEST_PORT` when using a nondefault server port.

## Supported subset

- Exactly one `void setup()` and `void loop()`, with empty parameter lists.
  Setup runs once; loop repeats with a direct jump, without a call/return wrapper.
- Global `uint8_t` variables, optionally initialized with byte literals.
  Uninitialized globals are zeroed by the pinned SG-1000 runtime before setup.
- Decimal and hexadecimal literals in `0..255`; `+`, `-`, unary minus,
  parentheses, assignment, and standalone `++`/`--`.
- `if`/`else` and `while`. Conditions use a byte value or one comparison:
  `==`, `!=`, `<`, `>`, `<=`, `>=`.
- `const uint8_t name[N] = {...}` as ROM data, with exactly N literal bytes.
  Arrays are currently only usable by `defineSprite`; indexing is not supported.
- `waitFrame()`, `clearScreen()`, `printAt(position, "ASCII text")`,
  `defineSprite(first, count, data)`, `sprite(index, y, x, pattern, color)`.
  Sprite API ordering follows CVBasic. Patterns are 16x16, 32 bytes each.

Names are case-sensitive and mapped to internal BASIC symbols. No header is
needed for `uint8_t` in this language. Byte arithmetic uses CVBasic's byte
semantics, including wraparound; it does **not** implement C integer promotions.
Comparisons are supported only as conditions, not as numeric expression values.
Strings currently exclude escapes and non-ASCII characters.

Unsupported types, locals, parameters, user functions, pointers, short-circuit
operators, preprocessing, SFRs, events, banking and other constructs are rejected.
Diagnostics contain source path and one-based line/column ranges (byte columns).
Safety limits: 1 MiB source, 256 symbols, 128 syntax levels, 64 statement levels,
8192 bytes per ROM array; generated BASIC lines must fit the upstream lexer.
These are prototype limits, not the final language specification.

## Validation

The test suite compares the counter example with handwritten BASIC and rebuilds
CVBasic's original Happy Face example from a local C-like fixture using
`setup()`/`loop()`. Its sprite data is read from the pinned upstream checkout at
test time and remains in ignored build output. Both comparisons require full
ROM byte identity between Gasm80 and the CVCC/sjasmplus pipeline.

Happy Face's 32 KiB ROM matches the earlier CVBasic baseline exactly:
`20a70be1be44280ae78dbe7de593a6c6386c3aab790abd80fdf2f97ac78d128b`.
The counter, square, Happy Face and byte-semantics probe have also been run
for 180 frames each on isolated GearSF7000 SG-1000 NTSC and SC-3000 PAL models.
Observed checks cover sprite movement, per-frame counter progress, byte overflow,
unary negation, unsigned comparison and termination of a while loop. These are
emulator checks, not physical-hardware validation; their artifacts stay local.
There are also semantic rejection tests, including malformed syntax, undeclared
symbols, unsupported operators, invalid arrays and invalid calls.

The assembly adapter is experimental and limited to the pinned, unbanked SG-1000
runtime. It normalizes symbol case and local labels, translates `TIMES`/`FORG`,
and reserves RAM without emitting it into ROM. `fileorg` warnings are disabled
for these deliberate address-only changes. Other machines and banking have not
been validated.

## Repository boundaries

Original CVCC source is BSD-3-Clause. Third-party source, binaries, ROMs, emulator
artifacts, scratch files and internal handoffs are not committed. `.work/`,
`build/` and `local-docs/` are ignored. See `THIRD_PARTY_NOTICES.md` for dependency
provenance and the unresolved upstream licensing discrepancy.

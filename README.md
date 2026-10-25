# CVCC

An experimental C/Arduino-like language for Z80 games, beginning with SG-1000
and SC-3000. The current prototype parses real C++ syntax with Tree-sitter,
validates a small CVCC subset, and builds a ROM with **sjasmplus**:

```text
source.cvc -> Tree-sitter C++ -> CVCC checks -> original Z80 backend
           -> original SG-1000 runtime -> sjasmplus -> program.sg
```

The default build no longer requires, runs or embeds CVBasic. The backend and
runtime are original CVCC code. The old pipeline is an optional development
reference (`--backend legacy`), with its dependency pinned separately under tests.
CVCC is **not** a standard C/C++ compiler and does not implement every CVBasic
command; the supported subset is listed below.

CVCC source files use the `.cvc` extension. The conventional project entry is
`main.cvc`, containing `setup()` and `loop()`; the current CLI accepts an explicit
source path. Parsing still uses the Tree-sitter C++ grammar.

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

As a historical reference, the original BASIC assembled through the legacy adapter and sjasmplus
to the **same 32 KiB ROM** as Gasm80 (SHA-256
`96dfdcbf21ef02f431ed3082f218250b954606f868703f9d7fb642d4a5d3c1b4`).
The pinned CVBasic reports **654 of 814 available RAM bytes** used. This verifies
the assembly path, not a CVCC port or gameplay validation. Game source, assets
and generated ROMs remain outside this repository. Completing this milestone
does not by itself establish full CVBasic feature parity.

## Future idea: optimization assistant

Deferred beyond the current implementation work: help programmers simplify
inefficient code and explore loop unrolling, instruction reduction and equivalent
transformations. Evaluate existing tools before choosing an implementation.
Show before/after source and assembly, with ROM/RAM and Z80 cycle costs so that
speed-versus-size tradeoffs are visible. Validate behavior and preserve observable
I/O, interrupt and frame timing requirements. This is an idea to revisit, not an
implemented feature or an additional Phase 1 requirement.

## Development build

Currently tested on macOS. A C11 compiler, Python 3, Git and sjasmplus are needed
for this prototype; Gasm80 is needed only for differential tests. Self-contained
Windows/macOS/Linux packages and WebAssembly remain future work.

Clone the two dependencies below into `.work/deps/`, then check out each
repository at the exact commit in `dependencies.lock.json`:

```sh
mkdir -p .work/deps
git clone https://github.com/tree-sitter/tree-sitter.git .work/deps/tree-sitter
git clone https://github.com/tree-sitter/tree-sitter-cpp.git .work/deps/tree-sitter-cpp
python3 - <<'PY'
import json, subprocess
from pathlib import Path
for name, dependency in json.loads(Path('dependencies.lock.json').read_text()).items():
    subprocess.run(['git', '-C', str(Path('.work/deps') / name),
                    'checkout', '--detach', dependency['commit']], check=True)
PY
./tools/build_frontend.sh
python3 tools/build_rom.py examples/square/main.cvc --out-dir build/square
```

Load `build/square/program.sg` in an SG-1000/SC-3000 emulator with the standard
SG-1000 cartridge mapper. The output directory also contains the intermediate
Z80 assembly, runtime sources, symbols, listing, logs, and build fingerprints.
Reassemble the saved assembly from its output directory with
`sjasmplus -Wno-fileorg program.sj.asm`.

The frontend alone writes Z80 assembly to stdout, with diagnostics on stderr:

```sh
build/cvcc examples/counter/main.cvc > build/counter.asm
python3 tests/test_frontend.py
```

Rejected input emits no assembly. The ROM command leaves the last successful output
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

### Open, save and GitHub

**Apri…** opens an existing project folder on this machine or a GitHub project.
**Salva copia…** creates a new folder from the current sources and binary assets;
existing folders are never overwritten. On macOS **Sfoglia…** opens the native
folder chooser; on other systems enter the absolute path. A project has a
`main.cvc` at its root. The Recent list remembers locations, not credentials.

For local folders, **Salva** / Command/Ctrl+S writes the whole project to disk.
The server checks the original content revision before replacing changed files;
external modifications stop the save. Each file is replaced atomically, but a
hardware/I/O failure can still interrupt a multi-file save. Unrelated files are
preserved. Examples remain browser drafts until saved as a personal copy.

For GitHub, install GitHub CLI and sign in using `gh auth login` on the machine
running the local server. Choose an accessible recent repository or enter
`owner/repository`, select a branch (blank uses the default), then use
**Trova progetti CVCC** to choose a folder containing `main.cvc`. This reads the
remote repository directly, without cloning or modifying a local checkout.
Credentials stay in GitHub CLI and are never returned to the browser.

**Salva bozza** / Command/Ctrl+S only stores GitHub edits in this browser.
**Modifiche** shows saved text alongside the draft; **Commit e invia** submits
changed project files as one commit to the displayed branch, attributed to the
authenticated GitHub user. There is no AI coauthor. Unrelated repository files
are preserved. A changed remote branch, missing write permissions or branch
protection stops the operation; force push is never used. Review and commit are
explicit actions, separate from compilation. Browser drafts are recovery copies,
not cloud backups. The storage strip always distinguishes disk, browser and
GitHub states. Reopening a project with a stale draft requires resolving it or
saving a separate copy before writing. After a server restart, reopen from Recent.

Dropbox/Google Drive currently work through their **locally synchronized folders**.
The UI explicitly labels this and does not claim that a disk save has reached the
cloud. Direct browser OAuth integrations are not implemented yet; they require
registering CVCC with each provider. GitHub currently uses the local CLI rather
than hosted OAuth. This workbench remains local, not a hosted service.

Storage tests: `python3 tests/test_workspaces.py` covers disk conflicts, binary
preservation, path restrictions and GitHub commit/race behavior against a fake API.
`python3 tests/test_web.py` exercises real HTTP persistence against the running
workbench. Live remote writes are not required by these tests.

The download menu offers the original image and 8, 16, 32 or 48 KiB files.
Only sizes that fit `ROM_END` (all generated code and ROM data) are enabled.
Exporting never changes the ROM currently running in the player. The original
is byte-for-byte unchanged. Native images have no Sega footer and use verified
0xFF padding to 8, 16 or 32 KiB; exports may extend this to 48 KiB. The legacy
format is recognized separately, including its optional identification footer. This is an SG-1000 size
export, not a new mapper or a change to the compiler's current 32 KiB limit.
Unknown layouts disable resizing rather than risk dropping meaningful bytes.
`python3 tests/test_rom_exports.py` checks size boundaries and preservation.

The browser sends source to a loopback-only Python service, which invokes the
native compiler pipeline. The returned ROM runs in the separate WebAssembly
player. **The compiler itself is not yet running in WebAssembly.** The editor,
compilation API and player adapter are separate components for a future desktop
or VS Code-style interface. This is a local development server, not a hosted
multi-user compilation service.

Only the two specified player artifacts are served from the external directory;
no emulator code, private game library or WebAssembly binary is copied into this
repository. The player adapter uses its published `_web_*` ABI (SG-1000 1 KiB
mapper, NTSC, RGB565 video, 48 kHz audio). At ROM load, the adapter requests
60 Hz through `_web_set_target_fps` and uses the effective rate returned by the
core. Older player builds without that API retain native timing. Native emulator
validation continues to use the original NTSC/PAL timing. The browser UI does not expose emulator
MCP/debugger controls.

With the workbench running, `python3 tests/test_web.py` verifies compilation,
errors, request origin checks and the static file allowlist. Set
`CVCC_WEB_TEST_PORT` when using a nondefault server port.

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

Build a folder with `python3 tools/build_rom.py examples/functions --out-dir build/functions`.
The build driver expands includes before Tree-sitter parsing and maps errors
back to the original file and line. The raw `build/cvcc` executable still accepts
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

### PSG sound

`sound(channel, periodOrControl, volume)` controls the PSG directly on the
SG-1000/SC-3000 SN76489. Channel must be a literal 0..3. Tone channels 0..2
accept a 10-bit divider (0..1023, not Hertz); channel 3 accepts a noise control
0..7. Volume is linear 0..15, with 0 silent. `soundVolume(channel, volume)`
changes volume without rewriting the divider or restarting noise. Expressions
are evaluated once, left to right; runtime values must stay within these ranges.
Sound continues until changed or muted. These calls do not wait for a frame.

## Supported subset

- Exactly one `void setup()` and `void loop()`, with empty parameter lists.
  Setup runs once; loop repeats with a direct jump, without a call/return wrapper.
- Helper functions return `void`, `uint8_t` or `uint16_t`, with up to 16 named
  `uint8_t`/`uint16_t` scalar parameters passed by value. Definitions may follow
  callers. Parameters are writable, scoped to their helper, and may shadow globals.
  Calls lower to GOSUB/PROCEDURE with static parameter/result slots; recursion
  (including indirect cycles) is rejected. This convention is not reentrant.
  `return;` exits a void helper, ends setup, or starts the next loop iteration.
  Numeric helpers use `return expression;`; all reachable exits must return a
  value. The check is conservative: loops alone do not prove a return.
  Calls work in arithmetic, array indices, conditions, switches and numeric
  builtin arguments. Arguments and operands evaluate left to right, with saved
  temporaries protecting nested calls and values from side effects. Logical
  conditions retain short-circuit evaluation; loop conditions rerun calls each
  iteration. Assignment indices and compound old values are saved before RHS
  calls. Assignment to parameters/results narrows to the declared width; a
  caller may ignore a numeric result. Temporaries consume RAM (no slot reuse yet).
- Global `uint8_t` and `uint16_t` variables, optionally initialized with literals.
  Scalar `const` declarations require a literal initializer.
  Uninitialized globals are zeroed by the pinned SG-1000 runtime before setup.
- Decimal and hexadecimal literals in `0..65535`; `+`, `-`, unary minus,
  parentheses, assignment, and standalone `++`/`--`. Bitwise `&`, `|`, `^`,
  `~`, and compound assignments `+=`, `-=`, `&=`, `|=`, `^=` are supported.
  Shifts `<<`, `>>`, `<<=`, `>>=` take a literal or scalar const count in
  `0..7` for a byte operand and `0..15` for a word operand. Right shift fills
  with zero; left shift discards bits beyond the operand width, even when
  assigned to a wider destination. Compound operands are masked before the
  shift. Binary integer expressions use the wider operand's width; shifts
  retain the left operand's width. Counts outside the range are rejected.
  Parentheses in generated BASIC preserve the source expression precedence.
- `if`/`else`, `while`, `do { ... } while (condition);`, and
  `for (init; condition; update)` with optional
  clauses, nested loops, `break` and `continue`. Counters must be global; local
  declarations and comma expressions in the header are not supported.
  The condition is tested before each iteration; `continue` runs the for-update
  before testing again, and `break` exits the innermost loop.
  A `do` loop executes its body at least once and tests its condition at the end;
  its `continue` jumps to that final test. All loop kinds can be nested, and
  `do` conditions support the same short-circuit logic as if/while/for.
  Unsigned counters wrap normally: use `uint16_t` for `i <= 255`, since a byte
  counter wraps to zero and cannot terminate that condition.
  Pre-test loops lower to WHILE plus labels; do loops use a body label and
  a final conditional branch to preserve these C-like control-flow rules. Conditions use an integer value or one comparison:
  `==`, `!=`, `<`, `>`, `<=`, `>=`. Conditions also support `&&`, `||` and
  `!`, including nesting and truth tests of nonzero integers. AND/OR conditions
  lower to branches with left-to-right short-circuit evaluation, not BASIC
  bitwise operators. Both sides are still checked for source errors.
- `switch (expression) { case value: ... default: ... }`, with the selector
  evaluated once. Case values are literals or scalar const names in 0..65535;
  duplicate values/defaults are rejected. Up to 256 labels per switch are
  supported, directly inside the braced switch body. The default may appear
  anywhere; omitted breaks preserve source-order fall-through, including stacked
  labels. `break` exits the nearest loop or switch; `continue` targets the nearest
  enclosing loop, even through switches. `return;` exits the containing function.
  The initial lowering uses comparisons and labels, with a shared two-byte
  selector scratch value; it is not a jump-table optimizer. Switch declarations,
  initializer clauses, arbitrary case constant expressions and statements before
  the first label are not supported yet.
- One-dimensional byte/word RAM arrays (`uint16_t values[N];`) and ROM arrays
  (`const uint16_t values[N] = {...};`), accessed with `values[index]`.
  Sizes are explicit positive literals. Optional RAM initializers and mandatory
  ROM initializers contain exactly N literals of the element type. RAM arrays
  support indexed assignment and standalone increment/decrement. Literal indices
  are checked against array size; other indices have no runtime bounds checks.
- `waitVBlank()`, `waitVBlank(n)` and its one-frame alias `waitFrame()`.
  The count is an unsigned byte/word expression evaluated once at entry; zero
  returns immediately. Counted waits keep the remaining count in HL.
  The runtime uses an atomic EI/HALT wait and an IRQ-updated VBlank counter;
  waits belong in normal program flow, not interrupt handlers.
  Waiting follows machine VBlank timing, not a fixed millisecond duration.
- `videoMode(0|1|2)` selects Graphics II with a font (0), Graphics II bitmap layout (1),
  or Graphics I (2). The original compact font renders lowercase as uppercase.
  `screenDisable()` / `screenEnable()` blank or enable display;
  `spriteFlicker(0|1)` disables/enables runtime sprite cycling.
  `vdpWrite(register, value)` writes a literal register 0..7, and
  `vramPoke(address, value)` writes one byte to VRAM.
  Mode/flicker selectors are literals. Register 1 controls sprite size:
  for the Air-Sea 8x8 configuration, use `vdpWrite(1, 0xE0)`. Screen enable/disable preserves the other register bits.
- `vramWrite(address, array, offset, length)` copies byte ROM or RAM arrays
  to VRAM; `vramRead(address, array, offset, length)` copies VRAM into a
  writable RAM byte array. Offset and length are literals, length is nonzero,
  and the span must fit the array. Literal VRAM addresses/spans are checked
  against 16 KiB; computed addresses are the caller's responsibility.
  These use original interrupt-protected bulk transfer routines. Large uploads
  belong in screen-disabled setup; frame-time transfers still need a timing budget.
  Numeric arguments can call helpers; their values are preserved in source order.
- `controllerRead(1)` / `controllerRead(2)` returns an active-high byte mask
  sampled directly from the controller ports: up `1`, right `2`, down
  `4`, left `8`, fire 1 `64`, fire 2 `128`. The player number must be a literal.
  Read after `waitVBlank()` and store the result to test multiple buttons from
  one sample. Value calls work in helpers, conditions and arguments with the
  same evaluation ordering as other calls. This does not wait or detect edges;
  compare previous state in your game for press/release events.
  Web player: click the screen; P1 arrows + Z/X, P2 WASD + F/G.
- `clearScreen()`, `printAt(position, "ASCII text")`,
  `defineSprite(first, count, data)`, `sprite(index, y, x, pattern, color)`.
  Sprite API ordering follows CVBasic. Patterns are 16x16, 32 bytes each.

Names are case-sensitive and preserved in prefixed assembly symbols. No header
is needed for either integer type. Arithmetic intermediates are unsigned 16-bit;
assignment, parameters and returns truncate to their declared width. Shifts mask
to the left operand width before and after shifting. This does **not** implement
C integer promotions. Byte destinations use shorter byte operations when equivalent.
Comparisons and logical operators are currently supported only as conditions,
not as numeric expression values. Shift counts computed at runtime are rejected.
Strings currently exclude escapes and non-ASCII characters.

Local declarations, array/reference/pointer parameters, default arguments, unsupported types, macro preprocessing, SFRs, events, banking and other constructs are rejected.
Diagnostics contain source path and one-based line/column ranges (byte columns).
Safety limits: 1 MiB source, 256 global symbols, 128 helper functions, 16 parameters per helper, 2048 expression temporaries,
128 syntax levels, 64 statement levels, 8192 bytes per array. The legacy reference path additionally limits BASIC line length.
These are prototype limits, not the final language specification.

The `examples/patrol/main.cvc` workbench example combines helper functions, indexed RAM byte
arrays and a ROM word table with a 16-bit frame counter. Available RAM remains
machine-dependent: the SG-1000 backend checks the total allocation at build time.

The `examples/masks/main.cvc` workbench example adds counted loops and AND/XOR masks to the
moving formation. Bitwise operators operate on unsigned byte/word values using
the backend's width rules; they do not provide short-circuit boolean evaluation.

The `examples/logic/main.cvc` example adds constant shifts and nested short-circuit conditions.

The `examples/states/main.cvc` workbench example moves a sprite around a rectangle using a
switch-driven state machine, with both fall-through and direct returns.

The `examples/functions/main.cvc` workbench example draws two squares moving in opposite
directions using `advance(value, period)`, `triangle(value, limit)` and
`drawPair(phase)`.

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
necessary. Assembly rejects ROMs above 32 KiB or RAM plus stack above 1 KiB.

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
from `tests/legacy-dependencies.lock.json` and Gasm80. Enable them with
`CVCC_TEST_LEGACY=1 python3 tests/test_frontend.py`; they are skipped by default.
The default toolchain and the native emulator suite do not require either tool.

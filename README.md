# CVCC

An experimental C/Arduino-like language for Z80 games, beginning with SG-1000
and SC-3000. The current prototype parses real C++ syntax with Tree-sitter,
validates a small CVCC subset, and builds a ROM with **sjasmplus**:

```text
source.cvc -> Tree-sitter C++ -> CVCC semantic checks -> generated CVBasic
           -> unmodified CVBasic -> assembly adapter -> sjasmplus -> program.sg
```

The generated BASIC is a temporary validation bridge. The intended architecture
will connect the frontend directly to CVBasic's Z80 engine. CVCC is **not** a
standard C/C++ compiler, and does not yet provide CVBasic feature parity.

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

The original BASIC already assembles through the current adapter and sjasmplus
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
python3 tools/build_rom.py examples/square.cvc --out-dir build/square
```

Load `build/square/program.sg` in an SG-1000/SC-3000 emulator with the standard
SG-1000 cartridge mapper. The output directory also contains the intermediate
BASIC, both assembly dialects, symbols, listing, logs, and build fingerprints.
Reassemble the saved assembly from its output directory with
`sjasmplus -Wno-fileorg program.sj.asm`.

The frontend alone writes BASIC to stdout, with diagnostics on stderr:

```sh
build/cvcc examples/counter.cvc > build/counter.bas
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

The download menu offers the original image and 8, 16, 32 or 48 KiB files.
Only sizes that fit `ROM_END` (all generated code and ROM data) are enabled.
Exporting never changes the ROM currently running in the player. The original
is byte-for-byte unchanged; smaller exports remove only verified padding and
CVBasic's optional Sega identification footer at 0x7FF0. The footer is retained
when it fits, and larger images are extended with 0xFF. This is an SG-1000 size
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

## Supported subset

- Exactly one `void setup()` and `void loop()`, with empty parameter lists.
  Setup runs once; loop repeats with a direct jump, without a call/return wrapper.
- Additional `void name()` functions, defined before or after their callers.
  Calls lower to GOSUB/PROCEDURE; recursion (including indirect cycles) is rejected.
  `return;` exits a helper, ends setup, or starts the next loop iteration.
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
  returns immediately. Counted waits use a shared two-byte runtime counter.
  The current SG-1000 backend emits CVBasic WAIT (HALT with VBlank interrupts
  enabled); waits belong in normal program flow, not interrupt handlers.
  Waiting follows machine VBlank timing, not a fixed millisecond duration.
- `clearScreen()`, `printAt(position, "ASCII text")`,
  `defineSprite(first, count, data)`, `sprite(index, y, x, pattern, color)`.
  Sprite API ordering follows CVBasic. Patterns are 16x16, 32 bytes each.

Names are case-sensitive and mapped to internal BASIC symbols. No header is
needed for either integer type. Arithmetic uses CVBasic's unsigned byte/word
semantics, including wraparound and truncation on assignment to a narrower type; it does **not** implement C integer promotions.
Comparisons and logical operators are currently supported only as conditions,
not as numeric expression values. Shift counts computed at runtime are rejected.
Strings currently exclude escapes and non-ASCII characters.

Function parameters, return values, locals, unsupported types, pointers, preprocessing, SFRs, events, banking and other constructs are rejected.
Diagnostics contain source path and one-based line/column ranges (byte columns).
Safety limits: 1 MiB source, 256 global symbols, 128 helper functions,
128 syntax levels, 64 statement levels, 8192 bytes per array; generated BASIC lines must fit the upstream lexer.
These are prototype limits, not the final language specification.

The `patrol.cvc` workbench example combines helper functions, indexed RAM byte
arrays and a ROM word table with a 16-bit frame counter. Available RAM remains
machine-dependent: the SG-1000 backend checks the total allocation at build time.

The `masks.cvc` workbench example adds counted loops and AND/XOR masks to the
moving formation. Bitwise operators operate on unsigned byte/word values using
the backend's width rules; they do not provide short-circuit boolean evaluation.

The `logic.cvc` example adds constant shifts and nested short-circuit conditions.

The `states.cvc` workbench example moves a sprite around a rectangle using a
switch-driven state machine, with both fall-through and direct returns.

## Validation

`switch.cvc` checks word selectors, stacked labels, missing/default-in-the-middle
cases, fall-through, nested switches, mixed loop/switch break and continue, and
returns from setup, loop and helper functions. Differential assembly and
180-frame state checks pass on SG-1000 NTSC and SC-3000 PAL.

`do_while.cvc` covers a false first condition, continue-to-test, break, nested
and mixed for/while/do loops, early return and short-circuit guarded array reads.
Its ROM passes differential assembly and 180-frame state checks on SG-1000 NTSC
and SC-3000 PAL.

`waitVBlank()` and `waitVBlank(1)` lower identically to `waitFrame()`; the counter
example keeps its exact baseline ROM hash. `wait_vblank.cvc` verifies zero-count
waits, a 260-frame word count and one update per three VBlanks in NTSC/PAL.
The count is sampled once, and the caller's variable is not decremented.

`shifts_logic.cvc` exercises byte/word shifts, compound shifts, width truncation,
operator precedence, logical negation, guarded array reads and short-circuit
conditions in if/for/while. Its ROM passes differential assembly and state
checks after 180 frames on both SG-1000 NTSC and SC-3000 PAL.

`for_bitwise.cvc` checks the full 0..255 iteration range with a word counter,
zero-iteration and descending loops, a changing bound, omitted clauses, nested
break/continue, early return, byte wraparound, byte/word complement, precedence,
compound array writes and masks. Its ROM passes Gasm80/sjasmplus differential
assembly and 180-frame state checks on SG-1000 NTSC and SC-3000 PAL.

`functions_arrays.cvc` is also compared byte-for-byte with a handwritten BASIC
reference (stable variable names preserve CVBasic's hash-based RAM placement).
Its ROM has been checked for 180 frames on both SG-1000 NTSC and SC-3000 PAL:
indexed byte/word reads and writes, initialized RAM, 16-bit wraparound, narrowing,
negation, unsigned comparison, nested calls and early returns all passed.

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

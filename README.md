# CVCC

A C/Arduino-like language and development environment for Z80 games, starting
with SG-1000 and SC-3000. Projects use `main.cvc`, `setup()` and `loop()`.

The repository contains independent components. **The compiler is written in
portable C11 and generates Z80 assembly.** The external assembler **sjasmplus**
turns that assembly, together with the original CVCC runtime, into a ROM.
The default pipeline does not require or run CVBasic.

```text
.cvc project → project tools → CVCC compiler → Z80 assembly + runtime → sjasmplus → ROM
                   ↑
             optional web IDE → external GearSF7000 Web player
```

CVCC is experimental: it implements a documented language subset, not full
C/C++ or every CVBasic feature. Native compilation currently runs on the host;
a complete WebAssembly compiler/toolchain remains planned.

## Repository layout

| Directory | Responsibility | Entry point |
| --- | --- | --- |
| [`compiler/`](compiler/README.md) | Standalone C11 compiler, parser integration and Z80 code generation | `./compiler/build.sh` |
| [`runtime/`](runtime/README.md) | Original Z80 startup, VBlank, video, audio, input and bank helpers | Assembled into a ROM by sjasmplus |
| [`toolchain/`](toolchain/README.md) | Includes/assets, cartridge layout, ROM builds and exports | `python3 toolchain/build_rom.py` |
| [`ide/`](ide/README.md) | Browser UI, local HTTP server, workspaces and player adapter | `./ide/run.sh` |
| [`examples/`](examples/README.md) | Small, self-contained `.cvc` projects | Pass a project folder to the ROM toolchain |
| [`tests/`](tests/README.md) | Compiler, integration and optional emulator tests | Python test scripts |
| [`tools/`](tools/README.md) | Compatibility launchers for the old command paths | Delegates to the components above |

`compiler/build/` contains compiler build output. Top-level `build/` contains
ROM/test output. Both are ignored. Dependency checkouts are ignored as well.
Internal `docs/`, `local-docs/` and `.work/` remain private and are not published.

## Build only the compiler

Prepare the two pinned dependencies as described in the
[compiler instructions](compiler/README.md), then:

```sh
./compiler/build.sh
compiler/build/cvcc examples/counter/main.cvc > compiler/build/counter.asm
```

You can copy **just `compiler/`**, supply its Tree-sitter dependencies and rebuild
it elsewhere. It includes its own build script, dependency lock, documentation,
license and dependency notices. No Python, IDE, emulator or assembler is needed
to build and run the compiler itself. Full project includes and binary assets are
handled separately by the Python toolchain.

## Build a ROM

Install sjasmplus and use Python 3.10 or newer:

```sh
python3 toolchain/build_rom.py examples/square --out-dir build/square
python3 toolchain/build_rom.py examples/banked-functions --out-dir build/banked-functions
```

Each output includes `program.sg`, assembly, runtime files, symbols, listing and
build metadata. A failed build preserves the last successful ROM. Reassemble a
saved build with `sjasmplus -Wno-fileorg program.sj.asm` from its output directory.
See the [project and cartridge guide](toolchain/README.md) for `#include`,
`#incbin`, mapper configuration, banked data and explicitly banked functions.

## Open the IDE

With the compiler built and an existing GearSF7000 Web player available:

```sh
./ide/run.sh --player-dist /path/to/GearSF7000/platforms/web/dist
```

Open `http://127.0.0.1:8844`. The IDE uses the same ROM toolchain as the CLI.
Its HTML, CSS and JavaScript need no separate build step. Player binaries remain
external and are served read-only. See the [IDE guide](ide/README.md) for local
projects, GitHub, saving and the current cloud limitations.

## Reference and validation

- [Supported language and bank annotations](compiler/LANGUAGE.md)
- [Tests and emulator validation](tests/README.md)
- [Phase 1 target and future work](ROADMAP.md)
- [Dependency provenance](THIRD_PARTY_NOTICES.md)

The private Air-Sea Attack port is the Phase 1 target. Its sources/assets and
reference dependencies are not part of the public repository. Current checks
include generated ROMs and emulator execution; hardware validation remains open.

## License

Original project code is licensed under [BSD-3-Clause](LICENSE). Dependency
licenses are separate; the standalone compiler carries its own copies of the
relevant notices. sjasmplus and the emulator are not vendored or redistributed.

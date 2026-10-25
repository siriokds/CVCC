# CVCC compiler

A standalone compiler written in **portable C11**. It parses the CVCC `.cvc`
language with Tree-sitter, validates the supported subset, and emits **Z80
assembly compatible with sjasmplus**. Diagnostics go to stderr; successful
assembly goes to stdout. Rejected input produces no partial assembly.

This directory can be copied and built independently. It does not depend on
Python at build/runtime, the repository's IDE, ROM tools, game runtime, sjasmplus
or the emulator. The generated assembly does reference runtime files: those are
needed later when assembling a complete game ROM, not to build the compiler.

## Dependencies

Build requirements: a C11 compiler (`cc` by default) and a POSIX shell. GCC and
Clang are the intended toolchains; current validation is on macOS. Windows shell
packaging and WebAssembly builds are not implemented yet.

External sources are pinned in `dependencies.lock.json`:

- Tree-sitter C runtime.
- Tree-sitter C++ grammar and scanner, compiled as C.

Keep them in `.deps/` beside this README, or set `CVCC_DEPS_DIR` to an existing
directory containing `tree-sitter/` and `tree-sitter-cpp/`. The checkout is never
included in Git. To prepare it, run the following **from this directory**. Git
and Python are used here only to fetch/select the exact dependency revisions:

```sh
mkdir -p .deps
git clone https://github.com/tree-sitter/tree-sitter.git .deps/tree-sitter
git clone https://github.com/tree-sitter/tree-sitter-cpp.git .deps/tree-sitter-cpp
python3 - <<'PY'
import json, subprocess
from pathlib import Path
for name, dependency in json.loads(Path('dependencies.lock.json').read_text()).items():
    subprocess.run(['git', '-C', str(Path('.deps') / name),
                    'checkout', '--detach', dependency['commit']], check=True)
PY
```

If you already have the pinned sources, skip the downloads and pass their path.
The build script never downloads anything implicitly.

## Build and run

From this directory:

```sh
./build.sh
./build/cvcc /path/to/main.cvc > build/program.sj.asm
./build/cvcc --list-cartridges
```

Or invoke `/path/to/compiler/build.sh` from any working directory. Default output
is always `compiler/build/` beside the script; the working directory is preserved.
Overrides are optional:

```sh
CC=clang CVCC_DEPS_DIR=/path/to/dependencies CVCC_BUILD_DIR=/path/to/output ./build.sh
```

Relative overrides are resolved from the calling working directory. CVCC sources
are compiled with `-std=c11 -Wall -Wextra -Werror -pedantic`; upstream parser
sources use their own build flags. No C++ compiler is required.

The executable accepts one source file. Project-level `#include` and `#incbin`
expansion belong to the separate ROM toolchain. Within the complete repository,
use `python3 toolchain/build_rom.py PROJECT --out-dir OUTPUT` from the root.
That command supplies expanded source and cartridge settings, then invokes the
external assembler. A different compiler binary can be selected with `--frontend`.

## Source layout

| File | Purpose |
| --- | --- |
| `src/cvcc.c` | CLI, symbol/type checks, supported syntax and semantic validation |
| `src/backend_z80.h` | Native Z80 expressions, statements and RAM/stack accounting |
| `src/bank_tags.h` | Explicit `__bank(n)` annotations and source positions |
| `src/backend_banks.h` | Fixed-ROM call wrappers and code-bank placement |
| `src/cartridges.h` | Supported cartridge memory maps and CLI profiles |

See [LANGUAGE.md](LANGUAGE.md) for implemented syntax and limitations. No new
language behavior is introduced by the repository reorganization.

The optional `--basic` output is a historical transpilation/reference path. The
native path currently reuses its semantic checks and discards that temporary
text before generating Z80 assembly. This is CVCC's own code; it does not execute
or link to CVBasic. Separating those checks from the reference emitter is future
internal work.

## License and distribution

[LICENSE](LICENSE) covers CVCC's original compiler sources. Retain the
[dependency notices](THIRD_PARTY_NOTICES.md) when distributing a compiler binary
linked with Tree-sitter and its grammar. Dependency checkouts and generated
executables are not committed to this repository.

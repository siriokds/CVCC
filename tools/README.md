# Compatibility commands

These small launchers preserve previously documented command paths. They contain
no compiler, ROM-building or IDE implementation. New scripts should use:

| Old entry point | Current entry point |
| --- | --- |
| `tools/build_frontend.sh` | `compiler/build.sh` |
| `python3 tools/build_rom.py` | `python3 toolchain/build_rom.py` |
| `python3 tools/serve_web.py` | `ide/run.sh` |

Arguments are forwarded unchanged. Compiler output now lives in
`compiler/build/`, not the root `build/`; update direct executable references.
Python consumers should import `toolchain.*` or `ide.*` from the repository root
instead of importing private modules out of this compatibility directory.

# Z80 runtime

Original CVCC target-side routines, assembled by **sjasmplus** into a game ROM.
This is Z80 code for the console, not a library linked into the host compiler.
The compiler can be built and run without this directory.

- `sg1000.asm`: startup, interrupt/VBlank handling, sprites, video/VRAM, input and sound.
- `font.asm`: built-in text font.
- `banking.asm`: fixed-ROM bank selection, restoration and data transfers.

The ROM toolchain copies the required sources into each build directory. The
compiler-generated assembly supplies entry points, variables, memory-map symbols
and bank layout. Runtime files are not standalone programs and therefore have
no separate host build script.

From the repository root, build and link them through a project:

```sh
python3 toolchain/build_rom.py examples/square --out-dir build/square
```

No CVBasic runtime is used by the native backend. See the root `LICENSE` for
licensing and `tests/README.md` for emulator checks and hardware limitations.

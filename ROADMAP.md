# Project milestones

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

## Compiler and distribution

The compiler is a working C11 implementation of the documented CVCC subset.
Further language features, optimization, user interrupt handlers, automatic bank
placement and a complete browser-side WebAssembly toolchain remain future work.
The current local web service compiles on its host; the emulator already runs
in the browser. Splitting components in this repository does not complete the
WebAssembly migration.

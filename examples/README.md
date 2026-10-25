# Example projects

Each subdirectory is a complete project with `main.cvc`. Projects can include
headers, binary assets and an optional `cartridge.json`. None requires the IDE.

From the repository root:

```sh
python3 toolchain/build_rom.py examples/functions --out-dir build/functions
```

| Project | Demonstrates |
| --- | --- |
| `square` | Setup/loop, VBlank and a moving sprite |
| `counter` | Variables, arithmetic and conditions |
| `patrol` | Loops, arrays and helper functions |
| `masks` | For loops and bitwise operators |
| `logic` | Shifts and short-circuit conditions |
| `states` | Switch dispatch, fall-through and loop control |
| `functions` | Parameters, return values, includes and binary graphics |
| `banks` | Graphics and movement data in cartridge banks |
| `banked-functions` | Explicit function placement across code banks |

Public example graphics are original small fixtures. The private Air-Sea Attack
port and its assets are intentionally excluded from this repository.

# Dependency provenance

This repository contains original CVCC source and development tools. Dependency
checkouts and generated binaries are kept outside version control. The CVCC
BSD-3-Clause license does not replace dependency licenses.

| Component | Role | Upstream license file |
| --- | --- | --- |
| Tree-sitter | C parsing runtime | `LICENSE`, MIT, copyright 2018 Max Brunsfeld |
| Tree-sitter C++ | Generated C++ parser and scanner | `LICENSE`, MIT, copyright 2014 Max Brunsfeld |
| CVBasic | Unmodified reference compiler and target runtime | `LICENSE.txt`, two-clause BSD text, copyright 2024 Oscar Toledo G. |
| sjasmplus | Installed assembler, invoked externally | Consult the installed version's upstream `LICENSE.md` and dependency notices |
| Gasm80 | Installed reference assembler for tests only | Consult its upstream `LICENSE.txt` |

Repository URLs and pinned source commits are recorded in
`dependencies.lock.json`. sjasmplus and Gasm80 are external tools, not vendored
components. The initial experiment used sjasmplus 1.23.1. Each ROM build records
the assembler version and executable hash in its ignored `build.json`.

At the pinned CVBasic commit, `LICENSE.txt` permits modification and
redistribution, while the opening of `manual.txt` still prohibits modification,
decompilation, disassembly and reverse engineering. This discrepancy has not
been clarified with the author. No modified CVBasic fork, bundled runtime,
third-party binary, or generated ROM is published here. Revisit the discrepancy
and retain all applicable notices before distributing bundled artifacts.

The Happy Face differential fixture reads upstream example data locally during
testing. That data and its generated source remain in ignored build output;
the public square example uses an independently specified outline-square bitmap.

The optional local Web Workbench reads `core.js` and `core.wasm` from the user's
existing GearSF7000/GearSC3000 Web player build. These artifacts are not part of
CVCC, are not copied or redistributed here, and retain their upstream terms.
`web/player.js` is an original adapter to the exported player ABI.

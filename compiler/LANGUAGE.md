# CVCC language reference

This describes the implemented subset, not standard C/C++ conformance.
Game runtime routines are assembled separately; the compiler emits calls to them.

## Supported subset

- Exactly one `void setup()` and `void loop()`, with empty parameter lists.
  Setup runs once; loop repeats with a direct jump, without a call/return wrapper.
- Helper functions return `void`, `uint8_t` or `uint16_t`, with up to 16 named
  `uint8_t`/`uint16_t` scalar parameters passed by value. Definitions may follow
  callers. Parameters are writable, scoped to their helper, and may shadow globals.
  Native calls use CALL/RET with static parameter cells and results in HL; recursion
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
  caller may ignore a numeric result. The native backend saves expression temporaries on the stack; the legacy emitter uses RAM slots.
- Global `uint8_t` and `uint16_t` variables, optionally initialized with literals.
  Scalar `const` declarations require a literal initializer.
  Uninitialized globals are zeroed by the original SG-1000 runtime before setup.
- Decimal and hexadecimal literals in `0..65535`; `+`, `-`, unary minus,
  parentheses, assignment, and standalone `++`/`--`. Bitwise `&`, `|`, `^`,
  `~`, and compound assignments `+=`, `-=`, `&=`, `|=`, `^=` are supported.
  Shifts `<<`, `>>`, `<<=`, `>>=` take a literal or scalar const count in
  `0..7` for a byte operand and `0..15` for a word operand. Right shift fills
  with zero; left shift discards bits beyond the operand width, even when
  assigned to a wider destination. Compound operands are masked before the
  shift. Binary integer expressions use the wider operand's width; shifts
  retain the left operand's width. Counts outside the range are rejected.
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
  Loops lower to Z80 labels and branches. Conditions use an integer value or one comparison:
  `==`, `!=`, `<`, `>`, `<=`, `>=`. Conditions also support `&&`, `||` and
  `!`, including nesting and truth tests of nonzero integers. AND/OR conditions
  lower to branches with left-to-right short-circuit evaluation. Both sides are still checked for source errors.
- `switch (expression) { case value: ... default: ... }`, with the selector
  evaluated once. Case values are literals or scalar const names in 0..65535;
  duplicate values/defaults are rejected. Up to 256 labels per switch are
  supported, directly inside the braced switch body. The default may appear
  anywhere; omitted breaks preserve source-order fall-through, including stacked
  labels. `break` exits the nearest loop or switch; `continue` targets the nearest
  enclosing loop, even through switches. `return;` exits the containing function.
  Native switch dispatch uses comparisons and labels, keeping the selector
  in registers; it is not a jump-table optimizer. Switch declarations,
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

Local declarations, array/reference/pointer parameters, default arguments, unsupported types, macro preprocessing, SFRs, user interrupt handlers and other constructs are rejected.
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

### Explicit banked functions

On ASC16L and Sega 315-5208 + Dahjee B, put `__bank(n)` before a helper function:

```c
__bank(3)
uint16_t advance(uint16_t value, uint16_t limit) {
    value++;
    if (value == limit) { return 0; }
    return value;
}
```

Calls use the usual syntax: `tick = advance(tick, 408);`. Fixed-ROM call wrappers
save the current bank, select the function's page, and restore the previous bank
on every return, preserving the result. Nested calls between different banks,
functions sharing one bank, and calls through fixed helpers are supported.
Parameters still use static cells; recursion remains unsupported.

The tag takes a decimal or hexadecimal literal from 2 to 255. `setup()` and
`loop()` must remain untagged. Each code page holds up to 16 KiB, with functions
in source order; overflow is a build error naming the bank and function.
There is no automatic placement. Untagged helpers and ordinary constants stay
in the fixed 32 KiB. Code and binary data cannot occupy the same page: reserve
data pages through `cartridge.json`, code pages through tags. The image grows to
include the highest page used by either, filling gaps with `0xFF`.

Banked calls reserve six stack bytes rather than two for a fixed call, in addition
to the callee's own needs. The compiler includes this in its call-chain RAM budget.
The implementation remains portable C11, with tag parsing in `src/bank_tags.h`,
placement in `src/backend_banks.h`, and fixed-ROM helpers in `runtime/banking.asm`.
See `examples/banked-functions` for a 64 KiB project with movement/drawing in
bank 2, math in bank 3, and a regular `main.cvc`.

### PSG sound

`sound(channel, periodOrControl, volume)` controls the PSG directly on the
SG-1000/SC-3000 SN76489. Channel must be a literal 0..3. Tone channels 0..2
accept a 10-bit divider (0..1023, not Hertz); channel 3 accepts a noise control
0..7. Volume is linear 0..15, with 0 silent. `soundVolume(channel, volume)`
changes volume without rewriting the divider or restarting noise. Expressions
are evaluated once, left to right; runtime values must stay within these ranges.
Sound continues until changed or muted. These calls do not wait for a frame.

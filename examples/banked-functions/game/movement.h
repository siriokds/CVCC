#pragma once

// Two functions can share one bank. Placement is explicit.
__bank(2)
uint16_t advance(uint16_t value, uint16_t period) {
    value++;
    if (value == period) { return 0; }
    return value;
}

__bank(3)
uint8_t triangle(uint16_t value, uint16_t limit) {
    if (value > limit) { return (limit << 1) - value; }
    return value;
}

// Every triangle() call switches from bank 2 to 3, then restores bank 2.
// The compiler preserves its return value through that switch.
__bank(2)
void drawPair(uint16_t phase) {
    sprite(0, 72, 20 + triangle(phase, 204), 0, 10);
    sprite(1, 144, 224 - triangle(phase, 204), 0, 7);
}

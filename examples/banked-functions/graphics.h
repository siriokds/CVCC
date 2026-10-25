#pragma once

// Ordinary constants stay in fixed ROM, visible from every code bank.
const uint8_t square[32] = {
#incbin "assets/square.bin"
};

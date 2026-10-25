uint8_t wrapped = 255;
uint8_t negative = 1;
uint8_t countdown = 3;
uint8_t zeroFlag;
uint8_t ticks;
uint8_t unsignedFlag;

void setup() {
    wrapped++;
    negative = -negative;
    while (countdown > 0) { countdown--; }
    if (wrapped == 0) { zeroFlag = 1; }
    if (negative > 200) { unsignedFlag = 1; }
}

void loop() {
    ticks++;
    waitFrame();
}

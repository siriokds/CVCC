// A 16x16 outline square. Sprite bytes: left half, then right half.
const uint8_t square[32] = {
    255,128,128,128,128,128,128,128,128,128,128,128,128,128,128,255,
    255,1,1,1,1,1,1,1,1,1,1,1,1,1,1,255
};
uint8_t x;
uint8_t y;
uint8_t dx;
uint8_t dy;

void setup() {
    defineSprite(0, 1, square);
    printAt(36, "CVCC moving square");
    x = 50;
    y = 100;
    dx = 1;
    dy = 1;
}

void loop() {
    waitFrame();
    waitFrame();
    sprite(0, y - 1, x, 0, 10);
    x = x + dx;
    if (x == 0) { dx = -dx; }
    if (x == 240) { dx = -dx; }
    y = y + dy;
    if (y == 0) { dy = -dy; }
    if (y == 176) { dy = -dy; }
}

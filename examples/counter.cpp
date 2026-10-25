// CVCC prototype: uint8_t arithmetic wraps at 256, without C integer promotion.
uint8_t counter = 0;

void setup() {
    clearScreen();
    printAt(36, "CVCC + Tree-sitter");
}

void loop() {
    if (counter < 100) {
        counter++;
    } else {
        counter = 0;
    }
    waitFrame();
}

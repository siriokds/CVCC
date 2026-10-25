/* Cartridge memory layouts. Original CVCC code, BSD-3-Clause.
 * web_mapper is an index in GearSF7000 platforms/web/player.cpp, not a core ID.
 * ram_end is exclusive; mirrors never count as additional storage. */
typedef struct {
    const char *id, *label;
    unsigned web_mapper, ram_start, ram_end, rom_limit, bank_register;
} Cartridge;
static const Cartridge cartridges[] = {
    {"sg1000", "SG-1000 · 1 KB RAM", 7, 0xc000, 0xc400, 0xc000, 0},
    {"sc3000", "SC-3000 · 2 KB RAM", 1, 0xc000, 0xc800, 0x8000, 0},
    {"sc3000-16k", "SC-3000 · 16 KB + 2 KB RAM", 3, 0x8000, 0xc800, 0x8000, 0},
    {"asc16l", "ASC16L · 8/16 KB RAM", 4, 0xc000, 0x10000, 0x8000, 0x8000},
    {"dahjee-b", "Dahjee B · 8 KB RAM", 12, 0xc000, 0xe000, 0xc000, 0},
    /* $FFFF also writes the RAM mirror at $DFFF. Keep that byte off the stack. */
    {"sega-dahjee-b", "Sega 315-5208 + Dahjee B · 8 KB RAM", 14, 0xc000, 0xdfff, 0x8000, 0xffff}
};
static const Cartridge *cartridge = &cartridges[0];
static unsigned cartridge_ram_kib = 0, cartridge_banks = 3;
static unsigned cartridge_ram_end(void) {
    return cartridge->web_mapper==4 && cartridge_ram_kib==8 ? 0xe000 : cartridge->ram_end;
}
static void list_cartridges(void) {
    puts("[");
    for(unsigned i=0;i<sizeof cartridges/sizeof cartridges[0];i++) {
        const Cartridge *p=&cartridges[i];
        printf("%s{\"id\":\"%s\",\"label\":\"%s\",\"web_mapper\":%u,\"ram_start\":%u,\"ram_end\":%u,\"rom_limit\":%u,\"banked\":%s}",
            i?",\n":"",p->id,p->label,p->web_mapper,p->ram_start,p->ram_end,p->rom_limit,p->bank_register?"true":"false");
    }
    puts("\n]");
}

/* Explicit bank placement and fixed-ROM call thunks. Original C11, BSD-3-Clause.
 * Keep the placement policy separate from expression/statement generation. */
static void zbank_thunks(Compiler *c) {
    for(unsigned i=0;i<c->function_count;i++) {
        Function *f=&c->functions[i];
        if(!f->bank)continue;
        /* Arguments are already in static cells. Save the previous page on the
           machine stack, so nested calls through fixed helpers remain safe.
           HL carries a byte/word return value through the restore operation. */
        fprintf(c->out,
            "cvcc_fn_%s:\n"
            " ld a,(cvcc_current_bank)\n"
            " push af\n"
            " ld a,%u\n"
            " call cvcc_select_bank\n"
            " call cvcc_body_%s\n"
            " pop af\n"
            " jp cvcc_select_bank\n", f->name, f->bank, f->name);
    }
}

static void zbank_payloads(Compiler *c) {
    fprintf(c->out,"CVCC_BANK_COUNT EQU %u\n",cartridge_banks);
    for(unsigned bank=2;bank<cartridge_banks;bank++) {
        int has_code=0;
        for(unsigned i=0;i<c->function_count;i++)if(c->functions[i].bank==bank)has_code=1;
        fprintf(c->out,"\n; Physical ROM bank %u, CPU window $8000-$BFFF\n ORG $8000\n",bank);
        if(has_code) {
            fprintf(c->out,"; CVCC_CODE_BANK %u\n",bank);
            for(unsigned i=0;i<c->function_count;i++) {
                Function *f=&c->functions[i];
                if(f->bank!=bank)continue;
                c->current_function=(int)i;
                fprintf(c->out,"cvcc_body_%s:\n",f->name);
                zstmt(c,f->body);
                fprintf(c->out," ret\n ASSERT $ <= $c000, bank %u overflow after %s\n",bank,f->name);
            }
            fprintf(c->out,"CVCC_BANK_%u_CODE_BYTES EQU $-$8000\n IF $ <= $c000\n defs $c000-$,$ff\n ENDIF\n",bank);
        } else {
            /* Project packaging replaces only these empty-data placeholders.
               Code banks and their labels remain in this assembly file. */
            fprintf(c->out,"; CVCC_DATA_BANK_%u\n defs 16384,$ff\n; CVCC_DATA_BANK_END_%u\n",bank,bank);
        }
    }
    c->current_function=-1;
}

/* CVCC's __bank(n) annotation. C11, no host-compiler extensions.
 * Blank annotations in the parser input without moving any byte or newline.
 * Tree-sitter still parses the function; diagnostics retain source positions. */
static void bank_tag_error(Compiler *c, size_t offset, const char *message) {
    unsigned row=1, column=1;
    for(size_t i=0;i<offset;i++) {
        if(c->source[i]=='\n') { row++; column=1; } else column++;
    }
    if(!c->failed)fprintf(stderr,"%s:%u:%u: error: %s\n",c->path,row,column,message);
    c->failed=1;
}

static size_t bank_skip_space(const char *s, size_t i) {
    for(;;) {
        if(isspace((unsigned char)s[i])) { i++; continue; }
        if(s[i]=='/' && s[i+1]=='/') {
            while(s[i] && s[i]!='\n')i++;
        } else if(s[i]=='/' && s[i+1]=='*') {
            i+=2;
            while(s[i] && !(s[i]=='*' && s[i+1]=='/'))i++;
            if(s[i])i+=2;
        } else return i;
    }
}

static int read_bank_tags(Compiler *c, char *parser_source) {
    const char *s=c->source;
    for(size_t i=0;s[i] && !c->failed;) {
        i=bank_skip_space(s,i);
        if(!s[i])break;
        if(s[i]=='"' || s[i]=='\'') {
            char quote=s[i++];
            while(s[i] && s[i]!=quote) {
                if(s[i]=='\\' && s[i+1])i++;
                i++;
            }
            if(s[i])i++;
            continue;
        }
        if(!isalpha((unsigned char)s[i]) && s[i]!='_') { i++; continue; }
        size_t start=i++;
        while(isalnum((unsigned char)s[i]) || s[i]=='_')i++;
        if(i-start!=6 || memcmp(s+start,"__bank",6))continue;
        if(!c->native || !cartridge->bank_register) {
            bank_tag_error(c,start,"__bank requires the native ASC16L or Sega 315-5208 backend");break;
        }
        size_t opening=bank_skip_space(s,i);
        if(s[opening]!='(') { bank_tag_error(c,start,"expected __bank(n), with a literal bank in 2..255");break; }
        size_t value=bank_skip_space(s,opening+1);
        char *end;
        errno=0;
        unsigned long bank=strtoul(s+value,&end,0);
        /* Match CVCC literals: decimal or hex, no sign, octal or suffix. */
        if(!isdigit((unsigned char)s[value]) || (s[value]=='0' && s[value+1]!='x' && s[value+1]!='X')
           || errno || end==s+value || bank<2 || bank>255) {
            bank_tag_error(c,start,"bank must be a decimal or hexadecimal literal in 2..255");break;
        }
        i=bank_skip_space(s,(size_t)(end-s));
        if(s[i]!=')') { bank_tag_error(c,start,"expected __bank(n), without expressions or extra arguments");break; }
        i++;
        if(c->bank_tag_count==128) { bank_tag_error(c,start,"too many bank annotations");break; }
        BankTag *tag=&c->bank_tags[c->bank_tag_count++];
        tag->start=start;tag->end=i;tag->bank=(unsigned)bank;
        for(size_t j=start;j<i;j++)if(parser_source[j]!='\n' && parser_source[j]!='\r')parser_source[j]=' ';
        if(bank>=cartridge_banks)cartridge_banks=(unsigned)bank+1;
    }
    return !c->failed;
}

static unsigned function_bank(Compiler *c, TSNode node) {
    size_t start=ts_node_start_byte(node);
    for(unsigned i=0;i<c->bank_tag_count;i++) {
        BankTag *tag=&c->bank_tags[i];
        if(!tag->used && tag->end<=start && bank_skip_space(c->source,tag->end)==start) {
            tag->used=1;
            return tag->bank;
        }
    }
    return 0; /* Untagged functions stay in fixed ROM. */
}

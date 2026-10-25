/* Original CVCC Z80 code generator. SPDX-License-Identifier: BSD-3-Clause.
 * Values use HL; expression spills use the machine stack. User arguments live
 * in static cells, populated only after all arguments have been evaluated.
 * The semantic pass rejects recursion before this generator runs.
 */
static unsigned zlabel;
static void zexpr(Compiler *,TSNode);
static void zstmt(Compiler *,TSNode);
static void zcall(Compiler *,TSNode);
static void zbyteexpr(Compiler *,TSNode);
static int zbytevalue(Compiler *,TSNode);

#include "backend_banks.h"
static void zname(Compiler *c,Symbol *s) {
    for(unsigned i=0;i<c->count;i++) if(s==&c->symbols[i]) { fprintf(c->out,"cvcc_var_%s",s->name); return; }
    fprintf(c->out,"cvcc_arg_%d_%s",c->current_function,s->name);
}
static unsigned zliteral(Compiler *c,TSNode n) {
    while(kind(n,"parenthesized_expression")) n=child(n,0);
    if(kind(n,"identifier")) { Symbol *s=lookup(c,n); if(s)n=s->value; }
    unsigned v=0; number(c,n,65535,&v); return v;
}
static Symbol *zaddress(Compiler *c,TSNode n) {
    Symbol *s=lookup(c,kind(n,"subscript_expression")?field(n,"argument"):n);
    if(!s)return NULL;
    if(s->array) {
        TSNode index=child(field(n,"indices"),0);
        if(kind(index,"number_literal")) {
            fputs(" ld hl,",c->out);zname(c,s);
            fprintf(c->out,"+%u\n",zliteral(c,index)*(s->word?2:1));return s;
        }
        if(s->constant && !s->word && s->size==256 && zbytevalue(c,index)) {
            zbyteexpr(c,index);fputs(" ld l,a\n ld h,high ",c->out);zname(c,s);fputc('\n',c->out);return s;
        }
        zexpr(c,index);
        if(s->word)fputs(" add hl,hl\n",c->out);
        fputs(" ld de,",c->out);zname(c,s);fputs("\n add hl,de\n",c->out);
    } else {fputs(" ld hl,",c->out);zname(c,s);fputc('\n',c->out);}
    return s;
}
static void zload(Compiler *c,Symbol *s) {
    fputs(s->word?" ld a,(hl)\n inc hl\n ld h,(hl)\n ld l,a\n":" ld l,(hl)\n ld h,0\n",c->out);
}
static void zstore(Compiler *c,Symbol *s) {
    /* Address in DE, value in HL. */
    fputs(" ld a,l\n ld (de),a\n",c->out);
    if(s->word)fputs(" inc de\n ld a,h\n ld (de),a\n",c->out);
}
static void zoperation(Compiler *c,TSNode op) {
    if(equals(c,op,"+")||equals(c,op,"+="))fputs(" add hl,de\n",c->out);
    else if(equals(c,op,"-")||equals(c,op,"-="))fputs(" or a\n sbc hl,de\n",c->out);
    else {
        const char *ins=(equals(c,op,"&")||equals(c,op,"&="))?"and":(equals(c,op,"|")||equals(c,op,"|="))?"or":"xor";
        fprintf(c->out," ld a,l\n %s e\n ld l,a\n ld a,h\n %s d\n ld h,a\n",ins,ins);
    }
}
static void zshift(Compiler *c,TSNode op,unsigned count) {
    int left=equals(c,op,"<<")||equals(c,op,"<<=");
    for(unsigned i=0;i<count;i++)fputs(left?" add hl,hl\n":" srl h\n rr l\n",c->out);
}
static void zexpr(Compiler *c,TSNode n) {
    if(c->failed)return;
    if(kind(n,"number_literal"))fprintf(c->out," ld hl,%u\n",zliteral(c,n));
    else if(kind(n,"parenthesized_expression"))zexpr(c,child(n,0));
    else if(kind(n,"identifier")||kind(n,"subscript_expression")) {
        Symbol *s=lookup(c,kind(n,"identifier")?n:field(n,"argument"));if(!s)return;
        if(s->constant&&!s->array)fprintf(c->out," ld hl,%u\n",zliteral(c,s->value));
        else if(!s->array) {
            if(s->word){fputs(" ld hl,(",c->out);zname(c,s);fputs(")\n",c->out);}
            else {fputs(" ld a,(",c->out);zname(c,s);fputs(")\n ld l,a\n ld h,0\n",c->out);}
        }else {zaddress(c,n);zload(c,s);}
    }else if(kind(n,"call_expression"))zcall(c,n);
    else if(kind(n,"unary_expression")) {
        zexpr(c,field(n,"argument"));
        if(equals(c,field(n,"operator"),"-"))fputs(" xor a\n sub l\n ld l,a\n ld a,0\n sbc a,h\n ld h,a\n",c->out);
        else fputs(" ld a,l\n cpl\n ld l,a\n ld a,h\n cpl\n ld h,a\n",c->out);
    }else if(kind(n,"binary_expression")) {
        TSNode op=field(n,"operator");zexpr(c,field(n,"left"));
        if(equals(c,op,"<<")||equals(c,op,">>")) {
            if(width(c,field(n,"left"))==8)fputs(" ld h,0\n",c->out);
            zshift(c,op,zliteral(c,field(n,"right")));
            if(width(c,field(n,"left"))==8)fputs(" ld h,0\n",c->out);
        }
        else {
            TSNode right=field(n,"right");
            if(kind(right,"number_literal"))fprintf(c->out," ld de,%u\n",zliteral(c,right));
            else {fputs(" push hl\n",c->out);zexpr(c,right);fputs(" ex de,hl\n pop hl\n",c->out);}
            zoperation(c,op);
        }
    }else error(c,n,"native Z80 expression not implemented: %s",ts_node_type(n));

}
static int zbytevalue(Compiler *c,TSNode n) {
    while(kind(n,"parenthesized_expression"))n=child(n,0);
    return (kind(n,"identifier")||kind(n,"subscript_expression")||kind(n,"call_expression")||kind(n,"number_literal")) && width(c,n)==8;
}
static void zbranch(Compiler *c,TSNode n,unsigned yes,unsigned no) {
    if(kind(n,"condition_clause")){zbranch(c,field(n,"value"),yes,no);return;}
    if(kind(n,"parenthesized_expression")){zbranch(c,child(n,0),yes,no);return;}
    TSNode op=field(n,"operator");
    if(equals(c,op,"!")){zbranch(c,field(n,"argument"),no,yes);return;}
    if(equals(c,op,"&&")||equals(c,op,"||")) {
        unsigned next=zlabel++;
        zbranch(c,field(n,"left"),equals(c,op,"&&")?next:yes,equals(c,op,"&&")?no:next);
        fprintf(c->out,"cvcc_L%u:\n",next);zbranch(c,field(n,"right"),yes,no);return;
    }
    const char *ops[]={"==","!=","<",">", "<=",">="};int comparison=-1;
    for(int i=0;i<6;i++)if(equals(c,op,ops[i]))comparison=i;
    if(comparison>=0) {
        TSNode left=field(n,"left"),right=field(n,"right");
        if(zbytevalue(c,left)&&zbytevalue(c,right)) {
            zbyteexpr(c,left);
            if(kind(right,"number_literal"))fprintf(c->out," cp %u\n",zliteral(c,right));
            else {fputs(" push af\n",c->out);zbyteexpr(c,right);fputs(" ld e,a\n pop af\n cp e\n",c->out);}
        }else {
            zexpr(c,left);fputs(" push hl\n",c->out);zexpr(c,right);
            fputs(" ex de,hl\n pop hl\n or a\n sbc hl,de\n",c->out);
        }
        if(comparison==3){fprintf(c->out," jp c,cvcc_L%u\n jp z,cvcc_L%u\n jp cvcc_L%u\n",no,no,yes);return;}
        if(comparison==4)fprintf(c->out," jp z,cvcc_L%u\n",yes);
        const char *cc=comparison==0?"z":comparison==1?"nz":comparison==5?"nc":"c";
        fprintf(c->out," jp %s,cvcc_L%u\n",cc,yes);
    }else {
        if(zbytevalue(c,n)){zbyteexpr(c,n);fputs(" or a\n",c->out);}
        else {zexpr(c,n);fputs(" ld a,h\n or l\n",c->out);}
        fprintf(c->out," jp nz,cvcc_L%u\n",yes);
    }
    fprintf(c->out," jp cvcc_L%u\n",no);
}
/* A byte destination permits arithmetic modulo 256 all the way down the
 * expression, except a right shift of a word. This avoids word spills in
 * sprite/VRAM hot paths while preserving the full-width expression ABI. */
static void zbyteexpr(Compiler *c,TSNode n) {
    if(kind(n,"parenthesized_expression")){zbyteexpr(c,child(n,0));return;}
    if(kind(n,"number_literal")){fprintf(c->out," ld a,%u\n",zliteral(c,n)&255);return;}
    if(kind(n,"identifier")) {
        Symbol *s=lookup(c,n);if(!s)return;
        if(s->constant)fprintf(c->out," ld a,%u\n",zliteral(c,s->value)&255);
        else {fputs(" ld a,(",c->out);zname(c,s);fputs(")\n",c->out);}
        return;
    }
    if(kind(n,"subscript_expression")) {
        Symbol *s=lookup(c,field(n,"argument"));if(!s)return;
        TSNode index=child(field(n,"indices"),0);
        if(kind(index,"number_literal")) {
            fputs(" ld a,(",c->out);zname(c,s);
            fprintf(c->out,"+%u)\n",zliteral(c,index)*(s->word?2:1));
        }else {zaddress(c,n);fputs(" ld a,(hl)\n",c->out);}
        return;
    }
    if(kind(n,"unary_expression")) {
        zbyteexpr(c,field(n,"argument"));
        fputs(equals(c,field(n,"operator"),"-")?" neg\n":" cpl\n",c->out);return;
    }
    if(kind(n,"binary_expression")) {
        TSNode op=field(n,"operator"),left=field(n,"left"),right=field(n,"right");
        if(equals(c,op,">>") && width(c,left)==16) {zexpr(c,n);fputs(" ld a,l\n",c->out);return;}
        zbyteexpr(c,left);
        if(equals(c,op,"<<")||equals(c,op,">>")) {
            for(unsigned i=0;i<zliteral(c,right);i++)fputs(equals(c,op,"<<")?" add a,a\n":" srl a\n",c->out);
        }else {
            const char *ins=equals(c,op,"+")?"add a,":equals(c,op,"-")?"sub ":equals(c,op,"&")?"and ":equals(c,op,"|")?"or ":"xor ";
            if(kind(right,"number_literal"))fprintf(c->out," %s%u\n",ins,zliteral(c,right)&255);
            else {fputs(" push af\n",c->out);zbyteexpr(c,right);fputs(" ld e,a\n pop af\n",c->out);fprintf(c->out," %se\n",ins);}
        }
        return;
    }
    zexpr(c,n);fputs(" ld a,l\n",c->out);
}
static void zeffect(Compiler *c,TSNode n) {
    if(ts_node_is_null(n))return;
    if(kind(n,"expression_statement")){zeffect(c,child(n,0));return;}
    if(kind(n,"call_expression")){zcall(c,n);return;}
    int update=kind(n,"update_expression");TSNode target=field(n,update?"argument":"left"),op=field(n,"operator"),rhs=field(n,"right");
    /* Scalar destinations have stable addresses: avoid spilling their address. */
    if(kind(target,"identifier")) {
        Symbol *s=lookup(c,target);if(!s)return;
        if(!s->word && equals(c,op,"=")) {
            zbyteexpr(c,rhs);fputs(" ld (",c->out);zname(c,s);fputs("),a\n",c->out);return;
        }
        if(!s->word && update) {
            fputs(" ld hl,",c->out);zname(c,s);
            fputs(equals(c,op,"++")?"\n inc (hl)\n":"\n dec (hl)\n",c->out);return;
        }
        if(equals(c,op,"="))zexpr(c,rhs);
        else {
            zexpr(c,target);
            if(update)fputs(equals(c,op,"++")?" inc hl\n":" dec hl\n",c->out);
            else if(equals(c,op,"<<=")||equals(c,op,">>="))zshift(c,op,zliteral(c,rhs));
            else {
                fputs(" push hl\n",c->out);zexpr(c,rhs);
                fputs(" ex de,hl\n pop hl\n",c->out);zoperation(c,op);
            }
        }
        if(!s->word)fputs(" ld a,l\n",c->out);
        fputs(" ld (",c->out);zname(c,s);fputs(s->word?"),hl\n":"),a\n",c->out);
        return;
    }
    if(kind(target,"subscript_expression") && equals(c,op,"=") && kind(child(field(target,"indices"),0),"number_literal")) {
        Symbol *s=lookup(c,field(target,"argument"));if(!s)return;
        if(s->word)zexpr(c,rhs);else zbyteexpr(c,rhs);
        fputs(" ld (",c->out);zname(c,s);
        fprintf(c->out,"+%u),%s\n",zliteral(c,child(field(target,"indices"),0))*(s->word?2:1),s->word?"hl":"a");return;
    }
    Symbol *s=zaddress(c,target);if(!s)return;
    if(!s->word && update) {fputs(equals(c,op,"++")?" inc (hl)\n":" dec (hl)\n",c->out);return;}
    if(!s->word && equals(c,op,"=")) {
        fputs(" push hl\n",c->out);zbyteexpr(c,rhs);fputs(" pop hl\n ld (hl),a\n",c->out);return;
    }
    fputs(" push hl\n",c->out);
    if(update || !equals(c,op,"=")) {
        zload(c,s);
        if(update)fputs(equals(c,op,"++")?" inc hl\n":" dec hl\n",c->out);
        else if(equals(c,op,"<<=")||equals(c,op,">>="))zshift(c,op,zliteral(c,rhs));
        else {fputs(" push hl\n",c->out);zexpr(c,rhs);fputs(" ex de,hl\n pop hl\n",c->out);zoperation(c,op);}
    }else zexpr(c,rhs);
    fputs(" pop de\n",c->out);zstore(c,s);
}
static void zcall(Compiler *c,TSNode n) {
    TSNode fn=field(n,"function"),args=field(n,"arguments");unsigned count=children(args);
    int id=-1;
    for(unsigned i=0;i<c->function_count;i++) if(equals(c,fn,c->functions[i].name)) id=(int)i;
    if(id>=0) {
        for(unsigned i=0;i<count;i++){zexpr(c,child(args,i));fputs(" push hl\n",c->out);}
        for(unsigned i=count;i>0;i--){
            int saved=c->current_function;c->current_function=id;
            fputs(" pop hl\n ld de,",c->out);zname(c,&c->functions[id].params[i-1]);fputc('\n',c->out);
            zstore(c,&c->functions[id].params[i-1]);c->current_function=saved;
        }
        fprintf(c->out," call cvcc_fn_%s\n",c->functions[id].name);return;
    }
    if(equals(c,fn,"waitFrame")||equals(c,fn,"waitVBlank")) {
        if(count)zexpr(c,child(args,0));else fputs(" ld hl,1\n",c->out);
        fputs(" call cvcc_wait\n",c->out);return;
    }
    if(equals(c,fn,"vramPoke")) {
        TSNode value=child(args,1);
        zexpr(c,child(args,0));
        int simple=kind(value,"number_literal")||kind(value,"identifier");
        if(!simple)fputs(" push hl\n",c->out);
        zbyteexpr(c,value);
        if(!simple)fputs(" pop hl\n",c->out);
        fputs(" call cvcc_poke_regs\n",c->out);return;
    }
    if(equals(c,fn,"sprite")) {
        int simple=1;
        for(unsigned i=0;i<5;i++)if(!kind(child(args,i),"identifier")&&!kind(child(args,i),"number_literal"))simple=0;
        if(simple) {
            const char *reg[]={"a","b","c","d","e"};
            for(unsigned i=1;i<5;i++) {
                TSNode arg=child(args,i);
                if(kind(arg,"number_literal"))fprintf(c->out," ld %s,%u\n",reg[i],zliteral(c,arg)&255);
                else {zbyteexpr(c,arg);fprintf(c->out," ld %s,a\n",reg[i]);}
            }
            zbyteexpr(c,child(args,0));fputs(" call cvcc_sprite_regs\n",c->out);return;
        }
        for(unsigned i=0;i<5;i++){zbyteexpr(c,child(args,i));fputs(" push af\n",c->out);}
        fputs(" pop af\n ld e,a\n pop af\n ld d,a\n pop af\n ld c,a\n pop af\n ld b,a\n pop af\n call cvcc_sprite_regs\n",c->out);return;
    }
    if(equals(c,fn,"bankRead")) {
        zexpr(c,child(args,1));
        fprintf(c->out," ld a,%u\n call cvcc_bank_read\n",zliteral(c,child(args,0)));return;
    }
    if(equals(c,fn,"vramWriteBank")) {
        zexpr(c,child(args,0));
        fprintf(c->out," ld a,%u\n ld de,%u\n ld bc,%u\n call cvcc_vram_write_bank\n",zliteral(c,child(args,1)),0x8000+zliteral(c,child(args,2)),zliteral(c,child(args,3)));return;
    }
    if(equals(c,fn,"controllerRead")) {
        fprintf(c->out," ld a,%u\n call cvcc_controller_port\n",zliteral(c,child(args,0)));return;
    }
    if(equals(c,fn,"vdpWrite")) {
        zbyteexpr(c,child(args,1));fprintf(c->out," ld d,a\n ld e,%u\n call cvcc_vdp_regs\n",zliteral(c,child(args,0)));return;
    }
    if(equals(c,fn,"sound")||equals(c,fn,"soundVolume")) {
        if(count==3){zexpr(c,child(args,1));fputs(" push hl\n",c->out);}
        zbyteexpr(c,child(args,count-1));
        if(count==3)fputs(" ld e,a\n pop hl\n",c->out);
        fprintf(c->out," ld c,%u\n call %s\n",zliteral(c,child(args,0)),count==3?"cvcc_sound_regs":"cvcc_volume_regs");return;
    }
    if(equals(c,fn,"printAt")) {
        char str[256];text(c,child(args,1),str,sizeof str);unsigned label=zlabel++;
        fprintf(c->out," ld hl,%u\n ld de,cvcc_string%u\n ld bc,%zu\n call cvcc_print\n jp cvcc_L%u\ncvcc_string%u:\n db %s\ncvcc_L%u:\n",zliteral(c,child(args,0)),label,strlen(str)-2,label,label,str,label);return;
    }
    if(equals(c,fn,"defineSprite")) {
        Symbol *s=lookup(c,child(args,2));if(!s)return;
        fprintf(c->out," ld hl,%u\n ld de,",0x3800+32*zliteral(c,child(args,0)));zname(c,s);
        fprintf(c->out,"\n ld bc,%u\n call cvcc_vram_write\n",32*zliteral(c,child(args,1)));return;
    }
    if(equals(c,fn,"vramWrite")||equals(c,fn,"vramRead")) {
        zexpr(c,child(args,0));fputs(" ld de,",c->out);Symbol *s=lookup(c,child(args,1));if(!s)return;zname(c,s);
        fprintf(c->out,"+%u\n ld bc,%u\n call cvcc_vram_%s\n",zliteral(c,child(args,2)),zliteral(c,child(args,3)),equals(c,fn,"vramRead")?"read":"write");return;
    }
    if(equals(c,fn,"videoMode")) {
        fprintf(c->out," ld a,%u\n call cvcc_mode\n",zliteral(c,child(args,0)));return;
    }
    if(equals(c,fn,"spriteFlicker")) {
        fprintf(c->out," ld a,%u\n ld (cvcc_flicker_enabled),a\n",zliteral(c,child(args,0)));return;
    }
    const char *names[]={"clearScreen","screenEnable","screenDisable"};
    const char *labels[]={"clear","screen_on","screen_off"};
    for(unsigned i=0;i<sizeof names/sizeof names[0];i++)if(equals(c,fn,names[i])) {
        fprintf(c->out," call cvcc_%s\n",labels[i]);return;
    }
    error(c,n,"native builtin not implemented");
}
static void zstmt(Compiler *c,TSNode n) {
    if(c->failed)return;
    if(kind(n,"compound_statement")){for(unsigned i=0;i<children(n);i++)zstmt(c,child(n,i));}
    else if(kind(n,"expression_statement"))zeffect(c,child(n,0));
    else if(kind(n,"if_statement")) {
        unsigned yes=zlabel++,no=zlabel++,end=zlabel++;
        zbranch(c,field(n,"condition"),yes,no);fprintf(c->out,"cvcc_L%u:\n",yes);zstmt(c,field(n,"consequence"));
        fprintf(c->out," jp cvcc_L%u\ncvcc_L%u:\n",end,no);
        TSNode alt=field(n,"alternative");if(!ts_node_is_null(alt))zstmt(c,child(alt,0));
        fprintf(c->out,"cvcc_L%u:\n",end);
    }else if(kind(n,"while_statement")||kind(n,"for_statement")||kind(n,"do_statement")) {
        unsigned start=zlabel++,body=zlabel++,cont=zlabel++,end=zlabel++;
        int counted=kind(n,"for_statement"),post=kind(n,"do_statement");
        c->loop_ids[c->loop_depth++]=cont;c->break_ids[c->break_depth++]=end;
        if(counted)zeffect(c,field(n,"initializer"));
        fprintf(c->out,"cvcc_L%u:\n",start);
        TSNode cond=field(n,"condition");
        if(!post&&!ts_node_is_null(cond))zbranch(c,cond,body,end);
        fprintf(c->out,"cvcc_L%u:\n",body);zstmt(c,field(n,"body"));fprintf(c->out,"cvcc_L%u:\n",cont);
        if(counted)zeffect(c,field(n,"update"));
        if(post)zbranch(c,cond,start,end);else fprintf(c->out," jp cvcc_L%u\n",start);
        fprintf(c->out,"cvcc_L%u:\n",end);c->loop_depth--;c->break_depth--;
    }else if(kind(n,"switch_statement")) {
        TSNode body=field(n,"body");unsigned end=zlabel++,count=children(body),labels[256],fallback=end;
        for(unsigned i=0;i<count;i++){labels[i]=zlabel++;if(ts_node_is_null(field(child(body,i),"value")))fallback=labels[i];}
        zexpr(c,field(field(n,"condition"),"value"));fputs(" ld b,h\n ld c,l\n",c->out);
        for(unsigned i=0;i<count;i++) {
            TSNode v=field(child(body,i),"value");if(ts_node_is_null(v))continue;
            fprintf(c->out," ld h,b\n ld l,c\n ld de,%u\n or a\n sbc hl,de\n jp z,cvcc_L%u\n",zliteral(c,v),labels[i]);
        }
        fprintf(c->out," jp cvcc_L%u\n",fallback);c->break_ids[c->break_depth++]=end;
        for(unsigned i=0;i<count;i++) {
            TSNode item=child(body,i),v=field(item,"value");fprintf(c->out,"cvcc_L%u:\n",labels[i]);
            for(unsigned j=0;j<children(item);j++)if(ts_node_is_null(v)||!ts_node_eq(child(item,j),v))zstmt(c,child(item,j));
        }
        c->break_depth--;fprintf(c->out,"cvcc_L%u:\n",end);
    }else if(kind(n,"break_statement"))fprintf(c->out," jp cvcc_L%u\n",c->break_ids[c->break_depth-1]);
    else if(kind(n,"continue_statement"))fprintf(c->out," jp cvcc_L%u\n",c->loop_ids[c->loop_depth-1]);
    else if(kind(n,"return_statement")){if(children(n)) { zexpr(c,child(n,0)); if(c->current_function>=0 && c->functions[c->current_function].result==0)fputs(" ld h,0\n",c->out); } fputs(" ret\n",c->out);}
    else error(c,n,"native statement not implemented: %s",ts_node_type(n));
}
/* Conservative peak stack accounting: argument snapshots, expression spills,
 * return addresses and the longest path through the acyclic user call graph.
 * Runtime/IRQ overhead is added separately; loops do not grow the stack. */
static unsigned zstack_function[128];
static unsigned zstack(Compiler *c,TSNode n) {
    if(ts_node_is_null(n))return 0;
    unsigned peak=0;
    if(kind(n,"call_expression")) {
        TSNode args=field(n,"arguments");
        for(unsigned i=0;i<children(args);i++) {
            unsigned need=2*i+zstack(c,child(args,i));if(need>peak)peak=need;
        }
        if(2*children(args)>peak)peak=2*children(args);
        for(unsigned i=0;i<c->function_count;i++)if(equals(c,field(n,"function"),c->functions[i].name)) {
            if(!zstack_function[i])zstack_function[i]=(c->functions[i].bank?5:1)+zstack(c,c->functions[i].body);
            unsigned need=1+zstack_function[i];if(need>peak)peak=need;
        }
        return peak;
    }
    if(kind(n,"binary_expression")) {
        unsigned left=zstack(c,field(n,"left")),right=2+zstack(c,field(n,"right"));
        return left>right?left:right;
    }
    if(kind(n,"assignment_expression")) {
        unsigned left=zstack(c,field(n,"left")),right=4+zstack(c,field(n,"right"));
        return left>right?left:right;
    }
    for(unsigned i=0;i<children(n);i++){unsigned need=zstack(c,child(n,i));if(need>peak)peak=need;}
    return peak;
}
static int compile_z80(Compiler *c) {
    /* Track allocation arithmetically: sjasmplus wraps ORG at $10000.
       A wrapped RAM_END must never make an overflowing program look small. */
    unsigned ram_bytes=4+8+128+(cartridge->bank_register?1u:0u); /* counters/flags, VDP registers, sprite shadow */
    for(unsigned i=0;i<c->count;i++) {
        Symbol *s=&c->symbols[i];
        if(!s->constant)ram_bytes+=(unsigned)(s->array?s->size:1)*(s->word?2u:1u);
    }
    for(unsigned i=0;i<c->function_count;i++)
        for(unsigned j=0;j<c->functions[i].arity;j++)ram_bytes+=c->functions[i].params[j].word?2u:1u;
    zlabel=0;c->loop_depth=c->break_depth=0;c->current_function=-1;
    memset(zstack_function,0,sizeof zstack_function);
    unsigned setup_stack=zstack(c,c->setup),loop_stack=zstack(c,c->loop);
    unsigned stack_bytes=32+(setup_stack>loop_stack?setup_stack:loop_stack);
    if(stack_bytes<256)stack_bytes=256;
    if(cartridge->bank_register)fprintf(c->out," DEFINE CVCC_BANKED 1\nCVCC_BANK_REGISTER EQU $%x\n",cartridge->bank_register);
    fprintf(c->out,"; Cartridge: %s\nSTACK_TOP EQU $%x\n",cartridge->id,cartridge_ram_end() & 65535);
    fputs("; Original CVCC backend, no CVBasic code or runtime.\n OUTPUT \"program.sg\"\n DEVICE NOSLOT64K\n ORG 0\n jp cvcc_start\n defs $38-$,0\n jp cvcc_irq\n defs $66-$,0\n retn\n INCLUDE \"sg1000.asm\"\n IFDEF CVCC_BANKED\n INCLUDE \"banking.asm\"\n ENDIF\ncvcc_setup:\n",c->out);
    for(unsigned i=0;i<c->count;i++) {
        Symbol *s=&c->symbols[i];if(!s->initialized||s->constant)continue;
        for(int j=0;j<(s->array?s->size:1);j++) {
            fprintf(c->out," ld hl,%u\n ld de,",zliteral(c,s->array?child(s->value,(unsigned)j):s->value));zname(c,s);
            fprintf(c->out,"+%d\n",j*(s->word?2:1));zstore(c,s);
        }
    }
    zstmt(c,c->setup);fputs(" ret\ncvcc_loop:\n",c->out);zstmt(c,c->loop);fputs(" ret\n",c->out);
    zbank_thunks(c);
    for(unsigned i=0;i<c->function_count;i++) {
        if(c->functions[i].bank)continue;
        c->current_function=(int)i;fprintf(c->out,"cvcc_fn_%s:\n",c->functions[i].name);zstmt(c,c->functions[i].body);fputs(" ret\n",c->out);
    }
    c->current_function=-1;
    for(unsigned i=0;i<c->count;i++) {
        Symbol *s=&c->symbols[i];if(!s->constant||!s->array)continue;
        if(!s->word && s->size==256)fputs(" ALIGN 256,$ff\n",c->out);
        zname(c,s);fputs(":\n",c->out);
        for(int j=0;j<s->size;j++)fprintf(c->out," %s %u\n",s->word?"dw":"db",zliteral(c,child(s->value,(unsigned)j)));
    }
    fprintf(c->out,"ROM_END:\n ASSERT ROM_END <= $%x ; cartridge fixed ROM capacity\n",cartridge->rom_limit);
    if(cartridge->bank_register)fputs(" defs 32768-$,$ff\n",c->out);
    else fputs(" IF $ <= 8192\n defs 8192-$,$ff\n ELSEIF $ <= 16384\n defs 16384-$,$ff\n ELSEIF $ <= 32768\n defs 32768-$,$ff\n ELSE\n defs 49152-$,$ff\n ENDIF\n",c->out);
    fprintf(c->out,"RAM_START EQU $%x\n ORG RAM_START\n",cartridge->ram_start);
    for(unsigned i=0;i<c->count;i++) {
        Symbol *s=&c->symbols[i];if(s->constant)continue;
        zname(c,s);fprintf(c->out," EQU $\n ORG $+%d\n",(s->array?s->size:1)*(s->word?2:1));
    }
    for(unsigned i=0;i<c->function_count;i++) {
        c->current_function=(int)i;
        for(unsigned j=0;j<c->functions[i].arity;j++){Symbol *s=&c->functions[i].params[j];zname(c,s);fprintf(c->out," EQU $\n ORG $+%d\n",s->word?2:1);}
    }
    fputs("cvcc_vblank EQU $\n ORG $+1\ncvcc_video_mode EQU $\n ORG $+1\ncvcc_flicker_enabled EQU $\n ORG $+1\ncvcc_sprite_rotation EQU $\n ORG $+1\ncvcc_registers EQU $\n ORG $+8\ncvcc_sprites EQU $\n ORG $+128\n",c->out);
    if(cartridge->bank_register)fputs("cvcc_current_bank EQU $\n ORG $+1\n",c->out);
    fprintf(c->out,"RAM_END EQU RAM_START+%u\n",ram_bytes);
    fprintf(c->out,"STACK_BYTES EQU %u\nRAM_LIMIT EQU $%x\n ASSERT RAM_END+STACK_BYTES <= RAM_LIMIT ; globals, runtime and worst-case stack must fit physical RAM\n",stack_bytes,cartridge_ram_end());
    if(cartridge->bank_register)zbank_payloads(c);
    return !c->failed;
}

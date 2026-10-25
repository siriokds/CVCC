/* CVCC experimental frontend. SPDX-License-Identifier: BSD-3-Clause */
#include <tree_sitter/api.h>
#include <ctype.h>
#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern const TSLanguage *tree_sitter_cpp(void);

typedef struct { char name[64]; int array, size, initialized, word, constant; TSNode value; } Symbol;
typedef struct { char name[64]; TSNode body, node; } Function;
typedef struct {
    const char *path;
    char *source;
    FILE *out;
    Symbol symbols[256];
    unsigned count;
    TSNode setup, loop;
    Function functions[128];
    unsigned function_count;
    unsigned char calls[128][128], visited[128];
    unsigned loop_ids[64], loop_depth, next_loop, next_bool;
    int current_function, wait_counter_declared, failed;
} Compiler;

static int kind(TSNode n, const char *s) { return !ts_node_is_null(n) && !strcmp(ts_node_type(n), s); }
static TSNode field(TSNode n, const char *s) { return ts_node_child_by_field_name(n, s, (uint32_t)strlen(s)); }
static void error(Compiler *c, TSNode n, const char *fmt, ...) {
    if (c->failed) return;
    TSPoint p = ts_node_start_point(n), q = ts_node_end_point(n);
    fprintf(stderr, "%s:%u:%u: error: ", c->path, p.row+1, p.column+1);
    va_list ap; va_start(ap, fmt); vfprintf(stderr, fmt, ap); va_end(ap);
    fprintf(stderr, " [through %u:%u]\n", q.row+1, q.column+1);
    c->failed = 1;
}
static int text(Compiler *c, TSNode n, char *dst, size_t cap) {
    size_t a = ts_node_start_byte(n), b = ts_node_end_byte(n);
    if (ts_node_is_null(n) || b-a >= cap) { error(c,n,"missing or overlong token"); return 0; }
    memcpy(dst,c->source+a,b-a); dst[b-a]=0; return 1;
}
static int equals(Compiler *c, TSNode n, const char *s) {
    return !ts_node_is_null(n) && ts_node_end_byte(n)-ts_node_start_byte(n)==strlen(s)
        && !memcmp(c->source+ts_node_start_byte(n),s,strlen(s));
}
static unsigned children(TSNode n) {
    unsigned count=0;
    for (unsigned i=0;i<ts_node_named_child_count(n);i++) if (!kind(ts_node_named_child(n,i),"comment")) count++;
    return count;
}
static TSNode child(TSNode n,unsigned index) {
    for (unsigned i=0;i<ts_node_named_child_count(n);i++) {
        TSNode k=ts_node_named_child(n,i);
        if (!kind(k,"comment") && index--==0) return k;
    }
    return (TSNode){0};
}
static int identifier(Compiler *c,TSNode n,char *name) {
    if (!kind(n,"identifier") || !text(c,n,name,64)) { error(c,n,"expected an identifier"); return 0; }
    /* ASCII names are deliberately narrower than C++, and reserve runtime names. */
    if (!isalpha((unsigned char)name[0]) || !strncmp(name,"cvcc",4)) { error(c,n,"identifier must start with an ASCII letter; cvcc prefix is reserved"); return 0; }
    for (char *p=name;*p;p++) if ((unsigned char)*p>127 || !(isalnum((unsigned char)*p)||*p=='_')) { error(c,n,"unsupported identifier"); return 0; }
    return 1;
}
static Symbol *lookup(Compiler *c,TSNode n) {
    char name[64]; if (!identifier(c,n,name)) return NULL;
    for (unsigned i=0;i<c->count;i++) if (!strcmp(name,c->symbols[i].name)) return &c->symbols[i];
    error(c,n,"undeclared identifier '%s'",name); return NULL;
}
static int number(Compiler *c,TSNode n,unsigned max,unsigned *result) {
    char s[64];
    if (!kind(n,"number_literal") || !text(c,n,s,sizeof s)) { error(c,n,"expected an unsigned integer literal"); return 0; }
    /* Decimal and hexadecimal only; reject octal ambiguity, suffixes, floats. */
    int base=10;
    if (s[0]=='0' && (s[1]=='x'||s[1]=='X')) base=16;
    else if (s[0]=='0' && s[1]) { error(c,n,"use decimal without leading zeros, or hexadecimal"); return 0; }
    char *end; errno=0; unsigned long v=strtoul(s,&end,base);
    if (errno || end==s || *end || v>max) { error(c,n,"integer literal must be in 0..%u",max); return 0; }
    *result=(unsigned)v; return 1;
}
static void validate_tree(Compiler *c,TSNode n,unsigned depth) {
    if (depth>128) { error(c,n,"syntax nesting exceeds 128"); return; }
    if (ts_node_is_error(n)||ts_node_is_missing(n)) { error(c,n,"invalid C++ syntax (%s)",ts_node_type(n)); return; }
    for (unsigned i=0;i<ts_node_child_count(n)&&!c->failed;i++) validate_tree(c,ts_node_child(n,i),depth+1);
}
static void declare(Compiler *c,TSNode n) {
    TSNode type=field(n,"type"), decl=field(n,"declarator"), val={0}; int constant=0;
    int word=equals(c,type,"uint16_t");
    if (!word && !equals(c,type,"uint8_t")) { error(c,type,"expected uint8_t or uint16_t"); return; }
    for (unsigned i=0;i<children(n);i++) {
        TSNode k=child(n,i);
        if (ts_node_eq(k,type)||ts_node_eq(k,decl)) continue;
        if (kind(k,"type_qualifier")&&equals(c,k,"const")&&!constant) constant=1;
        else { error(c,k,"unsupported declaration qualifier or multiple declarators"); return; }
    }
    if (kind(decl,"init_declarator")) { val=field(decl,"value"); decl=field(decl,"declarator"); }
    int array=kind(decl,"array_declarator"); TSNode name_node=array?field(decl,"declarator"):decl;
    char name[64]; if (!identifier(c,name_node,name)) return;
    const char *reserved[]={"setup","loop","waitFrame","waitVBlank","clearScreen","printAt","defineSprite","sprite"};
    for(unsigned i=0;i<sizeof reserved/sizeof reserved[0];i++) if(!strcmp(name,reserved[i])) {
        error(c,n,"reserved entry point or builtin name"); return;
    }
    for (unsigned i=0;i<c->count;i++) if (!strcmp(name,c->symbols[i].name)) { error(c,n,"duplicate declaration '%s'",name); return; }
    if (c->count==256) { error(c,n,"too many global symbols (maximum 256)"); return; }
    unsigned size=0, max=word?65535:255;
    if (array) {
        if (children(decl)!=2 || !number(c,field(decl,"size"),word?4096:8192,&size) || !size) { error(c,n,"arrays require an explicit nonzero size (maximum 8192 bytes)"); return; }
        if (constant && ts_node_is_null(val)) { error(c,n,"ROM arrays require an initializer"); return; }
        if (!ts_node_is_null(val)) {
            if (!kind(val,"initializer_list") || children(val)!=size) { error(c,n,"array initializer must contain exactly %u elements",size); return; }
            for (unsigned i=0;i<size;i++) { unsigned value; if (!number(c,child(val,i),max,&value)) return; }
        }
    } else {
        if (constant && ts_node_is_null(val)) { error(c,n,"constants require an initializer"); return; }
        if (!ts_node_is_null(val)) { unsigned value; if (!number(c,val,max,&value)) return; }
    }
    Symbol *s=&c->symbols[c->count++];
    strcpy(s->name,name); s->array=array; s->size=(int)size; s->value=val;
    s->initialized=!ts_node_is_null(val); s->word=word; s->constant=constant;
}
static void function(Compiler *c,TSNode n) {
    TSNode d=field(n,"declarator"), type=field(n,"type"), body=field(n,"body");
    if (!equals(c,type,"void") || !kind(d,"function_declarator") || !kind(body,"compound_statement") || children(n)!=3) {
        error(c,n,"functions must return void and have a body"); return;
    }
    if (children(d)!=2 || children(field(d,"parameters"))!=0) { error(c,d,"functions must have empty parameter lists and no qualifiers"); return; }
    TSNode name=field(d,"declarator"); TSNode *slot=NULL;
    if (equals(c,name,"setup")) slot=&c->setup;
    else if (equals(c,name,"loop")) slot=&c->loop;
    if (slot) {
        if (!ts_node_is_null(*slot)) { error(c,name,"duplicate entry point"); return; }
        *slot=body; return;
    }
    char id[64]; if (!identifier(c,name,id)) return;
    const char *reserved[]={"waitFrame","waitVBlank","clearScreen","printAt","defineSprite","sprite"};
    for(unsigned i=0;i<sizeof reserved/sizeof reserved[0];i++) if(!strcmp(id,reserved[i])) { error(c,name,"reserved builtin name"); return; }
    for(unsigned i=0;i<c->function_count;i++) if(!strcmp(id,c->functions[i].name)) { error(c,name,"duplicate function"); return; }
    if(c->function_count==128) { error(c,name,"too many functions (maximum 128)"); return; }
    Function *f=&c->functions[c->function_count++]; strcpy(f->name,id); f->body=body; f->node=n;
}
static void symbol_name(Compiler *c,Symbol *s) {
    fprintf(c->out,"%s%c%u",s->word?"#":"",s->constant?(s->array?'d':'k'):'v',(unsigned)(s-c->symbols));
}
static void expression(Compiler *c,TSNode n);
static Symbol *access(Compiler *c,TSNode n,int writing) {
    int indexed=kind(n,"subscript_expression");
    Symbol *s=lookup(c,indexed?field(n,"argument"):n); if(!s) return NULL;
    if(writing && s->constant) { error(c,n,"cannot assign to const data"); return NULL; }
    if(indexed!=s->array) { error(c,n,"arrays require exactly one index; scalars cannot be indexed"); return NULL; }
    TSNode index={0};
    if(indexed) {
        TSNode indices=field(n,"indices");
        if(children(indices)!=1) { error(c,n,"arrays require exactly one index"); return NULL; }
        index=child(indices,0);
        if(kind(index,"number_literal")) {
            unsigned value; if(!number(c,index,65535,&value)) return NULL;
            if(value>=(unsigned)s->size) { error(c,index,"array index outside 0..%d",s->size-1); return NULL; }
        }
    }
    symbol_name(c,s);
    if(indexed) { fputc('(',c->out); expression(c,index); fputc(')',c->out); }
    return s;
}
/* CVCC integers retain byte/word width rather than C integer promotions. */
static unsigned width(Compiler *c,TSNode n) {
    if(kind(n,"identifier") || kind(n,"subscript_expression")) {
        Symbol *s=lookup(c,kind(n,"identifier")?n:field(n,"argument"));
        return s && s->word?16:8;
    }
    if(kind(n,"number_literal")) { unsigned v=0; number(c,n,65535,&v); return v>255?16:8; }
    if(kind(n,"parenthesized_expression")) return width(c,child(n,0));
    if(kind(n,"unary_expression")) return width(c,field(n,"argument"));
    if(kind(n,"binary_expression")) {
        unsigned left=width(c,field(n,"left"));
        if(equals(c,field(n,"operator"),"<<")||equals(c,field(n,"operator"),">>")) return left;
        unsigned right=width(c,field(n,"right")); return left>right?left:right;
    }
    error(c,n,"unsupported shift operand"); return 8;
}
static void shift(Compiler *c,TSNode left,TSNode right,int to_left) {
    unsigned bits=width(c,left), count=0;
    while(kind(right,"parenthesized_expression")) right=child(right,0);
    if(kind(right,"identifier")) {
        Symbol *s=lookup(c,right);
        if(!s) return;
        if(!s->constant || s->array) { error(c,right,"shift count must be a literal or scalar const"); return; }
        if(!number(c,s->value,65535,&count)) return;
    } else if(!number(c,right,65535,&count)) return;
    if(count>=bits) { error(c,right,"shift count must be in 0..%u for this operand",bits-1); return; }
    // Mask before shifting to preserve width even when the backend widens arithmetic.
    fputs("(((",c->out); expression(c,left);
    fprintf(c->out," AND %u) %c %u) AND %u)",bits==8?255:65535,to_left?'*':'/',1u<<count,bits==8?255:65535);
}
static void expression(Compiler *c,TSNode n) {
    if (c->failed) return;
    if (kind(n,"number_literal")) { unsigned v; if (number(c,n,65535,&v)) fprintf(c->out,"%u",v); }
    else if (kind(n,"identifier") || kind(n,"subscript_expression")) access(c,n,0);
    else if (kind(n,"parenthesized_expression") && children(n)==1) {
        fputc('(',c->out); expression(c,child(n,0)); fputc(')',c->out);
    } else if (kind(n,"binary_expression")) {
        TSNode op=field(n,"operator");
        if(equals(c,op,"<<")||equals(c,op,">>")) { shift(c,field(n,"left"),field(n,"right"),equals(c,op,"<<")); return; }
        const char *ops[]={"+","-","&","|","^"};
        const char *basic[]={"+","-","AND","OR","XOR"};
        const char *mapped=NULL;
        for(unsigned i=0;i<5;i++) if(equals(c,op,ops[i])) mapped=basic[i];
        if(!mapped) { error(c,op,"unsupported integer operator"); return; }
        fputc('(',c->out); expression(c,field(n,"left"));
        fprintf(c->out," %s ",mapped); expression(c,field(n,"right")); fputc(')',c->out);
    } else if (kind(n,"unary_expression") && (equals(c,field(n,"operator"),"-") || equals(c,field(n,"operator"),"~"))) {
        int complement=equals(c,field(n,"operator"),"~");
        fputs(complement?"(NOT ":"-",c->out);
        expression(c,field(n,"argument")); if(complement) fputc(')',c->out);
    } else error(c,n,"unsupported integer expression '%s'",ts_node_type(n));
}

static void condition(Compiler *c,TSNode n) {
    if (kind(n,"condition_clause")) {
        if (children(n)!=1) { error(c,n,"declarations/initializers in conditions are unsupported"); return; }
        n=field(n,"value");
    }
    if (kind(n,"parenthesized_expression")) { condition(c,child(n,0)); return; }
    if (kind(n,"binary_expression")) {
        const char *ops[]={"==","!=","<",">","<=",">="};
        const char *basic[]={"=","<>","<",">","<=",">="};
        for (unsigned i=0;i<6;i++) if (equals(c,field(n,"operator"),ops[i])) {
            expression(c,field(n,"left")); fprintf(c->out," %s ",basic[i]); expression(c,field(n,"right")); return;
        }
    }
    expression(c,n);
}
static int logical(Compiler *c,TSNode n) {
    if(ts_node_is_null(n)) return 0;
    if(equals(c,field(n,"operator"),"&&") || equals(c,field(n,"operator"),"||") || equals(c,field(n,"operator"),"!")) return 1;
    for(unsigned i=0;i<children(n);i++) if(logical(c,child(n,i))) return 1;
    return 0;
}
/* Emit branches, not BASIC AND/OR: the right side must be skipped at runtime. */
static void branch(Compiler *c,TSNode n,unsigned yes,unsigned no) {
    if(c->failed) return;
    if(kind(n,"condition_clause")) {
        if(children(n)!=1) { error(c,n,"declarations/initializers in conditions are unsupported"); return; }
        n=field(n,"value");
    }
    if(kind(n,"parenthesized_expression")) { branch(c,child(n,0),yes,no); return; }
    TSNode op=field(n,"operator");
    if(kind(n,"unary_expression") && equals(c,op,"!")) { branch(c,field(n,"argument"),no,yes); return; }
    if(kind(n,"binary_expression") && (equals(c,op,"&&") || equals(c,op,"||"))) {
        unsigned next=c->next_bool++;
        if(equals(c,op,"&&")) branch(c,field(n,"left"),next,no);
        else branch(c,field(n,"left"),yes,next);
        fprintf(c->out,"cvcc_bool%u:\n",next);
        branch(c,field(n,"right"),yes,no); return;
    }
    fputs("IF ",c->out); condition(c,n);
    fprintf(c->out," THEN GOTO cvcc_bool%u\nGOTO cvcc_bool%u\n",yes,no);
}
static void literal_string(Compiler *c,TSNode n) {
    char s[256]; if (!kind(n,"string_literal")||!text(c,n,s,sizeof s)) { error(c,n,"expected a plain string literal"); return; }
    size_t length=strlen(s);
    if (length<2||s[0]!='"'||s[length-1]!='"') { error(c,n,"string prefixes are unsupported"); return; }
    for (size_t i=1;i+1<length;i++) if ((unsigned char)s[i]<32 || (unsigned char)s[i]>126 || s[i]=='\\' || s[i]=='"') {
        error(c,n,"strings must be printable ASCII without escapes"); return;
    }
    fputs(s,c->out);
}
static void builtin(Compiler *c,TSNode n) {
    TSNode fn=field(n,"function"), args=field(n,"arguments"); unsigned count=children(args);
    if (equals(c,fn,"waitVBlank") || equals(c,fn,"waitFrame")) {
        if(count>1 || (equals(c,fn,"waitFrame") && count)) { error(c,args,"waitVBlank expects zero or one argument; waitFrame expects none"); return; }
        if(!count) { fputs("WAIT\n",c->out); return; }
        TSNode amount=child(args,0);
        if(kind(amount,"number_literal")) {
            unsigned n; if(!number(c,amount,65535,&n)) return;
            if(n<=1) { if(n) fputs("WAIT\n",c->out); return; }
        }
        // Snapshot the count once. No callbacks/interrupt user code can reenter
        // this scratch counter in the currently supported frontend.
        if(!c->wait_counter_declared) {
            fputs("DIM #cvcc_wait_remaining\n",c->out); c->wait_counter_declared=1;
        }
        fputs("#cvcc_wait_remaining = ",c->out); expression(c,amount);
        fputs("\nWHILE #cvcc_wait_remaining > 0\nWAIT\n#cvcc_wait_remaining = #cvcc_wait_remaining - 1\nWEND\n",c->out);
    } else if(equals(c,fn,"clearScreen")) {
        if(count) { error(c,args,"expected no arguments"); return; }
        fputs("CLS\n",c->out);
    } else if (equals(c,fn,"printAt")) {
        unsigned pos; if (count!=2) { error(c,args,"printAt expects position and string"); return; }
        if (!number(c,child(args,0),767,&pos)) return;
        fprintf(c->out,"PRINT AT %u,",pos); literal_string(c,child(args,1)); fputc('\n',c->out);
    } else if (equals(c,fn,"defineSprite")) {
        unsigned first,total; if (count!=3) { error(c,args,"defineSprite expects first, count, ROM data"); return; }
        if (!number(c,child(args,0),63,&first)||!number(c,child(args,1),64,&total)) return;
        Symbol *s=lookup(c,child(args,2)); if (!s) return;
        if (!s->array || !s->constant || s->word || !total || first+total>64 || s->size!=(int)(total*32)) { error(c,args,"defineSprite needs 32 bytes per 16x16 pattern and a valid pattern range"); return; }
        fprintf(c->out,"DEFINE SPRITE %u,%u,d%u\n",first,total,(unsigned)(s-c->symbols));
    } else if (equals(c,fn,"sprite")) {
        if (count!=5) { error(c,args,"sprite expects index, y, x, pattern, color"); return; }
        fputs("SPRITE ",c->out);
        for (unsigned i=0;i<5;i++) { if(i) fputc(',',c->out); expression(c,child(args,i)); }
        fputc('\n',c->out);
    } else {
        for(unsigned i=0;i<c->function_count;i++) if(equals(c,fn,c->functions[i].name)) {
            if(count) { error(c,args,"user functions expect no arguments"); return; }
            if(c->current_function>=0) c->calls[c->current_function][i]=1;
            fprintf(c->out,"GOSUB cvcc_fn%u\n",i); return;
        }
        error(c,fn,"unsupported function call");
    }
}
/* Assignment indices cannot contain calls or updates, so compound lowering may
   safely evaluate the same index twice. */
static void effect(Compiler *c,TSNode e) {
    if(c->failed || ts_node_is_null(e)) return;
    if (kind(e,"assignment_expression") || kind(e,"update_expression")) {
        int update=kind(e,"update_expression");
        TSNode target=field(e,update?"argument":"left");
        TSNode op=field(e,"operator");
        int shifting=equals(c,op,"<<=")||equals(c,op,">>=");
        const char *compound=NULL;
        const char *ops[]={"+=","-=","&=","|=","^="};
        const char *basic[]={"+","-","AND","OR","XOR"};
        for(unsigned i=0;i<5;i++) if(equals(c,op,ops[i])) compound=basic[i];
        if ((!update&&!equals(c,op,"=")&&!compound&&!shifting) || (update&&!equals(c,op,"++")&&!equals(c,op,"--"))) { error(c,op,"unsupported assignment operator"); return; }
        if(!access(c,target,1)) return;
        fputs(" = ",c->out);
        if(update) { access(c,target,0); fprintf(c->out," %c 1",equals(c,op,"++")?'+':'-'); }
        else if(shifting) shift(c,target,field(e,"right"),equals(c,op,"<<="));
        else if(compound) {
            fputc('(',c->out); access(c,target,0); fprintf(c->out," %s ",compound);
            expression(c,field(e,"right")); fputc(')',c->out);
        } else expression(c,field(e,"right"));
        fputc('\n',c->out);
    } else if(kind(e,"call_expression")) builtin(c,e);
    else error(c,e,"unsupported expression statement");
}
static void statement(Compiler *c,TSNode n,unsigned depth) {
    if (c->failed) return;
    if (depth>64) { error(c,n,"statement nesting exceeds 64"); return; }
    if (kind(n,"compound_statement")) {
        for (unsigned i=0;i<children(n);i++) statement(c,child(n,i),depth+1);
    } else if (kind(n,"expression_statement")) {
        if (!children(n)) return;
        TSNode e=child(n,0);
        effect(c,e);
    } else if(kind(n,"if_statement")) {
        /* constexpr/consteval are not part of the supported language. */
        for(unsigned i=0;i<ts_node_child_count(n);i++) if(equals(c,ts_node_child(n,i),"constexpr")||equals(c,ts_node_child(n,i),"consteval")) { error(c,n,"compile-time if is unsupported"); return; }
        TSNode cond=field(n,"condition"), alt=field(n,"alternative");
        if(logical(c,cond)) {
            unsigned yes=c->next_bool++, no=c->next_bool++, end=c->next_bool++;
            branch(c,cond,yes,no); fprintf(c->out,"cvcc_bool%u:\n",yes);
            statement(c,field(n,"consequence"),depth+1);
            fprintf(c->out,"GOTO cvcc_bool%u\ncvcc_bool%u:\n",end,no);
            if(!ts_node_is_null(alt)) statement(c,child(alt,0),depth+1);
            fprintf(c->out,"cvcc_bool%u:\n",end);
        } else {
            fputs("IF ",c->out); condition(c,cond); fputs(" THEN\n",c->out);
            statement(c,field(n,"consequence"),depth+1);
            if(!ts_node_is_null(alt)) { fputs("ELSE\n",c->out); statement(c,child(alt,0),depth+1); }
            fputs("END IF\n",c->out);
        }
    } else if(kind(n,"while_statement") || kind(n,"for_statement")) {
        int counted=kind(n,"for_statement");
        if(c->loop_depth==64) { error(c,n,"loop nesting exceeds 64"); return; }
        unsigned id=c->next_loop++;
        if(counted) {
            TSNode init=field(n,"initializer");
            if(kind(init,"declaration")) { error(c,init,"for counters must be declared globally"); return; }
            if(kind(init,"expression_statement")) init=child(init,0);
            effect(c,init);
        }
        c->loop_ids[c->loop_depth++]=id;
        TSNode cond=field(n,"condition");
        if(logical(c,cond)) {
            unsigned yes=c->next_bool++, no=c->next_bool++;
            fputs("WHILE 1\n",c->out); branch(c,cond,yes,no);
            fprintf(c->out,"cvcc_bool%u:\nGOTO cvcc_break%u\ncvcc_bool%u:\n",no,id,yes);
        } else {
            fputs("WHILE ",c->out);
            if(ts_node_is_null(cond)) fputs("1",c->out); else condition(c,cond);
            fputc('\n',c->out);
        }
        statement(c,field(n,"body"),depth+1);
        fprintf(c->out,"cvcc_continue%u:\n",id);
        if(counted) effect(c,field(n,"update"));
        fprintf(c->out,"WEND\ncvcc_break%u:\n",id);
        c->loop_depth--;
    } else if(kind(n,"break_statement") || kind(n,"continue_statement")) {
        if(!c->loop_depth) { error(c,n,"break/continue require an enclosing loop"); return; }
        fprintf(c->out,"GOTO cvcc_%s%u\n",kind(n,"break_statement")?"break":"continue",c->loop_ids[c->loop_depth-1]);
    } else if(kind(n,"return_statement")) {
        if(children(n)) { error(c,n,"void functions cannot return a value"); return; }
        fputs(c->current_function<0?"GOTO cvcc_main_loop\n":"RETURN\n",c->out);
    } else error(c,n,"unsupported statement '%s'",ts_node_type(n));
}
static void check_calls(Compiler *c,unsigned id) {
    if(c->visited[id]==2 || c->failed) return;
    if(c->visited[id]==1) { error(c,c->functions[id].node,"recursive calls are unsupported"); return; }
    c->visited[id]=1;
    for(unsigned i=0;i<c->function_count;i++) if(c->calls[id][i]) check_calls(c,i);
    c->visited[id]=2;
}
static int compile(Compiler *c,TSNode root) {
    validate_tree(c,root,0);
    if(c->failed) return 0;
    for(unsigned i=0;i<children(root)&&!c->failed;i++) {
        TSNode n=child(root,i);
        if(kind(n,"declaration")) declare(c,n);
        else if(kind(n,"function_definition")) function(c,n);
        else error(c,n,"unsupported top-level construct '%s'",ts_node_type(n));
    }
    if(ts_node_is_null(c->setup)||ts_node_is_null(c->loop)) error(c,root,"exactly one setup() and loop() are required");
    if(c->failed) return 0;
    for(unsigned i=0;i<c->function_count;i++) for(unsigned j=0;j<c->count;j++)
        if(!strcmp(c->functions[i].name,c->symbols[j].name)) error(c,c->functions[i].node,"function conflicts with global symbol");
    if(c->failed) return 0;
    fputs("' Experimental CVCC output; SG-1000 only\n",c->out);
    for(unsigned i=0;i<c->count;i++) {
        Symbol *s=&c->symbols[i];
        if(s->constant && s->array) continue;
        fputs(s->constant?"CONST ":"DIM ",c->out); symbol_name(c,s);
        if(s->array) fprintf(c->out,"(%d)",s->size);
        if(s->constant) { unsigned v=0; number(c,s->value,s->word?65535:255,&v); fprintf(c->out," = %u",v); }
        fputc('\n',c->out);
    }
    for(unsigned i=0;i<c->count;i++) {
        Symbol *s=&c->symbols[i];
        if(s->constant || !s->initialized) continue;
        for(int j=0;j<(s->array?s->size:1);j++) {
            unsigned v=0; number(c,s->array?child(s->value,(unsigned)j):s->value,s->word?65535:255,&v);
            symbol_name(c,s); if(s->array) fprintf(c->out,"(%d)",j);
            fprintf(c->out," = %u\n",v);
        }
    }
    c->current_function=-1;
    statement(c,c->setup,0);
    fputs("cvcc_main_loop:\n",c->out); statement(c,c->loop,0); fputs("GOTO cvcc_main_loop\n",c->out);
    for(unsigned i=0;i<c->function_count;i++) {
        c->current_function=(int)i;
        fprintf(c->out,"cvcc_fn%u: PROCEDURE\n",i);
        statement(c,c->functions[i].body,0); fputs("END\n",c->out);
    }
    for(unsigned i=0;i<c->function_count;i++) check_calls(c,i);
    for(unsigned i=0;i<c->count;i++) if(c->symbols[i].array && c->symbols[i].constant) {
        Symbol *s=&c->symbols[i]; symbol_name(c,s); fputs(":\n",c->out);
        for(int j=0;j<s->size;j++) {
            unsigned v=0; number(c,child(s->value,(unsigned)j),s->word?65535:255,&v);
            if(j%16==0) fputs(s->word?"DATA ":"DATA BYTE ",c->out);
            fprintf(c->out,"%s%u",j%16?",":"",v);
            if(j%16==15 || j==s->size-1) fputc('\n',c->out);
        }
    }
    /* CVBasic's pinned lexer has a 1024-byte line buffer. Fail before handoff. */
    rewind(c->out);
    unsigned line_length=0; int ch;
    while((ch=fgetc(c->out))!=EOF) {
        if(ch=='\n') line_length=0;
        else if(++line_length>900) { error(c,root,"generated BASIC line is too long; simplify expressions"); break; }
    }
    return !c->failed;
}
int main(int argc,char **argv) {
    if(argc!=2) { fprintf(stderr,"Usage: cvcc source.cvc > output.bas\nExperimental SG-1000 frontend (not standard C++).\n"); return 2; }
    FILE *in=fopen(argv[1],"rb"); if(!in) { perror(argv[1]); return 1; }
    if(fseek(in,0,SEEK_END)||ftell(in)<0||ftell(in)>1024*1024) { fprintf(stderr,"source must be a seekable file of at most 1 MiB\n"); fclose(in); return 1; }
    long length=ftell(in); rewind(in);
    char *source=calloc((size_t)length+1,1);
    if(!source || fread(source,1,(size_t)length,in)!=(size_t)length) { fprintf(stderr,"cannot read source\n"); free(source); fclose(in); return 1; }
    fclose(in);
    if(memchr(source,0,(size_t)length)) { fprintf(stderr,"source contains a NUL byte\n"); free(source); return 1; }
    TSParser *parser=ts_parser_new();
    if(!parser||!ts_parser_set_language(parser,tree_sitter_cpp())) { fprintf(stderr,"incompatible Tree-sitter grammar/runtime\n"); free(source); ts_parser_delete(parser); return 1; }
    TSTree *tree=ts_parser_parse_string(parser,NULL,source,(uint32_t)length);
    FILE *out=tmpfile();
    if(!tree||!out) { fprintf(stderr,"cannot allocate parse/output resources\n"); if(out)fclose(out); ts_tree_delete(tree); ts_parser_delete(parser); free(source); return 1; }
    Compiler c={0}; c.source=source; c.path=argv[1]; c.out=out;
    int ok=compile(&c,ts_tree_root_node(tree));
    if(ok && !ferror(out)) {
        rewind(out); char buffer[4096]; size_t size;
        while((size=fread(buffer,1,sizeof buffer,out))) if(fwrite(buffer,1,size,stdout)!=size) { ok=0; break; }
        if(ferror(out)||fflush(stdout)) ok=0;
    } else ok=0;
    fclose(out); ts_tree_delete(tree); ts_parser_delete(parser); free(source); return ok?0:1;
}

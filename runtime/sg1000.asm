; CVCC original SG-1000 / SC-3000 runtime. BSD-3-Clause.
; ABI: values HL, all other registers volatile; IRQ preserves AF/BC/DE/HL.
; TMS9918 ports BE/BF; SN76489 port 7F; joypads DC/DD.
cvcc_start:
 di
 im 1
 ld sp,STACK_TOP
 xor a
 ld hl,RAM_START
 ld de,RAM_START+1
 ld bc,RAM_END-RAM_START-1
 ld (hl),a
 ldir
 IFDEF CVCC_BANKED
 ld a,2
 call cvcc_select_bank
 ENDIF
 ld a,$9f
 out ($7f),a
 ld a,$bf
 out ($7f),a
 ld a,$df
 out ($7f),a
 ld a,$ff
 out ($7f),a
 ld a,2
 call cvcc_mode
 call cvcc_setup
cvcc_main:
 call cvcc_loop
 jp cvcc_main

cvcc_irq:
 push af
 push bc
 push de
 push hl
 in a,($bf)
 bit 7,a
 jr z,.done
 ; Derive SAT base from shadow register 5, so vdpWrite stays effective.
 ld a,(cvcc_registers+5)
 and $7f
 ld l,a
 ld h,0
 REPT 7
 add hl,hl
 ENDR
 call cvcc_vram_address_write
 ld a,(cvcc_flicker_enabled)
 or a
 jr nz,.rotate
 ld de,cvcc_sprites
 ld bc,128
 call cvcc_vram_stream_write
 jr .tick
.rotate:
 ld a,(cvcc_sprite_rotation)
 add a,4
 and 124
 ld (cvcc_sprite_rotation),a
 ld e,a
 ld d,0
 ld b,32
.nextSprite:
 ld hl,cvcc_sprites
 add hl,de
 REPT 4
 ld a,(hl)
 out ($be),a
 inc hl
 nop
 ENDR
 ld a,e
 add a,4
 and 124
 ld e,a
 djnz .nextSprite
.tick:
 ld hl,cvcc_vblank
 inc (hl)
.done:
 pop hl
 pop de
 pop bc
 pop af
 ei
 reti

; EI's one-instruction delay makes EI/HALT an atomic wait for a future IRQ.
cvcc_wait:
 ld a,h
 or l
 ret z
.next:
 di
 ld a,(cvcc_vblank)
 ei
 halt
 ld b,a
 ld a,(cvcc_vblank)
 cp b
 jr z,.next
 dec hl
 ld a,h
 or l
 jr nz,.next
 ret

; VRAM routines are not reentrant. IRQ cannot interrupt a VDP latch/stream.
cvcc_vram_address_write:
 ld a,l
 out ($bf),a
 ld a,h
 and $3f
 or $40
 out ($bf),a
 ret
cvcc_vram_write:
 di
 call cvcc_vram_address_write
 call cvcc_vram_stream_write
 ei
 ret
cvcc_vram_stream_write:
 ld a,b
 or c
 ret z
 ex de,hl
 ld d,b
 ld b,c
 ld c,$be
 ld a,b
 or a
 jr z,.loop
 inc d
.loop:
 outi
 nop ; 30 T-states between writes: respect the TMS9918 access window.
 jp nz,.loop
 dec d
 jr nz,.loop
 ret
cvcc_vram_read:
 di
 ld a,l
 out ($bf),a
 ld a,h
 and $3f
 out ($bf),a
 ; Address setup performs the prefetch. Do not discard the first byte.
 ex de,hl
 ld d,b
 ld b,c
 ld c,$be
 ld a,b
 or a
 jr z,.loop
 inc d
.loop:
 ini
 nop
 jp nz,.loop
 dec d
 jr nz,.loop
 ei
 ret
cvcc_fill:
 ; HL=VRAM address, BC=count, E=fill byte. Caller holds interrupts disabled.
 call cvcc_vram_address_write
.loop:
 ld a,e
 out ($be),a
 dec bc
 ld a,b
 or c
 jr nz,.loop
 ret
cvcc_poke_regs:
 di
 ld d,a
 call cvcc_vram_address_write
 ld a,d
 out ($be),a
 ei
 ret
cvcc_print:
 push de
 ld de,$1800
 add hl,de
 pop de
 jp cvcc_vram_write
cvcc_clear:
 di
 ld hl,$1800
 ld bc,768
 ld e,32
 call cvcc_fill
 ei
 ret

; E=register, D=value. Keep a software shadow for screen and sprite operations.
cvcc_set_register:
 ld hl,cvcc_registers
 ld c,e
 ld b,0
 add hl,bc
 ld (hl),d
 ld a,d
 out ($bf),a
 ld a,e
 or $80
 out ($bf),a
 ret
cvcc_vdp_regs:
 di
 call cvcc_set_register
 ei
 ret
cvcc_screen_on:
 ld a,(cvcc_registers+1)
 or $40
 jr cvcc_screen_set
cvcc_screen_off:
 ld a,(cvcc_registers+1)
 and $bf
cvcc_screen_set:
 di
 ld d,a
 ld e,1
 call cvcc_set_register
 ei
 ret
cvcc_sprite_regs:
 di
 and 31
 add a,a
 add a,a
 ld l,a
 ld h,0
 push de
 ld de,cvcc_sprites
 add hl,de
 pop de
 ld (hl),b
 inc hl
 ld (hl),c
 inc hl
 ld (hl),d
 inc hl
 ld (hl),e
 ei
 ret
cvcc_mode:
 di
 ld (cvcc_video_mode),a
 ; Hide all 32 sprites without the 208 end-of-list marker (rotation-safe).
 ld hl,cvcc_sprites
 ld b,32
.hide:
 ld (hl),209
 inc hl
 ld (hl),0
 inc hl
 ld (hl),0
 inc hl
 ld (hl),0
 inc hl
 djnz .hide
 ld de,$8201 ; display off, 16x16 sprites, VRAM16K
 call cvcc_set_register
 ld hl,0
 ld bc,$4000
 ld e,0
 call cvcc_fill
 ld de,$0000
 ld a,(cvcc_video_mode)
 cp 2
 jr z,.reg0
 ld d,2 ; Graphics II
.reg0:
 call cvcc_set_register
 ld de,$0602
 call cvcc_set_register
 ld de,$8003
 ld a,(cvcc_video_mode)
 cp 2
 jr z,.reg3
 ld d,$ff
.reg3:
 call cvcc_set_register
 ld de,$0004
 ld a,(cvcc_video_mode)
 cp 2
 jr z,.reg4
 ld d,3
.reg4:
 call cvcc_set_register
 ld de,$3605 ; SAT at 1B00
 call cvcc_set_register
 ld de,$0706 ; sprite patterns 3800
 call cvcc_set_register
 ld de,$f107
 call cvcc_set_register
 ld hl,$2000
 ld bc,32
 ld a,(cvcc_video_mode)
 cp 2
 jr z,.colors
 ld bc,6144
.colors:
 ld e,$f1
 call cvcc_fill
 ld a,(cvcc_video_mode)
 cp 1
 jr z,.bitmap
 ld hl,$0100 ; font starts at character 32
 ld de,cvcc_font
 ld bc,768
 call cvcc_vram_address_write
 call cvcc_vram_stream_write
 ld a,(cvcc_video_mode)
 or a
 jr nz,.text
 ld hl,$0900
 ld de,cvcc_font
 ld bc,768
 call cvcc_vram_address_write
 call cvcc_vram_stream_write
 ld hl,$1100
 ld de,cvcc_font
 ld bc,768
 call cvcc_vram_address_write
 call cvcc_vram_stream_write
.text:
 ld hl,$1800
 ld bc,768
 ld e,32
 call cvcc_fill
 jr .enable
.bitmap:
 ld hl,$1800
 call cvcc_vram_address_write
 ld b,3
 ld a,0
.tile:
 out ($be),a
 nop
 nop
 nop
 inc a
 jr nz,.tile
 djnz .tile
.enable:
 ld de,$e201
 call cvcc_set_register
 in a,($bf)
 ei
 ret

cvcc_controller_port:
 cp 2
 jr z,.second
 in a,($dc)
 cpl
 and $3f
 jr .map
.second:
 in a,($dc)
 cpl
 rlca
 rlca
 and 3
 ld b,a
 in a,($dd)
 cpl
 and 15
 add a,a
 add a,a
 or b
.map:
 ; Hardware U,D,L,R,1,2 -> CVCC U,R,D,L,0,0,1,2.
 ld b,a
 and 1
 ld l,a
 ld a,b
 and 6
 add a,a
 or l
 ld l,a
 ld a,b
 and 8
 rrca
 rrca
 or l
 ld l,a
 ld a,b
 and $30
 add a,a
 add a,a
 or l
 ld l,a
 ld h,0
 ret
; C=channel, HL=divider/control, E=linear volume.
cvcc_sound_regs:
 ld a,c
 REPT 5
 add a,a
 ENDR
 or $80
 ld b,a
 ld a,l
 and 15
 or b
 out ($7f),a
 ld a,c
 cp 3
 jr z,.volume
 REPT 4
 srl h
 rr l
 ENDR
 ld a,l
 and $3f
 out ($7f),a
.volume:
 ld a,e
cvcc_volume_regs:
 and 15
 xor 15
 ld b,a
 ld a,c
 REPT 5
 add a,a
 ENDR
 or $90
 or b
 out ($7f),a
 ret
 INCLUDE "font.asm"

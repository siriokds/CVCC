; CVCC original fixed-ROM bank helpers. BSD-3-Clause.
; Only these helpers change the latch. IRQ code stays fixed and never banks.
; The shadow may briefly precede the latch: IRQ does not observe either value.
cvcc_select_bank:
 ld (cvcc_current_bank),a
 ld (CVCC_BANK_REGISTER),a
 ret

; A = data bank, HL = offset. Return byte in HL (H=0).
; This entire routine must stay fixed: the caller can itself be banked.
cvcc_bank_read:
 ld e,a
 ld a,(cvcc_current_bank)
 push af
 ld a,e
 call cvcc_select_bank
 ld a,h
 and $3f
 or $80
 ld h,a
 ld l,(hl)
 ld h,0
 pop af
 jp cvcc_select_bank       ; restore caller's bank without touching HL

; A = bank, HL = VRAM address, DE = ROM window address, BC = length.
cvcc_vram_write_bank:
 push bc                  ; temporarily use B to hold the requested bank
 ld b,a
 ld a,(cvcc_current_bank)
 push af
 ld a,b
 call cvcc_select_bank
 pop af
 pop bc
 push af                  ; saved caller bank, below the transfer's stack
 call cvcc_vram_write
 pop af
 jp cvcc_select_bank

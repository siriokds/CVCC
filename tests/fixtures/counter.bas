DIM v0
v0 = 0
CLS
PRINT AT 36,"CVCC + Tree-sitter"
cvcc_main_loop:
IF v0 < 100 THEN
v0 = v0 + 1
ELSE
v0 = 0
END IF
WAIT
GOTO cvcc_main_loop

' Stable variable names preserve CVBasic hash-based RAM placement.
' Independent BASIC reference for calls, byte/word arrays and early returns.
CONST #k2 = 6144
DIM v3(3)
DIM #v4(3)
DIM v5(2)
DIM #v6(2)
DIM v7
DIM #v8
DIM #v9
DIM v10
DIM v11
DIM v12
DIM #v13
DIM v14
v5(0) = 42
v5(1) = 99
#v6(0) = 256
#v6(1) = 65535
#v9 = 65535
GOSUB FILL
#v9 = #v9 + 1
v10 = 256
#v13 = -#v4(0)
IF #v4(0) > 255 THEN
v14 = 1
END IF
GOSUB EARLY
GOTO MAIN
v11 = 99
MAIN:
GOSUB TICK
WAIT
GOTO MAIN
v11 = 98
GOTO MAIN
FILL: PROCEDURE
v7 = 0
WHILE v7 < 3
v3(v7) = SEED(v7)
#v4(v7) = #ADDRESSES(v7)
v7 = v7 + 1
WEND
#v4(1) = #v4(1) + 1
#v4(2) = #v4(2) + 1
v3(2) = v3(2) + 1
#v8 = (#v4(0) + #v4(1)) - #k2
END
EARLY: PROCEDURE
IF v3(0) = 7 THEN
v11 = 1
RETURN
END IF
v11 = 2
END
TICK: PROCEDURE
GOSUB BUMP
END
BUMP: PROCEDURE
v12 = v12 + 1
END
SEED:
DATA BYTE 7,11,255
#ADDRESSES:
DATA 6144,6400,65535

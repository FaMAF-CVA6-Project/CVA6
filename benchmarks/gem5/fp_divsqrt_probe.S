  .section .text
  .global  main

main:
  li       a0, 0
  li       a1, 0
  call     m5_reset_stats

# -----------------------------------------------------------
# MAIN PROGRAM
# -----------------------------------------------------------
  j        __region_start

  .balign  4096
__region_start:
# --- constants ---
  li        t0, 0x3FF0000000000000   # 1.0
  fmv.d.x   f0, t0
  li        t0, 0x4000000000000000   # 2.0
  fmv.d.x   f1, t0
  li        t0, 0x400921FB54442D18   # pi, full mantissa
  fmv.d.x   f2, t0
  li        t0, 0x4005BF0A8B145769   # e, full mantissa
  fmv.d.x   f3, t0
  li        t0, 0x3FF8000000000000   # 1.5
  fmv.d.x   f4, t0
  li        t0, 0x3F800000           # 1.0f
  fmv.w.x   f8, t0
  li        t0, 0x40000000           # 2.0f
  fmv.w.x   f9, t0
  li        t0, 0x40490FDB           # pi as float
  fmv.w.x   f10, t0
  li        t0, 0x402DF854           # e as float
  fmv.w.x   f11, t0
  li        t0, 0x3FC00000           # 1.5f
  fmv.w.x   f12, t0

# ---------------------------------------------------------
# BLOCK 1 - fdiv.d, zero mantissas, the basic_test operands
# 1.0 / 2.0 = 0.5, then multiply back by 2.0 to restore
# ---------------------------------------------------------
  fmv.d     f5, f0
  .rept     32
  fdiv.d    f5, f5, f1
  fmul.d    f5, f5, f1
  .endr

# ---------------------------------------------------------
# BLOCK 2 - fdiv.d, full mantissas
# ---------------------------------------------------------
  fmv.d     f5, f2
  .rept     32
  fdiv.d    f5, f5, f3
  fmul.d    f5, f5, f3
  .endr

# ---------------------------------------------------------
# BLOCK 3 - fdiv.s, zero mantissas
# ---------------------------------------------------------
  fmv.s     f13, f8
  .rept     32
  fdiv.s    f13, f13, f9
  fmul.s    f13, f13, f9
  .endr

# ---------------------------------------------------------
# BLOCK 4 - fdiv.s, full mantissas
# ---------------------------------------------------------
  fmv.s     f13, f10
  .rept     32
  fdiv.s    f13, f13, f11
  fmul.s    f13, f13, f11
  .endr

# ---------------------------------------------------------
# BLOCK 5 - fsqrt.d, converging on the fixed point near 2.28
# ---------------------------------------------------------
  fmv.d     f6, f2
  .rept     32
  fsqrt.d   f6, f6
  fadd.d    f6, f6, f4
  .endr

# ---------------------------------------------------------
# BLOCK 6 - fsqrt.s, the same shape in single precision
# ---------------------------------------------------------
  fmv.s     f14, f10
  .rept     32
  fsqrt.s   f14, f14
  fadd.s    f14, f14, f12
  .endr

# ---------------------------------------------------------
# BLOCK 7 - fdiv.d, exact power-of-two divisor, one bit of
# quotient mantissa, the operand-law probe against block 1
# ---------------------------------------------------------
  fmv.d     f5, f2
  .rept     32
  fdiv.d    f5, f5, f1
  fmul.d    f5, f5, f1
  .endr

# ---------------------------------------------------------
# BLOCK 8 - independent fdiv.d pairs, the issue interval
# Sixteen pairs with no data dependence between the members
# of a pair, so the block prices back-to-back acceptance.
# ---------------------------------------------------------
  .rept     16
  fdiv.d    f5, f2, f3
  fdiv.d    f6, f2, f3
  fmul.d    f5, f5, f6
  .endr

# ---------------------------------------------------------
# BLOCK 9 - independent fdiv.d and fsqrt.d, the merged-unit
# serialisation the basic_test trace showed
# ---------------------------------------------------------
  .rept     16
  fdiv.d    f5, f2, f3
  fsqrt.d   f6, f2
  fmul.d    f5, f5, f6
  .endr
__region_end:
# -----------------------------------------------------------
# END OF MAIN PROGRAM
# -----------------------------------------------------------

  li       a0, 0
  li       a1, 0
  call     m5_dump_stats

# PADDING
  .rept    50
  nop
  .endr

# EXIT
  call     m5_exit

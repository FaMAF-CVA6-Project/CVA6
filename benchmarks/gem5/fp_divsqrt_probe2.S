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
  li        t0, 0x4010000000000000   # 4.0
  fmv.d.x   f3, t0
  li        t0, 0x3FF8000000000000   # 1.5, one mantissa bit
  fmv.d.x   f4, t0
  li        t0, 0x40000000           # 2.0f
  fmv.w.x   f8, t0
  li        t0, 0x40490FDB           # pi as float
  fmv.w.x   f9, t0
  li        t0, 0x40800000           # 4.0f
  fmv.w.x   f10, t0

# ---------------------------------------------------------
# BLOCK A - fsqrt.d on a zero-mantissa radicand
# sqrt(4.0) = 2.0, squared back to 4.0, exact both ways
# ---------------------------------------------------------
  fmv.d     f5, f3
  .rept     32
  fsqrt.d   f5, f5
  fmul.d    f5, f5, f5
  .endr

# ---------------------------------------------------------
# BLOCK B - fsqrt.s, the same in single precision
# ---------------------------------------------------------
  fmv.s     f11, f10
  .rept     32
  fsqrt.s   f11, f11
  fmul.s    f11, f11, f11
  .endr

# ---------------------------------------------------------
# BLOCK C - fdiv.d, zero-mantissa dividend over a full divisor
# 2.0 / f7 with f7 = quotient + pi, full mantissa throughout
# ---------------------------------------------------------
  fmv.d     f7, f2
  .rept     32
  fdiv.d    f5, f1, f7
  fadd.d    f7, f5, f2
  .endr

# ---------------------------------------------------------
# BLOCK D - fdiv.s, the same in single precision
# ---------------------------------------------------------
  fmv.s     f12, f9
  .rept     32
  fdiv.s    f11, f8, f12
  fadd.s    f12, f11, f9
  .endr

# ---------------------------------------------------------
# BLOCK E - fdiv.d, one-bit mantissa dividend over a power of two
# 1.5 / 2.0 = 0.75, back to 1.5, exact both ways
# ---------------------------------------------------------
  fmv.d     f5, f4
  .rept     32
  fdiv.d    f5, f5, f1
  fmul.d    f5, f5, f1
  .endr

# ---------------------------------------------------------
# BLOCK F - fdiv.d, identical operands, 1.0 / 1.0
# ---------------------------------------------------------
  fmv.d     f5, f0
  .rept     32
  fdiv.d    f5, f5, f0
  fmul.d    f5, f5, f0
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

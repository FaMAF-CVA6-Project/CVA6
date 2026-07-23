  .section .text
  .global  main

main:
  li       a0, 0
  li       a1, 0
  call     m5_reset_stats

# -----------------------------------------------------------
# MAIN PROGRAM
# -----------------------------------------------------------
  li       t0, 0x3FF8000000000000 # 1.5
  fmv.d.x  f3, t0

# fdiv.d dependent chain: converges towards 4.5
  li       t0, 0x4010000000000000 # 4.0
  fmv.d.x  f2, t0
  .rept    32
  fdiv.d   f2, f2, f3
  fadd.d   f2, f2, f3
  .endr

# fsqrt.d dependent chain: converges towards about 3.2
  li       t0, 0x4024000000000000 # 10.0
  fmv.d.x  f4, t0
  .rept    32
  fsqrt.d  f4, f4
  fadd.d   f4, f4, f3
  .endr

# single-precision counterparts
  li       t0, 0x3FC00000         # 1.5f
  fmv.w.x  f5, t0
  li       t0, 0x40800000         # 4.0f
  fmv.w.x  f6, t0
  .rept    32
  fdiv.s   f6, f6, f5
  fadd.s   f6, f6, f5
  .endr
  li       t0, 0x41200000         # 10.0f
  fmv.w.x  f7, t0
  .rept    32
  fsqrt.s  f7, f7
  fadd.s   f7, f7, f5
  .endr
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

  call     m5_exit

  .section .text
  .global  main

main:
  li       a0, 0
  li       a1, 0
  call     m5_reset_stats

# -----------------------------------------------------------
# MAIN PROGRAM
# -----------------------------------------------------------
  li       t0, 0x3F800000         # 1.0f
  fmv.w.x  f0, t0
  li       t0, 0x38D1B717         # about 1e-4f, keeps the sum small
  fmv.w.x  f1, t0
  li       t0, 0x3FF0000000000000 # 1.0
  fmv.d.x  f2, t0
  li       t0, 0x3F1A36E2EB1C432D # about 1e-4
  fmv.d.x  f3, t0

# single-precision add chain
  .rept    64
  fadd.s   f0, f0, f1
  .endr

# double-precision add chain
  .rept    64
  fadd.d   f2, f2, f3
  .endr

# single-precision multiply chain
  li       t0, 0x3F800001         # just above 1.0f
  fmv.w.x  f4, t0
  li       t0, 0x3F800000         # 1.0f
  fmv.w.x  f5, t0
  .rept    64
  fmul.s   f5, f5, f4
  .endr

# double-precision multiply chain
  li       t0, 0x3FF0000000000001 # just above 1.0
  fmv.d.x  f6, t0
  li       t0, 0x3FF0000000000000 # 1.0
  fmv.d.x  f7, t0
  .rept    64
  fmul.d   f7, f7, f6
  .endr

# fused multiply-add chains, both precisions
  .rept    64
  fmadd.s  f0, f0, f1, f0
  .endr
  .rept    64
  fmadd.d  f2, f2, f3, f2
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

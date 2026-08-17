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
# Loop A: large dividend / small divisor -> near worst case
  li       t3, 0x7FFFFFFFFFFFFFFF
  li       t1, 3
  .rept    48
  div      t0, t3, t1             # big / small
  andi     t1, t0, 7              # next divisor from result, stays small
  ori      t1, t1, 1              # never zero
  .endr

# Loop B: small dividend / large divisor -> best case
  li       t3, 1
  li       t1, 0x4000000000000000 # not 0x7FFF..., which would overflow
  .rept    48                     # to negative on the first add below
  div      t0, t3, t1             # 1 / huge = 0
  ori      t0, t0, 1
  add      t1, t1, t0             # keep the chain, divisor stays huge and positive
  .endr

# Loop C: remainder form, same worst-case shape
  li       t3, 0x7FFFFFFFFFFFFFFF
  li       t1, 5
  .rept    48
  rem      t0, t3, t1
  andi     t1, t0, 7
  ori      t1, t1, 1
  .endr

# Loop D: independent stream, worst-case operands, rotating dests
  li       t3, 0x7FFFFFFFFFFFFFFF
  li       t1, 3
  .rept    16
  div      t4, t3, t1
  div      t5, t3, t1
  div      t6, t3, t1
  .endr

# Loop E: divw worst case, big 32-bit dividend / small divisor
  li       t3, 0x7FFFFFFF
  li       t1, 3
  .rept    48
  divw     t0, t3, t1
  andi     t1, t0, 7
  ori      t1, t1, 1
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

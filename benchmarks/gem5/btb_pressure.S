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
  .option  push
  .option  norvc

  li       t0, 0
  li       t2, 4              # outer passes over the whole footprint

runahead_outer:
  .rept    128
  li       t1, 8
1:
  addi     t1, t1, -1
  addi     t0, t0, 1
  bnez     t1, 1b             # taken 7 times, run-ahead spills into the pad
  j        2f                 # skip the pad, so it is never executed
  .rept    32
  nop
  .endr
2:
  .endr
  addi     t2, t2, -1
  bnez     t2, runahead_outer

  .option  pop
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

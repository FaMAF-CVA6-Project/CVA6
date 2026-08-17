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
  .balign  16
  .option  push
  .option  norvc

  li       t2, 8            # outer passes over the stride buffer

fetch2_outer:
  la       a5, stride_buf
  li       t1, 512
1:
  ld       t3, 0(a5)        # misses, and the next address depends on it
  add      a5, a5, t3       # dependent, so the chain cannot overlap
  addi     t1, t1, -1
  bnez     t1, 1b           # taken: everything fetched past here is waste
  j        2f               # skip the pad, so it is never executed
  .rept    32
  nop
  .endr
2:
  addi     t2, t2, -1
  bnez     t2, fetch2_outer

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

  .section .data
  .balign  64
stride_buf:
  .rept    512
  .dword   128
  .space   120
  .endr

  .section .text
  .global  main

main:
  li       a0, 0
  li       a1, 0
  call     m5_reset_stats

# -----------------------------------------------------------
# MAIN PROGRAM
# -----------------------------------------------------------
  la       a0, fwd_buf
  li       t0, 0x0123456789ABCDEF

# Loop A: load from the address just stored (collision)
  .rept    64
  sd       t0, 0(a0)
  ld       t1, 0(a0)              # same address as the store above
  addi     t0, t1, 1              # dependency, forces full serialisation
  .endr

# Loop B: control, load from a different line (no collision)
  .rept    64
  sd       t0, 0(a0)
  ld       t1, 128(a0)            # 8 cache lines away at 128-bit lines
  addi     t0, t1, 1
  .endr

# Loop C: narrower load over a wider store (partial overlap)
  .rept    64
  sd       t0, 0(a0)
  lw       t1, 0(a0)              # word read of a doubleword store
  addi     t0, t1, 1
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

  .section .data
  .align   6
fwd_buf:
  .space   512

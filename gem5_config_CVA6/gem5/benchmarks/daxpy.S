  .data
  .balign  4096
N:
  .dword   4096           # Size of the vectors
Alpha:
  .dword   2              # Scalar multiplier

  .bss
  .balign  4096
  .align   3
X:
  .zero    32768          # Vector X (4096)*8 bytes
Y:
  .zero    32768          # Vector Y (4096)*8 bytes
Z:
  .zero    32768          # Vector Z (4096)*8 bytes

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
  la       t0, N
  ld       t1, 0(t0)

  la       t2, Alpha
  ld       t3, 0(t2)
  fcvt.d.l f10, t3

  la       s2, X
  la       s3, Y
  la       s4, Z

  mv       s5, s2
  mv       s6, s3
  mv       s7, s4

  li       t4, 0

# Z[i] = alpha * X[i] + Y[i], three 32 KiB streams through the 32 KiB D-cache
  .align   4
loop:
  fld      f5, 0(s5)
  fld      f6, 0(s6)
  fmul.d   f7, f10, f5
  fadd.d   f8, f7, f6
  fsd      f8, 0(s7)

  addi     s5, s5, 8
  addi     s6, s6, 8
  addi     s7, s7, 8

  addi     t4, t4, 1
  blt      t4, t1, loop
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

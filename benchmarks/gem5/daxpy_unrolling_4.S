  .data
N:
  .dword   4096           # Size of the vectors
Alpha:
  .dword   2              # Scalar multiplier

  .bss
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
  la       t0, N
  ld       t1, 0(t0)      # t1 = N (4096)

  la       t2, Alpha
  ld       t3, 0(t2)
  fcvt.d.l f10, t3        # f10 = Alpha (double)

  la       s2, X
  la       s3, Y
  la       s4, Z

  mv       s5, s2         # Pointer X
  mv       s6, s3         # Pointer Y
  mv       s7, s4         # Pointer Z

  srli     t5, t1, 2      # t5 = N >> 2

  li       t4, 0

  .align   4
loop:
# Block 1 (Offset 0)
  fld      f5, 0(s5)
  fld      f6, 0(s6)
  fmul.d   f7, f10, f5
  fadd.d   f8, f7, f6
  fsd      f8, 0(s7)

# Block 2 (Offset 8)
  fld      f9, 8(s5)
  fld      f11, 8(s6)
  fmul.d   f12, f10, f9
  fadd.d   f13, f12, f11
  fsd      f13, 8(s7)

# Block 3 (Offset 16)
  fld      f14, 16(s5)
  fld      f15, 16(s6)
  fmul.d   f16, f10, f14
  fadd.d   f17, f16, f15
  fsd      f17, 16(s7)

# Block 4 (Offset 24)
  fld      f18, 24(s5)
  fld      f19, 24(s6)
  fmul.d   f20, f10, f18
  fadd.d   f21, f20, f19
  fsd      f21, 24(s7)

  addi     s5, s5, 32
  addi     s6, s6, 32
  addi     s7, s7, 32

# Loop control
  addi     t4, t4, 1
  blt      t4, t5, loop
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

# SALIDA
  call     m5_exit
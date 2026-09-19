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
# --- constants: f31 = +0.0, f30 = +0.0f, the restore multiplicands ---
  fmv.d.x  f31, zero
  fmv.w.x  f30, zero

# ---------------------------------------------------------
# BLOCK R1 - restore op alone, fmadd.d
# f5 = f5 * 0 + 1.5, two passes, warm period 4
# ---------------------------------------------------------
  li       t0, 0x3ff8000000000000
  fmv.d.x  f1, t0
  fmv.d    f5, f1
  li       t1, 2
r1_pass:
  .rept    32
  fmadd.d  f5, f5, f31, f1
  .endr
  addi     t1, t1, -1
  bnez     t1, r1_pass

# ---------------------------------------------------------
# BLOCK R2 - restore op alone, fmadd.s
# f5 = f5 * 0 + 1.5, two passes, warm period 3
# ---------------------------------------------------------
  li       t0, 0x3fc00000
  fmv.w.x  f1, t0
  fmv.s    f5, f1
  li       t1, 2
r2_pass:
  .rept    32
  fmadd.s  f5, f5, f30, f1
  .endr
  addi     t1, t1, -1
  bnez     t1, r2_pass

# ---------------------------------------------------------
# BLOCK D1 - fdiv.d, exact quotient 1.5, 52-bit dividend, 50-bit divisor
# 1.0000000000000004 / 1.333333333333334, m = 1, latency 10, period 14
# ---------------------------------------------------------
  li       t0, 0x3ff0000000000002
  fmv.d.x  f1, t0
  li       t0, 0x3ff5555555555558
  fmv.d.x  f2, t0
  fmv.d    f5, f1
  .rept    32
  fdiv.d   f5, f5, f2
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK D2 - fdiv.d, exact quotient 1 + 2^-10, 52-bit dividend
# 1.3346354166668184 / 1.333333333333485, m = 3, latency 12, period 16
# ---------------------------------------------------------
  li       t0, 0x3ff55aaaaaaaad56
  fmv.d.x  f1, t0
  li       t0, 0x3ff5555555555800
  fmv.d.x  f2, t0
  fmv.d    f5, f1
  .rept    32
  fdiv.d   f5, f5, f2
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK D3 - fdiv.d, exact quotient 1 + 2^-30, 52-bit dividend
# 1.3333334935208163 / 1.3333334922790527, m = 8, latency 17, period 21
# ---------------------------------------------------------
  li       t0, 0x3ff5555580555556
  fmv.d.x  f1, t0
  li       t0, 0x3ff5555580000000
  fmv.d.x  f2, t0
  fmv.d    f5, f1
  .rept    32
  fdiv.d   f5, f5, f2
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK D4 - fdiv.d, exact quotient 1 + 2^-46, the last round before the cap
# 1.343750000000019 / 1.34375, m = 12, latency 21, period 25
# ---------------------------------------------------------
  li       t0, 0x3ff5800000000056
  fmv.d.x  f1, t0
  li       t0, 0x3ff5800000000000
  fmv.d.x  f2, t0
  fmv.d    f5, f1
  .rept    32
  fdiv.d   f5, f5, f2
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK D5 - fdiv.d, exact quotient 1 + 2^-47, lands on the cap
# 1.3125000000000093 / 1.3125, m = 13, latency 22, period 26
# ---------------------------------------------------------
  li       t0, 0x3ff500000000002a
  fmv.d.x  f1, t0
  li       t0, 0x3ff5000000000000
  fmv.d.x  f2, t0
  fmv.d    f5, f1
  .rept    32
  fdiv.d   f5, f5, f2
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK D6 - fdiv.d, 3.140625 / 2.71875, short inputs, inexact quotient
# 3.140625 / 2.71875, m = 13, latency 22, period 26
# ---------------------------------------------------------
  li       t0, 0x4009200000000000
  fmv.d.x  f1, t0
  li       t0, 0x4005c00000000000
  fmv.d.x  f2, t0
  fmv.d    f5, f1
  .rept    32
  fdiv.d   f5, f5, f2
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK D7 - fdiv.d, pi / e, full control
# 3.141592653589793 / 2.718281828459045, m = 13, latency 22, period 26
# ---------------------------------------------------------
  li       t0, 0x400921fb54442d18
  fmv.d.x  f1, t0
  li       t0, 0x4005bf0a8b145769
  fmv.d.x  f2, t0
  fmv.d    f5, f1
  .rept    32
  fdiv.d   f5, f5, f2
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK D8 - fdiv.d, 0.0 / 1.5, special operand, SRT skipped
# 0.0 / 1.5, m = 0, latency 9, period 13
# ---------------------------------------------------------
  li       t0, 0x0
  fmv.d.x  f1, t0
  li       t0, 0x3ff8000000000000
  fmv.d.x  f2, t0
  fmv.d    f5, f1
  .rept    32
  fdiv.d   f5, f5, f2
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK S1 - fdiv.s, exact quotient 1.5, 22-bit dividend, 21-bit divisor
# 1.9999995231628418 / 1.3333330154418945, m = 1, latency 10, period 13
# ---------------------------------------------------------
  li       t0, 0x3ffffffc
  fmv.w.x  f1, t0
  li       t0, 0x3faaaaa8
  fmv.w.x  f2, t0
  fmv.s    f5, f1
  .rept    32
  fdiv.s   f5, f5, f2
  fmadd.s  f5, f5, f30, f1
  .endr

# ---------------------------------------------------------
# BLOCK S2 - fdiv.s, exact quotient 1 + 2^-10, 23-bit dividend
# 1.3345539569854736 / 1.333251953125, m = 3, latency 12, period 15
# ---------------------------------------------------------
  li       t0, 0x3faad2aa
  fmv.w.x  f1, t0
  li       t0, 0x3faaa800
  fmv.w.x  f2, t0
  fmv.s    f5, f1
  .rept    32
  fdiv.s   f5, f5, f2
  fmadd.s  f5, f5, f30, f1
  .endr

# ---------------------------------------------------------
# BLOCK S3 - fdiv.s, exact quotient 1 + 2^-18, the last round before the cap
# 1.3125050067901611 / 1.3125, m = 5, latency 14, period 17
# ---------------------------------------------------------
  li       t0, 0x3fa8002a
  fmv.w.x  f1, t0
  li       t0, 0x3fa80000
  fmv.w.x  f2, t0
  fmv.s    f5, f1
  .rept    32
  fdiv.s   f5, f5, f2
  fmadd.s  f5, f5, f30, f1
  .endr

# ---------------------------------------------------------
# BLOCK S4 - fdiv.s, exact quotient 1 + 2^-19, lands on the cap
# 1.3750026226043701 / 1.375, m = 6, latency 15, period 18
# ---------------------------------------------------------
  li       t0, 0x3fb00016
  fmv.w.x  f1, t0
  li       t0, 0x3fb00000
  fmv.w.x  f2, t0
  fmv.s    f5, f1
  .rept    32
  fdiv.s   f5, f5, f2
  fmadd.s  f5, f5, f30, f1
  .endr

# ---------------------------------------------------------
# BLOCK S5 - fdiv.s, 3.140625f / 2.71875f, basic_test's operands
# 3.140625 / 2.71875, m = 6, latency 15, period 18
# ---------------------------------------------------------
  li       t0, 0x40490000
  fmv.w.x  f1, t0
  li       t0, 0x402e0000
  fmv.w.x  f2, t0
  fmv.s    f5, f1
  .rept    32
  fdiv.s   f5, f5, f2
  fmadd.s  f5, f5, f30, f1
  .endr

# ---------------------------------------------------------
# BLOCK Q1 - fsqrt.d, sqrt(2.25) = 1.5, odd exponent
# sqrt(2.25), m = 1, latency 10, period 14
# ---------------------------------------------------------
  li       t0, 0x4002000000000000
  fmv.d.x  f1, t0
  fmv.d    f5, f1
  .rept    32
  fsqrt.d  f5, f5
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK Q2 - fsqrt.d, root 1.5 + 2^-14, odd exponent
# sqrt(2.2501831091940403), m = 4, latency 13, period 17
# ---------------------------------------------------------
  li       t0, 0x4002006000800000
  fmv.d.x  f1, t0
  fmv.d    f5, f1
  .rept    32
  fsqrt.d  f5, f5
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK Q3 - fsqrt.d, root 1 + 2^-26, the longest exact double root, even exponent
# sqrt(1.0000000298023226), m = 7, latency 16, period 20
# ---------------------------------------------------------
  li       t0, 0x3ff0000008000001
  fmv.d.x  f1, t0
  fmv.d    f5, f1
  .rept    32
  fsqrt.d  f5, f5
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK Q4 - fsqrt.d, sqrt(2.71875), basic_test's radicand, 7 significant bits
# sqrt(2.71875), m = 13, latency 22, period 26
# ---------------------------------------------------------
  li       t0, 0x4005c00000000000
  fmv.d.x  f1, t0
  fmv.d    f5, f1
  .rept    32
  fsqrt.d  f5, f5
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK Q5 - fsqrt.d, sqrt(1.5), one-bit radicand, irrational root
# sqrt(1.5), m = 13, latency 22, period 26
# ---------------------------------------------------------
  li       t0, 0x3ff8000000000000
  fmv.d.x  f1, t0
  fmv.d    f5, f1
  .rept    32
  fsqrt.d  f5, f5
  fmadd.d  f5, f5, f31, f1
  .endr

# ---------------------------------------------------------
# BLOCK T1 - fsqrt.s, root 1 + 2^-6
# sqrt(1.031494140625), m = 2, latency 11, period 14
# ---------------------------------------------------------
  li       t0, 0x3f840800
  fmv.w.x  f1, t0
  fmv.s    f5, f1
  .rept    32
  fsqrt.s  f5, f5
  fmadd.s  f5, f5, f30, f1
  .endr

# ---------------------------------------------------------
# BLOCK T2 - fsqrt.s, root 1 + 2^-11, the longest exact single root
# sqrt(1.000976800918579), m = 4, latency 13, period 16
# ---------------------------------------------------------
  li       t0, 0x3f802002
  fmv.w.x  f1, t0
  fmv.s    f5, f1
  .rept    32
  fsqrt.s  f5, f5
  fmadd.s  f5, f5, f30, f1
  .endr

# ---------------------------------------------------------
# BLOCK T3 - fsqrt.s, sqrt(2.71875f), basic_test's radicand, 7 significant bits
# sqrt(2.71875), m = 6, latency 15, period 18
# ---------------------------------------------------------
  li       t0, 0x402e0000
  fmv.w.x  f1, t0
  fmv.s    f5, f1
  .rept    32
  fsqrt.s  f5, f5
  fmadd.s  f5, f5, f30, f1
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

  .section .text
  .global  main

# CSR addresses
  .equ     CSR_MCOUNTINHIBIT, 0x320
  .equ     CSR_MHPMEVENT3, 0x323
  .equ     CSR_MHPMEVENT4, 0x324
  .equ     CSR_MHPMEVENT5, 0x325
  .equ     CSR_MHPMEVENT6, 0x326
  .equ     CSR_MHPMEVENT7, 0x327
  .equ     CSR_MHPMEVENT8, 0x328

  .equ     CSR_MCYCLE, 0xB00
  .equ     CSR_MINSTRET, 0xB02
  .equ     CSR_MHPMCOUNTER3, 0xB03
  .equ     CSR_MHPMCOUNTER4, 0xB04
  .equ     CSR_MHPMCOUNTER5, 0xB05
  .equ     CSR_MHPMCOUNTER6, 0xB06
  .equ     CSR_MHPMCOUNTER7, 0xB07
  .equ     CSR_MHPMCOUNTER8, 0xB08

# CPU Frequency (for time calculation)
  .equ     CPU_FREQ, 50000000       # 50 MHz

main:
# ---------------------------------------------------------
# CONFIGURATION OF PERFORMANCE COUNTERS
# ---------------------------------------------------------
# Reserve the snapshot frame, and pause the counters during setup
  addi     sp, sp, -80
  li       t0, -1
  csrw     CSR_MCOUNTINHIBIT, t0

# Configure events to count
  li       t0, 1
  csrw     CSR_MHPMEVENT3, t0       # L1 I-cache Miss
  li       t0, 2
  csrw     CSR_MHPMEVENT4, t0       # L1 D-cache Miss
  li       t0, 16
  csrw     CSR_MHPMEVENT5, t0       # L1 I-cache Access
  li       t0, 17
  csrw     CSR_MHPMEVENT6, t0       # L1 D-cache Access
  li       t0, 9
  csrw     CSR_MHPMEVENT7, t0       # Branch Instr
  li       t0, 10
  csrw     CSR_MHPMEVENT8, t0       # Branch Mispredict + Unpredicted

# Zero the event counters, so a raw read of them counts from here
  csrw     CSR_MHPMCOUNTER3, zero
  csrw     CSR_MHPMCOUNTER4, zero
  csrw     CSR_MHPMCOUNTER5, zero
  csrw     CSR_MHPMCOUNTER6, zero
  csrw     CSR_MHPMCOUNTER7, zero
  csrw     CSR_MHPMCOUNTER8, zero

# Let lower privilege read the counters, then start them
  li       t0, -1
  csrw     mcounteren, t0
  csrw     CSR_MCOUNTINHIBIT, zero

# ---------------------------------------------------------
# INITIAL SNAPSHOT OF PERFORMANCE COUNTERS
# ---------------------------------------------------------
  csrr     t0, CSR_MCYCLE
  sd       t0, 0(sp)                # Cycle Start
  csrr     t0, CSR_MINSTRET
  sd       t0, 8(sp)                # Instret Start
  csrr     t0, CSR_MHPMCOUNTER3
  sd       t0, 16(sp)               # HPM3 Start
  csrr     t0, CSR_MHPMCOUNTER4
  sd       t0, 24(sp)               # HPM4 Start
  csrr     t0, CSR_MHPMCOUNTER5
  sd       t0, 32(sp)               # HPM5 Start
  csrr     t0, CSR_MHPMCOUNTER6
  sd       t0, 40(sp)               # HPM6 Start
  csrr     t0, CSR_MHPMCOUNTER7
  sd       t0, 48(sp)               # HPM7 Start
  csrr     t0, CSR_MHPMCOUNTER8
  sd       t0, 56(sp)               # HPM8 Start

# ---------------------------------------------------------
# MAIN PROGRAM
# ---------------------------------------------------------
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
# ---------------------------------------------------------
# END OF MAIN PROGRAM
# ---------------------------------------------------------

# ---------------------------------------------------------
# FINAL SNAPSHOT OF PERFORMANCE COUNTERS
# ---------------------------------------------------------
# x18 (s2) = Cycles
  csrr     s2, CSR_MCYCLE
  ld       t0, 0(sp)
  sub      s2, s2, t0

# x19 (s3) = Instructions
  csrr     s3, CSR_MINSTRET
  ld       t0, 8(sp)
  sub      s3, s3, t0

# x20 (s4) = I-cache Miss
  csrr     s4, CSR_MHPMCOUNTER3
  ld       t0, 16(sp)
  sub      s4, s4, t0

# x21 (s5) = D-cache Miss
  csrr     s5, CSR_MHPMCOUNTER4
  ld       t0, 24(sp)
  sub      s5, s5, t0

# x22 (s6) = I-cache Access
  csrr     s6, CSR_MHPMCOUNTER5
  ld       t0, 32(sp)
  sub      s6, s6, t0

# x23 (s7) = D-cache Access
  csrr     s7, CSR_MHPMCOUNTER6
  ld       t0, 40(sp)
  sub      s7, s7, t0

# x24 (s8) = Branches
  csrr     s8, CSR_MHPMCOUNTER7
  ld       t0, 48(sp)
  sub      s8, s8, t0

# x25 (s9) = Branch Miss + Unpred
  csrr     s9, CSR_MHPMCOUNTER8
  ld       t0, 56(sp)
  sub      s9, s9, t0

  addi     sp, sp, 80

# ---------------------------------------------------------
# TIME CALCULATION
# ---------------------------------------------------------
  li       t0, 1000000
  mul      s10, s2, t0              # s10 = Cycles (s2) * 1M
  li       t0, CPU_FREQ
  divu     s10, s10, t0             # s10 = s10 / Freq

# ---------------------------------------------------------
# EXIT
# ---------------------------------------------------------
  li       a0, 0
  jal      exit


  .section  .text
  .global   main

# Direction to CSRs
  .equ      CSR_MCOUNTINHIBIT, 0x320
  .equ      CSR_MHPMEVENT3, 0x323
  .equ      CSR_MHPMEVENT4, 0x324
  .equ      CSR_MHPMEVENT5, 0x325
  .equ      CSR_MHPMEVENT6, 0x326
  .equ      CSR_MHPMEVENT7, 0x327
  .equ      CSR_MHPMEVENT8, 0x328

  .equ      CSR_MCYCLE, 0xB00
  .equ      CSR_MINSTRET, 0xB02
  .equ      CSR_MHPMCOUNTER3, 0xB03
  .equ      CSR_MHPMCOUNTER4, 0xB04
  .equ      CSR_MHPMCOUNTER5, 0xB05
  .equ      CSR_MHPMCOUNTER6, 0xB06
  .equ      CSR_MHPMCOUNTER7, 0xB07
  .equ      CSR_MHPMCOUNTER8, 0xB08

# CPU Frequency (for time calculation)
  .equ      CPU_FREQ, 50000000       # 50 MHz

main:
# ---------------------------------------------------------
# CONFIGURATION OF PERFORMANCE COUNTERS
# ---------------------------------------------------------
# Pause counters during setup
  addi      sp, sp, -80
  li        t0, -1
  csrw      CSR_MCOUNTINHIBIT, t0

# Configure events to count
  li        t0, 1
  csrw      CSR_MHPMEVENT3, t0       # L1 I-Cache Miss
  li        t0, 2
  csrw      CSR_MHPMEVENT4, t0       # L1 D-Cache Miss
  li        t0, 16
  csrw      CSR_MHPMEVENT5, t0       # L1 I-Cache Access
  li        t0, 17
  csrw      CSR_MHPMEVENT6, t0       # L1 D-Cache Access
  li        t0, 9
  csrw      CSR_MHPMEVENT7, t0       # Branch Instr
  li        t0, 10
  csrw      CSR_MHPMEVENT8, t0       # Branch Mispredict + Unpredicted

# Reset counters to zero
  csrw      CSR_MHPMCOUNTER3, zero
  csrw      CSR_MHPMCOUNTER4, zero
  csrw      CSR_MHPMCOUNTER5, zero
  csrw      CSR_MHPMCOUNTER6, zero
  csrw      CSR_MHPMCOUNTER7, zero
  csrw      CSR_MHPMCOUNTER8, zero

# Enable counting
  li        t0, -1
  csrw      mcounteren, t0
  csrw      CSR_MCOUNTINHIBIT, zero

# ---------------------------------------------------------
# INITIAL SNAPSHOT OF PERFORMANCE COUNTERS
# ---------------------------------------------------------
  csrr      t0, CSR_MCYCLE
  sd        t0, 0(sp)                # Cycle Start
  csrr      t0, CSR_MINSTRET
  sd        t0, 8(sp)                # Instret Start
  csrr      t0, CSR_MHPMCOUNTER3
  sd        t0, 16(sp)               # HPM3 Start
  csrr      t0, CSR_MHPMCOUNTER4
  sd        t0, 24(sp)               # HPM4 Start
  csrr      t0, CSR_MHPMCOUNTER5
  sd        t0, 32(sp)               # HPM5 Start
  csrr      t0, CSR_MHPMCOUNTER6
  sd        t0, 40(sp)               # HPM6 Start
  csrr      t0, CSR_MHPMCOUNTER7
  sd        t0, 48(sp)               # HPM7 Start
  csrr      t0, CSR_MHPMCOUNTER8
  sd        t0, 56(sp)               # HPM8 Start

# ---------------------------------------------------------
# MAIN PROGRAM
# ---------------------------------------------------------
  nop
# ---------------------------------------------------------
# SECTION 1 - Initialize integer registers
# Hits IntALU (li expands to lui+addiw or just addi).
# ---------------------------------------------------------
  li        t0, 0x1234
  li        t1, 0x00FF
  li        t2, 0xAAAA
  li        t3, 0x5555
  li        t4, 0x3F800000           # IEEE-754 single 1.0
  li        t5, 0x40000000           # IEEE-754 single 2.0
  li        a4, 0x00000010           # 16
  li        a5, 0x00000004           # 4
  li        a6, 0xFFFFFFFF           # all-ones (sign-extends to 64-bit)
  li        a7, 0x0000FFFF

# ---------------------------------------------------------
# SECTION 2 - Move into FP regs and build doubles
# FloatMisc (fmv.w.x), then FPCvt (fcvt.d.s) to populate doubles.
# ---------------------------------------------------------
  fmv.w.x   f0, t4                   # f0 = 1.0f
  fmv.w.x   f1, t5                   # f1 = 2.0f
  fcvt.d.s  f2, f0                   # f2 = 1.0 (double)
  fcvt.d.s  f3, f1                   # f3 = 2.0 (double)

# ---------------------------------------------------------
# SECTION 3 - Integer ALU, register-register
# ---------------------------------------------------------
  add       s0, a4, a5               # 0x14
  sub       s1, a4, a5               # 0x0C
  sll       s2, a4, a5               # 0x100
  srl       s3, a4, a5               # 0x1
  sra       s4, a6, a5               # signed >>4
  and       s5, a6, a7
  or        s6, a4, a7
  xor       s7, a4, a7
  slt       s8, a5, a4
  sltu      s9, a5, a4

# ---------------------------------------------------------
# SECTION 4 - Integer ALU, immediate form
# ---------------------------------------------------------
  addi      s0, a4, 100
  slli      s1, a4, 2
  srli      s2, a4, 1
  srai      s3, a6, 4
  andi      s4, a4, 0xFF
  ori       s5, a4, 0x0F
  xori      s6, a4, 0xF0
  slti      s7, a5, 16
  sltiu     s8, a5, 16

# ---------------------------------------------------------
# SECTION 5 - RV64 word-form ALU
# ---------------------------------------------------------
  addw      s0, a4, a5
  subw      s1, a4, a5
  sllw      s2, a4, a5
  srlw      s3, a4, a5
  addiw     s4, a4, 100

# ---------------------------------------------------------
# SECTION 6 - Multiply
# multiplier.sv has one pipeline register, fully pipelined.
# ---------------------------------------------------------
  mul       s2, t0, t1
  mulh      s3, t0, t1
  mulhsu    s4, t0, t1
  mulhu     s5, t0, t1
  mulw      s6, t0, t1

# ---------------------------------------------------------
# SECTION 7 - Divide
# Coverage only. int_div is the test that measures the latency.
# ---------------------------------------------------------
  div       s6, t2, t1
  divu      s7, t2, t1
  rem       t0, t2, t1
  remu      t1, t2, t1
  divw      s2, t2, t1

# ---------------------------------------------------------
# SECTION 8 - FP single-precision basic
# ---------------------------------------------------------
  fadd.s    f4, f0, f1
  fsub.s    f5, f1, f0
  fmul.s    f6, f0, f1
  fdiv.s    f7, f0, f1
  fsqrt.s   f8, f1
  feq.s     t0, f0, f1
  flt.s     t1, f0, f1
  fle.s     t2, f0, f1

# ---------------------------------------------------------
# SECTION 9 - FP fused multiply-add
# ---------------------------------------------------------
  fmadd.s   f9, f0, f1, f4
  fmsub.s   f10, f0, f1, f4
  fnmadd.s  f11, f0, f1, f4
  fnmsub.s  f12, f0, f1, f4

# ---------------------------------------------------------
# SECTION 10 - FP sign / min / max / class
# ---------------------------------------------------------
  fsgnj.s   f13, f0, f1
  fsgnjn.s  f14, f0, f1
  fsgnjx.s  f15, f0, f1
  fmin.s    f16, f0, f1
  fmax.s    f17, f0, f1
  fclass.s  s0, f0

# ---------------------------------------------------------
# SECTION 11 - Int <-> FP conversions
# ---------------------------------------------------------
  fcvt.w.s  s1, f0
  fcvt.wu.s s2, f0
  fcvt.s.w  f18, a4
  fcvt.s.wu f19, a4
  fcvt.s.d  f20, f2
  fcvt.d.w  f21, a4

# ---------------------------------------------------------
# SECTION 12 - FP double-precision
# ---------------------------------------------------------
  fadd.d    f22, f2, f3
  fsub.d    f23, f3, f2
  fmul.d    f24, f2, f3
  fdiv.d    f25, f2, f3
  fsqrt.d   f26, f3
  feq.d     t3, f2, f3
  flt.d     t4, f2, f3
  fle.d     t5, f2, f3

# ---------------------------------------------------------
# SECTION 13 - Compressed arithmetic (RVC)
# ---------------------------------------------------------
  addi      s1, s1, 1                # uncompressed reference
  c.addi    s1, 1                    # compressed equivalent
  c.li      s2, 0x7
  c.add     s1, s2
  c.sub     s1, s0
  c.and     s1, s0
  c.or      s1, s0
  c.xor     s1, s0
  c.mv      s3, s1
# ---------------------------------------------------------
# END OF MAIN PROGRAM
# ---------------------------------------------------------

# ---------------------------------------------------------
# FINAL SNAPSHOT OF PERFORMANCE COUNTERS
# ---------------------------------------------------------
# x18 (s2) = Cycles
  csrr      s2, CSR_MCYCLE
  ld        t0, 0(sp)
  sub       s2, s2, t0

# x19 (s3) = Instructions
  csrr      s3, CSR_MINSTRET
  ld        t0, 8(sp)
  sub       s3, s3, t0

# x20 (s4) = I-Cache Miss
  csrr      s4, CSR_MHPMCOUNTER3
  ld        t0, 16(sp)
  sub       s4, s4, t0

# x21 (s5) = D-Cache Miss
  csrr      s5, CSR_MHPMCOUNTER4
  ld        t0, 24(sp)
  sub       s5, s5, t0

# x22 (s6) = I-Cache Access
  csrr      s6, CSR_MHPMCOUNTER5
  ld        t0, 32(sp)
  sub       s6, s6, t0

# x23 (s7) = D-Cache Access
  csrr      s7, CSR_MHPMCOUNTER6
  ld        t0, 40(sp)
  sub       s7, s7, t0

# x24 (s8) = Branches
  csrr      s8, CSR_MHPMCOUNTER7
  ld        t0, 48(sp)
  sub       s8, s8, t0

# x25 (s9) = Branch Miss + Unpred
  csrr      s9, CSR_MHPMCOUNTER8
  ld        t0, 56(sp)
  sub       s9, s9, t0

  addi      sp, sp, 80

# ---------------------------------------------------------
# TIME CALCULATION
# ---------------------------------------------------------
  li        t0, 1000000
  mul       s10, s2, t0              # s10 = Cycles (s2) * 1M
  li        t0, CPU_FREQ
  divu      s10, s10, t0             # s10 = s10 / Freq

# ---------------------------------------------------------
# EXIT
# ---------------------------------------------------------
  li        a0, 0
  jal       exit

# ---------------------------------------------------------
# DATA SECTION
# ---------------------------------------------------------

  .section  .bss
  .align    4
  .space    1024
stack_top:

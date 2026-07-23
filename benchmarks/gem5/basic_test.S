  .section  .text
  .global   main

main:
  li        a0, 0
  li        a1, 0
  call      m5_reset_stats

# -----------------------------------------------------------
# MAIN PROGRAM
# -----------------------------------------------------------
  nop
# -----------------------------------------------------------
# SECTION 1 - Initialize integer registers
# Hits IntALU (li expands to lui+addiw or just addi).
# -----------------------------------------------------------
  li        t0, 0x1234
  li        t1, 0x00FF
  li        t2, 0xAAAA
  li        t3, 0x5555
  li        t4, 0x3F800000  # IEEE-754 single 1.0
  li        t5, 0x40000000  # IEEE-754 single 2.0
  li        a4, 0x00000010  # 16
  li        a5, 0x00000004  # 4
  li        a6, 0xFFFFFFFF  # all-ones (sign-extends to 64-bit)
  li        a7, 0x0000FFFF

# -----------------------------------------------------------
# SECTION 2 - Move into FP regs and build doubles
# FloatMisc (fmv.w.x), then FPCvt (fcvt.d.s) to populate doubles.
# -----------------------------------------------------------
  fmv.w.x   f0, t4          # f0 = 1.0f
  fmv.w.x   f1, t5          # f1 = 2.0f
  fcvt.d.s  f2, f0          # f2 = 1.0 (double)
  fcvt.d.s  f3, f1          # f3 = 2.0 (double)

# -----------------------------------------------------------
# SECTION 3 - Integer ALU, register-register
# -----------------------------------------------------------
  add       s0, a4, a5      # 0x14
  sub       s1, a4, a5      # 0x0C
  sll       s2, a4, a5      # 0x100
  srl       s3, a4, a5      # 0x1
  sra       s4, a6, a5      # signed >>4
  and       s5, a6, a7
  or        s6, a4, a7
  xor       s7, a4, a7
  slt       s8, a5, a4
  sltu      s9, a5, a4

# -----------------------------------------------------------
# SECTION 4 - Integer ALU, immediate form
# -----------------------------------------------------------
  addi      s0, a4, 100
  slli      s1, a4, 2
  srli      s2, a4, 1
  srai      s3, a6, 4
  andi      s4, a4, 0xFF
  ori       s5, a4, 0x0F
  xori      s6, a4, 0xF0
  slti      s7, a5, 16
  sltiu     s8, a5, 16

# -----------------------------------------------------------
# SECTION 5 - RV64 word-form ALU
# -----------------------------------------------------------
  addw      s0, a4, a5
  subw      s1, a4, a5
  sllw      s2, a4, a5
  srlw      s3, a4, a5
  addiw     s4, a4, 100

# -----------------------------------------------------------
# SECTION 6 - Multiply
# multiplier.sv has one pipeline register, fully pipelined.
# -----------------------------------------------------------
  mul       s2, t0, t1
  mulh      s3, t0, t1
  mulhsu    s4, t0, t1
  mulhu     s5, t0, t1
  mulw      s6, t0, t1

# -----------------------------------------------------------
# SECTION 7 - Divide
# Coverage only. int_div is the test that measures the latency.
# -----------------------------------------------------------
  div       s6, t2, t1
  divu      s7, t2, t1
  rem       t0, t2, t1
  remu      t1, t2, t1
  divw      s2, t2, t1

# -----------------------------------------------------------
# SECTION 8 - FP single-precision basic
# -----------------------------------------------------------
  fadd.s    f4, f0, f1
  fsub.s    f5, f1, f0
  fmul.s    f6, f0, f1
  fdiv.s    f7, f0, f1
  fsqrt.s   f8, f1
  feq.s     t0, f0, f1
  flt.s     t1, f0, f1
  fle.s     t2, f0, f1

# -----------------------------------------------------------
# SECTION 9 - FP fused multiply-add
# -----------------------------------------------------------
  fmadd.s   f9, f0, f1, f4
  fmsub.s   f10, f0, f1, f4
  fnmadd.s  f11, f0, f1, f4
  fnmsub.s  f12, f0, f1, f4

# -----------------------------------------------------------
# SECTION 10 - FP sign / min / max / class
# -----------------------------------------------------------
  fsgnj.s   f13, f0, f1
  fsgnjn.s  f14, f0, f1
  fsgnjx.s  f15, f0, f1
  fmin.s    f16, f0, f1
  fmax.s    f17, f0, f1
  fclass.s  s0, f0

# -----------------------------------------------------------
# SECTION 11 - Int <-> FP conversions
# -----------------------------------------------------------
  fcvt.w.s  s1, f0
  fcvt.wu.s s2, f0
  fcvt.s.w  f18, a4
  fcvt.s.wu f19, a4
  fcvt.s.d  f20, f2
  fcvt.d.w  f21, a4

# -----------------------------------------------------------
# SECTION 12 - FP double-precision
# -----------------------------------------------------------
  fadd.d    f22, f2, f3
  fsub.d    f23, f3, f2
  fmul.d    f24, f2, f3
  fdiv.d    f25, f2, f3
  fsqrt.d   f26, f3
  feq.d     t3, f2, f3
  flt.d     t4, f2, f3
  fle.d     t5, f2, f3

# -----------------------------------------------------------
# SECTION 13 - Compressed arithmetic (RVC)
# -----------------------------------------------------------
  addi      s1, s1, 1       # uncompressed reference
  c.addi    s1, 1           # compressed equivalent
  c.li      s2, 0x7
  c.add     s1, s2
  c.sub     s1, s0
  c.and     s1, s0
  c.or      s1, s0
  c.xor     s1, s0
  c.mv      s3, s1
# -----------------------------------------------------------
# END OF MAIN PROGRAM
# -----------------------------------------------------------

  li        a0, 0
  li        a1, 0
  call      m5_dump_stats

# PADDING
  .rept     50
  nop
  .endr

  call      m5_exit

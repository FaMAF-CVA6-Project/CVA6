.section .text
.global main

# Direcciones CSR
.equ CSR_MCOUNTINHIBIT, 0x320
.equ CSR_MHPMEVENT3,    0x323
.equ CSR_MHPMEVENT4,    0x324
.equ CSR_MHPMEVENT5,    0x325
.equ CSR_MHPMEVENT6,    0x326
.equ CSR_MHPMEVENT7,    0x327
.equ CSR_MHPMEVENT8,    0x328

.equ CSR_MCYCLE,        0xB00
.equ CSR_MINSTRET,      0xB02
.equ CSR_MHPMCOUNTER3,  0xB03
.equ CSR_MHPMCOUNTER4,  0xB04
.equ CSR_MHPMCOUNTER5,  0xB05
.equ CSR_MHPMCOUNTER6,  0xB06
.equ CSR_MHPMCOUNTER7,  0xB07
.equ CSR_MHPMCOUNTER8,  0xB08

# Constantes de cálculo
.equ CPU_FREQ,          50000000  # 50 MHz

main:
  # ---------------------------------------------------------
  # CONFIGURACIÓN DEL PMU (PERFORMANCE MONITOR UNIT)
  # --------------------------------------------------------- 
  # Pausar todos los contadores
  addi    sp, sp, -80
  li      t0, -1
  csrw    CSR_MCOUNTINHIBIT, t0

  # Configurar Eventos
  li      t0, 1
  csrw    CSR_MHPMEVENT3, t0    # L1 I-Cache Miss
  li      t0, 2
  csrw    CSR_MHPMEVENT4, t0    # L1 D-Cache Miss
  li      t0, 16
  csrw    CSR_MHPMEVENT5, t0    # L1 I-Cache Access
  li      t0, 17
  csrw    CSR_MHPMEVENT6, t0    # L1 D-Cache Access
  li      t0, 9
  csrw    CSR_MHPMEVENT7, t0    # Branch Instr
  li      t0, 10
  csrw    CSR_MHPMEVENT8, t0    # Branch Mispredict + Unpredicted

  # Resetear contadores a 0
  csrw    CSR_MHPMCOUNTER3, zero
  csrw    CSR_MHPMCOUNTER4, zero
  csrw    CSR_MHPMCOUNTER5, zero
  csrw    CSR_MHPMCOUNTER6, zero
  csrw    CSR_MHPMCOUNTER7, zero
  csrw    CSR_MHPMCOUNTER8, zero

  # Habilitar acceso a contadores
  li      t0, -1
  csrw    mcounteren, t0
  csrw    CSR_MCOUNTINHIBIT, zero

  # ---------------------------------------------------------
  # SNAPSHOT INICIAL
  # ---------------------------------------------------------
  csrr    t0, CSR_MCYCLE
  sd      t0, 0(sp)       # Guardar Cycle Start
  csrr    t0, CSR_MINSTRET
  sd      t0, 8(sp)       # Guardar Instret Start
  csrr    t0, CSR_MHPMCOUNTER3
  sd      t0, 16(sp)      # Guardar HPM3 Start
  csrr    t0, CSR_MHPMCOUNTER4
  sd      t0, 24(sp)      # Guardar HPM4 Start
  csrr    t0, CSR_MHPMCOUNTER5
  sd      t0, 32(sp)      # Guardar HPM5 Start
  csrr    t0, CSR_MHPMCOUNTER6
  sd      t0, 40(sp)      # Guardar HPM6 Start
  csrr    t0, CSR_MHPMCOUNTER7
  sd      t0, 48(sp)      # Guardar HPM7 Start
  csrr    t0, CSR_MHPMCOUNTER8
  sd      t0, 56(sp)      # Guardar HPM8 Start

  # ---------------------------------------------------------
  # PROGRAMA
  # ---------------------------------------------------------
  addi    sp, sp, -64

  #--------------------------------------------------
  # Initializing Registers
  #--------------------------------------------------
  li      t0, 0x1234
  li      t1, 0x00FF
  li      t2, 0xAAAA
  li      t3, 0x5555
  li      t4, 0x3F800000
  li      t5, 0x40000000
  li      a4, 0x00000010    
  li      a5, 0x00000004    
  li      a6, 0xFFFFFFFF     
  li      a7, 0x0000FFFF     
  fmv.w.x f0, t4
  fmv.w.x f1, t5

  #--------------------------------------------------
  # Integer ALU
  #--------------------------------------------------
  add   s0, a4, a5              # s0 = 0x14
  sub   s1, a4, a5              # s1 = 0x0C
  sll   s2, a4, a5              # s2 = 0x10 << 4 = 0x100
  srl   s3, a4, a5              # s3 = 0x10 >> 4 = 0x1
  sra   s4, a6, a5              # s4 = signed shift right = 0xFFFFFFFF
  and   s5, a6, a7              # s5 = 0xFFFF
  or    s6, a4, a7              # s6 = 0x10 | 0xFFFF = 0xFFFF
  xor   s7, a4, a7              # s7 = 0x10 ^ 0xFFFF = 0xFFEF
  slt   s8, a5, a4              # s8 = 1 (4 < 16 signed)
  sltu  s9, a5, a4              # s9 = 1 (4 < 16 unsigned)

  #--------------------------------------------------
  # Multiply
  #--------------------------------------------------
  mul     s2, t0, t1            # s2 = low64(t0*t1)
  mulh    s3, t0, t1            # s3 = high64 signed
  mulhsu  s4, t0, t1            # s4 = high64 mixed
  mulhu   s5, t0, t1            # s5 = high64 unsigned
  div     s6, t2, t1            # s6 = t2 / t1 (signed)
  divu    s7, t2, t1            # s7 = t2 / t1 (unsigned)
  rem     t0, t2, t1            # t0 = t2 % t1 (signed)
  remu    t1, t2, t1            # t1 = t2 % t1 (unsigned)

  #--------------------------------------------------
  # Floating-point single-precision
  #--------------------------------------------------
  fadd.s  f4, f0, f1            # 1.0 + 2.0 = 3.0
  fsub.s  f5, f1, f0            # 2.0 - 1.0 = 1.0
  fmul.s  f6, f0, f1            # 1.0 * 2.0 = 2.0
  fdiv.s  f7, f0, f1            # 1.0 / 2.0 = 0.5
  fsqrt.s f8, f1                # sqrt(2.0)
  feq.s   t0, f0, f1            # t0 = (1.0 == 2.0)
  flt.s   t1, f0, f1            # t1 = (1.0 < 2.0)
  fle.s   t2, f0, f1            # t2 = (1.0 <= 2.0)

  #--------------------------------------------------
  # Floating-point double-precision
  #--------------------------------------------------
  fadd.d  f9,  f2, f3           # 1.0 + 2.0
  fsub.d  f10, f3, f2           # 2.0 - 1.0
  fmul.d  f11, f2, f3           # 1.0 * 2.0
  fdiv.d  f12, f2, f3           # 1.0 / 2.0
  fsqrt.d f13, f3               # sqrt(2.0)
  feq.d   t3, f2, f3            # t3 = (1.0 == 2.0)
  flt.d   t4, f2, f3            # t4 = (1.0 < 2.0)
  fle.d   t5, f2, f3            # t5 = (1.0 <= 2.0)

  #--------------------------------------------------
  # Compressed Instructions
  #--------------------------------------------------
  addi    s1, s1, 1             # uncompressed
  c.addi  s1, 1                 # compressed equivalent
  c.li    s2, 0x7               # load immediate
  c.lwsp  s3, 0(sp)             # load word from stack pointer
  c.swsp  s3, 4(sp)             # store word to stack
  li      t4, 0x3F800000
  li      t5, 0x40000000 
  fmv.w.x f0, t4
  fmv.w.x f1, t5

  #--------------------------------------------------
  # Atomic operations
  #--------------------------------------------------
  la      a0, atomic_var        # a0 = &atomic_var
  lr.d    a1, (a0)              # a1 = *a0 (load-reserved)
  addi    a2, a1, 5             # a2 = a1 + 5
  sc.d    a3, a2, (a0)          # store-conditional
  amoadd.d a4, a2, (a0)         # atomic add
  amoxor.d a5, a2, (a0)         # atomic xor
  amoor.d  a6, a2, (a0)         # atomic or
  amoand.d a7, a2, (a0)         # atomic and
  amomax.d s1, a2, (a0)         # atomic max

  # ---------------------------------------------------------
  # SINCRONIZACIÓN (Memory Fence)
  # ---------------------------------------------------------
  # Restauramos el SP original (donde están guardados los contadores)
  addi    sp, sp, 64
  fence

  # ---------------------------------------------------------
  # SNAPSHOT FINAL Y CÁLCULO DE DIFERENCIAS
  # ---------------------------------------------------------
  # x18 (s2) = Cycles
  csrr    s2, CSR_MCYCLE
  ld      t0, 0(sp)
  sub     s2, s2, t0

  # x19 (s3) = Instructions
  csrr    s3, CSR_MINSTRET
  ld      t0, 8(sp)
  sub     s3, s3, t0

  # x20 (s4) = I-Cache Miss
  csrr    s4, CSR_MHPMCOUNTER3
  ld      t0, 16(sp)
  sub     s4, s4, t0

  # x21 (s5) = D-Cache Miss
  csrr    s5, CSR_MHPMCOUNTER4
  ld      t0, 24(sp)
  sub     s5, s5, t0

  # x22 (s6) = I-Cache Access
  csrr    s6, CSR_MHPMCOUNTER5
  ld      t0, 32(sp)
  sub     s6, s6, t0

  # x23 (s7) = D-Cache Access
  csrr    s7, CSR_MHPMCOUNTER6
  ld      t0, 40(sp)
  sub     s7, s7, t0

  # x24 (s8) = Branches
  csrr    s8, CSR_MHPMCOUNTER7
  ld      t0, 48(sp)
  sub     s8, s8, t0

  # x25 (s9) = Branch Miss + Unpred
  csrr    s9, CSR_MHPMCOUNTER8
  ld      t0, 56(sp)
  sub     s9, s9, t0

  # Restaurar Stack Pointer
  addi    sp, sp, 80

  # ---------------------------------------------------------
  # CÁLCULO TIEMPO (us) -> x26 (s10)
  # ---------------------------------------------------------
  li      t0, 1000000
  mul     s10, s2, t0      # s10 = Cycles (s2) * 1M
  li      t0, CPU_FREQ
  divu    s10, s10, t0     # s10 = s10 / Freq

  # ---------------------------------------------------------
  # SALIDA
  # ---------------------------------------------------------
  li      a0, 0
  jal     exit

# ---------------------------------------------------------
# SECCION DE DATOS Y STACK
# ---------------------------------------------------------
.section .data
.align 4
atomic_var: 
    .dword 0    # Variable para las operaciones atómicas

.section .bss
.align 4
    .space 1024
stack_top:

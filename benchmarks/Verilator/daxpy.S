.data
  N:      .dword 4096          # Tamaño de los vectores
  Alpha:  .dword 2             # Escalar a multiplicar

.bss
  .align 3
  X: .zero 32768               # Vector X (4096)*8 bytes
  Y: .zero 32768               # Vector Y (4096)*8 bytes
  Z: .zero 32768               # Vector Z (4096)*8 bytes

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
  # Cargar valores iniciales
  la t0, N                     # Dirección de N
  ld t1, 0(t0)                 # t1 = N

  la t2, Alpha                 # Dirección de Alpha
  ld t3, 0(t2)                 # t3 = Alpha (entero)
  fcvt.d.l f10, t3             # f10 = (double) Alpha

  la s2, X                     # Base de X
  la s3, Y                     # Base de Y
  la s4, Z                     # Base de Z

  mv s5, s2                    # Offset X -> s5
  mv s6, s3                    # Offset Y -> s6
  mv s7, s4                    # Offset Z -> s7

  li t4, 0                     # i = 0 (contador)

.align 4 
loop:
  fld f5, 0(s5)                # f5 = X[i]
  fld f6, 0(s6)                # f6 = Y[i]
  fmul.d f7, f10, f5           # f7 = alpha * X[i]
  fadd.d f8, f7, f6            # f8 = f7 + Y[i]
  fsd f8, 0(s7)                # Z[i] = f8

  addi s5, s5, 8               # avanzar en X
  addi s6, s6, 8               # avanzar en Y
  addi s7, s7, 8               # avanzar en Z

  addi t4, t4, 1               # i++
  blt  t4, t1, loop            # while i < N

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
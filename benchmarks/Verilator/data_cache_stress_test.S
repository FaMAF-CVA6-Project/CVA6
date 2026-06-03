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
.equ BUFFER_SIZE,       16384     # Tamaño del buffer en bytes (16KB)
.equ STRIDE_SIZE,       64        # Salto grande para romper localidad (64 bytes = cache line común)

main:
  # ---------------------------------------------------------
  # INICIALIZACIÓN DE STACK Y BASE
  # ---------------------------------------------------------
  la      sp, stack_top           # Configurar Stack Pointer

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
  csrw    CSR_MHPMEVENT8, t0    # Branch Mispredict

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
  # Cargar dirección base del buffer de datos
  la      a0, data_buffer
  li      a1, BUFFER_SIZE
  add     a2, a0, a1              # a2 = Dirección final del buffer

  # LINEAR WRITE (Warm-up & Dirty Lines)
  mv      t0, a0                  # t0 = puntero actual
loop_write_linear:
  bge     t0, a2, end_phase_1
  li      t1, 0xAA55              # Dato patrón
  sw      t1, 0(t0)               # Store Word
  addi    t0, t0, 4               # Siguiente palabra
  j       loop_write_linear
end_phase_1:

  # STRIDED READ (Force Misses)
  mv      t0, a0
  li      t2, STRIDE_SIZE         # Salto de 64 bytes
loop_read_stride:
  bge     t0, a2, end_phase_2
  lw      t1, 0(t0)               # Load Word (fuerza acceso a D-Cache)
  add     t0, t0, t2              # Salto grande
  j       loop_read_stride
end_phase_2:

  # THRASHING (Read-Modify-Write Conflict)
  li      s11, 200          
loop_outer_thrash:
    
  addi    t0, a2, -4              
loop_inner_thrash:
  blt     t0, a0, end_inner_thrash
  lw      t1, 0(t0)               
  addi    t1, t1, 1               
  sw      t1, 0(t0)               
  addi    t0, t0, -128            
  j       loop_inner_thrash
end_inner_thrash:

  addi    s11, s11, -1
  bnez    s11, loop_outer_thrash

  # ---------------------------------------------------------
  # SINCRONIZACIÓN (Memory Fence)
  # ---------------------------------------------------------
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

  # x25 (s9) = Branch Miss
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
  # SECCIÓN DE DATOS (BSS)
  # ---------------------------------------------------------
.section .bss
.align 4
  # Definimos un buffer grande (64KB) para exceder la cache L1 típica (16-32KB)
  .comm data_buffer, 65536, 4 
    
  # Stack simple
  .comm stack_space, 4096, 4
stack_top:

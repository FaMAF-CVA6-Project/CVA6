.section .data
.align 6

my_array:
.dword 0xA0A0A0A0A0A0A0A0
.dword 0xA8A8A8A8A8A8A8A8  # Offset 8   (Será leído por t2)
.zero 48                   # Rellenamos los 48 bytes restantes de la línea (64 - 16 = 48)

# --- Línea de Caché 1 (Offsets 64 al 127) ---
.dword 0xB0B0B0B0B0B0B0B0  # Offset 64  (Será leído por t1)
.dword 0xB8B8B8B8B8B8B8B8  # Offset 72  (Será leído por t5)
.zero 48                   # Rellenamos

# --- Línea de Caché 2 (Offsets 128 al 191) ---
.dword 0xC0C0C0C0C0C0C0C0  # Offset 128 (Será leído por t3)
.zero 56                   # Rellenamos los 56 bytes restantes (64 - 8 = 56)

# --- Línea de Caché 3 (Offsets 192 al 255) ---
.dword 0xD0D0D0D0D0D0D0D0  # Offset 192 (Será leído por t4)
.dword 0xD8D8D8D8D8D8D8D8  # Offset 200 (Será leído por t6)
.zero 48

# --- Línea de Caché 4 (Offsets 256 al 319) ---
.dword 0xE0E0E0E0E0E0E0E0  # Offset 256 (Será leído por a1)
.dword 0xE8E8E8E8E8E8E8E8  # Offset 264 (Será leído por a4)
.zero 48

# --- Línea de Caché 5 (Offsets 320 al 383) ---
.dword 0xF0F0F0F0F0F0F0F0  # Offset 320 (Será leído por a2)
.zero 56

# --- Línea de Caché 6 (Offsets 384 al 447) ---
.dword 0x1111111111111111  # Offset 384 (Será leído por a3)
.dword 0x1818181818181818  # Offset 392 (Será leído por a5)
.zero 48

# --- Línea de Caché 7 (Offsets 448 al 511) ---
.dword 0x2222222222222222  # Offset 448 (Será leído por a6)
.dword 0x2828282828282828  # Offset 456 (Será leído por s2)
.zero 48

# --- Línea de Caché 8 (Offsets 512 al 575) ---
.dword 0x3333333333333333  # Offset 512 (Será leído por a7)
.zero 56

# --- Línea de Caché 9 (Offsets 576 al 639) ---
.dword 0x4444444444444444  # Offset 576 (Será leído por s1)
.zero 56

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
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop

  .align 4
  la a0, my_array
    
  ld t0, 0(a0)      # MISS 1: Trae los bytes del 0 al 63 a la caché
  ld t1, 64(a0)     # MISS 2: Trae los bytes del 64 al 127
  ld t2, 8(a0)      # HIT 1: Lee el byte 8. ¡Ya está en caché gracias al Miss 1!
  ld t3, 128(a0)    # MISS 3: Trae los bytes del 128 al 191
  ld t4, 192(a0)    # MISS 4: Trae los bytes del 192 al 255
  ld t5, 72(a0)     # HIT 2: Lee el byte 72. ¡Ya está en caché gracias al Miss 2!
  ld t6, 200(a0)    # HIT 3: Lee el byte 200. ¡Ya está en caché gracias al Miss 4!
  ld a1, 256(a0)    # MISS 5: Trae los bytes del 256 al 319
  ld a2, 320(a0)    # MISS 6: Trae los bytes del 320 al 383
  ld a3, 384(a0)    # MISS 7: Trae los bytes del 384 al 447
  ld a4, 264(a0)    # HIT 4: Dentro de la línea del Miss 5
  ld a5, 392(a0)    # HIT 5: Dentro de la línea del Miss 7
  ld a6, 448(a0)    # MISS 8: Trae los bytes del 448 al 511
  ld a7, 512(a0)    # MISS 9: Trae los bytes del 512 al 575
  ld s1, 576(a0)    # MISS 10: Trae los bytes del 576 al 639
  ld s2, 456(a0)    # HIT 6: Dentro de la línea del Miss 8
  sd s2, 64(a0)     # STORE

  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop
  nop

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
  .section  .text
  .global   main

main:
  li        a0, 0
  li        a1, 0
  call      m5_reset_stats

# -----------------------------------------------------------
# MAIN PROGRAM
# -----------------------------------------------------------
  la        a0, atomic_var
  li        t0, 0

# --- load-reserved / store-conditional ---
  .rept     16
  lr.d      a1, (a0)
  addi      a2, a1, 5
  sc.d      a3, a2, (a0)
  .endr

# --- atomic read-modify-write forms ---
  li        a2, 3
  .rept     16
  amoadd.d  a4, a2, (a0)
  amoxor.d  a5, a2, (a0)
  amoor.d   a6, a2, (a0)
  amoand.d  a7, a2, (a0)
  amomax.d  t1, a2, (a0)
  amomin.d  t2, a2, (a0)
  amoswap.d t3, a2, (a0)
  .endr

# --- fences, each of which flushes the CVA6 D-cache ---
  .rept     8
  sd        a2, 0(a0)
  fence
  ld        a3, 0(a0)
  .endr
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

  .section  .data
  .align    4
atomic_var:
  .dword    0

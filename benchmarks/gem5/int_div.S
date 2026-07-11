  .section .text
  .global  main

main:
  li       a0, 0
  li       a1, 0
  call     m5_reset_stats

# -----------------------------------------------------------
# MAIN PROGRAM
# -----------------------------------------------------------
  li   t0, 0x5DEECE66D
  li   t1, 0x12345
  .rept 60
  div  t0, t0, t1
  ori  t0, t0, 1
  .endr
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
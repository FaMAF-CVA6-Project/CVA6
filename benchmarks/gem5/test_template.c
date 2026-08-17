#include <gem5/m5ops.h>

#define BARE_ALIGN __attribute__((aligned(4096)))

int main(void)
{
#if defined(__riscv)
    __asm__ volatile(
        ".option push\n"
        ".option norelax\n"
        "1: auipc gp, %%pcrel_hi(__global_pointer$)\n"
        "   addi  gp, gp, %%pcrel_lo(1b)\n"
        ".option pop\n" ::: "gp");
#endif

    m5_reset_stats(0, 0);

    // MAIN PROGRAM
    __asm__ volatile("j 1770f; .balign 4096; 1770:" ::: "memory");
    // END OF MAIN PROGRAM

    m5_dump_stats(0, 0);

    m5_exit(0);
}
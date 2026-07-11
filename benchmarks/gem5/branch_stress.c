#include <gem5/m5ops.h>

static volatile int data[256];

__attribute__((noinline)) static int classify(int x)
{
    if (x < 0)
        return 0;
    if (x < 100)
        return 1;
    if (x < 1000)
        return 2;
    if (x < 5000)
        return 3;
    return 4;
}

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
    unsigned int seed = 0x12345678u;
    for (int i = 0; i < 256; i++)
    {
        seed = seed * 1103515245u + 12345u;
        data[i] = (int)(seed >> 8);
    }

    int counts[5] = {0, 0, 0, 0, 0};
    for (int iter = 0; iter < 10; iter++)
    {
        for (int i = 0; i < 256; i++)
        {
            counts[classify(data[i])]++;
        }
    }

    static volatile int sink;
    sink = counts[0] + counts[1] + counts[2] + counts[3] + counts[4];
    // END OF MAIN PROGRAM

    m5_dump_stats(0, 0);

    m5_exit(0);
}

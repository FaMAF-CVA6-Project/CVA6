#include <gem5/m5ops.h>

#define PHASE_A_REPS 64
#define PHASE_B_REPS 32
#define PHASE_C_REPS 32
#define PHASE_D_REPS 32

typedef int (*fn_t)(int);

static fn_t fn_table[8];

static int fn_0(int v) { return v + 1; }
static int fn_1(int v) { return v + 2; }
static int fn_2(int v) { return v ^ 3; }
static int fn_3(int v) { return v - 1; }
static int fn_4(int v) { return v + 5; }
static int fn_5(int v) { return v ^ 6; }
static int fn_6(int v) { return v - 3; }
static int fn_7(int v) { return v + 8; }

static int leaf_fn(int v) { return v + 1; }
static int nest_3(int v) { return leaf_fn(v) + 1; }
static int nest_2(int v) { return nest_3(v) + 1; }
static int nest_1(int v) { return nest_2(v) + 1; }

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
    unsigned int rs = 2463534242u;
    int acc = 0;

    fn_table[0] = fn_0;
    fn_table[1] = fn_1;
    fn_table[2] = fn_2;
    fn_table[3] = fn_3;
    fn_table[4] = fn_4;
    fn_table[5] = fn_5;
    fn_table[6] = fn_6;
    fn_table[7] = fn_7;

    // Phase A: well predicted loops. The backward branch is taken 63 times
    // out of 64, so the 2-bit counters saturate and stay saturated. This is
    // the accuracy baseline for the BHT
    for (int rep = 0; rep < PHASE_A_REPS; rep++)
    {
        for (int i = 0; i < 64; i++)
        {
            acc += (i & 3);
        }
    }

    // Phase B: data dependent conditionals. The xorshift bits are close to
    // random, so each if is about 50 per cent taken and the 2-bit counters
    // thrash. Three distinct branch sites per iteration exercise separate
    // BHT indices. The generator is expanded inline so that this phase
    // contains no calls and does not disturb the RAS
    for (int rep = 0; rep < PHASE_B_REPS; rep++)
    {
        for (int i = 0; i < 64; i++)
        {
            rs ^= rs << 13;
            rs ^= rs >> 17;
            rs ^= rs << 5;

            if (rs & 1u)
                acc += 3;
            else
                acc -= 1;

            if (rs & 2u)
                acc ^= 5;

            if (rs & 4u)
                acc += 7;
            else
                acc -= 2;
        }
    }

    // Phase C: indirect calls through a function pointer table. One call site
    // whose target rotates over eight functions, so the BTB entry for that PC
    // is overwritten constantly and most target predictions miss
    for (int rep = 0; rep < PHASE_C_REPS; rep++)
    {
        for (int i = 0; i < 32; i++)
        {
            rs ^= rs << 13;
            rs ^= rs >> 17;
            rs ^= rs << 5;

            acc = fn_table[rs & 7u](acc);
        }
    }

    // Phase D: call nesting four deep against a depth 2 RAS. The two inner
    // returns find the stack already overwritten, so they mispredict, while
    // the two outer ones hit
    for (int rep = 0; rep < PHASE_D_REPS; rep++)
    {
        for (int i = 0; i < 32; i++)
        {
            acc += nest_1(i);
        }
    }

    static volatile int sink;
    sink = acc;
    // END OF MAIN PROGRAM

    m5_dump_stats(0, 0);

    m5_exit(0);
}

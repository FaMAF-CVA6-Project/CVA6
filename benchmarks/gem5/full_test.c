#include <gem5/m5ops.h>

// Sized against the CVA6 32 KiB 8-way D-cache. fp_x and fp_y are 4 KiB each
// and stream is 32 KiB, so the working set is 40 KiB and cannot all be held,
// which keeps the streaming phases missing rather than warming up once and
// hitting for ever. stream is walked with SP_STRIDE, which is one 16-byte
// cache line, so each access lands on a fresh line and produces a miss for
// every iteration rather than one in four. That buys the D-cache miss signal
// at a quarter of the instruction count, which keeps the traces inside the
// 500 MB the viewers can load.
#define SP_VEC 512
#define SP_STREAM 8192
#define SP_STRIDE 4
#define SP_MM_N 8

#define SP_FP_REPS 2
#define SP_MM_REPS 2
#define SP_BR_REPS 8
#define SP_ST_REPS 2

static double fp_x[SP_VEC];
static double fp_y[SP_VEC];
static int stream[SP_STREAM];
static int mm_a[SP_MM_N][SP_MM_N];
static int mm_b[SP_MM_N][SP_MM_N];
static volatile int mm_c[SP_MM_N][SP_MM_N];

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
    double fp_acc = 0.0;

    fn_table[0] = fn_0;
    fn_table[1] = fn_1;
    fn_table[2] = fn_2;
    fn_table[3] = fn_3;
    fn_table[4] = fn_4;
    fn_table[5] = fn_5;
    fn_table[6] = fn_6;
    fn_table[7] = fn_7;

    // Phase 1: initialisation. Every array is touched once, so this is the
    // cold miss phase, and the integer to double conversions exercise the
    // fpnew CONV group (LAT_CONV = 2) which no earlier kernel reached
    for (int i = 0; i < SP_VEC; i++)
    {
        fp_x[i] = (double)(i & 63) + 1.0;
        fp_y[i] = (double)(i & 31) + 2.0;
    }

    for (int i = 0; i < SP_STREAM; i += SP_STRIDE)
    {
        stream[i] = (i * 7) & 0xff;
    }

    for (int i = 0; i < SP_MM_N; i++)
    {
        for (int j = 0; j < SP_MM_N; j++)
        {
            mm_a[i][j] = (i * 7 + j * 3) & 0xff;
            mm_b[i][j] = (i * 5 + j * 11) & 0xff;
        }
    }

    // Phase 2: floating point vector update, the daxpy shape. Exercises the
    // fpnew ADDMUL group at LAT_COMP_FP64 = 3 and streams two arrays past the
    // D-cache, so it also leans on the miss penalty and the memory latency
    for (int rep = 0; rep < SP_FP_REPS; rep++)
    {
        double a = 2.5;
        for (int i = 0; i < SP_VEC; i++)
        {
            fp_y[i] = a * fp_x[i] + fp_y[i];
        }
    }

    // Phase 3: integer matrix multiply. Exercises the one cycle multiplier and
    // a working set small enough to hit, so the D-cache hit path and the stack
    // store-to-load collisions dominate here rather than the miss path
    for (int rep = 0; rep < SP_MM_REPS; rep++)
    {
        for (int i = 0; i < SP_MM_N; i++)
        {
            for (int j = 0; j < SP_MM_N; j++)
            {
                int sum = 0;
                for (int k = 0; k < SP_MM_N; k++)
                {
                    sum += mm_a[i][k] * mm_b[k][j];
                }
                mm_c[i][j] = sum;
            }
        }
    }

    // Phase 4a: well predicted loops. The BHT counters saturate and stay
    // saturated, so this is the branch accuracy baseline
    for (int rep = 0; rep < SP_BR_REPS; rep++)
    {
        for (int i = 0; i < 64; i++)
        {
            acc += (i & 3);
        }
    }

    // Phase 4b: data dependent conditionals. The xorshift bits are close to
    // random, so each if is about half taken and the 2-bit counters thrash.
    // The generator is inline so this phase contains no calls and leaves the
    // RAS alone
    for (int rep = 0; rep < SP_BR_REPS; rep++)
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

    // Phase 4c: indirect calls. One call site whose target rotates over eight
    // functions, so the BTB entry for that PC is overwritten constantly
    for (int rep = 0; rep < SP_BR_REPS; rep++)
    {
        for (int i = 0; i < 32; i++)
        {
            rs ^= rs << 13;
            rs ^= rs >> 17;
            rs ^= rs << 5;

            acc = fn_table[rs & 7u](acc);
        }
    }

    // Phase 4d: call nesting four deep against the depth 2 RAS, so the two
    // inner returns mispredict and the two outer ones hit
    for (int rep = 0; rep < SP_BR_REPS; rep++)
    {
        for (int i = 0; i < 32; i++)
        {
            acc += nest_1(i);
        }
    }

    // Phase 5: strided streaming read. A 32 KiB array walked one cache line at
    // a time, so every access misses. This is the clearest test of the miss
    // penalty, of the PLRU victim selection, and of how far MinorCPU's single
    // outstanding miss diverges from the HPDcache overlapping two
    for (int rep = 0; rep < SP_ST_REPS; rep++)
    {
        for (int i = 0; i < SP_STREAM; i += SP_STRIDE)
        {
            acc += stream[i];
        }
    }

    // Phase 6: everything at once. Unpredictable branches selecting between
    // floating point paths, an integer multiply, and a strided load, so no
    // single mechanism is isolated and the phases interact
    for (int i = 0; i < SP_VEC; i++)
    {
        rs ^= rs << 13;
        rs ^= rs >> 17;
        rs ^= rs << 5;

        if (rs & 1u)
            fp_acc += fp_y[i] * 0.5;
        else
            fp_acc -= fp_x[i];

        acc += stream[(i * SP_STRIDE) & (SP_STREAM - 1)] * (int)(i & 7u);
    }

    static volatile int sink;
    static volatile double fp_sink;
    sink = acc;
    fp_sink = fp_acc;
    // END OF MAIN PROGRAM

    m5_dump_stats(0, 0);

    m5_exit(0);
}
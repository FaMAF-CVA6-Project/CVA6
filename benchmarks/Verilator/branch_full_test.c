#include <stdint.h>
#include <string.h>
#include <limits.h>
#include <encoding.h>

#define uint64_t __uint64_t
#define CPU_FREQ_HZ 50000000ULL
#define asm __asm__

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

void configure_pmu()
{
    asm volatile("csrw 0x320, %0" ::"r"(-1));

    // Configure PMU to count specific events
    write_csr(mhpmevent3, 1);  // ID 1:  L1 I-Cache Misses
    write_csr(mhpmevent4, 2);  // ID 2:  L1 D-Cache Misses
    write_csr(mhpmevent5, 16); // ID 16: L1 I-Cache Access
    write_csr(mhpmevent6, 17); // ID 17: L1 D-Cache Access
    write_csr(mhpmevent7, 9);  // ID 9:  Branch Instr
    write_csr(mhpmevent8, 10); // ID 10: Branch Mispredict + Unpredicted

    asm volatile("li t0, -1");
    asm volatile("csrw mcounteren, t0");
    asm volatile("csrw 0x320, zero");
}

int main()
{
    configure_pmu();

    // Initial read of performance counters
    uint64_t start_cyc = read_csr(mcycle);
    uint64_t start_ins = read_csr(minstret);
    uint64_t start_hpm3 = read_csr(mhpmcounter3);
    uint64_t start_hpm4 = read_csr(mhpmcounter4);
    uint64_t start_hpm5 = read_csr(mhpmcounter5);
    uint64_t start_hpm6 = read_csr(mhpmcounter6);
    uint64_t start_hpm7 = read_csr(mhpmcounter7);
    uint64_t start_hpm8 = read_csr(mhpmcounter8);

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

    // Final read of performance counters
    uint64_t end_cyc = read_csr(mcycle);
    uint64_t end_ins = read_csr(minstret);
    uint64_t end_hpm3 = read_csr(mhpmcounter3);
    uint64_t end_hpm4 = read_csr(mhpmcounter4);
    uint64_t end_hpm5 = read_csr(mhpmcounter5);
    uint64_t end_hpm6 = read_csr(mhpmcounter6);
    uint64_t end_hpm7 = read_csr(mhpmcounter7);
    uint64_t end_hpm8 = read_csr(mhpmcounter8);

    // Calculate deltas
    uint64_t d_cyc = end_cyc - start_cyc;
    uint64_t d_ins = end_ins - start_ins;
    uint64_t d_ic_miss = end_hpm3 - start_hpm3;
    uint64_t d_dc_miss = end_hpm4 - start_hpm4;
    uint64_t d_ic_acc = end_hpm5 - start_hpm5;
    uint64_t d_dc_acc = end_hpm6 - start_hpm6;
    uint64_t d_br_inst = end_hpm7 - start_hpm7;
    uint64_t d_br_miss_unp = end_hpm8 - start_hpm8;
    uint64_t time_us = (d_cyc * 1000000) / CPU_FREQ_HZ;

    // Show results by moving them to registers and calling exit
    asm volatile(
        "mv s2, %0 \n\t"  // x18
        "mv s3, %1 \n\t"  // x19
        "mv s4, %2 \n\t"  // x20
        "mv s5, %3 \n\t"  // x21
        "mv s6, %4 \n\t"  // x22
        "mv s7, %5 \n\t"  // x23
        "mv s8, %6 \n\t"  // x24
        "mv s9, %7 \n\t"  // x25
        "mv s10, %8 \n\t" // x26

        "li a0, 0 \n\t"
        "jal    exit\n\t"
        :
        : "r"(d_cyc), "r"(d_ins), "r"(d_ic_miss), "r"(d_dc_miss),
          "r"(d_ic_acc), "r"(d_dc_acc), "r"(d_br_inst), "r"(d_br_miss_unp),
          "r"(time_us)
        : "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "t0");

    return 0;
}

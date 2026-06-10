/* fib_recursive — recursive Fibonacci.
 * Workload type: call/return-intensive. fib(15) makes 1597 recursive
 * calls and the same number of returns. The base-case branch is highly
 * predictable, so this test is really about the Return Address Stack
 * (RAS) predictor on jalr returns. */
#include <string.h>
#include <limits.h>
#include <encoding.h>

#define uint64_t __uint64_t
#define CPU_FREQ_HZ 50000000ULL
#define asm __asm__

static volatile int fib_result;

void configure_pmu() {
    asm volatile("csrw 0x320, %0" :: "r"(-1));

    write_csr(mhpmevent3, 1);
    write_csr(mhpmevent4, 2);
    write_csr(mhpmevent5, 16);
    write_csr(mhpmevent6, 17);
    write_csr(mhpmevent7, 9);
    write_csr(mhpmevent8, 10);

    asm volatile("li t0, -1");
    asm volatile("csrw mcounteren, t0");
    asm volatile("csrw 0x320, zero");
}

/* Standard recursive Fibonacci. The __attribute__((noinline)) prevents
 * the compiler from unrolling or memoising the recursion, which would
 * defeat the purpose of stressing call/return prediction. */
__attribute__((noinline)) static int fib(int n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}

int main() {
    configure_pmu();

    // Lectura Inicial
    uint64_t start_cyc = read_csr(mcycle);
    uint64_t start_ins = read_csr(minstret);
    uint64_t start_hpm3 = read_csr(mhpmcounter3);
    uint64_t start_hpm4 = read_csr(mhpmcounter4);
    uint64_t start_hpm5 = read_csr(mhpmcounter5);
    uint64_t start_hpm6 = read_csr(mhpmcounter6);
    uint64_t start_hpm7 = read_csr(mhpmcounter7);
    uint64_t start_hpm8 = read_csr(mhpmcounter8);

    // Programa: fib(15) = 610, with 1597 recursive calls and returns
    fib_result = fib(15);

    // Lectura Final
    uint64_t end_cyc = read_csr(mcycle);
    uint64_t end_ins = read_csr(minstret);
    uint64_t end_hpm3 = read_csr(mhpmcounter3);
    uint64_t end_hpm4 = read_csr(mhpmcounter4);
    uint64_t end_hpm5 = read_csr(mhpmcounter5);
    uint64_t end_hpm6 = read_csr(mhpmcounter6);
    uint64_t end_hpm7 = read_csr(mhpmcounter7);
    uint64_t end_hpm8 = read_csr(mhpmcounter8);

    // Calculo de Diferencias
    uint64_t d_cyc  = end_cyc - start_cyc;
    uint64_t d_ins  = end_ins - start_ins;
    uint64_t d_ic_miss = end_hpm3 - start_hpm3;
    uint64_t d_dc_miss = end_hpm4 - start_hpm4;
    uint64_t d_ic_acc  = end_hpm5 - start_hpm5;
    uint64_t d_dc_acc  = end_hpm6 - start_hpm6;
    uint64_t d_br_inst = end_hpm7 - start_hpm7;
    uint64_t d_br_miss_unp = end_hpm8 - start_hpm8;
    uint64_t time_us = (d_cyc * 1000000) / CPU_FREQ_HZ;

    // Mostrar Resultados
    asm volatile (
        "mv s2, %0 \n\t"
        "mv s3, %1 \n\t"
        "mv s4, %2 \n\t"
        "mv s5, %3 \n\t"
        "mv s6, %4 \n\t"
        "mv s7, %5 \n\t"
        "mv s8, %6 \n\t"
        "mv s9, %7 \n\t"
        "mv s10, %8 \n\t"
        "li a0, 0 \n\t"
        "jal    exit\n\t"
        :
        : "r"(d_cyc), "r"(d_ins), "r"(d_ic_miss), "r"(d_dc_miss),
          "r"(d_ic_acc), "r"(d_dc_acc), "r"(d_br_inst), "r"(d_br_miss_unp),
          "r"(time_us)
        : "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "t0"
    );
    return 0;
}

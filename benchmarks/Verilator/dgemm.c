/* dgemm — 16x16 double-precision matrix multiply (C = A * B).
 * Workload type: FPU compute-bound. Exercises fmadd / fmul / fadd,
 * register pressure on the FP regfile, nested loop control, and
 * D-cache locality (3 matrices x 2KB = 6KB total, fits in L1D). */
#include <string.h>
#include <limits.h>
#include <encoding.h>

#define uint64_t __uint64_t
#define CPU_FREQ_HZ 50000000ULL
#define asm __asm__

#define N 16

/* Global storage. A and B are pure inputs. C is declared volatile so
 * the compiler cannot dead-store-eliminate the kernel writes; every
 * fsd into C must execute. */
static double A[N][N];
static double B[N][N];
static volatile double C[N][N];

void configure_pmu() {
    asm volatile("csrw 0x320, %0" :: "r"(-1));

    write_csr(mhpmevent3, 1);   // ID 1:  L1 I-Cache Misses
    write_csr(mhpmevent4, 2);   // ID 2:  L1 D-Cache Misses
    write_csr(mhpmevent5, 16);  // ID 16: L1 I-Cache Access
    write_csr(mhpmevent6, 17);  // ID 17: L1 D-Cache Access
    write_csr(mhpmevent7, 9);   // ID 9:  Branch Instr
    write_csr(mhpmevent8, 10);  // ID 10: Branch Mispredict + Unpredicted

    asm volatile("li t0, -1");
    asm volatile("csrw mcounteren, t0");
    asm volatile("csrw 0x320, zero");
}

int main() {
    configure_pmu();

    /* Initialise A and B with deterministic but non-trivial values.
     * Done outside the CSR window so init traffic is not measured. */
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            A[i][j] = (double)(i + j + 1);
            B[i][j] = (double)((i * 3 + j * 5 + 7) & 0xF);
        }
    }

    // Lectura Inicial
    uint64_t start_cyc = read_csr(mcycle);
    uint64_t start_ins = read_csr(minstret);
    uint64_t start_hpm3 = read_csr(mhpmcounter3);
    uint64_t start_hpm4 = read_csr(mhpmcounter4);
    uint64_t start_hpm5 = read_csr(mhpmcounter5);
    uint64_t start_hpm6 = read_csr(mhpmcounter6);
    uint64_t start_hpm7 = read_csr(mhpmcounter7);
    uint64_t start_hpm8 = read_csr(mhpmcounter8);

    // Programa: C = A * B  (naive triple-loop dgemm)
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            double acc = 0.0;
            for (int k = 0; k < N; k++) {
                acc += A[i][k] * B[k][j];
            }
            C[i][j] = acc;
        }
    }

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
        "mv s2, %0 \n\t"   // x18
        "mv s3, %1 \n\t"   // x19
        "mv s4, %2 \n\t"   // x20
        "mv s5, %3 \n\t"   // x21
        "mv s6, %4 \n\t"   // x22
        "mv s7, %5 \n\t"   // x23
        "mv s8, %6 \n\t"   // x24
        "mv s9, %7 \n\t"   // x25
        "mv s10, %8 \n\t"  // x26
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

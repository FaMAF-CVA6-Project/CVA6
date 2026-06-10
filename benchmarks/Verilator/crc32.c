/* crc32 — bitwise CRC32 over a small buffer.
 * Workload type: integer compute. ALU-heavy (xor, shr, and, neg) with
 * no floating-point traffic. Inner loop runs 8 iterations per byte, so
 * BUFSIZE=64 produces 512 inner iterations and a very tight branchy
 * loop. Contrast point against the FP-heavy dgemm. */
#include <string.h>
#include <limits.h>
#include <encoding.h>

#define uint64_t __uint64_t
#define CPU_FREQ_HZ 50000000ULL
#define asm __asm__

#define BUFSIZE 64

static unsigned char buffer[BUFSIZE];
static volatile unsigned int crc_result;

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

/* Bitwise (no-table) CRC32 using the reflected polynomial 0xEDB88320.
 * The `mask = -(crc & 1)` trick conditionally XORs the polynomial
 * without an explicit branch on the LSB, but the outer for-loops are
 * fully branchy. */
static unsigned int crc32(const unsigned char *buf, int len) {
    unsigned int crc = 0xFFFFFFFFu;
    for (int i = 0; i < len; i++) {
        crc ^= buf[i];
        for (int b = 0; b < 8; b++) {
            unsigned int mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

int main() {
    configure_pmu();

    /* Deterministic pseudo-data so the CRC is reproducible. */
    for (int i = 0; i < BUFSIZE; i++) {
        buffer[i] = (unsigned char)((i * 31 + 7) & 0xFF);
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

    // Programa: CRC32 over the whole buffer
    crc_result = crc32(buffer, BUFSIZE);

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

#include <stdint.h>
#include <string.h>
#include <limits.h>
#include <encoding.h>

#define uint64_t __uint64_t
#define CPU_FREQ_HZ 50000000ULL
#define ARRAY_SIZE 8
#define asm __asm__

uint32_t rand32(uint32_t seed) {
    return seed * 1664525u + 1013904223u;
}

uint32_t fibonacci(uint32_t n) {
    uint32_t a = 0, b = 1, t;
    for (uint32_t i = 0; i < n; ++i) {
        t = a + b;
        a = b;
        b = t;
    }
    return a;
}

uint32_t reverse_bytes(uint32_t x) {
    return ((x >> 24) & 0x000000FF) |
           ((x >> 8)  & 0x0000FF00) |
           ((x << 8)  & 0x00FF0000) |
           ((x << 24) & 0xFF000000);
}

float float_sum(float* arr, int len) {
    float sum = 0.0f;
    for (int i = 0; i < len; ++i) {
        sum += arr[i];
    }
    return sum;
}

double double_product(double* arr, int len) {
    double prod = 1.0;
    for (int i = 0; i < len; ++i) {
        prod *= arr[i];
    }
    return prod;
}

void configure_pmu() {
	asm volatile("csrw 0x320, %0" :: "r"(-1));

    // Configurar los eventos
    write_csr(mhpmevent3, 1);  // ID 1:  L1 I-Cache Misses
    write_csr(mhpmevent4, 2);  // ID 2:  L1 D-Cache Misses
    write_csr(mhpmevent5, 16); // ID 16: L1 I-Cache Access
    write_csr(mhpmevent6, 17); // ID 17: L1 D-Cache Access
    write_csr(mhpmevent7, 9);  // ID 9:  Branch Instr
    write_csr(mhpmevent8, 10); // ID 10: Branch Mispredicts

    asm volatile("li t0, -1");
    asm volatile("csrw mcounteren, t0");
	asm volatile("csrw 0x320, zero");
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

    // Programa
    // Integer section
    uint32_t arr[ARRAY_SIZE];
    uint32_t seed = 1234;

    for (int i = 0; i < ARRAY_SIZE; ++i) {
        seed = rand32(seed);
        arr[i] = seed;
    }

    uint32_t fib = fibonacci(12);
    uint32_t checksum = 0;
    for (int i = 0; i < ARRAY_SIZE; ++i) {
        checksum ^= arr[i];
    }
    uint32_t rev = reverse_bytes(checksum);

    // Floating-point section
    float fvalues[ARRAY_SIZE] = {1.5f, 2.0f, -0.5f, 3.25f, 4.0f, 0.0f, -1.0f, 2.75f};
    double dvalues[ARRAY_SIZE] = {1.1, 1.5, 2.0, 0.5, 1.25, 2.25, 1.0, 1.2};

    float fsum = float_sum(fvalues, ARRAY_SIZE);
    double dprod = double_product(dvalues, ARRAY_SIZE);

    // String manipulation section
    char msg1[] = "cva6";
    char msg2[5];
    memcpy(msg2, msg1, 5);

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
    uint64_t d_br_miss = end_hpm8 - start_hpm8;
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
          "r"(d_ic_acc), "r"(d_dc_acc), "r"(d_br_inst), "r"(d_br_miss),
          "r"(time_us)
        : "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "t0"
    );

    return 0;
}
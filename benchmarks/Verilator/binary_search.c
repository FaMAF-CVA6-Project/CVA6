/* binary_search — hard-to-predict branches.
 * Workload type: branch-intensive. Sorted array of N=128 ints, NSEARCH=64
 * lookups with pseudorandom keys split between in-range (hits) and
 * out-of-range (misses). The lo/hi adjustment inside binary_search is
 * roughly 50/50 per iteration — neither static nor history-based
 * predictors get an easy ride here. */
#include <string.h>
#include <limits.h>
#include <encoding.h>

#define uint64_t __uint64_t
#define CPU_FREQ_HZ 50000000ULL
#define asm __asm__

#define N 128
#define NSEARCH 64

static int sorted_arr[N];
static int search_keys[NSEARCH];
static volatile int results[NSEARCH];

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

/* Standard iterative binary search. Returns index of `key` in `arr`,
 * or -1 if not present. */
static int binary_search(int *arr, int n, int key) {
    int lo = 0, hi = n - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (arr[mid] == key) return mid;
        if (arr[mid] < key) lo = mid + 1;
        else hi = mid - 1;
    }
    return -1;
}

int main() {
    configure_pmu();

    /* sorted_arr = [0, 1, 2, ..., N-1]. */
    for (int i = 0; i < N; i++) sorted_arr[i] = i;

    /* Pseudorandom keys spread over [0, 2N) so roughly half are hits
     * (key in [0, N)) and half are misses (key in [N, 2N)).
     * (i * 37 + 11) mod 256 produces a non-trivial mix. */
    for (int i = 0; i < NSEARCH; i++) {
        search_keys[i] = (i * 37 + 11) & (2 * N - 1);
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

    // Programa: NSEARCH binary-search lookups
    for (int i = 0; i < NSEARCH; i++) {
        results[i] = binary_search(sorted_arr, N, search_keys[i]);
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

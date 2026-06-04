#include <stdint.h>
#include <string.h>
#include <limits.h>
#include <encoding.h>

#define PAGE_SIZE 4096 
#define NUM_PAGES 64
#define uint64_t __uint64_t
#define CPU_FREQ_HZ 50000000ULL
#define asm __asm__

// Variables globales para guardar las metricas de inicio 
uint64_t start_cyc, start_ins, start_hpm3, start_hpm4, start_hpm5, start_hpm6, start_hpm7, start_hpm8;

// Datos alineados a 4KB para DTLB
__attribute__((aligned(PAGE_SIZE))) volatile uint32_t data_array[NUM_PAGES * (PAGE_SIZE / sizeof(uint32_t))];

// Funciones alineadas a 4KB para ITLB
__attribute__((aligned(PAGE_SIZE))) void page_jump_0() { asm volatile("nop"); }
__attribute__((aligned(PAGE_SIZE))) void page_jump_1() { asm volatile("nop"); }
__attribute__((aligned(PAGE_SIZE))) void page_jump_2() { asm volatile("nop"); }
__attribute__((aligned(PAGE_SIZE))) void page_jump_3() { asm volatile("nop"); }
__attribute__((aligned(PAGE_SIZE))) void page_jump_4() { asm volatile("nop"); }

// Tablas de paginas
__attribute__((aligned(PAGE_SIZE))) uint64_t l2_table[512]; 
__attribute__((aligned(PAGE_SIZE))) uint64_t l1_table[512]; 
__attribute__((aligned(PAGE_SIZE))) uint64_t l0_table[512]; 

#define PTE_V (1ULL << 0) 
#define PTE_R (1ULL << 1) 
#define PTE_W (1ULL << 2) 
#define PTE_X (1ULL << 3) 
#define PTE_A (1ULL << 6) 
#define PTE_D (1ULL << 7) 

uint64_t make_pte(uint64_t phys_addr, uint64_t flags) {
    return ((phys_addr >> 12) << 10) | flags | PTE_V | PTE_A | PTE_D;
}

void setup_mmu_and_pmp() {
    asm volatile("csrw pmpaddr0, %0" : : "r"(-1ULL)); 
    asm volatile("csrw pmpcfg0, %0" : : "r"(0x1FULL));
    asm volatile("csrw mcounteren, %0" : : "r"(-1ULL));

    l2_table[2] = make_pte((uint64_t)l1_table, 0); 
    l1_table[0] = make_pte((uint64_t)l0_table, 0); 

    uint64_t base_pa = 0x80000000;
    for(int i = 0; i < 512; i++) {
        l0_table[i] = make_pte(base_pa + (i * PAGE_SIZE), PTE_R | PTE_W | PTE_X);
    }

    uint64_t satp = (8ULL << 60) | ((uint64_t)l2_table >> 12);
    asm volatile("csrw satp, %0" : : "r"(satp));
    asm volatile("sfence.vma");
}

void configure_pmu() {
    asm volatile("csrw 0x320, %0" :: "r"(-1));

    write_csr(mhpmevent3, 3);  
    write_csr(mhpmevent4, 4);  
    write_csr(mhpmevent5, 16); 
    write_csr(mhpmevent6, 17); 
    write_csr(mhpmevent7, 9);  
    write_csr(mhpmevent8, 10); 

    asm volatile("li t0, -1");
    asm volatile("csrw mcounteren, t0");
    asm volatile("csrw 0x320, zero");
}

void s_mode_payload() {
    // Programa
    uint32_t sum = 0;
    
    for (int iter = 0; iter < 100; iter++) {
        for (int p = 0; p < NUM_PAGES; p++) {
            int index = p * (PAGE_SIZE / sizeof(uint32_t));
            
            data_array[index] = 0xDEADBEEF + iter; 
            
            asm volatile("" ::: "memory"); 
        }
    }

    for (int iter = 0; iter < 1000; iter++) {
        page_jump_0(); page_jump_1(); page_jump_2(); page_jump_3(); page_jump_4();
    }

    uint64_t end_cyc, end_ins, end_hpm3, end_hpm4, end_hpm5, end_hpm6, end_hpm7, end_hpm8;
    asm volatile("csrr %0, cycle" : "=r"(end_cyc));
    asm volatile("csrr %0, instret" : "=r"(end_ins));
    asm volatile("csrr %0, hpmcounter3" : "=r"(end_hpm3));
    asm volatile("csrr %0, hpmcounter4" : "=r"(end_hpm4));
    asm volatile("csrr %0, hpmcounter5" : "=r"(end_hpm5));
    asm volatile("csrr %0, hpmcounter6" : "=r"(end_hpm6));
    asm volatile("csrr %0, hpmcounter7" : "=r"(end_hpm7));
    asm volatile("csrr %0, hpmcounter8" : "=r"(end_hpm8));

    // Lectura Final
    uint64_t d_cyc  = end_cyc - start_cyc;
    uint64_t d_ins  = end_ins - start_ins;
    uint64_t itlb_miss = end_hpm3 - start_hpm3;
    uint64_t dtlb_miss = end_hpm4 - start_hpm4;
    uint64_t d_ic_acc  = end_hpm5 - start_hpm5;
    uint64_t d_dc_acc  = end_hpm6 - start_hpm6;
    uint64_t d_br_inst = end_hpm7 - start_hpm7;
    uint64_t d_br_miss_unp = end_hpm8 - start_hpm8;
    uint64_t time_us = (d_cyc * 1000000) / CPU_FREQ_HZ;

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

        "mv a0, %9 \n\t" 
        
        "li a0, 0 \n\t"
        "jal exit \n\t"
        : 
        : "r"(d_cyc), "r"(d_ins), "r"(itlb_miss), "r"(dtlb_miss), 
          "r"(d_ic_acc), "r"(d_dc_acc), "r"(d_br_inst), "r"(d_br_miss_unp),
          "r"(time_us), "r"(sum)
        : "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "a0"
    );

    while(1); 
}

int main() {
    configure_pmu();

    // Lectura Inicial
    asm volatile("csrr %0, mcycle" : "=r"(start_cyc));
    asm volatile("csrr %0, minstret" : "=r"(start_ins));
    asm volatile("csrr %0, mhpmcounter3" : "=r"(start_hpm3));
    asm volatile("csrr %0, mhpmcounter4" : "=r"(start_hpm4));
    asm volatile("csrr %0, mhpmcounter5" : "=r"(start_hpm5));
    asm volatile("csrr %0, mhpmcounter6" : "=r"(start_hpm6));
    asm volatile("csrr %0, mhpmcounter7" : "=r"(start_hpm7));
    asm volatile("csrr %0, mhpmcounter8" : "=r"(start_hpm8));

    setup_mmu_and_pmp();

    uint64_t mstatus;
    asm volatile("csrr %0, mstatus" : "=r"(mstatus));
    mstatus &= ~(3ULL << 11);
    mstatus |=  (1ULL << 11);
    asm volatile("csrw mstatus, %0" : : "r"(mstatus));

    asm volatile("csrw mepc, %0" : : "r"((uint64_t)s_mode_payload));

    asm volatile("mret");

    return 0;
}
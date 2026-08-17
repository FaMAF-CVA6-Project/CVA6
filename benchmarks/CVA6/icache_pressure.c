#include <stdint.h>
#include <string.h>
#include <limits.h>
#include <encoding.h>

#define uint64_t __uint64_t
#define CPU_FREQ_HZ 50000000ULL
#define asm __asm__
#define BARE_ALIGN __attribute__((aligned(4096)))

#define CAT_(a, b) a##b
#define CAT(a, b) CAT_(a, b)

#define FUNC(N)                                                     \
    __attribute__((noinline)) static int CAT(f, N)(int x)           \
    {                                                               \
        x = x * ((N) + 1) ^ 0x1234567;                              \
        x = (x << (((N) & 7) + 1)) | (x >> (32 - (((N) & 7) + 1))); \
        x = x + ((N) * 7919);                                       \
        return x;                                                   \
    }

#define FUNC10(a, b, c, d, e, f, g, h, i, j) \
    FUNC(a)                                  \
    FUNC(b)                                  \
    FUNC(c)                                  \
    FUNC(d)                                  \
    FUNC(e)                                  \
    FUNC(f)                                  \
    FUNC(g)                                  \
    FUNC(h)                                  \
    FUNC(i)                                  \
    FUNC(j)

FUNC10(0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
FUNC10(10, 11, 12, 13, 14, 15, 16, 17, 18, 19)
FUNC10(20, 21, 22, 23, 24, 25, 26, 27, 28, 29)
FUNC10(30, 31, 32, 33, 34, 35, 36, 37, 38, 39)
FUNC10(40, 41, 42, 43, 44, 45, 46, 47, 48, 49)
FUNC10(50, 51, 52, 53, 54, 55, 56, 57, 58, 59)
FUNC10(60, 61, 62, 63, 64, 65, 66, 67, 68, 69)
FUNC10(70, 71, 72, 73, 74, 75, 76, 77, 78, 79)
FUNC10(80, 81, 82, 83, 84, 85, 86, 87, 88, 89)
FUNC10(90, 91, 92, 93, 94, 95, 96, 97, 98, 99)
FUNC10(100, 101, 102, 103, 104, 105, 106, 107, 108, 109)
FUNC10(110, 111, 112, 113, 114, 115, 116, 117, 118, 119)
FUNC10(120, 121, 122, 123, 124, 125, 126, 127, 128, 129)
FUNC10(130, 131, 132, 133, 134, 135, 136, 137, 138, 139)
FUNC10(140, 141, 142, 143, 144, 145, 146, 147, 148, 149)
FUNC10(150, 151, 152, 153, 154, 155, 156, 157, 158, 159)
FUNC10(160, 161, 162, 163, 164, 165, 166, 167, 168, 169)
FUNC10(170, 171, 172, 173, 174, 175, 176, 177, 178, 179)
FUNC10(180, 181, 182, 183, 184, 185, 186, 187, 188, 189)
FUNC10(190, 191, 192, 193, 194, 195, 196, 197, 198, 199)
FUNC10(200, 201, 202, 203, 204, 205, 206, 207, 208, 209)
FUNC10(210, 211, 212, 213, 214, 215, 216, 217, 218, 219)
FUNC10(220, 221, 222, 223, 224, 225, 226, 227, 228, 229)
FUNC10(230, 231, 232, 233, 234, 235, 236, 237, 238, 239)
FUNC10(240, 241, 242, 243, 244, 245, 246, 247, 248, 249)
FUNC(250)
FUNC(251)
FUNC(252)
FUNC(253)
FUNC(254)
FUNC(255)

#define CASE(N) \
    case N:     \
        return CAT(f, N)(x);

#define CASE10(a, b, c, d, e, f, g, h, i, j) \
    CASE(a)                                  \
    CASE(b)                                  \
    CASE(c)                                  \
    CASE(d)                                  \
    CASE(e)                                  \
    CASE(f)                                  \
    CASE(g)                                  \
    CASE(h)                                  \
    CASE(i)                                  \
    CASE(j)

__attribute__((noinline)) static int dispatch(int sel, int x)
{
    switch (sel)
    {
        CASE10(0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
        CASE10(10, 11, 12, 13, 14, 15, 16, 17, 18, 19)
        CASE10(20, 21, 22, 23, 24, 25, 26, 27, 28, 29)
        CASE10(30, 31, 32, 33, 34, 35, 36, 37, 38, 39)
        CASE10(40, 41, 42, 43, 44, 45, 46, 47, 48, 49)
        CASE10(50, 51, 52, 53, 54, 55, 56, 57, 58, 59)
        CASE10(60, 61, 62, 63, 64, 65, 66, 67, 68, 69)
        CASE10(70, 71, 72, 73, 74, 75, 76, 77, 78, 79)
        CASE10(80, 81, 82, 83, 84, 85, 86, 87, 88, 89)
        CASE10(90, 91, 92, 93, 94, 95, 96, 97, 98, 99)
        CASE10(100, 101, 102, 103, 104, 105, 106, 107, 108, 109)
        CASE10(110, 111, 112, 113, 114, 115, 116, 117, 118, 119)
        CASE10(120, 121, 122, 123, 124, 125, 126, 127, 128, 129)
        CASE10(130, 131, 132, 133, 134, 135, 136, 137, 138, 139)
        CASE10(140, 141, 142, 143, 144, 145, 146, 147, 148, 149)
        CASE10(150, 151, 152, 153, 154, 155, 156, 157, 158, 159)
        CASE10(160, 161, 162, 163, 164, 165, 166, 167, 168, 169)
        CASE10(170, 171, 172, 173, 174, 175, 176, 177, 178, 179)
        CASE10(180, 181, 182, 183, 184, 185, 186, 187, 188, 189)
        CASE10(190, 191, 192, 193, 194, 195, 196, 197, 198, 199)
        CASE10(200, 201, 202, 203, 204, 205, 206, 207, 208, 209)
        CASE10(210, 211, 212, 213, 214, 215, 216, 217, 218, 219)
        CASE10(220, 221, 222, 223, 224, 225, 226, 227, 228, 229)
        CASE10(230, 231, 232, 233, 234, 235, 236, 237, 238, 239)
        CASE10(240, 241, 242, 243, 244, 245, 246, 247, 248, 249)
        CASE(250)
        CASE(251)
        CASE(252)
        CASE(253)
        CASE(254)
        CASE(255)
    default:
        return x;
    }
}

BARE_ALIGN static unsigned char order[256];

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
    __asm__ volatile("j 1770f; .balign 4096; 1770:" ::: "memory");
    for (int i = 0; i < 256; i++)
        order[i] = (unsigned char)i;

    unsigned int seed = 0xabcdef01u;

    for (int i = 255; i > 0; i--)
    {
        seed = seed * 1103515245u + 12345u;
        int j = (int)((seed >> 8) % (unsigned)(i + 1));
        unsigned char t = order[i];
        order[i] = order[j];
        order[j] = t;
    }

    int x = 0x42;

    for (int iter = 0; iter < 8; iter++)
    {
        for (int i = 0; i < 256; i++)
        {
            x = dispatch(order[i], x);
        }
    }

    static volatile int sink;
    sink = x;
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

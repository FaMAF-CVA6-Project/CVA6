import argparse
import os

from m5.params import NULL  # type: ignore
from gem5.components.boards.simple_board import SimpleBoard  # type: ignore
from gem5.components.processors.base_cpu_core import (  # type: ignore
    BaseCPUCore,
)
from gem5.components.processors.base_cpu_processor import (  # type: ignore
    BaseCPUProcessor,
)
from gem5.components.memory.simple import (  # type: ignore
    SingleChannelSimpleMemory,
)
from gem5.components.memory.single_channel import (  # type: ignore
    SingleChannelDDR3_1600,
)
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import (  # type: ignore
    PrivateL1CacheHierarchy,
)
from gem5.isas import ISA  # type: ignore
from gem5.simulate.simulator import Simulator  # type: ignore
from gem5.resources.resource import BinaryResource  # type: ignore

from m5.objects import (  # type: ignore
    LocalBP,
    TournamentBP,
    LRURP,
    RandomRP,
    MinorFUPool,
    MinorDefaultIntFU,
    MinorDefaultIntMulFU,
    MinorDefaultIntDivFU,
    MinorDefaultMemFU,
    MinorDefaultFloatSimdFU,
    MinorDefaultPredFU,
    MinorDefaultMiscFU,
    MinorFU,
    MinorFUTiming,
    MinorOpClassSet,
    MinorOpClass,
    ReturnAddrStack,
    RiscvMinorCPU,
    SimpleBTB,
    TimingExprLiteral,
    TimingExprSrcReg,
    TimingExprUn,
    TimingExprBin,
    TimingExprIf,
)

# Calibration harness for the CVA6 gem5 MinorCPU configuration, on an
# UNMODIFIED gem5 v25.0.0.1. TEST 1 is the stock gem5_config_CVA6.py, and every
# other TEST perturbs it, most single-knob, front of the pipeline first.
#
# TESTS 1 to 39 are the whole grid here. gem5_config_CVA6_patch_testing.py
# repeats them on the same baseline, then continues at TEST 40 with full
# production and the entries that set patch parameters.
#
# TEST table fields:
#   (name, cpu_overrides, l1i_size, l1d_size, dcache_overrides,
#    icache_overrides, clk_freq, mem_latency, bp_overrides)
#
# Special keys: cpu_overrides["branchPred"] picks LocalBP or TournamentBP,
# bp_overrides["fuVariant"] a CVA6FUPool variant. dcache_overrides takes
# "_membus_width" in bytes and "_mem_bandwidth" as a SimpleMemory string.
#
#   1   adopted baseline                          workload: all
#   --- fetch geometry ---
#   2   fetch1FetchLimit 2 -> 1                   workload: matmul_small
#   3   fetch1FetchLimit 2 -> 3                   workload: matmul_small
#   4   fetch lines 8 bytes, fetch2 buffer 8      workload: all
#   5   fetch2InputBufferSize 2 -> 4              workload: fetch2_probe
#   --- instruction cache ---
#   6   L1I random -> LRU                         workload: full_test
#   7   L1I response_latency 0 -> 1               workload: daxpy
#   8   L1I response_latency 0 -> 2               workload: daxpy
#   9   L1I 4 KiB                                 workload: daxpy
#   --- decode buffer ---
#  10   decodeInputBufferSize 1 -> 4              workload: daxpy, full_test
#  11   decodeInputBufferSize 1 -> 8              workload: daxpy, full_test
#   --- branch prediction ---
#  12   Morillas 2025 predictor sizing            workload: branch_full_test, btb_pressure, full_test
#  13   BTB 32 -> 512                             workload: branch_full_test, btb_pressure, full_test
#  14   BTB 32 -> 4096                            workload: branch_full_test, btb_pressure, full_test
#   --- LSQ queue geometry ---
#  15   requests queue 2 -> 4                     workload: store_fwd
#  16   requests queue 2 -> 8                     workload: store_fwd
#  17   store buffer 4 -> 8                       workload: store_fwd
#  18   requests 8, store buffer 8                workload: store_fwd
#   --- functional units ---
#  19   int_mul opLat 2 -> 1                      workload: daxpy, full_test
#  20   fp_divsqrt legacy                         workload: fp_divsqrt
#  21   serdiv base 1 -> 0                        workload: int_div
#  22   fp_addmul without the double mask         workload: fp_addmul
#  23   FP mem classes back on vec_mem_fast       workload: daxpy
#  24   LR/SC, AMO and fence occupancy removed    workload: atomic_fence
#   --- data cache ---
#  25   L1D random -> LRU                         workload: full_test
#  26   response_latency 4 -> 5                   workload: daxpy
#  27   response_latency 4 -> 6                   workload: daxpy
#  28   response_latency 4 -> 3                   workload: daxpy
#  29   L1D 16 KiB                                workload: daxpy
#  30   L1D 64 KiB                                workload: daxpy
#  31   L1D assoc 8 -> 2                          workload: daxpy
#  32   L1D mshrs 8 -> 1                          workload: daxpy
#  33   L1D write_buffers 8 -> 2                  workload: daxpy
#  34   L1D hit lat +1                            workload: daxpy
#   --- memory system ---
#  35   membus width 8 -> 16                      workload: daxpy
#  36   membus width 8 -> 4                       workload: daxpy
#  37   memory bandwidth 12.8 GiB/s -> 0.4 GiB/s  workload: daxpy
#  38   mem latency 0 -> 60 ns                    workload: daxpy
#   --- core-wide ---
#  39   threadPolicy -> RoundRobin                workload: daxpy
#
#   --- cache geometry ---
# CACHE_TESTS is a table of its own: nothing in it touches the CPU, only L1I
# and L1D size and associativity. Each entry runs the workloads its cut moves
# on CACHE_BASE_TEST, this file's TEST 1 baseline, since the production
# stack needs the patch.
# 201   L1I 4 KiB                                 workload: icache_pressure
# 202   L1I 8 KiB                                 workload: icache_pressure
# 203   L1I 32 KiB                                workload: icache_pressure
# 204   L1I 64 KiB                                workload: icache_pressure
# 205   L1I direct mapped, assoc 4 -> 1           workload: icache_pressure
# 206   L1I assoc 4 -> 2                          workload: icache_pressure
# 207   L1I assoc 4 -> 8                          workload: icache_pressure
# 208   L1D 8 KiB                                 workload: daxpy, full_test, atomic_fence
# 209   L1D 16 KiB                                workload: full_test, fetch2_probe
# 210   L1D 64 KiB                                workload: daxpy, full_test, atomic_fence
# 211   L1D direct mapped, assoc 8 -> 1           workload: daxpy, daxpy_unrolling_4, fetch2_probe
# 212   L1D assoc 8 -> 2                          workload: daxpy, daxpy_unrolling_4, fetch2_probe
# 213   L1D assoc 8 -> 4                          workload: daxpy, fetch2_probe
# 214   both small, L1I 4 KiB and L1D 8 KiB       workload: icache_pressure, full_test
# 215   both large, L1I 64 KiB and L1D 64 KiB     workload: icache_pressure, full_test
# 216   both direct mapped                        workload: icache_pressure, daxpy, daxpy_unrolling_4
# 217   both doubled, L1I 32 KiB and L1D 64 KiB   workload: icache_pressure, full_test, daxpy

TEST = 1

# When True, ignore the TEST table and run the full Morillas 2025 config.
USE_MORILLAS = False


TESTS = {
    1:  ("adopted baseline",             {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    # --- fetch geometry ---
    2:  ("fetch1FetchLimit 2->1",        {"fetch1FetchLimit": 1}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    3:  ("fetch1FetchLimit 2->3",        {"fetch1FetchLimit": 3}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    4:  ("fetch 8B alternative side",    {"fetch1LineWidth": 8, "fetch1LineSnapWidth": 8,
                                          "fetch2InputBufferSize": 8}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    5:  ("fetch2 buffer 2->4",           {"fetch2InputBufferSize": 4}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    # --- instruction cache ---
    6:  ("L1I random->LRU",              {}, "16KiB", "32KiB", {}, {"replacement_policy": LRURP()}, "50MHz", "0ns", {}),
    7:  ("L1I response 0->1",            {}, "16KiB", "32KiB", {}, {"response_latency": 1}, "50MHz", "0ns", {}),
    8:  ("L1I resp 0->2",                {}, "16KiB", "32KiB", {}, {"response_latency": 2}, "50MHz", "0ns", {}),
    9:  ("L1I 4KiB",                     {}, "4KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    # --- decode buffer ---
    10: ("decode buffer 1->4",           {"decodeInputBufferSize": 4}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    11: ("decode buffer 1->8",           {"decodeInputBufferSize": 8}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    # --- branch prediction ---
    12: ("Morillas branch predictor",    {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"localPredictorSize": 1024, "bhtInstShiftAmt": 2,
          "btbNumEntries": 64, "btbAssociativity": 16, "btbInstShiftAmt": 2}),
    13: ("BTB 32->512",                  {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"btbNumEntries": 512}),
    14: ("BTB 32->4096",                 {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"btbNumEntries": 4096}),
    # --- LSQ queue geometry ---
    15: ("LSQ requests queue 2->4",      {"executeLSQRequestsQueueSize": 4}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    16: ("LSQ requests queue 2->8",      {"executeLSQRequestsQueueSize": 8}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    17: ("LSQ store buffer 4->8",        {"executeLSQStoreBufferSize": 8}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    18: ("LSQ queue 8 buffer 8",         {"executeLSQRequestsQueueSize": 8, "executeLSQStoreBufferSize": 8}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    # --- functional units ---
    19: ("int_mul opLat 2->1",           {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"fuVariant": "int_mul_1"}),
    20: ("fp_divsqrt legacy 2 flat +2",  {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"fuVariant": "divsqrt_legacy"}),
    21: ("serdiv base 1->0",             {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"fuVariant": "serdiv_base0"}),
    22: ("fp_addmul without fmt mask",   {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"fuVariant": "addmul_flat"}),
    23: ("FP mem classes on vec unit",   {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"fuVariant": "fp_on_vec"}),
    24: ("occupancy entries removed",    {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"fuVariant": "no_occupancy"}),
    # --- data cache ---
    25: ("L1D random->LRU",              {}, "16KiB", "32KiB", {"replacement_policy": LRURP()}, {}, "50MHz", "0ns", {}),
    26: ("response_latency 4->5",        {}, "16KiB", "32KiB", {"response_latency": 5}, {}, "50MHz", "0ns", {}),
    27: ("response_latency 4->6",        {}, "16KiB", "32KiB", {"response_latency": 6}, {}, "50MHz", "0ns", {}),
    28: ("response_latency 4->3",        {}, "16KiB", "32KiB", {"response_latency": 3}, {}, "50MHz", "0ns", {}),
    29: ("L1D 16KiB",                    {}, "16KiB", "16KiB", {}, {}, "50MHz", "0ns", {}),
    30: ("L1D 64KiB",                    {}, "16KiB", "64KiB", {}, {}, "50MHz", "0ns", {}),
    31: ("L1D assoc 8->2",               {}, "16KiB", "32KiB", {"assoc": 2}, {}, "50MHz", "0ns", {}),
    32: ("L1D mshrs 8->1",               {}, "16KiB", "32KiB", {"mshrs": 1}, {}, "50MHz", "0ns", {}),
    33: ("write_buffers 8->2",           {}, "16KiB", "32KiB", {"write_buffers": 2}, {}, "50MHz", "0ns", {}),
    34: ("L1D hit lat +1",               {}, "16KiB", "32KiB", {"tag_latency": 2, "data_latency": 2}, {}, "50MHz", "0ns", {}),
    # --- memory system ---
    35: ("membus width 8->16",           {}, "16KiB", "32KiB", {"_membus_width": 16}, {}, "50MHz", "0ns", {}),
    36: ("membus width 8->4",            {}, "16KiB", "32KiB", {"_membus_width": 4}, {}, "50MHz", "0ns", {}),
    37: ("memory bandwidth 0.4GiB/s",    {}, "16KiB", "32KiB", {"_mem_bandwidth": "0.4GiB/s"}, {}, "50MHz", "0ns", {}),
    38: ("legacy 60ns memory",           {}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
    # --- core-wide ---
    39: ("threadPolicy RoundRobin",      {"threadPolicy": "RoundRobin"}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
}

# The entry every cache geometry is laid over: TEST 1, the stock baseline,
# since the production stack needs the patch. Each cut is merged into it
# when the harness runs, so the list follows the baseline when 1 changes.
CACHE_BASE_TEST = 1

# Cache geometry, kept apart from the grid above so a plain sweep leaves it
# out. These vary nothing but L1I and L1D size and associativity, and their
# ids start at 201, so an id says which table it came from.
CACHE_TESTS = {
    201: ("L1I 4KiB",                       {}, "4KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    202: ("L1I 8KiB",                       {}, "8KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    203: ("L1I 32KiB",                      {}, "32KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    204: ("L1I 64KiB",                      {}, "64KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    205: ("L1I direct mapped",              {}, "16KiB", "32KiB", {}, {"assoc": 1}, "50MHz", "0ns", {}),
    206: ("L1I assoc 4->2",                 {}, "16KiB", "32KiB", {}, {"assoc": 2}, "50MHz", "0ns", {}),
    207: ("L1I assoc 4->8",                 {}, "16KiB", "32KiB", {}, {"assoc": 8}, "50MHz", "0ns", {}),
    208: ("L1D 8KiB",                       {}, "16KiB", "8KiB", {}, {}, "50MHz", "0ns", {}),
    209: ("L1D 16KiB",                      {}, "16KiB", "16KiB", {}, {}, "50MHz", "0ns", {}),
    210: ("L1D 64KiB",                      {}, "16KiB", "64KiB", {}, {}, "50MHz", "0ns", {}),
    211: ("L1D direct mapped",              {}, "16KiB", "32KiB", {"assoc": 1}, {}, "50MHz", "0ns", {}),
    212: ("L1D assoc 8->2",                 {}, "16KiB", "32KiB", {"assoc": 2}, {}, "50MHz", "0ns", {}),
    213: ("L1D assoc 8->4",                 {}, "16KiB", "32KiB", {"assoc": 4}, {}, "50MHz", "0ns", {}),
    214: ("both small 4KiB/8KiB",           {}, "4KiB", "8KiB", {}, {}, "50MHz", "0ns", {}),
    215: ("both large 64KiB/64KiB",         {}, "64KiB", "64KiB", {}, {}, "50MHz", "0ns", {}),
    216: ("both direct mapped",             {}, "16KiB", "32KiB", {"assoc": 1}, {"assoc": 1}, "50MHz", "0ns", {}),
    217: ("both doubled 32KiB/64KiB",       {}, "32KiB", "64KiB", {}, {}, "50MHz", "0ns", {}),
}

# TEST picks from either table. The two id ranges do not overlap, so a number
# is enough and the caller never has to say which list it came from.
ALL_TESTS = {**TESTS, **CACHE_TESTS}


# Each base can set these fields of a TEST tuple, by position.
OVERRIDE_FIELDS = {1: "cpu", 4: "dcache", 5: "icache", 8: "bp"}


def laid_over(base, entry):
    """entry with each override dict merged over base's, entry's keys winning.
    base maps a field name to its dict, as PATCH_BASE does."""
    merged = list(entry)
    for field, name in OVERRIDE_FIELDS.items():
        merged[field] = {**base.get(name, {}), **entry[field]}
    return tuple(merged)


def as_base(entry):
    """A TEST tuple's override dicts, keyed as PATCH_BASE is."""
    return {name: entry[field] for field, name in OVERRIDE_FIELDS.items()}


def resolve(test):
    """The TEST entry with the base it sits on merged in: a cache entry over
    CACHE_BASE_TEST, the grid as written."""
    entry = ALL_TESTS[test]
    if test in CACHE_TESTS:
        return laid_over(as_base(ALL_TESTS[CACHE_BASE_TEST]), entry)
    return entry


def _lit(value):
    e = TimingExprLiteral()
    e.value = value
    return e


def _src(index):
    e = TimingExprSrcReg()
    e.index = index
    return e


def _un(op, arg):
    e = TimingExprUn()
    e.op = op
    e.arg = arg
    return e


def _bin(op, left, right):
    e = TimingExprBin()
    e.op = op
    e.left = left
    e.right = right
    return e


def _if(cond, then_expr, else_expr):
    e = TimingExprIf()
    e.cond = cond
    e.trueExpr = then_expr
    e.falseExpr = else_expr
    return e


def serdivExtraLatency(base=1):
    """Data-dependent latency of the CVA6 integer divider."""
    bits_a = _un('timingExprSizeInBits', _src(0))
    bits_b = _un('timingExprSizeInBits', _src(1))
    diff = _bin('timingExprSub', bits_a, bits_b)
    clamped = _if(_bin('timingExprSGreaterThan',
                  bits_a, bits_b), diff, _lit(0))
    return _bin('timingExprAdd', clamped, _lit(base))


def minorMakeOpClassSet(op_classes):
    def boxOpClass(op_class):
        return MinorOpClass(opClass=op_class)
    return MinorOpClassSet(opClasses=[boxOpClass(o) for o in op_classes])


class CVA6FUPool(MinorFUPool):
    # variant selects one FU-level perturbation, "baseline" is the adopted
    # configuration, identical to gem5_config_CVA6.py. An unknown name
    # also gives the baseline.
    def __init__(self, variant="baseline"):
        super().__init__()

        int_alu = MinorFU()
        int_alu.opClasses = minorMakeOpClassSet(['IntAlu'])
        int_alu.opLat = 1
        int_alu.issueLat = 1

        int_mul = MinorFU()
        int_mul.opClasses = minorMakeOpClassSet(['IntMult'])
        int_mul.opLat = 1 if variant == "int_mul_1" else 2
        int_mul.issueLat = 1

        int_div = MinorFU()
        int_div.opClasses = minorMakeOpClassSet(['IntDiv'])
        int_div.opLat = 2
        int_div.issueLat = 3
        int_div.timings = [MinorFUTiming(
            description='IntDivSerdiv',
            srcRegsRelativeLats=[0],
            extraCommitLatExpr=serdivExtraLatency(
                base=0 if variant == "serdiv_base0" else 1))]

        fp_addmul = MinorFU()
        fp_addmul.opClasses = minorMakeOpClassSet(
            ['FloatAdd', 'FloatMult', 'FloatMultAcc'])
        fp_addmul.opLat = 3
        fp_addmul.issueLat = 1
        if variant != "addmul_flat":
            fp_addmul.timings = [MinorFUTiming(
                description='FpAddMulDouble',
                srcRegsRelativeLats=[0],
                mask=0x06000000,
                match=0x02000000,
                extraCommitLat=1)]

        fp_cvt = MinorFU()
        fp_cvt.opClasses = minorMakeOpClassSet(['FloatCvt'])
        fp_cvt.opLat = 2
        fp_cvt.issueLat = 1

        fp_noncomp = MinorFU()
        fp_noncomp.opClasses = minorMakeOpClassSet(['FloatCmp', 'FloatMisc'])
        fp_noncomp.opLat = 1
        fp_noncomp.issueLat = 1

        fp_divsqrt = MinorFU()
        fp_divsqrt.opClasses = minorMakeOpClassSet(['FloatDiv', 'FloatSqrt'])
        if variant == "divsqrt_legacy":
            fp_divsqrt.opLat = 2
            fp_divsqrt.issueLat = 2
            fp_divsqrt.timings = [MinorFUTiming(
                description='FpDivSqrtLegacy',
                srcRegsRelativeLats=[0],
                extraCommitLat=2)]
        else:
            fp_divsqrt.opLat = 15
            fp_divsqrt.issueLat = 15
            fp_divsqrt.timings = [MinorFUTiming(
                description='FpDivSqrtDouble',
                srcRegsRelativeLats=[0],
                mask=0x06000000,
                match=0x02000000,
                extraCommitLat=7)]

        mem_classes = ['MemRead', 'MemWrite']
        if variant != "fp_on_vec":
            mem_classes += ['FloatMemRead', 'FloatMemWrite']
        mem_fu = MinorFU()
        mem_fu.opClasses = minorMakeOpClassSet(mem_classes)
        mem_fu.opLat = 2
        mem_fu.issueLat = 1
        if variant != "no_occupancy":
            mem_fu.timings = [
                MinorFUTiming(
                    description='LrScOccupancy',
                    srcRegsRelativeLats=[0],
                    mask=0xF000007F,
                    match=0x1000002F,
                    extraCommitLat=10),
                MinorFUTiming(
                    description='AmoOccupancy',
                    srcRegsRelativeLats=[0],
                    mask=0x0000007F,
                    match=0x0000002F,
                    extraCommitLat=13),
                MinorFUTiming(
                    description='FenceOccupancy',
                    srcRegsRelativeLats=[0],
                    mask=0x0000007F,
                    match=0x0000000F,
                    extraCommitLat=3),
            ]

        simd_int_fast = MinorDefaultFloatSimdFU()
        simd_int_fast.opClasses = minorMakeOpClassSet([
            'SimdAdd', 'SimdAlu', 'SimdCmp', 'SimdShift', 'SimdShiftAcc',
            'SimdMisc', 'SimdExt', 'SimdConfig'
        ])
        simd_int_fast.timings = [MinorFUTiming(
            description='SimdIntFast', srcRegsRelativeLats=[2])]
        simd_int_fast.opLat = 2
        simd_int_fast.issueLat = 1

        simd_complex = MinorDefaultFloatSimdFU()
        simd_complex.opClasses = minorMakeOpClassSet([
            'SimdAddAcc', 'SimdCvt', 'SimdMult', 'SimdMultAcc',
            'SimdFloatAdd', 'SimdFloatAlu', 'SimdFloatCmp', 'SimdFloatCvt',
            'SimdFloatMisc', 'SimdFloatMult', 'SimdFloatMultAcc',
            'SimdFloatExt',
            'SimdReduceAdd', 'SimdReduceAlu', 'SimdReduceCmp',
            'SimdFloatReduceAdd', 'SimdFloatReduceCmp',
            'SimdAes', 'SimdAesMix', 'SimdSha1Hash', 'SimdSha1Hash2',
            'SimdSha256Hash', 'SimdSha256Hash2', 'SimdShaSigma2',
            'SimdShaSigma3'
        ])
        simd_complex.timings = [MinorFUTiming(
            description='SimdComplex', srcRegsRelativeLats=[2])]
        simd_complex.opLat = 4
        simd_complex.issueLat = 1

        simd_matrix = MinorDefaultFloatSimdFU()
        simd_matrix.opClasses = minorMakeOpClassSet([
            'Matrix', 'MatrixMov', 'MatrixOP',
            'SimdMatMultAcc', 'SimdFloatMatMultAcc'
        ])
        simd_matrix.timings = [MinorFUTiming(
            description='SimdMatrix', srcRegsRelativeLats=[2])]
        simd_matrix.opLat = 6
        simd_matrix.issueLat = 2

        simd_div_sqrt = MinorDefaultFloatSimdFU()
        simd_div_sqrt.opClasses = minorMakeOpClassSet([
            'SimdDiv', 'SimdSqrt', 'SimdFloatDiv', 'SimdFloatSqrt'
        ])
        simd_div_sqrt.timings = [MinorFUTiming(
            description='SimdDivSqrt', srcRegsRelativeLats=[2])]
        simd_div_sqrt.opLat = 15
        simd_div_sqrt.issueLat = 12

        pred = MinorDefaultPredFU()
        pred.opClasses = minorMakeOpClassSet(['SimdPredAlu'])
        pred.timings = [MinorFUTiming(
            description='Pred', srcRegsRelativeLats=[2])]
        pred.opLat = 1
        pred.issueLat = 1

        vec_fast_classes = [
            'SimdUnitStrideLoad', 'SimdUnitStrideStore',
            'SimdUnitStrideMaskLoad', 'SimdUnitStrideMaskStore',
            'SimdUnitStrideFaultOnlyFirstLoad',
            'SimdWholeRegisterLoad', 'SimdWholeRegisterStore'
        ]
        if variant == "fp_on_vec":
            vec_fast_classes = ['FloatMemRead',
                                'FloatMemWrite'] + vec_fast_classes
        vec_mem_fast = MinorFU()
        vec_mem_fast.opClasses = minorMakeOpClassSet(vec_fast_classes)
        vec_mem_fast.timings = [MinorFUTiming(
            description='VecMemFast', srcRegsRelativeLats=[1],
            extraAssumedLat=2)]
        vec_mem_fast.opLat = 2
        vec_mem_fast.issueLat = 1

        vec_mem_slow = MinorFU()
        vec_mem_slow.opClasses = minorMakeOpClassSet([
            'SimdStridedLoad', 'SimdStridedStore',
            'SimdIndexedLoad', 'SimdIndexedStore',
            'SimdUnitStrideSegmentedLoad', 'SimdUnitStrideSegmentedStore',
            'SimdUnitStrideSegmentedFaultOnlyFirstLoad',
            'SimdStrideSegmentedLoad', 'SimdStrideSegmentedStore'
        ])
        vec_mem_slow.timings = [MinorFUTiming(
            description='VecMemSlow', srcRegsRelativeLats=[1],
            extraAssumedLat=2)]
        vec_mem_slow.opLat = 10
        vec_mem_slow.issueLat = 4

        misc = MinorDefaultMiscFU()
        misc.opClasses = minorMakeOpClassSet(['InstPrefetch', 'IprAccess'])
        misc.opLat = 1
        misc.issueLat = 1

        self.funcUnits = [
            int_alu, int_mul, int_div,
            fp_addmul, fp_cvt, fp_noncomp, fp_divsqrt,
            mem_fu,
            simd_int_fast, simd_complex, simd_matrix, simd_div_sqrt, pred,
            vec_mem_fast, vec_mem_slow, misc,
        ]


class MorillasFUPool(MinorFUPool):
    # Morillas 2025 as published (thesis Table 6.2). Its op-class groupings
    # differ from ours, and integer divide is one averaged latency of 35, the
    # midpoint of the RTL range 2 to 64, plus two.
    def __init__(self):
        super().__init__()

        int_alu_ops = ['IntAlu']
        int_alu = MinorDefaultIntFU()
        int_alu.opClasses = minorMakeOpClassSet(int_alu_ops)
        int_alu.opLat = 3
        int_alu.issueLat = 1

        int_mul_ops = ['IntMult']
        int_mul = MinorDefaultIntMulFU()
        int_mul.opClasses = minorMakeOpClassSet(int_mul_ops)
        int_mul.opLat = 4
        int_mul.issueLat = 1

        int_div_ops = ['IntDiv']
        int_div = MinorDefaultIntDivFU()
        int_div.opClasses = minorMakeOpClassSet(int_div_ops)
        int_div.opLat = 35
        int_div.issueLat = 35

        fp_fast_ops = ['FloatAdd', 'FloatMult', 'FloatMultAcc', 'FloatMisc']
        fp_fast = MinorFU(
            opClasses=minorMakeOpClassSet(fp_fast_ops),
            opLat=3, issueLat=1
        )

        fp_slow_ops = ['FloatCvt', 'FloatSqrt']
        fp_slow = MinorFU(
            opClasses=minorMakeOpClassSet(fp_slow_ops),
            opLat=4, issueLat=1
        )

        fp_div_ops = ['FloatDiv']
        fp_div = MinorFU(
            opClasses=minorMakeOpClassSet(fp_div_ops),
            opLat=4, issueLat=4
        )

        fp_cmp_ops = ['FloatCmp']
        fp_cmp = MinorFU(
            opClasses=minorMakeOpClassSet(fp_cmp_ops),
            opLat=5, issueLat=1
        )

        mem_ops = ['MemRead', 'MemWrite', 'FloatMemRead', 'FloatMemWrite']
        mem_fu = MinorDefaultMemFU()
        mem_fu.opClasses = minorMakeOpClassSet(mem_ops)
        mem_fu.opLat = 3
        mem_fu.issueLat = 1

        # An op class no unit provides never issues, so the classes the
        # published table leaves out share this catch-all.
        defined_ops = set(int_alu_ops + int_mul_ops + int_div_ops + fp_fast_ops
                          + fp_slow_ops + fp_div_ops + fp_cmp_ops + mem_ops)
        misc_ops_list = ['IprAccess']
        all_ops = [op.opClass for op in MinorOpClassSet().opClasses]
        undefined_ops = [op for op in all_ops
                         if op not in defined_ops and op not in misc_ops_list]

        misc_fu = MinorDefaultMiscFU()
        misc_fu.opClasses = minorMakeOpClassSet(misc_ops_list)

        catch_all_fu = MinorFU(
            opClasses=minorMakeOpClassSet(undefined_ops),
            opLat=6, issueLat=1
        )

        self.funcUnits = [
            int_alu, int_mul, int_div,
            fp_fast, fp_slow, fp_div, fp_cmp,
            mem_fu, misc_fu, catch_all_fu
        ]


class CVA6CPU(RiscvMinorCPU):
    def __init__(self, overrides=None, bp=None):
        super().__init__()
        overrides = dict(overrides or {})
        bp = dict(bp or {})
        fu_variant = bp.pop("fuVariant", "baseline")

        self.executeFuncUnits = CVA6FUPool(variant=fu_variant)

        # Adopted baseline, identical to gem5_config_CVA6.py.
        self.fetch1FetchLimit = 2
        self.fetch1LineSnapWidth = 4
        self.fetch1LineWidth = 4
        self.fetch1ToFetch2ForwardDelay = 1
        self.fetch1ToFetch2BackwardDelay = 0
        self.fetch2InputBufferSize = 2
        self.fetch2ToDecodeForwardDelay = 1
        self.fetch2CycleInput = True
        self.decodeInputBufferSize = 1
        self.decodeToExecuteForwardDelay = 1
        self.decodeInputWidth = 1
        self.decodeCycleInput = False
        self.executeInputWidth = 1
        self.executeCycleInput = False
        self.executeIssueLimit = 1
        self.executeMemoryIssueLimit = 1
        self.executeCommitLimit = 2
        self.executeMemoryCommitLimit = 1
        self.executeInputBufferSize = 8
        self.executeMemoryWidth = 8
        self.executeMaxAccessesInMemory = 8
        self.executeLSQMaxStoreBufferStoresPerCycle = 1
        self.executeLSQRequestsQueueSize = 2
        self.executeLSQTransfersQueueSize = 8
        self.executeLSQStoreBufferSize = 4
        self.executeBranchDelay = 1
        self.executeSetTraceTimeOnCommit = True
        self.executeSetTraceTimeOnIssue = False
        self.executeAllowEarlyMemoryIssue = True
        self.threadPolicy = 'SingleThreaded'
        self.enableIdling = False

        bp_class_name = overrides.pop("branchPred", "LocalBP")
        for key, value in overrides.items():
            setattr(self, key, value)

        if bp_class_name == "LocalBP":
            self.branchPred = LocalBP(
                localPredictorSize=bp.get("localPredictorSize", 256),
                localCtrBits=bp.get("localCtrBits", 2),
                instShiftAmt=bp.get("bhtInstShiftAmt", 1),
            )
        elif bp_class_name == "TournamentBP":
            self.branchPred = TournamentBP(
                instShiftAmt=1,
            )
        else:
            raise ValueError(f"Unknown branchPred class: {bp_class_name}")

        self.branchPred.btb = SimpleBTB(
            numEntries=bp.get("btbNumEntries", 32),
            tagBits=bp.get("btbTagBits", 20),
            associativity=bp.get("btbAssociativity", 1),
            instShiftAmt=bp.get("btbInstShiftAmt", 1),
            btbReplPolicy=LRURP(),
        )
        self.branchPred.ras = ReturnAddrStack(
            numEntries=bp.get("rasNumEntries", 2),
        )


class MorillasCPU(RiscvMinorCPU):
    # Transcription of the Morillas 2025 configuration (thesis
    # Table 6.1 and Table 6.3). Parameters absent here are absent in the
    # published configuration and therefore keep their gem5 defaults.
    def __init__(self):
        super().__init__()

        self.executeFuncUnits = MorillasFUPool()

        self.fetch1LineSnapWidth = 4
        self.fetch1LineWidth = 4
        self.fetch1FetchLimit = 1
        self.fetch1ToFetch2ForwardDelay = 1
        self.fetch1ToFetch2BackwardDelay = 1
        self.fetch2InputBufferSize = 2
        self.fetch2ToDecodeForwardDelay = 1
        self.fetch2CycleInput = True
        self.decodeInputBufferSize = 2
        self.decodeToExecuteForwardDelay = 1
        self.decodeInputWidth = 2
        self.decodeCycleInput = False
        self.executeInputWidth = 8
        self.executeCycleInput = False
        self.executeInputBufferSize = 8
        self.executeIssueLimit = 1
        self.executeMemoryIssueLimit = 1
        self.executeCommitLimit = 2
        self.executeMemoryCommitLimit = 1
        self.executeBranchDelay = 1
        self.executeMaxAccessesInMemory = 1
        self.executeLSQMaxStoreBufferStoresPerCycle = 1
        self.executeLSQRequestsQueueSize = 2
        self.executeLSQTransfersQueueSize = 2
        self.executeLSQStoreBufferSize = 8

        self.branchPred = LocalBP(
            localPredictorSize=1024,
            localCtrBits=2,
            instShiftAmt=2,
        )
        self.branchPred.btb = SimpleBTB(
            numEntries=64,
            tagBits=20,
            associativity=16,
            instShiftAmt=2,
            btbReplPolicy=LRURP(),
        )
        self.branchPred.ras = ReturnAddrStack(
            numEntries=2,
        )


class CVA6Processor(BaseCPUProcessor):
    def __init__(self, cpu_overrides=None, bp_overrides=None, morillas=False):
        if morillas:
            cpu = MorillasCPU()
        else:
            cpu = CVA6CPU(overrides=cpu_overrides, bp=bp_overrides)
        core = BaseCPUCore(core=cpu, isa=ISA.RISCV)
        super().__init__(cores=[core])


class CVA6CacheHierarchy(PrivateL1CacheHierarchy):
    def __init__(self, l1d_size, l1i_size, dcache_overrides=None,
                 icache_overrides=None, morillas=False):
        super().__init__(l1d_size=l1d_size, l1i_size=l1i_size)
        self._dcache_overrides = dict(dcache_overrides or {})
        self._icache_overrides = dict(icache_overrides or {})
        self._membus_width = self._dcache_overrides.pop("_membus_width", 8)
        self._dcache_overrides.pop("_mem_bandwidth", None)
        self._morillas = morillas

    def incorporate_cache(self, board):
        super().incorporate_cache(board)

        # Morillas 2025 leaves the gem5 crossbar at its default latencies.
        if not self._morillas:
            self.membus.frontend_latency = 1
            self.membus.forward_latency = 1
            self.membus.response_latency = 1
            self.membus.width = self._membus_width

        for i, core in enumerate(board.get_processor().get_cores()):
            if self._morillas:
                # Thesis Table 6.4, transcribed as published. Neither the
                # replacement policy nor the prefetcher is overridden, so the
                # gem5 defaults apply.
                self.l1icaches[i].assoc = 4
                self.l1icaches[i].tag_latency = 1
                self.l1icaches[i].data_latency = 2
                self.l1icaches[i].response_latency = 2
                self.l1icaches[i].mshrs = 4
                self.l1icaches[i].tgts_per_mshr = 1
                self.l1icaches[i].is_read_only = True
                self.l1icaches[i].writeback_clean = True

                self.l1dcaches[i].assoc = 8
                self.l1dcaches[i].tag_latency = 1
                self.l1dcaches[i].data_latency = 2
                self.l1dcaches[i].response_latency = 2
                self.l1dcaches[i].mshrs = 2
                self.l1dcaches[i].tgts_per_mshr = 1
                self.l1dcaches[i].write_buffers = 8
                self.l1dcaches[i].is_read_only = False
                self.l1dcaches[i].writeback_clean = True
                continue

            # Adopted baseline, identical to gem5_config_CVA6.py.
            self.l1icaches[i].assoc = 4
            self.l1icaches[i].tag_latency = 1
            self.l1icaches[i].data_latency = 1
            self.l1icaches[i].response_latency = 0
            self.l1icaches[i].mshrs = 1
            self.l1icaches[i].tgts_per_mshr = 16
            self.l1icaches[i].is_read_only = True
            self.l1icaches[i].sequential_access = False
            self.l1icaches[i].writeback_clean = False
            self.l1icaches[i].replacement_policy = RandomRP()

            self.l1dcaches[i].assoc = 8
            self.l1dcaches[i].tag_latency = 1
            self.l1dcaches[i].data_latency = 1
            self.l1dcaches[i].response_latency = 4
            self.l1dcaches[i].mshrs = 8
            self.l1dcaches[i].tgts_per_mshr = 16
            self.l1dcaches[i].write_buffers = 8
            self.l1dcaches[i].is_read_only = False
            self.l1dcaches[i].sequential_access = False
            self.l1dcaches[i].writeback_clean = False
            self.l1dcaches[i].prefetcher = NULL
            self.l1dcaches[i].replacement_policy = RandomRP()

            for key, value in self._icache_overrides.items():
                setattr(self.l1icaches[i], key, value)
            for key, value in self._dcache_overrides.items():
                setattr(self.l1dcaches[i], key, value)


parser = argparse.ArgumentParser(
    description="CVA6 replication on gem5 (calibration harness)")
parser.add_argument("binary", type=str,
                    help="Path to the compiled RISC-V ELF binary")
args = parser.parse_args()

if USE_MORILLAS:
    test_name = "Morillas 2025 full configuration"
    clk_freq = "50MHz"
    l1i_size, l1d_size = "16KiB", "32KiB"
    cpu_overrides = dcache_overrides = icache_overrides = bp_overrides = {}
    mem_latency = None
    mem_bandwidth = "12.8GiB/s"
else:
    if TEST not in ALL_TESTS:
        raise ValueError(
            f"TEST={TEST} is not in the test table. "
            f"Valid IDs: {sorted(ALL_TESTS.keys())}")
    (test_name, cpu_overrides, l1i_size, l1d_size, dcache_overrides,
     icache_overrides, clk_freq, mem_latency, bp_overrides) = resolve(TEST)
    mem_bandwidth = dict(dcache_overrides).get("_mem_bandwidth", "12.8GiB/s")

print("=" * 70)
if USE_MORILLAS:
    print("   MORILLAS 2025 FULL CONFIGURATION")
else:
    print(f"   CVA6 HARNESS  -  TEST {TEST}: {test_name}")
    if TEST in CACHE_TESTS:
        print(f"   Laid over     : TEST {CACHE_BASE_TEST}, "
              f"{TESTS[CACHE_BASE_TEST][0]}")
    print(f"   CPU overrides : {cpu_overrides}")
    print(f"   BP overrides  : {bp_overrides}")
    print(f"   Mem latency   : {mem_latency}   Bandwidth: {mem_bandwidth}")
print(f"   Binary        : {args.binary}")
print("=" * 70)

binary = BinaryResource(args.binary)

processor = CVA6Processor(
    cpu_overrides=cpu_overrides,
    bp_overrides=bp_overrides,
    morillas=USE_MORILLAS,
)

cache_hierarchy = CVA6CacheHierarchy(
    l1d_size=l1d_size,
    l1i_size=l1i_size,
    dcache_overrides=dcache_overrides,
    icache_overrides=icache_overrides,
    morillas=USE_MORILLAS,
)

if USE_MORILLAS:
    memory = SingleChannelDDR3_1600(size="1GiB")
else:
    memory = SingleChannelSimpleMemory(
        latency=mem_latency,
        latency_var="0ns",
        bandwidth=mem_bandwidth,
        size="1GiB",
    )

board = SimpleBoard(
    clk_freq=clk_freq,
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# Morillas 2025 does not set the cache line size, so the gem5 default of 64
# bytes applies.
if not USE_MORILLAS:
    board.cache_line_size = 16
board.set_se_binary_workload(binary)

for _core in board.get_processor().get_cores():
    _core.core.workload[0].cmd = [os.path.basename(args.binary)]

simulator = Simulator(board=board)
print("Starting CVA6 simulation")
simulator.run()

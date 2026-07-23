import argparse

from m5.params import NULL  # type: ignore
from gem5.components.boards.simple_board import SimpleBoard  # type: ignore
from gem5.components.processors.base_cpu_core import BaseCPUCore  # type: ignore
from gem5.components.processors.base_cpu_processor import BaseCPUProcessor  # type: ignore
from gem5.components.memory.simple import SingleChannelSimpleMemory  # type: ignore
from gem5.components.memory.single_channel import SingleChannelDDR3_1600  # type: ignore
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
    TreePLRURP,
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
)

# Calibration harness for the CVA6 gem5 MinorCPU configuration. TEST 1 is the
# final matched baseline. Every other TEST is a single-knob perturbation used
# to localise a divergence during calibration, or a published alternative for
# comparison.
#
# TEST table fields:
#   (name, cpu_overrides, l1i_size, l1d_size, dcache_overrides,
#    icache_overrides, clk_freq, mem_latency, bp_overrides)
#
#   1   matched baseline
#   2   store forwarding re-enabled (isolate the LSQ patch)
#   3   replay delay 2 -> 0 (isolate the re-request modelling)
#   4   L1D replacement PLRU -> LRU (isolate the policy)
#   5   L1I replacement random -> LRU (isolate the policy)
#   6   fetch1FetchLimit 2 -> 1 (reproduce the fetch starvation)
#   7   fetch1FetchLimit 2 -> 3 (fetch headroom check)
#   8   Morillas 2025 branch predictor only (over our baseline)
#   9   FU latency int_mul/fp_cvt/fp_noncomp +1 (execute-latency check)
#  10   FU latency as 9 plus fp_addmul 3 -> 4 (double-precision check)
#  11   LSQ requests queue 2 -> 4 (store-load throughput check)
#  12   LSQ requests queue 2 -> 8 (store-load throughput check)
#  13   LSQ store buffer 4 -> 8 (store-load throughput check)
#  14   LSQ requests queue 8 and store buffer 8 (store-load throughput check)
#
# The full Morillas 2025 configuration is a separate path, not a TEST row,
# because it changes the memory model, the cache line size and the whole FU
# schedule, none of which fit the single-knob override mechanism. Select it
# with USE_MORILLAS below.

TEST = 1

# When True, ignore the TEST table and run the full Morillas 2025 config.
USE_MORILLAS = False


TESTS = {
    1: ("matched baseline",              {}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
    2: ("store forwarding on",           {"executeLSQNoStoreForwarding": False,
                                          "executeLSQStoreCollisionReplayDelay": 0}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
    3: ("replay delay 2->0",             {"executeLSQStoreCollisionReplayDelay": 0}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
    4: ("L1D PLRU->LRU",                 {}, "16KiB", "32KiB", {"replacement_policy": LRURP()}, {}, "50MHz", "60ns", {}),
    5: ("L1I random->LRU",               {}, "16KiB", "32KiB", {}, {"replacement_policy": LRURP()}, "50MHz", "60ns", {}),
    6: ("fetch1FetchLimit 2->1",         {"fetch1FetchLimit": 1}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
    7: ("fetch1FetchLimit 2->3",         {"fetch1FetchLimit": 3}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
    8: ("Morillas branch predictor",     {}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns",
        {"localPredictorSize": 1024, "bhtInstShiftAmt": 2,
         "btbNumEntries": 64, "btbAssociativity": 16, "btbInstShiftAmt": 2}),
    9: ("FU exec latency +1",            {}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns",
        {"fuLatency": "a1"}),
    10: ("FU exec latency +1, addmul 4", {}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns",
         {"fuLatency": "a2"}),
    11: ("LSQ requests queue 2->4",      {"executeLSQRequestsQueueSize": 4}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
    12: ("LSQ requests queue 2->8",      {"executeLSQRequestsQueueSize": 8}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
    13: ("LSQ store buffer 4->8",        {"executeLSQStoreBufferSize": 8}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
    14: ("LSQ queue 8 buffer 8",         {"executeLSQRequestsQueueSize": 8, "executeLSQStoreBufferSize": 8}, "16KiB", "32KiB", {}, {}, "50MHz", "60ns", {}),
}


def minorMakeOpClassSet(op_classes):
    def boxOpClass(op_class):
        return MinorOpClass(opClass=op_class)
    return MinorOpClassSet(opClasses=[boxOpClass(o) for o in op_classes])


# fu_latency selects the scalar-integer and scalar-FP execute latencies.
#   "baseline"  the matched CVA6 values
#   "a1"        int_mul 2, fp_cvt 3, fp_noncomp 2 (RTL registers plus one)
#   "a2"        a1 plus fp_addmul 4 (double-precision ADDMUL)
_FU_LAT = {
    "baseline": {"int_mul": 1, "int_div": 20, "fp_addmul": 3, "fp_cvt": 2,
                 "fp_noncomp": 1, "fp_divsqrt": 20, "mem_fu": 2},
    "a1":       {"int_mul": 2, "int_div": 20, "fp_addmul": 3, "fp_cvt": 3,
                 "fp_noncomp": 2, "fp_divsqrt": 20, "mem_fu": 2},
    "a2":       {"int_mul": 2, "int_div": 20, "fp_addmul": 4, "fp_cvt": 3,
                 "fp_noncomp": 2, "fp_divsqrt": 20, "mem_fu": 2},
}


class CVA6FUPool(MinorFUPool):
    def __init__(self, fu_latency="baseline"):
        super().__init__()
        lat = _FU_LAT[fu_latency]

        int_alu = MinorFU()
        int_alu.opClasses = minorMakeOpClassSet(['IntAlu'])
        int_alu.opLat = 1
        int_alu.issueLat = 1

        int_mul = MinorFU()
        int_mul.opClasses = minorMakeOpClassSet(['IntMult'])
        int_mul.opLat = lat["int_mul"]
        int_mul.issueLat = 1

        int_div = MinorFU()
        int_div.opClasses = minorMakeOpClassSet(['IntDiv'])
        int_div.opLat = lat["int_div"]
        int_div.issueLat = lat["int_div"]

        fp_addmul = MinorFU()
        fp_addmul.opClasses = minorMakeOpClassSet(
            ['FloatAdd', 'FloatMult', 'FloatMultAcc'])
        fp_addmul.opLat = lat["fp_addmul"]
        fp_addmul.issueLat = 1

        fp_cvt = MinorFU()
        fp_cvt.opClasses = minorMakeOpClassSet(['FloatCvt'])
        fp_cvt.opLat = lat["fp_cvt"]
        fp_cvt.issueLat = 1

        fp_noncomp = MinorFU()
        fp_noncomp.opClasses = minorMakeOpClassSet(['FloatCmp', 'FloatMisc'])
        fp_noncomp.opLat = lat["fp_noncomp"]
        fp_noncomp.issueLat = 1

        fp_divsqrt = MinorFU()
        fp_divsqrt.opClasses = minorMakeOpClassSet(['FloatDiv', 'FloatSqrt'])
        fp_divsqrt.opLat = lat["fp_divsqrt"]
        fp_divsqrt.issueLat = 17

        mem_fu = MinorFU()
        mem_fu.opClasses = minorMakeOpClassSet(['MemRead', 'MemWrite'])
        mem_fu.opLat = lat["mem_fu"]
        mem_fu.issueLat = 1

        simd_int_fast = MinorDefaultFloatSimdFU()
        simd_int_fast.opClasses = minorMakeOpClassSet([
            'SimdAdd', 'SimdAlu', 'SimdCmp', 'SimdShift',
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
            'SimdFloatMisc', 'SimdFloatMult', 'SimdFloatMultAcc', 'SimdFloatExt',
            'SimdReduceAdd', 'SimdReduceAlu', 'SimdReduceCmp',
            'SimdFloatReduceAdd', 'SimdFloatReduceCmp',
            'SimdAes', 'SimdAesMix', 'SimdSha1Hash', 'SimdSha1Hash2',
            'SimdSha256Hash', 'SimdSha256Hash2', 'SimdShaSigma2', 'SimdShaSigma3'
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

        vec_mem_fast = MinorFU()
        vec_mem_fast.opClasses = minorMakeOpClassSet([
            'FloatMemRead', 'FloatMemWrite',
            'SimdUnitStrideLoad', 'SimdUnitStrideStore',
            'SimdUnitStrideMaskLoad', 'SimdUnitStrideMaskStore',
            'SimdUnitStrideFaultOnlyFirstLoad',
            'SimdWholeRegisterLoad', 'SimdWholeRegisterStore'
        ])
        vec_mem_fast.timings = [MinorFUTiming(
            description='VecMemFast', srcRegsRelativeLats=[1], extraAssumedLat=2)]
        vec_mem_fast.opLat = 2
        vec_mem_fast.issueLat = 1

        vec_mem_slow = MinorFU()
        vec_mem_slow.opClasses = minorMakeOpClassSet([
            'SimdStridedLoad', 'SimdStridedStore',
            'SimdIndexedLoad', 'SimdIndexedStore'
        ])
        vec_mem_slow.timings = [MinorFUTiming(
            description='VecMemSlow', srcRegsRelativeLats=[1], extraAssumedLat=2)]
        vec_mem_slow.opLat = 10
        vec_mem_slow.issueLat = 4

        misc = MinorDefaultMiscFU()
        misc.opClasses = minorMakeOpClassSet(['InstPrefetch'])
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
    # Transcribed from the Morillas 2025 configuration as published (thesis
    # Table 6.2). The op-class groupings differ from ours: FloatMisc sits with
    # the fast ADDMUL group, FloatSqrt sits with FloatCvt, and FloatDiv is
    # alone and unpipelined. Integer divide is a single averaged latency of 35,
    # the midpoint of the RTL range 2 to 64 with the uniform plus two added.
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

        # Catch-all for any op class not named above.
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
        fu_latency = bp.pop("fuLatency", "baseline")

        self.executeFuncUnits = CVA6FUPool(fu_latency=fu_latency)

        self.fetch1FetchLimit = 2
        self.fetch1LineSnapWidth = 4
        self.fetch1LineWidth = 4
        self.fetch1ToFetch2ForwardDelay = 1
        self.fetch1ToFetch2BackwardDelay = 1
        self.fetch2InputBufferSize = 2
        self.fetch2ToDecodeForwardDelay = 1
        self.fetch2CycleInput = False
        self.decodeInputBufferSize = 4
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
        self.executeLSQNoStoreForwarding = True
        self.executeLSQStoreCollisionReplayDelay = 2
        self.executeBranchDelay = 1
        self.executeSetTraceTimeOnCommit = True
        self.executeSetTraceTimeOnIssue = False
        self.executeAllowEarlyMemoryIssue = True
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
    # Faithful transcription of the Morillas 2025 configuration (thesis
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
        self._morillas = morillas

    def incorporate_cache(self, board):
        super().incorporate_cache(board)

        # Morillas 2025 leaves the gem5 crossbar at its default latencies.
        if not self._morillas:
            self.membus.frontend_latency = 1
            self.membus.forward_latency = 1
            self.membus.response_latency = 1

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

            self.l1icaches[i].assoc = 4
            self.l1icaches[i].tag_latency = 1
            self.l1icaches[i].data_latency = 1
            self.l1icaches[i].response_latency = 1
            self.l1icaches[i].mshrs = 1
            self.l1icaches[i].tgts_per_mshr = 16
            self.l1icaches[i].is_read_only = True
            self.l1icaches[i].sequential_access = False
            self.l1icaches[i].writeback_clean = False
            self.l1icaches[i].replacement_policy = RandomRP()

            self.l1dcaches[i].assoc = 8
            self.l1dcaches[i].tag_latency = 1
            self.l1dcaches[i].data_latency = 1
            self.l1dcaches[i].response_latency = 1
            self.l1dcaches[i].mshrs = 8
            self.l1dcaches[i].tgts_per_mshr = 16
            self.l1dcaches[i].write_buffers = 8
            self.l1dcaches[i].is_read_only = False
            self.l1dcaches[i].sequential_access = False
            self.l1dcaches[i].writeback_clean = False
            self.l1dcaches[i].prefetcher = NULL
            self.l1dcaches[i].replacement_policy = TreePLRURP()

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
else:
    if TEST not in TESTS:
        raise ValueError(
            f"TEST={TEST} is not in the test table. Valid IDs: {sorted(TESTS.keys())}")
    (test_name, cpu_overrides, l1i_size, l1d_size, dcache_overrides,
     icache_overrides, clk_freq, mem_latency, bp_overrides) = TESTS[TEST]

print("=" * 70)
if USE_MORILLAS:
    print("   MORILLAS 2025 FULL CONFIGURATION")
else:
    print(f"   CVA6 MATCH  -  TEST {TEST}: {test_name}")
    print(f"   CPU overrides : {cpu_overrides}")
    print(f"   BP overrides  : {bp_overrides}")
    print(f"   Mem latency   : {mem_latency}")
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
        bandwidth="12.8GiB/s",
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

simulator = Simulator(board=board)
print("Starting CVA6 simulation")
simulator.run()

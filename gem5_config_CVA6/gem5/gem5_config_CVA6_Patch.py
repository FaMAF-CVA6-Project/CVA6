import argparse
import os

from m5.params import NULL  # type: ignore
from gem5.components.boards.simple_board import SimpleBoard  # type: ignore
from gem5.components.processors.base_cpu_core import BaseCPUCore  # type: ignore
from gem5.components.processors.base_cpu_processor import BaseCPUProcessor  # type: ignore
from gem5.components.memory.simple import SingleChannelSimpleMemory  # type: ignore
from gem5.components.memory.single_channel import SingleChannelDDR3_1600  # type: ignore
from gem5.components.memory.memory import ChanneledMemory  # type: ignore
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import (  # type: ignore
    PrivateL1CacheHierarchy,
)
from gem5.isas import ISA  # type: ignore
from gem5.simulate.simulator import Simulator  # type: ignore
from gem5.resources.resource import BinaryResource  # type: ignore

from m5.objects import (  # type: ignore
    Axi2MemPort,
    DDR3_1600_8x8,
    CVA6IcacheRandomRP,
    HPDcacheRandomRP,
    LocalBP,
    LRURP,
    TreePLRURP,
    RandomRP,
    MinorFUPool,
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

# gem5 MinorCPU configuration matched to CVA6 (cv64a6_imafdc_sv39_hpdcache_wb).
# Every value is either derived from a CVA6 RTL localparam or is a gem5-side
# estimate where CVA6 has no clean counterpart.
#
# The production configuration. Every transcribed mechanism is on by default
# and each has a --no- switch that turns it off, so this doubles as its own
# ablation harness. The README lists what each switch does.
#
# Comment the three executeLSQ lines and pass every --no- switch to run
# against a stock gem5.

CLK_FREQ = "50MHz"
L1I_SIZE = "16KiB"
L1D_SIZE = "32KiB"

# Cycles a load waits after a store collision clears, the CVA6 LSU re-request.
STORE_COLLISION_REPLAY_DELAY = 2

# Class extras on the dirty-victim readout window, the additive law's
# x and z terms (hpdcache_rtab.sv POP_TRY, hpdcache_flush.sv).
VICTIM_READOUT_STORE_EXTRA = 4
VICTIM_READOUT_FIRST_LOAD_EXTRA = 1

# Miss-latency split, L1D only. L1D_FILL_DELAY is the flat split used
# when the window mechanism is off. Under it the fill delay is 0,
# because the readout window charges the trigger's own fill and a flat
# delay on every fill would double-charge the base.
MEM_LATENCY = "0ns"
L1D_FILL_DELAY = 2
L1D_RESPONSE_LATENCY = 2
FROZEN_L1D_FILL_DELAY = 0
FROZEN_L1D_RESPONSE_LATENCY = 4


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


def serdivExtraLatency(base=2):
    """Data-dependent latency of the CVA6 integer divider."""
    bits_a = _un('timingExprSizeInBits', _src(0))
    bits_b = _un('timingExprSizeInBits', _src(1))
    diff = _bin('timingExprSub', bits_a, bits_b)
    # max(bits(a) - bits(b), 0), since the subtraction is unsigned and wraps
    clamped = _if(_bin('timingExprSGreaterThan',
                  bits_a, bits_b), diff, _lit(0))
    return _bin('timingExprAdd', clamped, _lit(base))


def minorMakeOpClassSet(op_classes):
    def boxOpClass(op_class):
        return MinorOpClass(opClass=op_class)
    return MinorOpClassSet(opClasses=[boxOpClass(o) for o in op_classes])


class CVA6FUPool(MinorFUPool):
    def __init__(self):
        super().__init__()

        int_alu = MinorFU()
        int_alu.opClasses = minorMakeOpClassSet(['IntAlu'])
        int_alu.opLat = 1
        int_alu.issueLat = 1

        int_mul = MinorFU()
        int_mul.opClasses = minorMakeOpClassSet(['IntMult'])
        int_mul.opLat = 2
        int_mul.issueLat = 1

        int_div = MinorFU()
        int_div.opClasses = minorMakeOpClassSet(['IntDiv'])
        int_div.opLat = 2
        int_div.issueLat = 3
        int_div.timings = [MinorFUTiming(
            description='IntDivSerdiv',
            srcRegsRelativeLats=[0],
            extraCommitLatExpr=serdivExtraLatency(base=1))]

        fp_addmul = MinorFU()
        fp_addmul.opClasses = minorMakeOpClassSet(
            ['FloatAdd', 'FloatMult', 'FloatMultAcc'])
        fp_addmul.opLat = 3
        fp_addmul.issueLat = 1
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
        fp_divsqrt.opLat = 15
        fp_divsqrt.issueLat = 15
        fp_divsqrt.timings = [MinorFUTiming(
            description='FpDivSqrtDouble',
            srcRegsRelativeLats=[0],
            mask=0x06000000,
            match=0x02000000,
            extraCommitLat=7)]

        mem_fu = MinorFU()
        mem_fu.opClasses = minorMakeOpClassSet(
            ['MemRead', 'MemWrite', 'FloatMemRead', 'FloatMemWrite'])
        mem_fu.opLat = 2
        mem_fu.issueLat = 1
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

        # Vector and SIMD units are inert under CVA6 RVV = 0, retained only for
        # op-class completeness.
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
            'SimdIndexedLoad', 'SimdIndexedStore',
            'SimdUnitStrideSegmentedLoad', 'SimdUnitStrideSegmentedStore',
            'SimdUnitStrideSegmentedFaultOnlyFirstLoad',
            'SimdStrideSegmentedLoad', 'SimdStrideSegmentedStore'
        ])
        vec_mem_slow.timings = [MinorFUTiming(
            description='VecMemSlow', srcRegsRelativeLats=[1], extraAssumedLat=2)]
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


class CVA6CPU(RiscvMinorCPU):
    def __init__(self, direct_targets=True, store_forwarding_model=True,
                 fence_signal=True, ras_no_recovery=True):
        super().__init__()

        self.executeFuncUnits = CVA6FUPool()

        # Pipeline.
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
        # Requires the MinorCPU patch. Each defaults to the stock behaviour,
        # so switching a mechanism off here leaves nothing of it behind.
        self.executeLSQNoStoreForwarding = store_forwarding_model
        self.executeLSQStoreCollisionReplayDelay = (
            STORE_COLLISION_REPLAY_DELAY if store_forwarding_model else 0)
        self.executeLSQFenceSignalsDcache = fence_signal

        # Branch predictor.
        self.branchPred = LocalBP(
            localPredictorSize=256,
            localCtrBits=2,
            instShiftAmt=1,
        )
        self.branchPred.btb = SimpleBTB(
            numEntries=32,
            tagBits=20,
            associativity=1,
            instShiftAmt=1,
            btbReplPolicy=LRURP(),
        )
        self.branchPred.ras = ReturnAddrStack(
            numEntries=2,
        )
        # Taken direct branches and jumps take their target from the
        # decoded instruction and never install in the BTB
        if direct_targets:
            self.branchPred.directTargetsFromDecode = True
            self.branchPred.indirectBranchPred = NULL
            self.branchPred.btb.tagBits = 0
            if ras_no_recovery:
                self.branchPred.rasNoRecovery = True


class CVA6Processor(BaseCPUProcessor):
    def __init__(self, direct_targets=True, store_forwarding_model=True,
                 fence_signal=True, ras_no_recovery=True):
        cpu = CVA6CPU(direct_targets=direct_targets,
                      store_forwarding_model=store_forwarding_model,
                      fence_signal=fence_signal,
                      ras_no_recovery=ras_no_recovery)
        core = BaseCPUCore(core=cpu, isa=ISA.RISCV)
        super().__init__(cores=[core])


class CVA6CacheHierarchy(PrivateL1CacheHierarchy):
    def __init__(self, l1d_size, l1i_size, evict_on_allocate=True,
                 victim_readout_stall=True, cva6_victim_policy=True,
                 victim_readable_until_fill=True, fill_phase=True,
                 fence_flush=True, icache_policy=True,
                 window_charge=True):
        super().__init__(l1d_size=l1d_size, l1i_size=l1i_size)
        self._evict_on_allocate = evict_on_allocate
        self._victim_readout_stall = victim_readout_stall
        self._cva6_victim_policy = cva6_victim_policy
        self._victim_readable_until_fill = victim_readable_until_fill
        self._fill_phase = fill_phase
        self._window_charge = window_charge
        self._fence_flush = fence_flush
        self._icache_policy = icache_policy

    def incorporate_cache(self, board):
        super().incorporate_cache(board)

        # The HPDcache reaches AXI with minimal interconnect delay, so the
        # gem5 crossbar latencies are trimmed to remove overhead CVA6 does
        # not incur.
        self.membus.frontend_latency = 1
        self.membus.forward_latency = 1
        self.membus.response_latency = 1
        self.membus.width = 8

        for i, core in enumerate(board.get_processor().get_cores()):
            # L1I: 16 KiB, 4-way, 128-bit line.
            self.l1icaches[i].assoc = 4
            self.l1icaches[i].tag_latency = 1
            self.l1icaches[i].data_latency = 1
            self.l1icaches[i].response_latency = 0
            self.l1icaches[i].mshrs = 1
            self.l1icaches[i].tgts_per_mshr = 16
            self.l1icaches[i].is_read_only = True
            self.l1icaches[i].sequential_access = False
            self.l1icaches[i].writeback_clean = False
            if self._icache_policy:
                # The transcribed cva6_icache.sv policy.
                self.l1icaches[i].replacement_policy = CVA6IcacheRandomRP()
            else:
                self.l1icaches[i].replacement_policy = RandomRP()

            # L1D: 32 KiB, 8-way, 128-bit line.
            self.l1dcaches[i].assoc = 8
            self.l1dcaches[i].tag_latency = 1
            self.l1dcaches[i].data_latency = 1
            self.l1dcaches[i].response_latency = (
                L1D_RESPONSE_LATENCY if self._fill_phase
                else FROZEN_L1D_RESPONSE_LATENCY)
            self.l1dcaches[i].fill_delay = (
                0 if self._window_charge
                else (L1D_FILL_DELAY if self._fill_phase
                      else FROZEN_L1D_FILL_DELAY))
            self.l1dcaches[i].fence_flushes_dcache = self._fence_flush
            self.l1dcaches[i].mshrs = 8
            self.l1dcaches[i].tgts_per_mshr = 16
            self.l1dcaches[i].write_buffers = 8
            self.l1dcaches[i].is_read_only = False
            self.l1dcaches[i].sequential_access = False
            self.l1dcaches[i].writeback_clean = False
            self.l1dcaches[i].prefetcher = NULL

            # Transcribed memory mechanisms, L1D only: the eviction story
            # is data-side and the read-only L1I produces no writebacks.
            if self._cva6_victim_policy:
                self.l1dcaches[i].replacement_policy = HPDcacheRandomRP()
            else:
                self.l1dcaches[i].replacement_policy = TreePLRURP()
            self.l1dcaches[i].evict_on_allocate = self._evict_on_allocate
            self.l1dcaches[i].victim_readout_stall = \
                self._victim_readout_stall
            self.l1dcaches[i].victim_readable_until_fill = \
                self._victim_readable_until_fill
            self.l1dcaches[i].window_accept_and_charge = self._window_charge
            self.l1dcaches[i].victim_readout_store_extra = (
                VICTIM_READOUT_STORE_EXTRA if self._window_charge else 0)
            self.l1dcaches[i].victim_readout_first_load_extra = (
                VICTIM_READOUT_FIRST_LOAD_EXTRA if self._window_charge
                else 0)


class Axi2MemPortedMemory(SingleChannelSimpleMemory):
    """SingleChannelSimpleMemory with the Axi2MemPort model in front."""

    def __init__(self, latency, latency_var, bandwidth, size):
        super().__init__(
            latency=latency,
            latency_var=latency_var,
            bandwidth=bandwidth,
            size=size,
        )
        self.port_model = Axi2MemPort()
        self.port_model.mem_side = self.module.port

    def get_mem_ports(self):
        return [(self.module.range, self.port_model.cpu_side)]


class Axi2MemPortedDDR3(ChanneledMemory):
    """SingleChannelDDR3_1600 with the Axi2MemPort model in front."""

    def __init__(self, size):
        super().__init__(DDR3_1600_8x8, 1, 64, size=size)
        self.port_model = Axi2MemPort()
        self.port_model.mem_side = self.mem_ctrl[0].port

    def get_mem_ports(self):
        return [(self.mem_ctrl[0].dram.range, self.port_model.cpu_side)]


parser = argparse.ArgumentParser(description="CVA6 replication on gem5")
parser.add_argument("binary", type=str,
                    help="Path to the compiled RISC-V ELF binary")
parser.add_argument("--ddr3", action="store_true",
                    help="Use the DDR3-1600 device instead of a flat memory "
                         "at MEM_LATENCY. Matches the Verilator DDR3 model in "
                         "verilator_changes/ddr3_memory.")
parser.add_argument("--no-patch", action="store_true",
                    help="Turn every transcribed mechanism below off at once, "
                         "leaving the stock MinorCPU behaviour the "
                         "calibration started from. A patched build run this "
                         "way should match a stock one exactly")
parser.add_argument("--no-port-model", action="store_true",
                    help="Remove the axi2mem single-port model")
parser.add_argument("--no-evict-on-allocate", action="store_true",
                    help="Select victims at fill time instead of at MSHR "
                         "allocation")
parser.add_argument("--no-victim-readout-stall", action="store_true",
                    help="Do not charge the 2-cycle dirty victim readout")
parser.add_argument("--no-cva6-victim-policy", action="store_true",
                    help="Use gem5 TreePLRU instead of the transcribed "
                         "HPDcache random policy")
parser.add_argument("--no-victim-readable-until-fill", action="store_true",
                    help="Make the victim unreachable at allocation instead "
                         "of at its refill")
parser.add_argument("--no-cva6-icache-policy", action="store_true",
                    help="L1I uses gem5 RandomRP instead of the transcribed "
                         "instruction cache policy")
parser.add_argument("--no-cva6-direct-targets", action="store_true",
                    help="Direct branches and jumps take targets from the "
                         "BTB only, the stock gem5 behaviour")
parser.add_argument("--no-store-forwarding-model", action="store_true",
                    help="Let the store buffer forward to loads, the stock "
                         "gem5 behaviour, and drop the replay delay with it")
parser.add_argument("--no-fence-flush", action="store_true",
                    help="A fence does not flush the L1D, and the core stops "
                         "signalling the cache")
parser.add_argument("--no-fill-phase", action="store_true",
                    help="Use the frozen miss-latency split, 0ns memory and "
                         "L1D response latency 4")
parser.add_argument("--no-window-charge", action="store_true",
                    help="Drop the accept-and-charge window mechanism and "
                         "its class extras, leaving the flat fill split")
parser.add_argument("--no-ras-decay", action="store_true",
                    help="Repair the RAS on squash, the stock gem5 "
                         "behaviour, instead of CVA6's unrecovered "
                         "stack")
args = parser.parse_args()

if args.no_patch:
    for _switch in vars(args):
        if _switch.startswith("no_") and _switch != "no_patch":
            setattr(args, _switch, True)

evict_on_allocate = not args.no_evict_on_allocate
victim_readout_stall = not args.no_victim_readout_stall
cva6_victim_policy = not args.no_cva6_victim_policy
victim_readable_until_fill = not args.no_victim_readable_until_fill
fill_phase = not args.no_fill_phase
window_charge = not args.no_window_charge
fence_flush = not args.no_fence_flush
store_forwarding_model = not args.no_store_forwarding_model
icache_policy = not args.no_cva6_icache_policy
direct_targets = not args.no_cva6_direct_targets

# The window charge is the readout window's accept-and-charge form.
if window_charge and not victim_readout_stall:
    parser.error("--no-victim-readout-stall also requires "
                 "--no-window-charge")

# The three cache levers all live under evict-at-allocate.
if not evict_on_allocate:
    if victim_readout_stall or victim_readable_until_fill:
        parser.error("--no-evict-on-allocate also requires "
                     "--no-victim-readout-stall and "
                     "--no-victim-readable-until-fill")

binary = BinaryResource(args.binary)

processor = CVA6Processor(direct_targets=direct_targets,
                          store_forwarding_model=store_forwarding_model,
                          fence_signal=fence_flush,
                          ras_no_recovery=not args.no_ras_decay)

cache_hierarchy = CVA6CacheHierarchy(
    l1d_size=L1D_SIZE,
    l1i_size=L1I_SIZE,
    evict_on_allocate=evict_on_allocate,
    victim_readout_stall=victim_readout_stall,
    cva6_victim_policy=cva6_victim_policy,
    victim_readable_until_fill=victim_readable_until_fill,
    fill_phase=fill_phase,
    window_charge=window_charge,
    fence_flush=fence_flush,
    icache_policy=icache_policy,
)

if args.ddr3:
    memory = (SingleChannelDDR3_1600(size="1GiB") if args.no_port_model
              else Axi2MemPortedDDR3(size="1GiB"))
else:
    mem_class = (SingleChannelSimpleMemory if args.no_port_model
                 else Axi2MemPortedMemory)
    memory = mem_class(
        latency=MEM_LATENCY,
        latency_var="0ns",
        bandwidth="12.8GiB/s",
        size="1GiB",
    )

board = SimpleBoard(
    clk_freq=CLK_FREQ,
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

board.cache_line_size = 16
board.set_se_binary_workload(binary)

for _core in board.get_processor().get_cores():
    _core.core.workload[0].cmd = [os.path.basename(args.binary)]

simulator = Simulator(board=board)
active = [n for n, on in (
    ("ddr3" if args.ddr3 else f"flat-mem-{MEM_LATENCY}", True),
    ("port-model", not args.no_port_model),
    ("evict-on-allocate", evict_on_allocate),
    ("victim-readout-stall", victim_readout_stall),
    ("cva6-victim-policy", cva6_victim_policy),
    ("victim-readable-until-fill", victim_readable_until_fill),
    ("fill-phase", fill_phase),
    ("window-charge", window_charge),
    ("fence-flush", fence_flush),
    ("cva6-icache-policy", icache_policy),
    ("cva6-direct-targets", direct_targets),
    ("store-forwarding-model", store_forwarding_model)) if on]
print("Starting CVA6 simulation with: " +
      (", ".join(active) if active else "no transcribed mechanisms"))
simulator.run()

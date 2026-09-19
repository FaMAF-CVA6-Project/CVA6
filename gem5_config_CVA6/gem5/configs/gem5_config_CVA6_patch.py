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
    TimingExprLet,
    TimingExprRef,
)

# gem5 MinorCPU configuration matched to CVA6 (cv64a6_imafdc_sv39_hpdcache_wb).
# Every value is either derived from a CVA6 RTL localparam or is a gem5-side
# estimate where CVA6 has no clean counterpart.
#
# The production configuration. Every transcribed mechanism is on by default
# and each has a --no- switch that turns it off, so this doubles as its own
# ablation harness. The README lists what each switch does.
#
# It needs the patched build even with --no-patch, for its imports and the
# patch parameters it sets. gem5_config_CVA6.py is the stock-gem5 version.

CLK_FREQ = "50MHz"
L1I_SIZE = "16KiB"
L1D_SIZE = "32KiB"

# Cycles a load waits after a store collision clears, the CVA6 LSU re-request.
STORE_COLLISION_REPLAY_DELAY = 2

# Class extras on the dirty-victim readout window, the additive law's
# x and z terms (hpdcache_rtab.sv POP_TRY, hpdcache_flush.sv).
VICTIM_READOUT_STORE_EXTRA = 4
VICTIM_READOUT_FIRST_LOAD_EXTRA = 1

# Miss-latency split, L1D only. L1D_FILL_DELAY is the flat split used when the
# window mechanism is off. Under the window the fill delay is 0, because it
# charges the trigger's own fill and a flat delay would double-charge.
MEM_LATENCY = "0ns"
L1D_FILL_DELAY = 2
L1D_RESPONSE_LATENCY = 2
FROZEN_L1D_FILL_DELAY = 0
FROZEN_L1D_RESPONSE_LATENCY = 4


def _lit(value):
    # The literal is a UInt64, so a negative bound goes in as its two's
    # complement, which the signed comparisons read back.
    e = TimingExprLiteral()
    e.value = value & 0xFFFFFFFFFFFFFFFF
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
    """Data-dependent latency of the CVA6 integer divider,
    max(bits(a) - bits(b), 0) + base. The calibration harnesses pass 0 for
    TEST 21, so base stays a parameter."""
    bits_a = _un('timingExprSizeInBits', _src(0))
    bits_b = _un('timingExprSizeInBits', _src(1))
    diff = _bin('timingExprSub', bits_a, bits_b)
    # max(bits(a) - bits(b), 0), since the subtraction is unsigned and wraps
    clamped = _if(_bin('timingExprSGreaterThan',
                  bits_a, bits_b), diff, _lit(0))
    return _bin('timingExprAdd', clamped, _lit(base))


# The C910 radix-16 SRT divider CVA6 runs (fpnew DivSqrtSel THMULTI) stops a
# round after its partial remainder reaches zero, so an exact short result
# runs short. Each timing's consumers wait for its commit, the latency unseen.
def _add(a, b): return _bin('timingExprAdd', a, b)
def _sub(a, b): return _bin('timingExprSub', a, b)
def _mul(a, b): return _bin('timingExprUMul', a, b)
def _div(a, b): return _bin('timingExprUDiv', a, b)
def _eq(a, b): return _bin('timingExprEqual', a, b)
def _ne(a, b): return _bin('timingExprNotEqual', a, b)
def _ult(a, b): return _bin('timingExprULessThan', a, b)
def _sgt(a, b): return _bin('timingExprSGreaterThan', a, b)
def _slt(a, b): return _bin('timingExprSLessThan', a, b)
def _and(a, b): return _bin('timingExprAnd', a, b)   # logical
def _or(a, b): return _bin('timingExprOr', a, b)     # logical


class _Let:
    """One TimingExprLet. bind() stores a subterm once and returns a factory
    of fresh TimingExprRef nodes, so no SimObject has two parents and no
    subterm is evaluated twice (timing_expr.cc memoises Refs per Let)."""

    def __init__(self):
        self.defns = []

    def bind(self, expr):
        self.defns.append(expr)
        index = len(self.defns) - 1

        def ref():
            e = TimingExprRef()
            e.index = index
            return e
        return ref

    def build(self, body):
        e = TimingExprLet()
        e.defns = self.defns
        e.expr = body
        return e


def _mod_pow2(x_ref, k):
    """x mod 2**k, with x already bound."""
    p = 1 << k
    return _sub(x_ref(), _mul(_div(x_ref(), _lit(p)), _lit(p)))


# ------------------------------------------------------ operand decoding


def _decode(let, fmt, index):
    """Bind sign, biased exponent, fraction and the normalised 53-bit
    significand of source`index`."""
    if fmt == 'd':
        v = let.bind(_src(index))
        sign = let.bind(_div(v(), _lit(1 << 63)))
        e = let.bind(_div(_mod_pow2(v, 63), _lit(1 << 52)))
        f = let.bind(_mod_pow2(v, 52))
        emax = 0x7FF
    else:
        v64 = let.bind(_src(index))
        v = let.bind(_mod_pow2(v64, 32))
        sign = let.bind(_div(v(), _lit(1 << 31)))
        e = let.bind(_div(_mod_pow2(v, 31), _lit(1 << 23)))
        f = let.bind(_mul(_mod_pow2(v, 23), _lit(1 << 29)))
        emax = 0xFF

    # Subnormal normalisation, a six-step binary shift network. c_j is 1 when
    # the step shifts by 2**j, and the total shift sh = 53 - bitlen(f).
    x = f
    shift_terms = []
    for j, limit in ((5, 21), (4, 37), (3, 45), (2, 49), (1, 51), (0, 52)):
        c = let.bind(_ult(x(), _lit(1 << limit)))
        x_prev = x
        x = let.bind(_if(c(), _mul(x_prev(), _lit(1 << (1 << j))), x_prev()))
        shift_terms.append((c, 1 << j))
    sh = None
    for c, w in shift_terms:
        term = _mul(c(), _lit(w))
        sh = term if sh is None else _add(sh, term)
    sh = let.bind(sh)

    is_sub = let.bind(_eq(e(), _lit(0)))
    sig = let.bind(_if(is_sub(), x(), _add(f(), _lit(1 << 52))))
    # biased exponent, 1 - sh for a subnormal (ct_vfdsu_ff1.v frac_bin_val)
    exp = let.bind(_if(is_sub(), _sub(_lit(1), sh()), e()))
    zero = _and(_eq(e(), _lit(0)), _eq(f(), _lit(0)))
    special = let.bind(_or(_eq(e(), _lit(emax)), zero))
    return dict(sign=sign, e=e, f=f, sig=sig, exp=exp, special=special)


# ------------------------------------------------------------ the law


def _div_rounds(fmt):
    """m for fdiv.{s,d}."""
    N = 13 if fmt == 'd' else 6
    let = _Let()
    a = _decode(let, fmt, 0)
    b = _decode(let, fmt, 1)
    A, B = a['sig'], b['sig']

    # rem_zero after round k  <=>  B divides A * 2**(4k-2)
    # (Q = A / 4B, the first quotient digit weighs 1/16). r_k is that
    # residue, r_1 = 4A mod B and r_{k+1} = 16 r_k mod B. Zero is absorbing.
    def mod_b(x_factory):
        return _sub(x_factory(), _mul(_div(x_factory(), B()), B()))

    r = let.bind(mod_b(lambda: _mul(_lit(4), A())))
    rounds = _lit(1)
    for k in range(1, N):
        rounds = _add(rounds, _ne(r(), _lit(0)))
        if k < N - 1:
            r_prev = r
            r = let.bind(mod_b(lambda rp=r_prev: _mul(_lit(16), rp())))

    diff = let.bind(_sub(a['exp'](), b['exp']()))
    of_lim, uf_lim = (1024, -1075) if fmt == 'd' else (128, -150)
    skip = _or(_or(a['special'](), b['special']()),
               _or(_sgt(diff(), _lit(of_lim)), _slt(diff(), _lit(uf_lim))))
    return let.build(_if(skip, _lit(0), rounds))


def _sqrt_rounds(fmt):
    """m for fsqrt.{s,d}."""
    N = 13 if fmt == 'd' else 6
    let = _Let()
    a = _decode(let, fmt, 0)

    # radicand at the double scale, doubled when the unbiased exponent is odd
    exp = a['exp']
    odd = _eq(_sub(exp(), _mul(_div(exp(), _lit(2)), _lit(2))), _lit(0))
    c = let.bind(_if(odd, _mul(a['sig'](), _lit(2)), a['sig']()))

    # y = isqrt(c) by integer Newton from above, c in [2**52, 2**54)
    y = let.bind(_lit(1 << 27))
    for _ in range(6):
        y_prev = y
        y = let.bind(_div(_add(y_prev(), _div(c(), y_prev())), _lit(2)))

    # root significand y / 2**26, and rem_zero after round k
    # <=>  2**(28-4k) divides y
    exact = _eq(_mul(y(), y()), c())
    rounds = _lit(1)
    for k in range(1, N):
        if 28 - 4 * k <= 0:
            break
        rounds = _add(rounds, _ne(_mod_pow2(y, 28 - 4 * k), _lit(0)))

    skip = _or(a['special'](), _ne(a['sign'](), _lit(0)))
    return let.build(_if(skip, _lit(0),
                         _if(exact, rounds, _lit(N))))


# ------------------------------------------------------- MinorFUTiming

# funct7 [31:25] and opcode [6:0] of OP-FP
_MASK = 0xFE00007F
_MATCH = {
    ('div', 's'): (0x0C << 25) | 0x53,
    ('div', 'd'): (0x0D << 25) | 0x53,
    ('sqrt', 's'): (0x2C << 25) | 0x53,
    ('sqrt', 'd'): (0x2D << 25) | 0x53,
}

# Issue to writeback is 8 + R with R = m + 1 SRT rounds: five hand-offs lead
# into the first round and four follow the last, so opLat is 9 and the
# expression adds m.
FP_DIVSQRT_BASE_LAT = 9

# A divide or root arriving while the unit is busy waits in fpnew's input
# register and starts in the WB cycle of the one ahead, so it writes back
# 6 + m after that one, 3 cycles sooner than a start at the writeback.
FP_DIVSQRT_QUEUE_OVERLAP = 3


def fpDivSqrtTimings(extra=0):
    timings = []
    for (op, fmt), match in _MATCH.items():
        expr = _div_rounds(fmt) if op == 'div' else _sqrt_rounds(fmt)
        if extra:
            expr = _add(expr, _lit(extra))
        timings.append(MinorFUTiming(
            description=f'FpDivSqrt_{op}_{fmt}',
            srcRegsRelativeLats=[0],
            mask=_MASK,
            match=match,
            extraCommitLatExpr=expr,
            consumersWaitForCommit=True))
    return timings


def flatDivSqrtTimings(extra=0):
    # The flat law, 15 cycles and 7 more for a double.
    timings = [MinorFUTiming(
        description='FpDivSqrtDouble',
        srcRegsRelativeLats=[0],
        mask=0x06000000,
        match=0x02000000,
        extraCommitLat=7 + extra)]
    if extra:
        timings.append(MinorFUTiming(
            description='FpDivSqrtSingle',
            srcRegsRelativeLats=[0],
            mask=0x06000000,
            match=0x00000000,
            extraCommitLat=extra))
    return timings


def minorMakeOpClassSet(op_classes):
    def boxOpClass(op_class):
        return MinorOpClass(opClass=op_class)
    return MinorOpClassSet(opClasses=[boxOpClass(o) for o in op_classes])


class CVA6FUPool(MinorFUPool):
    def __init__(self, c910_divider=True, divider_queue=True):
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
        # fpnew's input register, and a divider that writes back out of order.
        # The overlap moves out of opLat into the extra latency, where a held
        # operation skips it.
        overlap = FP_DIVSQRT_QUEUE_OVERLAP if divider_queue else 0
        if divider_queue:
            fp_divsqrt.holdWhileBusy = True
            fp_divsqrt.heldLatencyOverlap = overlap
            fp_divsqrt.extraCommitLatFromFUEnd = True
        if c910_divider:
            fp_divsqrt.opLat = FP_DIVSQRT_BASE_LAT - overlap
            fp_divsqrt.issueLat = FP_DIVSQRT_BASE_LAT - overlap
            fp_divsqrt.timings = fpDivSqrtTimings(overlap)
        else:
            # The flat law, exact for every full-count operation.
            fp_divsqrt.opLat = 15 - overlap
            fp_divsqrt.issueLat = 15 - overlap
            fp_divsqrt.timings = flatDivSqrtTimings(overlap)

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

        vec_mem_fast = MinorFU()
        vec_mem_fast.opClasses = minorMakeOpClassSet([
            'SimdUnitStrideLoad', 'SimdUnitStrideStore',
            'SimdUnitStrideMaskLoad', 'SimdUnitStrideMaskStore',
            'SimdUnitStrideFaultOnlyFirstLoad',
            'SimdWholeRegisterLoad', 'SimdWholeRegisterStore'
        ])
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


class CVA6CPU(RiscvMinorCPU):
    def __init__(self, direct_targets=True, store_forwarding_model=True,
                 fence_signal=True, ras_no_recovery=True,
                 fence_squash=True, icache_hold=True,
                 kill_on_redirect=True, fetch_limit=None,
                 fetch2_buffer=None, c910_divider=True, divider_queue=True,
                 drop_killed_lines=True):
        super().__init__()

        self.executeFuncUnits = CVA6FUPool(c910_divider=c910_divider,
                                           divider_queue=divider_queue)

        # This config adopts depth 3 and gem5_config_CVA6.py keeps 2, so a
        # parity run against the stock build needs a way to make them equal.
        self.fetch1FetchLimit = (
            3 if fetch_limit is None else fetch_limit)
        self.fetch1LineSnapWidth = 4
        self.fetch1LineWidth = 4
        self.fetch1ToFetch2ForwardDelay = 1
        self.fetch1ToFetch2BackwardDelay = 0
        self.fetch2InputBufferSize = (
            3 if fetch2_buffer is None else fetch2_buffer)
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
        # Requires the MinorCPU patch.
        self.fetch1WaitsForIcache = icache_hold
        self.fetch1KillsOnRedirect = kill_on_redirect
        self.fetch1DropsKilledLines = drop_killed_lines
        self.executeLSQNoStoreForwarding = store_forwarding_model
        self.executeLSQStoreCollisionReplayDelay = (
            STORE_COLLISION_REPLAY_DELAY if store_forwarding_model else 0)
        self.executeLSQFenceSignalsDcache = fence_signal
        self.executeFenceSquashesPipeline = fence_squash

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
        # Taken direct branches and jumps take their target from decode, and
        # the tagless BTB serves only indirect control, as CVA6's front end.
        if direct_targets:
            self.branchPred.directTargetsFromDecode = True
            self.branchPred.indirectBranchPred = NULL
            self.branchPred.btb.tagBits = 0

        if ras_no_recovery:
            self.branchPred.rasNoRecovery = True


class CVA6Processor(BaseCPUProcessor):
    def __init__(self, direct_targets=True, store_forwarding_model=True,
                 fence_signal=True, ras_no_recovery=True,
                 fence_squash=True, icache_hold=True,
                 kill_on_redirect=True, fetch_limit=None,
                 fetch2_buffer=None, c910_divider=True, divider_queue=True,
                 drop_killed_lines=True):
        cpu = CVA6CPU(direct_targets=direct_targets,
                      store_forwarding_model=store_forwarding_model,
                      fence_signal=fence_signal,
                      fence_squash=fence_squash,
                      ras_no_recovery=ras_no_recovery,
                      icache_hold=icache_hold,
                      kill_on_redirect=kill_on_redirect,
                      fetch_limit=fetch_limit,
                      fetch2_buffer=fetch2_buffer,
                      c910_divider=c910_divider,
                      divider_queue=divider_queue,
                      drop_killed_lines=drop_killed_lines)
        core = BaseCPUCore(core=cpu, isa=ISA.RISCV)
        super().__init__(cores=[core])


class CVA6CacheHierarchy(PrivateL1CacheHierarchy):
    def __init__(self, l1d_size, l1i_size, evict_on_allocate=True,
                 victim_readout_stall=True, cva6_victim_policy=True,
                 l1d_plru=False,
                 victim_readable_until_fill=True, fill_phase=True,
                 fence_flush=True, icache_policy=True,
                 window_charge=True, icache_structure=True,
                 fill_at_response=True):
        super().__init__(l1d_size=l1d_size, l1i_size=l1i_size)
        self._fill_at_response = fill_at_response
        self._icache_structure = icache_structure
        self._evict_on_allocate = evict_on_allocate
        self._victim_readout_stall = victim_readout_stall
        self._cva6_victim_policy = cva6_victim_policy
        self._l1d_plru = l1d_plru
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
            if self._icache_structure:
                self.l1icaches[i].fill_ready_at_fill = True
                self.l1icaches[i].reopen_at_ready = True
            self.l1icaches[i].tgts_per_mshr = 16
            self.l1icaches[i].is_read_only = True
            self.l1icaches[i].sequential_access = False
            self.l1icaches[i].writeback_clean = False
            if self._icache_policy:
                # Transcribed from cva6_icache.sv, so victims follow its LFSR.
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
            # The victim dies in the core-response cycle, as the HPDcache
            # rewrites its directory then.
            self.l1dcaches[i].fill_at_response = self._fill_at_response
            self.l1dcaches[i].fence_flushes_dcache = self._fence_flush
            self.l1dcaches[i].mshrs = 8
            self.l1dcaches[i].tgts_per_mshr = 16
            self.l1dcaches[i].write_buffers = 8
            self.l1dcaches[i].is_read_only = False
            self.l1dcaches[i].sequential_access = False
            self.l1dcaches[i].writeback_clean = False
            self.l1dcaches[i].prefetcher = NULL

            # Eviction mechanisms, L1D only: the read-only L1I produces no
            # writebacks.
            if self._l1d_plru:
                self.l1dcaches[i].replacement_policy = TreePLRURP()
            elif self._cva6_victim_policy:
                self.l1dcaches[i].replacement_policy = HPDcacheRandomRP()
            else:
                self.l1dcaches[i].replacement_policy = RandomRP()
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
parser.add_argument("--fetch-limit", type=int, default=None,
                    metavar="N",
                    help="Override fetch1FetchLimit. The two configs differ "
                         "here, so a parity run needs them equal")
parser.add_argument("--fetch2-buffer", type=int, default=None, metavar="N",
                    help="Override fetch2InputBufferSize, for the same "
                         "reason as --fetch-limit")
parser.add_argument("--ddr3", action="store_true",
                    help="Use the DDR3-1600 device instead of a flat memory "
                         "at MEM_LATENCY. Matches the Verilator DDR3 model in "
                         "verilator_changes/ddr3_memory.")
parser.add_argument("--no-patch", action="store_true",
                    help="Turn every transcribed mechanism below off at once, "
                         "leaving the stock MinorCPU behaviour the "
                         "calibration started from. With --fetch-limit 2 "
                         "--fetch2-buffer 2 it should reproduce "
                         "gem5_config_CVA6.py on a stock build")
parser.add_argument("--no-port-model", action="store_true",
                    help="Remove the axi2mem single-port model")
parser.add_argument("--no-evict-on-allocate", action="store_true",
                    help="Select victims at fill time instead of at MSHR "
                         "allocation")
parser.add_argument("--no-victim-readout-stall", action="store_true",
                    help="Do not charge the 2-cycle dirty victim readout")
parser.add_argument("--no-cva6-victim-policy", action="store_true",
                    help="Use gem5 RandomRP instead of the transcribed "
                         "HPDcache LFSR. Same policy family as the hardware, "
                         "so this isolates the generator")
parser.add_argument("--l1d-plru", action="store_true",
                    help="L1D uses gem5 TreePLRU. A counterfactual: the "
                         "HPDcache PLRU generate branch is not elaborated "
                         "in cv64a6_imafdc_sv39_hpdcache_wb. The harness "
                         "measures the transcribed HPDcachePLRURP instead")
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
                    help="Use the frozen miss-latency split, L1D response "
                         "latency 4")
parser.add_argument("--no-fence-squash", action="store_true",
                    help="Drop the rule F5 pipeline squash on a committed "
                         "full fence")
parser.add_argument("--no-icache-hold", action="store_true",
                    help="Let Fetch1 send into a busy I-cache and pay the "
                         "refuse-and-retry round trip instead of holding")
parser.add_argument("--no-kill-on-redirect", action="store_true",
                    help="Keep killed lines' fetch slots until their "
                         "responses return")
parser.add_argument("--no-drop-killed-lines", action="store_true",
                    help="Spend a Fetch1 cycle on each killed line, sent or "
                         "returned, instead of dropping it at once, so the "
                         "new stream's first line waits behind it")
parser.add_argument("--no-icache-structure", action="store_true",
                    help="Drop fill readiness at the fill and the reopen "
                         "at readiness on the L1I")
parser.add_argument("--no-window-charge", action="store_true",
                    help="Drop the accept-and-charge window mechanism and "
                         "its class extras, leaving the flat fill split")
parser.add_argument("--no-fill-at-response", action="store_true",
                    help="Fill the L1D response_latency cycles before the "
                         "core sees the data, the stock order, so a victim "
                         "dies before its successor's next loads")
parser.add_argument("--no-c910-divider", action="store_true",
                    help="Charge every FP divide and square root the flat 15 "
                         "and 22 cycles instead of the C910 SRT law on its "
                         "operands")
parser.add_argument("--no-divider-queue", action="store_true",
                    help="Stall issue behind a busy FP divider instead of "
                         "holding the next divide or square root in fpnew's "
                         "input register, and start a divide's extra latency "
                         "at the commit head, not at the unit's end")
parser.add_argument("--no-ras-decay", action="store_true",
                    help="Repair the RAS on squash, the stock gem5 "
                         "behaviour, instead of CVA6's unrecovered "
                         "stack. Independent of "
                         "--no-cva6-direct-targets")
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

# With no refill window set here, the charge has only the readout to act on.
if window_charge and not victim_readout_stall:
    parser.error("--no-victim-readout-stall also requires "
                 "--no-window-charge")

# The readout stall and the readable victim need evict-on-allocate.
if not evict_on_allocate:
    if victim_readout_stall or victim_readable_until_fill:
        parser.error("--no-evict-on-allocate also requires "
                     "--no-victim-readout-stall and "
                     "--no-victim-readable-until-fill")

binary = BinaryResource(args.binary)

ras_no_recovery = not args.no_ras_decay

processor = CVA6Processor(direct_targets=direct_targets,
                          store_forwarding_model=store_forwarding_model,
                          fence_signal=fence_flush,
                          ras_no_recovery=ras_no_recovery,
                          fence_squash=not args.no_fence_squash,
                          icache_hold=not args.no_icache_hold,
                          kill_on_redirect=not args.no_kill_on_redirect,
                          fetch_limit=args.fetch_limit,
                          fetch2_buffer=args.fetch2_buffer,
                          c910_divider=not args.no_c910_divider,
                          divider_queue=not args.no_divider_queue,
                          drop_killed_lines=not args.no_drop_killed_lines)

cache_hierarchy = CVA6CacheHierarchy(
    l1d_size=L1D_SIZE,
    l1i_size=L1I_SIZE,
    evict_on_allocate=evict_on_allocate,
    victim_readout_stall=victim_readout_stall,
    cva6_victim_policy=cva6_victim_policy,
    l1d_plru=args.l1d_plru,
    victim_readable_until_fill=victim_readable_until_fill,
    fill_phase=fill_phase,
    window_charge=window_charge,
    fence_flush=fence_flush,
    icache_policy=icache_policy,
    icache_structure=not args.no_icache_structure,
    fill_at_response=not args.no_fill_at_response,
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
    ("cva6-victim-policy", cva6_victim_policy and not args.l1d_plru),
    ("l1d-plru-counterfactual", args.l1d_plru),
    ("victim-readable-until-fill", victim_readable_until_fill),
    ("fill-phase", fill_phase),
    ("window-charge", window_charge),
    ("fill-at-response", not args.no_fill_at_response),
    ("fence-squash", not args.no_fence_squash),
    ("icache-hold", not args.no_icache_hold),
    ("kill-on-redirect", not args.no_kill_on_redirect),
    ("drop-killed-lines", not args.no_drop_killed_lines),
    ("icache-structure", not args.no_icache_structure),
    ("fence-flush", fence_flush),
    ("cva6-icache-policy", icache_policy),
    ("cva6-direct-targets", direct_targets),
    ("ras-decay", ras_no_recovery),
    ("store-forwarding-model", store_forwarding_model),
    ("c910-divider", not args.no_c910_divider),
    ("divider-queue", not args.no_divider_queue)) if on]
print("Starting CVA6 simulation with: " +
      (", ".join(active) if active else "no transcribed mechanisms"))
simulator.run()

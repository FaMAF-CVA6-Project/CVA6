import argparse

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.processors.base_cpu_core import BaseCPUCore
from gem5.components.processors.base_cpu_processor import BaseCPUProcessor
from gem5.components.memory.simple import SingleChannelSimpleMemory
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import (
    PrivateL1CacheHierarchy,
)
from gem5.isas import ISA
from gem5.simulate.simulator import Simulator
from gem5.resources.resource import BinaryResource

# Importamos objetos m5 nativos
from m5.objects import (
    LocalBP,
    LRURP,
    MinorFUPool,
    MinorDefaultFloatSimdFU,
    MinorDefaultPredFU,
    MinorDefaultMemFU,
    MinorDefaultMiscFU,
    MinorFU,
    MinorFUTiming,
    MinorOpClassSet,
    MinorOpClass,
    ReturnAddrStack,
    RiscvMinorCPU,
    SimpleBTB,
)

# -------------------------------------------------------------------------
# Parsear Argumentos
# -------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Simulación CVA6 en gem5")
parser.add_argument("binary", type=str, help="Ruta al binario compilado (RISC-V ELF)")
args = parser.parse_args()

# -------------------------------------------------------------------------
# Helper para definir clases de operaciones
# -------------------------------------------------------------------------
def minorMakeOpClassSet(op_classes):
    def boxOpClass(op_class):
        return MinorOpClass(opClass=op_class)

    return MinorOpClassSet(opClasses=[boxOpClass(o) for o in op_classes])

# -------------------------------------------------------------------------
# Definicion de las Unidades Funcionales
# -------------------------------------------------------------------------
class CVA6FUPool(MinorFUPool):
    def __init__(self):
        super().__init__()

        # Revisar todos estos valores

        int_alu_ops = ['IntAlu']
        int_alu = MinorFU()
        int_alu.opClasses = minorMakeOpClassSet(int_alu_ops)
        int_alu.opLat = 3
        int_alu.issueLat = 1 

        int_mul_ops = ['IntMult']
        int_mul = MinorFU()
        int_mul.opClasses = minorMakeOpClassSet(int_mul_ops)
        int_mul.opLat = 4
        int_mul.issueLat = 1 

        int_div_ops = ['IntDiv']
        int_div = MinorFU()
        int_div.opClasses = minorMakeOpClassSet(int_div_ops)
        int_div.opLat = 35
        int_div.issueLat = 35 

        fp_fast_ops = ['FloatAdd', 'FloatMult']
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
        
        mem_ops = ['MemRead', 'MemWrite']
        mem_fu = MinorFU()
        mem_fu.opClasses = minorMakeOpClassSet(mem_ops)
        mem_fu.opLat = 3
        mem_fu.issueLat = 1

        float_simd_ops = [
            "FloatMisc",
            "FloatMultAcc",
            "SimdAdd",
            "SimdAddAcc",
            "SimdAlu",
            "SimdCmp",
            "SimdCvt",
            "SimdMisc",
            "SimdMult",
            "SimdMultAcc",
            "SimdMatMultAcc",
            "SimdShift",
            "SimdShiftAcc",
            "SimdDiv",
            "SimdSqrt",
            "SimdFloatAdd",
            "SimdFloatAlu",
            "SimdFloatCmp",
            "SimdFloatCvt",
            "SimdFloatDiv",
            "SimdFloatMisc",
            "SimdFloatMult",
            "SimdFloatMultAcc",
            "SimdFloatMatMultAcc",
            "SimdFloatSqrt",
            "SimdReduceAdd",
            "SimdReduceAlu",
            "SimdReduceCmp",
            "SimdFloatReduceAdd",
            "SimdFloatReduceCmp",
            "SimdAes",
            "SimdAesMix",
            "SimdSha1Hash",
            "SimdSha1Hash2",
            "SimdSha256Hash",
            "SimdSha256Hash2",
            "SimdShaSigma2",
            "SimdShaSigma3",
            "Matrix",
            "MatrixMov",
            "MatrixOP",
            "SimdExt",
            "SimdFloatExt",
            "SimdFloatCvt",
            "SimdConfig"
        ]
        float_simd = MinorDefaultFloatSimdFU()
        float_simd.opClasses = minorMakeOpClassSet(float_simd_ops)
        float_simd.timings = [MinorFUTiming(description="FloatSimd", srcRegsRelativeLats=[2])]
        float_simd.opLat = 6
        float_simd.issueLat = 1

        pred_ops = ["SimdPredAlu"]
        pred = MinorDefaultPredFU()
        pred.opClasses = minorMakeOpClassSet(pred_ops)
        pred.timings = [MinorFUTiming(description="Pred", srcRegsRelativeLats=[2])]
        pred.opLat = 3
        pred.issueLat = 1

        mem_ops = [
            "FloatMemRead",
            "FloatMemWrite",
            "SimdUnitStrideLoad",
            "SimdUnitStrideStore",
            "SimdUnitStrideMaskLoad",
            "SimdUnitStrideMaskStore",
            "SimdStridedLoad",
            "SimdStridedStore",
            "SimdIndexedLoad",
            "SimdIndexedStore",
            "SimdUnitStrideFaultOnlyFirstLoad",
            "SimdWholeRegisterLoad",
            "SimdWholeRegisterStore",
        ]
        mem = MinorFU()
        mem.opClasses = minorMakeOpClassSet(mem_ops)
        mem.timings = [MinorFUTiming(description="Mem", srcRegsRelativeLats=[1], extraAssumedLat=2)] 
        mem.opLat = 1
        mem.issueLat = 1

        misc = MinorDefaultMiscFU()
        misc.opClasses = minorMakeOpClassSet(["InstPrefetch"])
        misc.opLat = 1
        misc.issueLat = 1

        self.funcUnits = [
            int_alu, int_mul, int_div, 
            fp_fast, fp_slow, fp_div, fp_cmp,
            mem_fu, float_simd, pred, mem, misc
        ]
        
        """
        Valores por defectos de MinorCPU

        int_alu_ops = ['IntAlu']
        int_alu = MinorDefaultIntFU()
        int_alu.opClasses = minorMakeOpClassSet(int_alu_ops)
        int_alu.timings = timings = [MinorFUTiming(description="Int", srcRegsRelativeLats=[2])]
        int_alu.opLat = 3
        int_alu.issueLat = 1 

        int_mul_ops = ['IntMult']
        int_mul = MinorDefaultIntMulFU()
        int_mul.opClasses = minorMakeOpClassSet(int_mul_ops)
        int_mul.timings = [MinorFUTiming(description="Mul", srcRegsRelativeLats=[0])]
        int_mul.opLat = 3
        int_mul.issueLat = 1 

        int_div_ops = ['IntDiv']
        int_div = MinorDefaultIntDivFU()
        int_div.opClasses = minorMakeOpClassSet(int_div_ops)
        int_div.opLat = 9
        int_div.issueLat = 9

        float_simd_ops = [
            "FloatAdd",
            "FloatCmp",
            "FloatCvt",
            "FloatMisc",
            "FloatMult",
            "FloatMultAcc",
            "FloatDiv",
            "FloatSqrt",
            "SimdAdd",
            "SimdAddAcc",
            "SimdAlu",
            "SimdCmp",
            "SimdCvt",
            "SimdMisc",
            "SimdMult",
            "SimdMultAcc",
            "SimdMatMultAcc",
            "SimdShift",
            "SimdShiftAcc",
            "SimdDiv",
            "SimdSqrt",
            "SimdFloatAdd",
            "SimdFloatAlu",
            "SimdFloatCmp",
            "SimdFloatCvt",
            "SimdFloatDiv",
            "SimdFloatMisc",
            "SimdFloatMult",
            "SimdFloatMultAcc",
            "SimdFloatMatMultAcc",
            "SimdFloatSqrt",
            "SimdReduceAdd",
            "SimdReduceAlu",
            "SimdReduceCmp",
            "SimdFloatReduceAdd",
            "SimdFloatReduceCmp",
            "SimdAes",
            "SimdAesMix",
            "SimdSha1Hash",
            "SimdSha1Hash2",
            "SimdSha256Hash",
            "SimdSha256Hash2",
            "SimdShaSigma2",
            "SimdShaSigma3",
            "Matrix",
            "MatrixMov",
            "MatrixOP",
            "SimdExt",
            "SimdFloatExt",
            "SimdFloatCvt",
            "SimdConfig"
        ]
        float_simd = MinorDefaultFloatSimdFU()
        float_simd.opClasses = minorMakeOpClassSet(float_simd_ops)
        float_simd.timings = [MinorFUTiming(description="FloatSimd", srcRegsRelativeLats=[2])]
        float_simd.opLat = 6
        float_simd.issueLat = 1

        pred_ops = ["SimdPredAlu"]
        pred = MinorDefaultPredFU()
        pred.opClasses = minorMakeOpClassSet(pred_ops)
        pred.timings = [MinorFUTiming(description="Pred", srcRegsRelativeLats=[2])]
        pred.opLat = 3
        pred.issueLat = 1

        mem_ops = [
            "MemRead",
            "MemWrite",
            "FloatMemRead",
            "FloatMemWrite",
            "SimdUnitStrideLoad",
            "SimdUnitStrideStore",
            "SimdUnitStrideMaskLoad",
            "SimdUnitStrideMaskStore",
            "SimdStridedLoad",
            "SimdStridedStore",
            "SimdIndexedLoad",
            "SimdIndexedStore",
            "SimdUnitStrideFaultOnlyFirstLoad",
            "SimdWholeRegisterLoad",
            "SimdWholeRegisterStore",
        ]
        mem = MinorDefaultMemFU()
        mem.opClasses = minorMakeOpClassSet(mem_ops)
        mem.timings = [MinorFUTiming(description="Mem", srcRegsRelativeLats=[1], extraAssumedLat=2)] 
        mem.opLat = 1
        mem.issueLat = 1

        misc = MinorDefaultMiscFU()
        misc.opClasses = minorMakeOpClassSet(["InstPrefetch"])
        misc.opLat = 1
        misc.issueLat = 1

        self.funcUnits = [
            int_alu, int_mul, int_div, 
            float_simd, pred, mem, misc
        ]
        """

# -------------------------------------------------------------------------
# Definicion del CPU CVA6
# -------------------------------------------------------------------------
class CVA6CPU(RiscvMinorCPU):
    def __init__(self):
        super().__init__()

        # Unidades Funcionales Personalizadas
        self.executeFuncUnits = CVA6FUPool()

        # Configuración del Pipeline
        self.fetch1FetchLimit = 1
        self.fetch1LineSnapWidth = 4
        self.fetch1LineWidth = 4
        self.fetch1ToFetch2ForwardDelay = 1 
        self.fetch1ToFetch2BackwardDelay = 1 
        self.fetch2InputBufferSize = 1
        self.fetch2ToDecodeForwardDelay = 1 
        self.fetch2CycleInput = False 
        self.decodeInputBufferSize = 4
        self.decodeToExecuteForwardDelay = 1
        self.decodeInputWidth = 1 # Revisar. Hacer pruebas con instrucciones comprimidadas. Dejar para mas adelante
        self.decodeCycleInput = False # Revisar. Hacer pruebas con instrucciones comprimidadas. Dejar para mas adelante
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
        self.enableIdling = False

        self.branchPred = LocalBP(
            localPredictorSize = 1024, # Revisar
            localCtrBits = 2, # Revisar
            instShiftAmt = 2  # Revisar
        )

        self.branchPred.btb = SimpleBTB(
            numEntries = 64,          # Revisar
            tagBits = 20,             # Revisar
            associativity = 16,       # Revisar
            instShiftAmt = 2,         # Revisar
            btbReplPolicy = LRURP()   # Revisar
        )

        self.branchPred.ras = ReturnAddrStack(
            numEntries = 2 # Revisar
        )

# Wrapper para usarlo con la Standard Library de gem5
class CVA6Processor(BaseCPUProcessor):
    def __init__(self):
        core = BaseCPUCore(core=CVA6CPU(), isa=ISA.RISCV)
        super().__init__(cores=[core])

# -------------------------------------------------------------------------
# Configuracion de Caches
# -------------------------------------------------------------------------
class CVA6CacheHierarchy(PrivateL1CacheHierarchy):
    def __init__(self, l1d_size, l1i_size):
        super().__init__(l1d_size=l1d_size, l1i_size=l1i_size)

    def incorporate_cache(self, board):
        super().incorporate_cache(board)

        for i, core in enumerate(board.get_processor().get_cores()):
            self.l1icaches[i].assoc = 4
            self.l1icaches[i].tag_latency = 1
            self.l1icaches[i].data_latency = 1
            self.l1icaches[i].response_latency = 2 # Revisar
            self.l1icaches[i].mshrs = 4 # Revisar
            self.l1icaches[i].tgts_per_mshr = 1 # Revisar
            self.l1icaches[i].write_buffers = 8 # Revisar
            self.l1icaches[i].is_read_only = True
            self.l1icaches[i].sequential_access = False
            self.l1icaches[i].writeback_clean = True

            self.l1dcaches[i].assoc = 8
            self.l1dcaches[i].tag_latency = 1 # Revisar
            self.l1dcaches[i].data_latency = 2 # Revisar
            self.l1dcaches[i].response_latency = 2 # Revisar
            self.l1dcaches[i].mshrs = 2 # Revisar. Buscar definitivamente
            self.l1dcaches[i].tgts_per_mshr = 1 # Revisar. Buscar definitivamente
            self.l1dcaches[i].write_buffers = 8 # Revisar
            self.l1dcaches[i].is_read_only = False
            self.l1dcaches[i].sequential_access = False # Revisar
            self.l1dcaches[i].writeback_clean = True

# -------------------------------------------------------------------------
# Script Principal
# -------------------------------------------------------------------------
binary = BinaryResource(args.binary)

processor = CVA6Processor()

cache_hierarchy = CVA6CacheHierarchy(
    l1d_size="32KiB",
    l1i_size="16KiB"
)

memory = SingleChannelSimpleMemory(
    latency="20ns",
    latency_var="0ns",
    bandwidth= "0.375GiB/s",
    size="1GiB"
)

board = SimpleBoard(
    clk_freq="50MHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy
)

board.cache_line_size = 16  # 128 bits    
board.set_se_binary_workload(binary)

simulator = Simulator(board=board)
print("Iniciando simulacion del CVA6")
simulator.run()
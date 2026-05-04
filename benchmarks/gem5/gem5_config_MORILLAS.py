import argparse

from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.processors.base_cpu_core import BaseCPUCore
from gem5.components.processors.base_cpu_processor import BaseCPUProcessor
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import (
    PrivateL1CacheHierarchy,
)
from gem5.isas import ISA
from gem5.simulate.simulator import Simulator
from gem5.resources.resource import BinaryResource

# Importamos objetos m5 nativos
from m5.objects import (
    LocalBP,
    SimpleBTB,
    LRURP,
    ReturnAddrStack,
    RiscvMinorCPU,
    MinorFUPool,
    MinorDefaultIntFU,
    MinorDefaultIntMulFU,
    MinorDefaultIntDivFU,
    MinorDefaultMemFU,
    MinorDefaultMiscFU,
    MinorFU,
    MinorOpClassSet,
    MinorOpClass
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
def make_op_class_set(op_classes_list):
    return MinorOpClassSet(
        opClasses=[MinorOpClass(opClass=name) for name in op_classes_list]
    )

# -------------------------------------------------------------------------
# Definicion de las Unidades Funcionales
# -------------------------------------------------------------------------
class CVA6FUPool(MinorFUPool):
    def __init__(self):
        super().__init__()

        # ALU Entera Simple
        int_alu_ops = ['IntAlu']
        int_alu = MinorDefaultIntFU()
        int_alu.opClasses = make_op_class_set(int_alu_ops)
        int_alu.opLat = 3
        int_alu.issueLat = 1 

        # Multiplicación Entera
        int_mul_ops = ['IntMult']
        int_mul = MinorDefaultIntMulFU()
        int_mul.opClasses = make_op_class_set(int_mul_ops)
        int_mul.opLat = 4
        int_mul.issueLat = 1 

        # Division Entera
        int_div_ops = ['IntDiv']
        int_div = MinorDefaultIntDivFU()
        int_div.opClasses = make_op_class_set(int_div_ops)
        int_div.opLat = 35
        int_div.issueLat = 35 

        # Floating Point
        fp_fast_ops = ['FloatAdd', 'FloatMult', 'FloatMultAcc', 'FloatMisc']
        fp_fast = MinorFU(
            opClasses=make_op_class_set(fp_fast_ops),
            opLat=3, issueLat=1
        )

        fp_slow_ops = ['FloatCvt', 'FloatSqrt']
        fp_slow = MinorFU(
            opClasses=make_op_class_set(fp_slow_ops),
            opLat=4, issueLat=1 
        )
        
        fp_div_ops = ['FloatDiv']
        fp_div = MinorFU(
            opClasses=make_op_class_set(fp_div_ops),
            opLat=4, issueLat=4 
        )

        fp_cmp_ops = ['FloatCmp']
        fp_cmp = MinorFU(
            opClasses=make_op_class_set(fp_cmp_ops),
            opLat=5, issueLat=1
        )
        
        # Memoria
        mem_ops = ['MemRead', 'MemWrite', 'FloatMemRead', 'FloatMemWrite']
        mem_fu = MinorDefaultMemFU()
        mem_fu.opClasses = make_op_class_set(mem_ops)
        mem_fu.opLat = 3
        mem_fu.issueLat = 1

        # Resto de Unidades
        # Juntamos todas las que ya definimos
        defined_ops = set(int_alu_ops + int_mul_ops + int_div_ops + fp_fast_ops
                        + fp_slow_ops + fp_div_ops + fp_cmp_ops + mem_ops)
        
        misc_ops_list = ['IprAccess'] 
        
        # Buscamos TODAS las clases que existen en Gem5 y restamos las nuestras
        all_ops = [op.opClass for op in MinorOpClassSet().opClasses]
        undefined_ops = [op for op in all_ops if op not in defined_ops and op not in misc_ops_list]

        # Unidad Misc Real (Saltos)
        misc_fu = MinorDefaultMiscFU()
        misc_fu.opClasses = make_op_class_set(misc_ops_list)
        
        # Unidad para Vectores y cosas que no usaremos
        catch_all_fu = MinorFU(
            opClasses=make_op_class_set(undefined_ops),
            opLat=6, issueLat=1
        )

        self.funcUnits = [
            int_alu, int_mul, int_div, 
            fp_fast, fp_slow, fp_div, fp_cmp,
            mem_fu, misc_fu, catch_all_fu
        ]

# -------------------------------------------------------------------------
# Definicion del CPU CVA6
# -------------------------------------------------------------------------
class CVA6CPU(RiscvMinorCPU):
    def __init__(self):
        super().__init__()

        # Unidades Funcionales Personalizadas
        self.executeFuncUnits = CVA6FUPool()

        # Configuración del Pipeline
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
            localPredictorSize = 1024,
            localCtrBits = 2, # BHT localCtrBits ?
            instShiftAmt = 2  # BHT Instruction Shift Amount ?
        )

        self.branchPred.btb = SimpleBTB(
            numEntries = 64,
            tagBits = 20,
            associativity = 16,
            instShiftAmt = 2,         # BTB Instruction Shift Amount
            btbReplPolicy = LRURP()   # LRU Replacement Policy
        )

        self.branchPred.ras = ReturnAddrStack(
            numEntries = 2
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


# -------------------------------------------------------------------------
# Script Principal
# -------------------------------------------------------------------------
binary = BinaryResource(args.binary)

processor = CVA6Processor()

cache_hierarchy = CVA6CacheHierarchy(
    l1d_size="32KiB",
    l1i_size="16KiB"
)

memory = SingleChannelDDR3_1600(size="1GiB")

board = SimpleBoard(
    clk_freq="50MHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy
)

board.set_se_binary_workload(binary)

simulator = Simulator(board=board)
print("Iniciando simulacion del CVA6")
simulator.run()
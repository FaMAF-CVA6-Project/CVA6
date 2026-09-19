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
    Axi2MemPort,
    HPDcachePLRURP,
    HPDcacheRandomRP,
    CVA6IcacheRandomRP,
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
    TimingExprLet,
    TimingExprRef,
)

# Calibration harness for the CVA6 gem5 MinorCPU configuration.
#
# TEST 1 is the stock gem5_config_CVA6.py and TEST 40 full production, the
# gem5_config_CVA6_patch.py. Every other TEST is a perturbation of the
# campaign, most single-knob, and a row marked duplicate reduces to another.
#
# TESTS 1 to 39 are gem5_config_CVA6_testing.py's on the same stock baseline,
# setting no patch parameter. From TEST 40 on, every entry is laid over
# PATCH_BASE, the patch parameters the campaign adopted first.
#
# TEST table fields:
#   (name, cpu_overrides, l1i_size, l1d_size, dcache_overrides,
#    icache_overrides, clk_freq, mem_latency, bp_overrides)
#
# Special keys:
#   cpu_overrides["branchPred"]      LocalBP or TournamentBP
#   bp_overrides["fuVariant"]        selects a CVA6FUPool variant (below)
#   bp_overrides["directTargetsFromDecode"], ["indirectBranchPred"],
#   ["btbTagBits"] and ["rasNoRecovery"] set the built predictor
#   dcache_overrides["_membus_width"]   crossbar payload width in bytes
#   dcache_overrides["_mem_bandwidth"]  SimpleMemory bandwidth string
#   dcache_overrides["_port_model"]     splice the axi2mem single-port model
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
#   === from here on, every entry is laid over PATCH_BASE ===
#   --- full production ---
#  40   full production                           workload: all
#   --- store-to-load forwarding ---
#  41   store forwarding re-enabled               workload: store_fwd
#  42   replay delay 2 -> 0                       workload: store_fwd
#   --- data-cache stack ---
#  43   port model alone                          workload: daxpy
#  44   + evict-on-allocate                       workload: daxpy
#  45   + victim readout stall                    workload: daxpy
#  46   + HPDcache bit-PLRU                       workload: daxpy
#  47   + HPDcache random, on 45 not 46           workload: daxpy
#  48   + victim readable until fill              workload: daxpy
#  49   + fill phase, the production stack        workload: daxpy
#   --- production stack, ablations and geometry ---
#  50   production stack, L1D 16 KiB              workload: daxpy
#  51   production stack, L1D 64 KiB              workload: daxpy
#  52   production minus the port model           workload: daxpy
#  53   production minus the readout stall        workload: daxpy
#  54   production with bit-PLRU instead          workload: daxpy
#  55   duplicate of 48, minus the fill phase     workload: daxpy
#  56   fill delay, gem5 RandomRP policy          workload: daxpy
#   --- fence and instruction-cache policy ---
#  57   + fence flushes the L1D                   workload: atomic_fence
#  58   + transcribed L1I policy                  workload: all
#   --- front end, direct targets and the BTB ---
#  59   duplicate of 58, the delay is baseline    workload: btb_pressure
#  60   59 + decode direct targets                workload: all
#  61   BTB as the JALR store, redirect delay 1   workload: all
#  62   tagless BTB                               workload: all
#   --- fill timing ---
#  63   dirty-only fill delay                     workload: all
#   --- refill window ---
#  64   refill window + clean fill                workload: all
#  65   refill window alone, isolation            workload: all
#  66   duplicate of 62, F5 squash is baseline    workload: all
#  67   RAS no-recovery                           workload: all
#  68   store-class readout extra, isolation      workload: all
#  69   clean fill + class z                      workload: all
#  70   all candidates together                   workload: all
#  71   pair + class x and z                      workload: all
#   --- accept-and-charge ---
#  72   accept-and-charge, dirty-only fill        workload: all
#  73   accept-and-charge with the class law      workload: all
#  74   accept-and-charge, the full pair          workload: all
#  75   accept-and-charge refill window           workload: all
#   --- the fetch supply beat, basic_test's owner ---
#  76   fetch1FetchLimit 2 -> 4                   workload: all
#  77   fetch1FetchLimit 4, fetch2 buffer 2 -> 1  workload: all
#  78   fetch limit 4, fetch2 buffer 2 -> 4       workload: all
#   --- the per-line cadence, already the baseline ---
#  79   duplicate of 78, cycle input is baseline  workload: all
#  80   duplicate of 67, cycle input is baseline  workload: all
#   --- the class law without the fill-0 phase artefact ---
#  81   flat fill, accept-and-charge              workload: all
#  82   duplicate of 73, 80 front end is baseline workload: all
#  83   duplicate of 73, turnaround is baseline   workload: all
#  84   adopted stack + C910 divider law          workload: all
#  85   duplicate of 73, fence squash is baseline workload: all
#   --- the final-check probes, on the adopted stack ---
#  86   L1I mshrs 2 -> 1, the I-side retry tax    workload: all
#  87   fetch limit 3, fetch2 buffer 3            workload: all
#  88   fetch limit 4, fetch2 buffer 3            workload: all
#  89   L1I reopen at ready                       workload: all
#   --- the structural I-side ---
#  90   mshrs 1, reopen at ready, fetch1 holds    workload: all
#  91   ablation of 90 without reopen at ready    workload: all
#  92   the 90 with fetch limit 3 and buffer 3    workload: all
#  93   the 91 with fetch limit 3 and buffer 3    workload: all
#  94   the 93 with the fill readable at the fill workload: all
#  95   the 94 with kill on redirect              workload: all
#  96   previous full production                  workload: all
#   --- final adoptions, each taken back out ---
#  97   production minus fill at the response     workload: all
#  98   production minus the C910 divider law     workload: all
#  99   production minus the divider queue        workload: all
#   --- direct targets against the stack ---
# 100   production minus direct targets           workload: all
#   --- the killed-line drop against the stack ---
# 101   production minus the killed-line drop     workload: all
#
#   --- cache geometry ---
# CACHE_TESTS is a table of its own: nothing in it touches the CPU, only L1I
# and L1D size and associativity. Each entry runs the workloads its cut moves
# on CACHE_BASE_TEST, this file's TEST 40, the full production configuration,
# so a cut differs from what ships by the cut alone.
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

# From PATCH_TIER_START on, every entry is laid over PATCH_BASE, the patch
# parameters the campaign adopted before it varied anything else. The entry's
# own overrides win, so an ablation sets the value it takes away.
PATCH_TIER_START = 40
PATCH_BASE = {
    "cpu": {"executeLSQNoStoreForwarding": True,
            "executeLSQStoreCollisionReplayDelay": 2,
            "executeLSQFenceSignalsDcache": True,
            "executeFenceSquashesPipeline": True},
    "icache": {"mshrs": 2},
}


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
    # === from here on, every entry is laid over PATCH_BASE ===
    # --- full production ---
    40: ("full production",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True, "fetch1KillsOnRedirect": True,
          "fetch1DropsKilledLines": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0, "fill_at_response": True,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
          "fill_ready_at_fill": True, "reopen_at_ready": True},
         "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True,
          "fuVariant": "divsqrt_c910_queue"}),
    # --- store-to-load forwarding ---
    41: ("store forwarding on",          {"executeLSQNoStoreForwarding": False,
                                          "executeLSQStoreCollisionReplayDelay": 0}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    42: ("replay delay 2->0",            {"executeLSQStoreCollisionReplayDelay": 0}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    # --- data-cache stack ---
    43: ("port model alone",              {}, "16KiB", "32KiB",
         {"_port_model": True}, {}, "50MHz", "0ns", {}),
    44: ("port + evict-on-allocate",      {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True}, {}, "50MHz", "0ns", {}),
    45: ("+ victim readout stall",        {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True}, {}, "50MHz", "0ns", {}),
    46: ("+ bit-PLRU counterfactual",     {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcachePLRURP()}, {}, "50MHz", "0ns", {}),
    47: ("+ random, configured branch",   {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP()}, {}, "50MHz", "0ns", {}),
    48: ("+ victim readable until fill",  {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True}, {}, "50MHz", "0ns", {}),
    49: ("production stack",              {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    # --- production stack, ablations and geometry ---
    50: ("production stack, L1D 16KiB",   {}, "16KiB", "16KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    51: ("production stack, L1D 64KiB",   {}, "16KiB", "64KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    52: ("production minus port model",   {}, "16KiB", "32KiB",
         {"evict_on_allocate": True, "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    53: ("production minus readout stall", {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    54: ("production with bit-PLRU",      {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcachePLRURP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    55: ("duplicate of 48, minus fill phase", {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True}, {}, "50MHz", "0ns", {}),
    56: ("fill delay, gem5 RandomRP policy", {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    # --- fence and instruction-cache policy ---
    57: ("+ fence flushes the L1D",       {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True}, {}, "50MHz", "0ns", {}),
    58: ("+ transcribed L1I policy",      {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns", {}),
    # --- front end, direct targets and the BTB ---
    59: ("duplicate of 58, the backward delay is baseline",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns", {}),
    60: ("59 with decode direct targets", {},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True}),
    61: ("BTB as the JALR store, redirect delay 1", {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL}),
    62: ("tagless BTB",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0}),
    # --- fill timing ---
    63: ("dirty-only fill delay",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0}),
    # --- refill window ---
    64: ("refill window + clean fill (the pair)",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "refill_window_blocks": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0}),
    65: ("refill window alone, isolation",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "refill_window_blocks": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0}),
    66: ("duplicate of 62, F5 squash is baseline",
         {"executeFenceSquashesPipeline": True}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0}),
    67: ("RAS no-recovery",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0,
          "rasNoRecovery": True}),
    68: ("store-class readout extra, isolation",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "victim_readout_store_extra": 4,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0}),
    69: ("clean fill with class z",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0}),
    70: ("all candidates together",
         {"executeFenceSquashesPipeline": True}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0,
          "rasNoRecovery": True}),
    71: ("pair with class x and z",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0}),
    # --- accept-and-charge ---
    72: ("accept-and-charge, dirty-only fill",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    73: ("accept-and-charge with the class law",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    74: ("accept-and-charge, the full pair",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "refill_window_blocks": True,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    75: ("accept-and-charge refill window, flat fill",
         {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": False,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "refill_window_blocks": True,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    # --- the fetch supply beat, basic_test's owner ---
    76: ("fetch1FetchLimit 2->4, the supply beat",
         {"fetch1FetchLimit": 4},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    77: ("fetch limit 4, fetch2 buffer 1",
         {"fetch1FetchLimit": 4,
          "fetch2InputBufferSize": 1},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    78: ("fetch limit 4, fetch2 buffer 4",
         {"fetch1FetchLimit": 4,
          "fetch2InputBufferSize": 4},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    # --- the per-line cadence, already the baseline ---
    79: ("duplicate of 78, fetch2CycleInput is baseline",
         {"fetch1FetchLimit": 4,
          "fetch2InputBufferSize": 4, "fetch2CycleInput": True},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    80: ("duplicate of 67, fetch2CycleInput is baseline",
         {"fetch2CycleInput": True},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    # --- the class law without the fill-0 phase artefact ---
    81: ("flat fill, class extras accept-and-charge",
         {"fetch2CycleInput": True},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    82: ("duplicate of 73, the 80 front end is baseline",
         {"fetch2CycleInput": True},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    83: ("duplicate of 73, serdiv_turnaround is no variant",
         {"fetch2CycleInput": True},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True,
          "fuVariant": "serdiv_turnaround"}),
    84: ("adopted stack + C910 divider law",
         {"fetch2CycleInput": True},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True,
          "fuVariant": "divsqrt_c910_law"}),
    85: ("duplicate of 73, fence squash is baseline",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    # --- the final-check probes, on the adopted stack ---
    86: ("adopted stack, L1I mshrs 1, the retry tax",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    87: ("adopted stack, fetch limit 3, buffer 3",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    88: ("adopted stack, fetch limit 4, buffer 3",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1FetchLimit": 4, "fetch2InputBufferSize": 3}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    89: ("adopted stack, L1I reopen at ready",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 2,
          "reopen_at_ready": True}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    # --- the structural I-side ---
    90: ("structural I-side: mshrs 1, reopen at ready, fetch1 holds",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
          "reopen_at_ready": True}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    91: ("ablation: mshrs 1, fetch1 holds, no reopen at ready",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    92: ("structural I-side with fetch limit 3 and buffer 3",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
          "reopen_at_ready": True}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    93: ("ablation 91 with fetch limit 3 and buffer 3",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    94: ("the 93 stack with the fill readable at the fill",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
          "fill_ready_at_fill": True}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    95: ("the 94 stack with kill on redirect",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3,
          "fetch1KillsOnRedirect": True}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
          "fill_ready_at_fill": True}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    96: ("previous full production, the 95 stack with reopen at ready",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3,
          "fetch1KillsOnRedirect": True}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
          "fill_ready_at_fill": True, "reopen_at_ready": True}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    # --- the final adoptions, each taken back out ---
    97: ("production minus the fill at the core response",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True, "fetch1KillsOnRedirect": True,
          "fetch1DropsKilledLines": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
          "fill_ready_at_fill": True, "reopen_at_ready": True},
         "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True,
          "fuVariant": "divsqrt_c910_queue"}),
    98: ("production minus the C910 divider law",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True, "fetch1KillsOnRedirect": True,
          "fetch1DropsKilledLines": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0, "fill_at_response": True,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
          "fill_ready_at_fill": True, "reopen_at_ready": True},
         "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True,
          "fuVariant": "divsqrt_flat_queue"}),
    99: ("production minus the divider queue",
         {"fetch2CycleInput": True,
          "executeFenceSquashesPipeline": True,
          "fetch1WaitsForIcache": True, "fetch1KillsOnRedirect": True,
          "fetch1DropsKilledLines": True,
          "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 0, "fill_at_response": True,
          "victim_readout_store_extra": 4,
          "victim_readout_first_load_extra": 1,
          "window_accept_and_charge": True,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
          "fill_ready_at_fill": True, "reopen_at_ready": True},
         "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True,
          "fuVariant": "divsqrt_c910_law"}),
    # --- direct targets against the stack ---
    100: ("production minus direct targets",
          {"fetch2CycleInput": True,
           "executeFenceSquashesPipeline": True,
           "fetch1WaitsForIcache": True, "fetch1KillsOnRedirect": True,
           "fetch1DropsKilledLines": True,
           "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3},
          "16KiB", "32KiB",
          {"_port_model": True, "evict_on_allocate": True,
           "victim_readout_stall": True,
           "replacement_policy": HPDcacheRandomRP(),
           "victim_readable_until_fill": True,
           "response_latency": 2, "fill_delay": 0, "fill_at_response": True,
           "victim_readout_store_extra": 4,
           "victim_readout_first_load_extra": 1,
           "window_accept_and_charge": True,
           "fence_flushes_dcache": True},
          {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
           "fill_ready_at_fill": True, "reopen_at_ready": True},
          "50MHz", "0ns",
          {"rasNoRecovery": True, "fuVariant": "divsqrt_c910_queue"}),
    # --- the killed-line drop against the stack ---
    101: ("production minus the killed-line drop",
          {"fetch2CycleInput": True,
           "executeFenceSquashesPipeline": True,
           "fetch1WaitsForIcache": True, "fetch1KillsOnRedirect": True,
           "fetch1FetchLimit": 3, "fetch2InputBufferSize": 3},
          "16KiB", "32KiB",
          {"_port_model": True, "evict_on_allocate": True,
           "victim_readout_stall": True,
           "replacement_policy": HPDcacheRandomRP(),
           "victim_readable_until_fill": True,
           "response_latency": 2, "fill_delay": 0, "fill_at_response": True,
           "victim_readout_store_extra": 4,
           "victim_readout_first_load_extra": 1,
           "window_accept_and_charge": True,
           "fence_flushes_dcache": True},
          {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 1,
           "fill_ready_at_fill": True, "reopen_at_ready": True},
          "50MHz", "0ns",
          {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
           "btbTagBits": 0, "rasNoRecovery": True,
           "fuVariant": "divsqrt_c910_queue"}),
}

# The entry every cache geometry is laid over: TEST 40, the full production
# configuration, which is gem5_config_CVA6_patch.py. Each cut is merged into
# it when the harness runs, so the list follows production when 40 changes.
CACHE_BASE_TEST = 40

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
    """The TEST entry with the bases it sits on merged in: a cache entry over
    CACHE_BASE_TEST, and the grid from PATCH_TIER_START on over PATCH_BASE."""
    entry = ALL_TESTS[test]
    if test in CACHE_TESTS:
        return laid_over(as_base(resolve(CACHE_BASE_TEST)), entry)
    if test >= PATCH_TIER_START:
        return laid_over(PATCH_BASE, entry)
    return entry


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
    """Data-dependent latency of the CVA6 integer divider."""
    bits_a = _un('timingExprSizeInBits', _src(0))
    bits_b = _un('timingExprSizeInBits', _src(1))
    diff = _bin('timingExprSub', bits_a, bits_b)
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
    significand of source `index`."""
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

    # srt_ctrl_skip_srt, ct_vfdsu_srt.v 295-300, 391-417
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
    # (ex1_sqrt_expnt_odd, ct_vfdsu_prepare.v 462 and 625-627)
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
# expression adds m to that.
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
        int_div.issueLat = 2 if variant == "serdiv_no_turnaround" else 3
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
        # fpnew's input register, and a divider that writes back out of order.
        # The overlap moves out of opLat into the extra latency, where a held
        # operation skips it.
        overlap = 0
        if variant == "divsqrt_c910_queue" or variant == "divsqrt_flat_queue":
            overlap = FP_DIVSQRT_QUEUE_OVERLAP
            fp_divsqrt.holdWhileBusy = True
            fp_divsqrt.heldLatencyOverlap = overlap
            fp_divsqrt.extraCommitLatFromFUEnd = True
        if variant == "divsqrt_legacy":
            fp_divsqrt.opLat = 2
            fp_divsqrt.issueLat = 2
            fp_divsqrt.timings = [MinorFUTiming(
                description='FpDivSqrtLegacy',
                srcRegsRelativeLats=[0],
                extraCommitLat=2)]
        elif variant == "divsqrt_c910_law" or variant == "divsqrt_c910_queue":
            fp_divsqrt.opLat = FP_DIVSQRT_BASE_LAT - overlap
            fp_divsqrt.issueLat = FP_DIVSQRT_BASE_LAT - overlap
            fp_divsqrt.timings = fpDivSqrtTimings(overlap)
        else:
            fp_divsqrt.opLat = 15 - overlap
            fp_divsqrt.issueLat = 15 - overlap
            fp_divsqrt.timings = flatDivSqrtTimings(overlap)

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

        # The stock baseline, identical to gem5_config_CVA6.py. PATCH_BASE
        # adds the patch parameters from PATCH_TIER_START on.
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
        if bp.get("directTargetsFromDecode", False):
            self.branchPred.directTargetsFromDecode = True
        if "indirectBranchPred" in bp:
            self.branchPred.indirectBranchPred = bp["indirectBranchPred"]
        if "btbTagBits" in bp:
            self.branchPred.btb.tagBits = bp["btbTagBits"]
        if "rasNoRecovery" in bp:
            self.branchPred.rasNoRecovery = bp["rasNoRecovery"]


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
        self._dcache_overrides.pop("_port_model", None)
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


parser = argparse.ArgumentParser(
    description="CVA6 replication on gem5 (calibration harness)")
parser.add_argument("binary", type=str,
                    help="Path to the compiled RISC-V ELF binary")
args = parser.parse_args()

use_port_model = False

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
use_port_model = bool(dict(dcache_overrides).get("_port_model", False))

print("=" * 70)
if USE_MORILLAS:
    print("   MORILLAS 2025 FULL CONFIGURATION")
else:
    print(f"   CVA6 HARNESS  -  TEST {TEST}: {test_name}")
    if TEST in CACHE_TESTS:
        print(f"   Laid over     : TEST {CACHE_BASE_TEST}, "
              f"{TESTS[CACHE_BASE_TEST][0]}")
    elif TEST >= PATCH_TIER_START:
        print(f"   Laid over     : PATCH_BASE {PATCH_BASE}")
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
    mem_class = (Axi2MemPortedMemory if use_port_model
                 else SingleChannelSimpleMemory)
    memory = mem_class(
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

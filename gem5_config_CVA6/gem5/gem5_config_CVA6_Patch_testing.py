import argparse
import os

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
    Axi2MemPort,
    HPDcachePLRURP,
    HPDcacheRandomRP,
    CVA6IcacheRandomRP,
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
    TimingExprLiteral,
    TimingExprSrcReg,
    TimingExprUn,
    TimingExprBin,
    TimingExprIf,
)

# Calibration harness for the CVA6 gem5 MinorCPU configuration.
#
# TEST 1 is the frozen CPU-side baseline, TEST 99 the full production
# configuration. Every other TEST is a single-knob perturbation of the
# calibration campaign, with its observation in the entry's own comment.
#
# The table is ordered by what a TEST needs to run. TESTS 1 to 39 use nothing
# the patch adds, and are the same entries, under the same numbers, as in
# gem5_config_CVA6_testing.py. TESTS 40 to 70 and TEST 99 need
# MinorCPU_CVA6.patch.
#
# TEST table fields (unchanged shape):
#   (name, cpu_overrides, l1i_size, l1d_size, dcache_overrides,
#    icache_overrides, clk_freq, mem_latency, bp_overrides)
#
# Special keys:
#   bp_overrides["fuVariant"]        selects a CVA6FUPool variant (below)
#   dcache_overrides["_membus_width"]   crossbar payload width in bytes
#   dcache_overrides["_mem_bandwidth"]  SimpleMemory bandwidth string
#   dcache_overrides["_port_model"]     splice the axi2mem single-port model
#
#   1   adopted baseline                          workload: all
#   --- fetch geometry ---
#   2   fetch1FetchLimit 2 -> 1                   workload: matmul_small
#   3   fetch1FetchLimit 2 -> 3                   workload: matmul_small
#   4   fetch 8B/8B, fetch2 buffer 8              workload: all
#   5   fetch2InputBufferSize 2 -> 4              workload: fetch2_probe
#   --- instruction cache ---
#   6   L1I random -> LRU                         workload: full_test
#   7   L1I response_latency 0 -> 1               workload: daxpy
#   8   L1I response_latency 0 -> 2               workload: daxpy
#   9   L1I 4KiB                                  workload: daxpy
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
#  24   atomic occupancy entries removed          workload: atomic_fence
#   --- data cache ---
#  25   L1D PLRU -> true LRU                      workload: full_test
#  26   response_latency 4 -> 5                   workload: daxpy
#  27   response_latency 4 -> 6                   workload: daxpy
#  28   response_latency 4 -> 3                   workload: daxpy
#  29   L1D 16KiB                                 workload: daxpy
#  30   L1D 64KiB                                 workload: daxpy
#  31   L1D assoc 8 -> 2                          workload: daxpy
#  32   L1D mshrs 8 -> 1                          workload: daxpy
#  33   L1D write_buffers 8 -> 2                  workload: daxpy
#  34   L1D hit lat +1                            workload: daxpy
#   --- memory system ---
#  35   membus width 8 -> 16                      workload: daxpy
#  36   membus width 8 -> 4                       workload: daxpy
#  37   memory bandwidth 12.8GiB/s -> 0.4GiB/s    workload: daxpy
#  38   mem latency 0 -> 60ns                     workload: daxpy
#   --- core-wide ---
#  39   threadPolicy -> RoundRobin                workload: daxpy
#   === every TEST below needs MinorCPU_CVA6.patch ===
#   --- store-to-load forwarding ---
#  40   store forwarding re-enabled               workload: store_fwd
#  41   replay delay 2 -> 0                       workload: store_fwd
#   --- data-cache stack ---
#  42   port model alone                          workload: daxpy
#  43   + evict-on-allocate                       workload: daxpy
#  44   + victim readout stall                    workload: daxpy
#  45   + HPDcache bit-PLRU                       workload: daxpy
#  46   + HPDcache random                         workload: daxpy
#  47   + victim readable until fill              workload: daxpy
#  48   + fill phase, the production stack        workload: daxpy
#   --- production stack, ablations and geometry ---
#  49   production stack, L1D 16 KiB              workload: daxpy
#  50   production stack, L1D 64 KiB              workload: daxpy
#  51   production minus the port model           workload: daxpy
#  52   production minus the readout stall        workload: daxpy
#  53   production with bit-PLRU instead          workload: daxpy
#  54   production minus the fill phase           workload: daxpy
#  55   fill delay without the random policy      workload: daxpy
#   --- fence and instruction-cache policy ---
#  56   + fence flushes the L1D                   workload: atomic_fence
#  57   + transcribed L1I policy                  workload: all
#   --- front end, direct targets and the BTB ---
#  58   production minus direct targets           workload: btb_pressure
#  59   same-cycle fetch2 redirect                workload: all
#  60   BTB as the JALR store                     workload: all
#  61   tagless BTB                               workload: all
#   --- fill timing ---
#  62   dirty-only fill delay                     workload: all
#   --- refill window ---
#  63   refill window + clean fill                workload: all
#  64   refill window alone, isolation            workload: all
#  65   fence pipeline squash, rule F5            workload: all
#  66   RAS no-recovery                           workload: all
#  67   store-class readout extra, isolation      workload: all
#  68   the tier 0 plus 2 pair                    workload: all
#  69   all candidates together                   workload: all
#  70   pair + class x and z                      workload: all
#   --- accept-and-charge ---
#  71   accept-and-charge, dirty-only fill        workload: all
#  72   accept-and-charge with the class law      workload: all
#  73   accept-and-charge, the full pair          workload: all
#  74   accept-and-charge refill window           workload: all
#   --- the fetch supply beat, basic_test's owner ---
#  75   fetch1FetchLimit 2 -> 4                   workload: all
#  76   fetch1FetchLimit 4, fetch2 buffer 2 -> 1  workload: all
#  77   fetch limit 4, fetch2 buffer 2 -> 4       workload: all
#   --- the per-line cadence, the beat's real owner ---
#  78   fetch2CycleInput False -> True            workload: all
#  79   fetch2CycleInput True, fetch & buffer 2   workload: all
#   --- the class law without the fill-0 phase artefact ---
#  80   flat fill, accept-and-charge              workload: all
#  81   TEST 72 stack on the 79 frontend          workload: all
#  82   adopted stack plus the serdiv turnaround  workload: all
#  83   adopted stack plus the divsqrt format law workload: all
#  84   adopted stack plus all                    workload: all
#   --- the final-check probes, on the adopted stack ---
#  85   L1I mshrs 1 -> 2, the I-side retry tax    workload: all
#  86   fetch limit 3, fetch2 buffer 3,           workload: all
#  87   fetch limit 4, fetch2 buffer 3            workload: all
#  88   L1I reopen at ready                       workload: all
#   --- full patch baseline ---
#  99   full production                           workload: all

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
    24: ("atomic occupancy removed",     {}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns",
         {"fuVariant": "no_occupancy"}),
    # --- data cache ---
    25: ("L1D PLRU->LRU",                {}, "16KiB", "32KiB", {"replacement_policy": LRURP()}, {}, "50MHz", "0ns", {}),
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
    # === every TEST below needs MinorCPU_CVA6.patch ===
    # --- store-to-load forwarding ---
    40: ("store forwarding on",          {"executeLSQNoStoreForwarding": False,
                                          "executeLSQStoreCollisionReplayDelay": 0}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    41: ("replay delay 2->0",            {"executeLSQStoreCollisionReplayDelay": 0}, "16KiB", "32KiB", {}, {}, "50MHz", "0ns", {}),
    # --- data-cache stack ---
    42: ("port model alone",              {}, "16KiB", "32KiB",
         {"_port_model": True}, {}, "50MHz", "0ns", {}),
    43: ("port + evict-on-allocate",      {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True}, {}, "50MHz", "0ns", {}),
    44: ("+ victim readout stall",        {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True}, {}, "50MHz", "0ns", {}),
    45: ("+ bit-PLRU counterfactual",     {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcachePLRURP()}, {}, "50MHz", "0ns", {}),
    46: ("+ random, configured branch",   {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP()}, {}, "50MHz", "0ns", {}),
    47: ("+ victim readable until fill",  {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True}, {}, "50MHz", "0ns", {}),
    48: ("production stack",              {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    # --- production stack, ablations and geometry ---
    49: ("production stack, L1D 16KiB",   {}, "16KiB", "16KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    50: ("production stack, L1D 64KiB",   {}, "16KiB", "64KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    51: ("production minus port model",   {}, "16KiB", "32KiB",
         {"evict_on_allocate": True, "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    52: ("production minus readout stall", {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    53: ("production with bit-PLRU",      {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcachePLRURP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    54: ("production minus fill phase",   {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True}, {}, "50MHz", "0ns", {}),
    55: ("fill delay, TreePLRU policy",   {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2}, {}, "50MHz", "0ns", {}),
    # --- fence and instruction-cache policy ---
    56: ("+ fence flushes the L1D",       {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True}, {}, "50MHz", "0ns", {}),
    57: ("+ transcribed L1I policy",      {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns", {}),
    # --- front end, direct targets and the BTB ---
    58: ("production minus direct targets",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns", {}),
    59: ("same-cycle fetch2 redirect",   {"fetch1ToFetch2BackwardDelay": 0},
         "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True}),
    60: ("BTB as the JALR store",        {}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL}),
    61: ("tagless BTB",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    62: ("dirty-only fill delay",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    63: ("refill window + clean fill (the pair)",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    64: ("refill window alone, isolation",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    # --- final tests ---
    65: ("fence pipeline squash, rule F5",
         {"fetch1ToFetch2BackwardDelay": 0,
          "executeFenceSquashesPipeline": True}, "16KiB", "32KiB",
         {"_port_model": True, "evict_on_allocate": True,
          "victim_readout_stall": True,
          "replacement_policy": HPDcacheRandomRP(),
          "victim_readable_until_fill": True,
          "response_latency": 2, "fill_delay": 2,
          "fence_flushes_dcache": True},
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0}),
    66: ("RAS no-recovery",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    67: ("store-class readout extra, isolation",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    68: ("the pair with class z",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    69: ("all candidates together",
         {"fetch1ToFetch2BackwardDelay": 0,
          "executeFenceSquashesPipeline": True}, "16KiB", "32KiB",
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
    70: ("pair with class x and z",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    # --- accept-and-charge, the form conversion ---
    71: ("accept-and-charge, dirty-only fill",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    72: ("accept-and-charge with the class law",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    73: ("accept-and-charge, the full pair",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    74: ("accept-and-charge refill window, flat fill",
         {"fetch1ToFetch2BackwardDelay": 0}, "16KiB", "32KiB",
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
    # --- the fetch supply beat ---
    75: ("fetch1FetchLimit 2->4, the supply beat",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch1FetchLimit": 4},
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
    76: ("fetch limit 4, fetch2 buffer 1",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch1FetchLimit": 4,
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
    77: ("fetch limit 4, fetch2 buffer 4",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch1FetchLimit": 4,
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
    # --- the per-line cadence ---
    78: ("fetch2CycleInput True, limit 4, buffer 4",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch1FetchLimit": 4,
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
    79: ("fetch2CycleInput True, production queues",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True},
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
    # --- the class law on the 79 frontend ---
    80: ("flat fill, class extras accept-and-charge",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True},
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
    81: ("TEST 72 stack on the 79 frontend",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True},
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
    82: ("adopted stack, serdiv turnaround",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True},
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
    83: ("adopted stack, divsqrt format law",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True},
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
          "fuVariant": "divsqrt_format_law"}),
    84: ("adopted stack, fence squash",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True,
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
    # --- full patch baseline ---
    85: ("adopted stack, L1I mshrs 2",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True,
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
         {"replacement_policy": CVA6IcacheRandomRP(), "mshrs": 2}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
    86: ("adopted stack, fetch limit 3, buffer 3",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True,
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
    87: ("adopted stack, fetch limit 4, buffer 3",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True,
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
    88: ("adopted stack, L1I reopen at ready",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True,
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
    99: ("full production",
         {"fetch1ToFetch2BackwardDelay": 0, "fetch2CycleInput": True,
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
         {"replacement_policy": CVA6IcacheRandomRP()}, "50MHz", "0ns",
         {"directTargetsFromDecode": True, "indirectBranchPred": NULL,
          "btbTagBits": 0, "rasNoRecovery": True}),
}


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
    # configuration, identical to gem5_config_CVA6.py.
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
        if variant == "divsqrt_legacy":
            fp_divsqrt.opLat = 2
            fp_divsqrt.issueLat = 2
            fp_divsqrt.timings = [MinorFUTiming(
                description='FpDivSqrtLegacy',
                srcRegsRelativeLats=[0],
                extraCommitLat=2)]
        elif variant == "divsqrt_format_law":
            fp_divsqrt.opLat = 12
            fp_divsqrt.issueLat = 12
            fp_divsqrt.timings = [MinorFUTiming(
                description='FpDivSqrtFp64',
                srcRegsRelativeLats=[0],
                mask=0x06000000,
                match=0x02000000,
                extraCommitLat=7)]
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


class MorillasFUPool(MinorFUPool):
    # Morillas 2025 as published (thesis Table 6.2). Its op-class groupings
    # differ from ours, and integer divide is one averaged latency of 35, the
    # midpoint of the RTL range 2 to 64 with the uniform plus two added.
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
        fu_variant = bp.pop("fuVariant", "baseline")

        self.executeFuncUnits = CVA6FUPool(variant=fu_variant)

        # Adopted baseline, identical to gem5_config_CVA6_Patch.py.
        self.fetch1FetchLimit = 2
        self.fetch1LineSnapWidth = 4
        self.fetch1LineWidth = 4
        self.fetch1ToFetch2ForwardDelay = 1
        self.fetch1ToFetch2BackwardDelay = 1
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
        # Requires the MinorCPU patch.
        self.executeLSQNoStoreForwarding = True
        self.executeLSQStoreCollisionReplayDelay = 2
        self.executeLSQFenceSignalsDcache = True
        self.executeFenceSquashesPipeline = True

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

            # Adopted baseline, identical to gem5_config_CVA6_Patch.py.
            self.l1icaches[i].assoc = 4
            self.l1icaches[i].tag_latency = 1
            self.l1icaches[i].data_latency = 1
            self.l1icaches[i].response_latency = 0
            self.l1icaches[i].mshrs = 2
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
            self.l1dcaches[i].replacement_policy = TreePLRURP()

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
    if TEST not in TESTS:
        raise ValueError(
            f"TEST={TEST} is not in the test table. Valid IDs: {sorted(TESTS.keys())}")
    (test_name, cpu_overrides, l1i_size, l1d_size, dcache_overrides,
     icache_overrides, clk_freq, mem_latency, bp_overrides) = TESTS[TEST]
    mem_bandwidth = dict(dcache_overrides).get("_mem_bandwidth", "12.8GiB/s")
use_port_model = bool(dict(dcache_overrides).get("_port_model", False))

print("=" * 70)
if USE_MORILLAS:
    print("   MORILLAS 2025 FULL CONFIGURATION")
else:
    print(f"   CVA6 HARNESS  -  TEST {TEST}: {test_name}")
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

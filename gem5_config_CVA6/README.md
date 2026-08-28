# gem5_config_CVA6

The gem5 MinorCPU configuration matched to CVA6, and the patch it depends on.

## Layout

| Path | What it is |
| --- | --- |
| `gem5/gem5_config_CVA6.py` | The matched configuration, for a **stock** gem5 |
| `gem5/gem5_config_CVA6_Patch.py` | The matched configuration, for a **patched** gem5 |
| `gem5/gem5_config_CVA6_testing.py` | The calibration harness: the stock core as a table of single-knob perturbations, `TEST 1` to `TEST 39` |
| `gem5/gem5_config_CVA6_Patch_testing.py` | The same 39 entries under the same numbers, then the ones that need the patch. This is the sweep's `DEFAULT_CONFIG` |
| `gem5/run_CVA6_testing_sweep.py` | Replays that table, sweeping its `DEFAULT_CONFIG`. See the main [README](../README.md#the-calibration-sweep) |
| `gem5/MinorCPU_CVA6.patch` | Every gem5 change the patched configuration depends on, CPU, front end and caches, in one verified file |
| `gem5/tests/` | The gem5 tests side |
| `CVA6/tests/` | The CVA6 tests side |

The comparison runs over the fourteen benchmarks `DEFAULT_ALL_TESTS` names in the sweep: `atomic_fence`, `basic_test`, `branch_full_test`, `btb_pressure`, `daxpy`, `daxpy_unrolling_4`, `fetch2_probe`, `fp_addmul`, `fp_divsqrt`, `full_test`, `icache_pressure`, `int_div`, `matmul_small` and `store_fwd`. They live in [benchmarks/gem5/](../benchmarks/gem5/) and [benchmarks/CVA6/](../benchmarks/CVA6/).

## Results

gem5 NET against CVA6 NET, both harnesses removing their own marker instructions, from the production configuration on the verified patch. Eleven of the fourteen rows sit inside 2 percent.

| Benchmark | gem5 | CVA6 | Error |
| --- | --- | --- | --- |
| `basic_test` | 14,378 | 12,557 | +14.50% |
| `fp_addmul` | 87,541 | 87,262 | +0.32% |
| `store_fwd` | 1,604 | 1,602 | +0.12% |
| `fp_divsqrt` | 2,834 | 2,828 | +0.21% |
| `int_div` | 11,343 | 11,558 | -1.86% |
| `btb_pressure` | 21,557 | 21,945 | -1.77% |
| `atomic_fence` | 34,792 | 35,838 | -2.92% |
| `fetch2_probe` | 45,052 | 44,970 | +0.18% |
| `daxpy_unrolling_4` | 71,741 | 70,844 | +1.27% |
| `daxpy` | 87,113 | 86,566 | +0.63% |
| `icache_pressure` | 363,619 | 358,907 | +1.31% |
| `matmul_small` | 454,723 | 445,958 | +1.97% |
| `full_test` | 523,208 | 525,326 | -0.40% |
| `branch_full_test` | 545,999 | 542,216 | +0.70% |

Mean absolute error 2.01 percent, and 1.05 excluding the one footnoted row, `basic_test`, whose owners are named and priced in the limitations below. Mispredict counts sit within tens of the hardware on every row, `icache_pressure` at 4,104 against 4,113, and the demand miss counts match to a handful everywhere except `daxpy`'s documented 6,595 against 6,147.

The stock configuration on an unpatched gem5 reads 14.02 percent on the same pairs. That figure is itself lower than the 21.4 the calibration started from, because three of this work's findings, the fetch cadence, the divider turnaround and the second instruction MSHR, are stock parameters and improve the unpatched baseline too. The distance from 14.02 to 2.01 is the transcribed mechanisms: the fence flush walk alone is `atomic_fence` at -94 percent without it, and `fetch2_probe` reads +27.9 against +0.18.

The two divider probes, `fp_divsqrt_probe` and `fp_divsqrt_probe2`, are diagnostic rows rather than suite members, and their errors, +10.9 and +40.9 percent, are the divider limitation measuring itself: probe2's 1,316-cycle gap against a fast-path arithmetic of 1,312.

## The matched configuration

It comes in two versions. `gem5_config_CVA6.py` runs on a **stock gem5**, using only what upstream already provides, so it works against an unmodified build. `gem5_config_CVA6_Patch.py` runs on a **patched gem5** and adds the mechanisms the patch makes available. Each has a `_testing` twin carrying the calibration table.

Both target `cv64a6_imafdc_sv39_hpdcache_wb` at 50 MHz, with a 16 KiB L1I and a 32 KiB L1D. Every value is either derived from a CVA6 RTL localparam or is a gem5-side estimate where CVA6 has no clean counterpart.

Run either like any other gem5 config:

```bash
python3 run_gem5.py gem5_config_CVA6.py <test>         # stock gem5
python3 run_gem5.py gem5_config_CVA6_Patch.py <test>   # patched gem5
```

In the patched version every transcribed mechanism is on by default and each has a `--no-` switch that turns it off, so it doubles as its own ablation harness. `--no-patch` is all of them at once, which reproduces the stock MinorCPU behaviour the calibration started from. The stock configuration takes no switches, since it carries none of these mechanisms.

| Switch | Turns off |
| --- | --- |
| `--no-patch` | Every mechanism below, at once |
| `--no-port-model` | The single-ported memory adapter |
| `--no-evict-on-allocate` | Victim selection and writeback at MSHR allocation |
| `--no-victim-readout-stall` | The dirty-victim data-array occupancy |
| `--no-cva6-victim-policy` | The transcribed L1D victim policy, back to gem5 TreePLRU |
| `--no-victim-readable-until-fill` | The victim staying readable until its refill |
| `--no-fill-phase` | The L1D fill-instant correction |
| `--no-fence-flush` | A fence flushing the L1D, both the core's signal and the cache acting on it |
| `--no-fence-squash` | The rule F5 pipeline squash on a committed full fence |
| `--no-window-charge` | The accept-and-charge form of the readout window and its class extras, back to the flat fill split |
| `--no-cva6-icache-policy` | The transcribed L1I policy, back to gem5 RandomRP |
| `--no-cva6-direct-targets` | Decode-computed direct targets, and with them the JALR-only tagless BTB |
| `--no-ras-decay` | The unrecovered speculative RAS, back to gem5's repair on squash. Implied by `--no-cva6-direct-targets` |
| `--no-store-forwarding-model` | CVA6 having no store-to-load forwarding, and the replay delay with it |

### The calibration table

`gem5_config_CVA6_Patch_testing.py` is the campaign in one file. `TEST 1` is the frozen CPU-side baseline, `TEST 99` is the full production configuration, and every other entry is a single-knob perturbation.

The table is ordered by what an entry needs to run, then by the part of the machine it touches, front of the pipeline first. `gem5_config_CVA6_testing.py` carries the first tier, `TEST 1` to `TEST 39`, under the same numbers, so a row means the same thing in both files.

**TESTS 1 to 39 run on a stock gem5.**

| # | What it changes | Workload |
| --- | --- | --- |
| 1 | adopted baseline | all |
| | **fetch geometry** | |
| 2 | fetch1FetchLimit 2 -> 1 | matmul_small |
| 3 | fetch1FetchLimit 2 -> 3 | matmul_small |
| 4 | fetch 8B/8B, fetch2 buffer 8 | all |
| 5 | fetch2InputBufferSize 2 -> 4 | fetch2_probe |
| | **instruction cache** | |
| 6 | L1I random -> LRU | full_test |
| 7 | L1I response_latency 0 -> 1 | daxpy |
| 8 | L1I response_latency 0 -> 2 | daxpy |
| 9 | L1I 4KiB | daxpy |
| | **decode buffer** | |
| 10 | decodeInputBufferSize 1 -> 4 | daxpy, full_test |
| 11 | decodeInputBufferSize 1 -> 8 | daxpy, full_test |
| | **branch prediction** | |
| 12 | Morillas 2025 predictor sizing | branch_full_test, btb_pressure, full_test |
| 13 | BTB 32 -> 512 | branch_full_test, btb_pressure, full_test |
| 14 | BTB 32 -> 4096 | branch_full_test, btb_pressure, full_test |
| | **LSQ queue geometry** | |
| 15 | requests queue 2 -> 4 | store_fwd |
| 16 | requests queue 2 -> 8 | store_fwd |
| 17 | store buffer 4 -> 8 | store_fwd |
| 18 | requests 8, store buffer 8 | store_fwd |
| | **functional units** | |
| 19 | int_mul opLat 2 -> 1 | daxpy, full_test |
| 20 | fp_divsqrt legacy | fp_divsqrt |
| 21 | serdiv base 1 -> 0 | int_div |
| 22 | fp_addmul without the double mask | fp_addmul |
| 23 | FP mem classes back on vec_mem_fast | daxpy |
| 24 | atomic occupancy entries removed | atomic_fence |
| | **data cache** | |
| 25 | L1D PLRU -> true LRU | full_test |
| 26 | response_latency 4 -> 5 | daxpy |
| 27 | response_latency 4 -> 6 | daxpy |
| 28 | response_latency 4 -> 3 | daxpy |
| 29 | L1D 16KiB | daxpy |
| 30 | L1D 64KiB | daxpy |
| 31 | L1D assoc 8 -> 2 | daxpy |
| 32 | L1D mshrs 8 -> 1 | daxpy |
| 33 | L1D write_buffers 8 -> 2 | daxpy |
| 34 | L1D hit lat +1 | daxpy |
| | **memory system** | |
| 35 | membus width 8 -> 16 | daxpy |
| 36 | membus width 8 -> 4 | daxpy |
| 37 | memory bandwidth 12.8GiB/s -> 0.4GiB/s | daxpy |
| 38 | mem latency 0 -> 60ns | daxpy |
| | **core-wide** | |
| 39 | threadPolicy -> RoundRobin | daxpy |

**TESTS 40 to 87 and TEST 99 need the patch.**

| # | What it changes | Workload |
| --- | --- | --- |
| | **store-to-load forwarding** | |
| 40 | store forwarding re-enabled | store_fwd |
| 41 | replay delay 2 -> 0 | store_fwd |
| | **data-cache stack** | |
| 42 | port model alone | daxpy |
| 43 | + evict-on-allocate | daxpy |
| 44 | + victim readout stall | daxpy |
| 45 | + HPDcache bit-PLRU | daxpy |
| 46 | + HPDcache random | daxpy |
| 47 | + victim readable until fill | daxpy |
| 48 | + fill phase, the production stack | daxpy |
| | **production stack, ablations and geometry** | |
| 49 | production stack, L1D 16 KiB | daxpy |
| 50 | production stack, L1D 64 KiB | daxpy |
| 51 | production minus the port model | daxpy |
| 52 | production minus the readout stall | daxpy |
| 53 | production with bit-PLRU instead | daxpy |
| 54 | production minus the fill phase | daxpy |
| 55 | fill delay without the random policy | daxpy |
| | **fence and instruction-cache policy** | |
| 56 | + fence flushes the L1D | atomic_fence |
| 57 | + transcribed L1I policy | all |
| | **front end, direct targets and the BTB** | |
| 58 | production minus direct targets | btb_pressure |
| 59 | same-cycle fetch2 redirect | all |
| 60 | BTB as the JALR store | all |
| 61 | tagless BTB | all |
| | **fill timing** | |
| 62 | dirty-only fill delay | all |
| | **refill window** | |
| 63 | refill window + clean fill | all |
| 64 | refill window alone, isolation | all |
| 65 | fence pipeline squash, rule F5 | all |
| 66 | RAS no-recovery | all |
| 67 | store-class readout extra, isolation | all |
| 68 | the tier 0 plus 2 pair | all |
| 69 | all candidates together | all |
| 70 | pair + class x and z | all |
| | **accept-and-charge** | |
| 71 | accept-and-charge, dirty-only fill | all |
| 72 | accept-and-charge with the class law | all |
| 73 | accept-and-charge, the full pair | all |
| 74 | accept-and-charge refill window | all |
| | **the fetch supply beat, basic_test's owner** | |
| 75 | fetch1FetchLimit 2 -> 4 | all |
| 76 | fetch1FetchLimit 4, fetch2 buffer 2 -> 1 | all |
| 77 | fetch limit 4, fetch2 buffer 2 -> 4 | all |
| | **the per-line cadence, the beat's real owner** | |
| 78 | fetch2CycleInput False -> True | all |
| 79 | fetch2CycleInput True, fetch & buffer 2 | all |
| | **the class law without the fill-0 phase artefact** | |
| 80 | flat fill, accept-and-charge | all |
| 81 | TEST 72 stack on the 79 frontend | all |
| 82 | adopted stack plus the serdiv turnaround | all |
| 83 | adopted stack plus the divsqrt format law | all |
| 84 | adopted stack plus all | all |
| | **the final-check probes, on the adopted stack** | |
| 85 | L1I mshrs 1 -> 2, the I-side retry tax | all |
| 86 | fetch limit 3, fetch2 buffer 3 | all |
| 87 | fetch limit 4, fetch2 buffer 3 | all |
| | **full patch baseline** | |
| 99 | full production | all |

## The patch

`MinorCPU_CVA6.patch` is the whole gem5 side in one file, verified to apply cleanly on pristine v25.0.0.1 with both `git apply` and `patch`, and to revert to a byte-identical tree. Every behaviour it adds is a transcription of a specific RTL rule, every one is behind a parameter that defaults to the stock behaviour, and every one carries its citation in the source comments. A patched gem5 runs unpatched configurations unchanged.

### Applying it

Run from the gem5 source root. The paths carry `a/` and `b/` prefixes, so the default strip level is right and no `-p` flag is needed.

```bash
cd /gem5
git apply --check MinorCPU_CVA6.patch    # dry run, silent on success
git apply MinorCPU_CVA6.patch
scons defconfig build/RISCV_PATCH build_opts/RISCV
scons build/RISCV_PATCH/gem5.opt -j$(nproc)
```

The build directory is `RISCV_PATCH` and not `RISCV` because this project keeps `build/RISCV` as the stock binary. Building the patch into it would overwrite that, and nothing afterwards would say so.

The rebuild is not optional. The patch adds SimObjects and `SConscript` entries, so the generated Python parameter set changes and an existing `build/` will not pick the new parameters up on its own.

`patch -p1 < MinorCPU_CVA6.patch` works the same way outside a git checkout and produces a byte-identical tree.

### Reverting it

Feed the same file back with `-R`. Both tools restore the 22 edited files and delete the 9 created ones, leaving a tree that `git status` reports as clean.

```bash
cd /gem5
git apply -R MinorCPU_CVA6.patch          # or: patch -R -p1 < MinorCPU_CVA6.patch
scons build/RISCV_PATCH/gem5.opt -j$(nproc)
```

That rebuild turns `build/RISCV_PATCH` back into a stock binary, which is rarely what you want. If a stock binary is all you need, `build/RISCV` already is one and nothing has to be rebuilt.

[`run_gem5.py`](../benchmarks/gem5/run_gem5.py) takes `--variant stock`, the default, or `--variant patch`, which picks the binary and the overhead profile together and names the build in the table header. `--build` runs any other build directory without changing the profile.

Since every added parameter defaults off, the patched binary running `gem5_config_CVA6.py` should reproduce the stock binary exactly. Diffing the two `stats.txt` files is the test of that, and any line that differs is a mechanism leaking when it should be inert. `gem5_config_CVA6_Patch.py --no-patch` is the same test from the other direction, holding the configuration fixed and turning the mechanisms off.

### New parameters

| Parameter | Object | Default | What it does |
| --- | --- | --- | --- |
| `executeLSQNoStoreForwarding` | MinorCPU | `False` | Disables store-to-load forwarding from the store buffer |
| `executeLSQStoreCollisionReplayDelay` | MinorCPU | `0` | Cycles a load waits after a store collision clears |
| `executeLSQFenceSignalsDcache` | MinorCPU | `False` | A fence signals the data cache, modelling the core's flush wire |
| `directTargetsFromDecode` | BranchPredictor | `False` | Taken direct control takes its target from the decoded instruction and never installs in the BTB |
| `executeFenceSquashesPipeline` | MinorCPU | `False` | A committed full fence squashes the pipeline and restarts fetch at the next PC |
| `rasNoRecovery` | BranchPredictor | `False` | Speculative RAS pushes and pops stand uncorrected on a squash, as CVA6's scan-driven stack |
| `evict_on_allocate` | Cache | `False` | Selects the victim and issues its writeback at MSHR allocation |
| `victim_readout_stall` | Cache | `False` | Charges the dirty-victim data-array readout, `blkSize / 8` cycles |
| `victim_readout_store_extra` | Cache | `0` | Extra readout-window cycles when a store triggered the eviction |
| `victim_readout_first_load_extra` | Cache | `0` | Extra readout-window cycles when a lone load triggered the eviction |
| `refill_window_blocks` | Cache | `False` | Blocks the CPU side for `blkSize / 8` cycles while a refill writes the data array |
| `window_accept_and_charge` | Cache | `False` | The accept-and-charge form of both windows: the port never blocks, a request inside a window takes the overlap as latency, the miss that opens a readout window takes it on its own fill |
| `victim_readable_until_fill` | Cache | `False` | Keeps the victim answering hits until its refill lands |
| `fill_delay` | Cache | `0` | Extra cycles from response arrival to fill, without touching shared memory latency |
| `fence_flushes_dcache` | Cache | `False` | A fence writes back every dirty line and holds the cache 2 cycles per line |

### New SimObjects

| Object | What it is |
| --- | --- |
| `Axi2MemPort` | The CVA6 testbench memory adapter: one transaction at a time, fixed read priority, `1 + N` cycle occupancy for `N` eight-byte beats |
| `HPDcacheRandomRP` | The L1D victim policy the build configures: four tiers, with an 8-bit Galois LFSR, polynomial `0xE1` |
| `HPDcachePLRURP` | The L1D bit-PLRU branch the build does **not** configure |
| `CVA6IcacheRandomRP` | The L1I policy: lowest-index invalid way, else an 8-bit Galois LFSR, polynomial `0xFA` |

### New statistics

The patch leaves every stock counter untouched and adds its own beside them.

| Statistic | Object | What it counts |
| --- | --- | --- |
| `preemptionBlockedCycles` | Cache | Cycles blocked by a CVA6 preemption cause: victim readout, fence flush or refill window |
| `cva6ComparableDemandAccesses` | Cache | Demand accesses plus the preemption and window cycles below, the count the HPDcache PMU reports |
| `earlyReservations` | Cache | Victims reserved at miss time by evict-on-allocate |
| `reservationFallbacks` | Cache | Misses that fell back to stock fill-time allocation |
| `inPlaceReservations` | Cache | Reservations that kept the victim readable |
| `reservationRedirties` | Cache | In-place victims dirtied again before their refill landed, so written back twice |
| `fenceFlushes` | Cache | Full flushes a fence triggered |
| `fenceFlushWritebacks` | Cache | Dirty lines those flushes wrote back |
| `windowTriggerCharges`, `windowTriggerCycles` | Cache | Misses charged their own readout window under accept-and-charge, and the cycles |
| `windowOverlapCharges`, `windowOverlapCycles` | Cache | Requests charged a window overlap, and the cycles |
| `reservationUpgradeFallbacks` | Cache | In-place reservations released at fill time because an upgrade on the victim was still outstanding |
| `unusedTier`, `randomTier`, `cleanTier`, `dirtyTier`, `noVictim` | HPDcacheRandomRP | Which tier of the victim policy supplied each selection |
| `readsAdmitted`, `writesAdmitted` | Axi2MemPort | Transactions admitted to the single port, by class |
| `passThrough` | Axi2MemPort | Packets with no AXI equivalent, forwarded without occupancy |
| `readWaitCycles`, `writeWaitCycles` | Axi2MemPort | Admission wait histograms, by class |

The metrics table uses three of these: `preemptionBlockedCycles`, `windowTriggerCycles` and `windowOverlapCycles`. Both `run_gem5.py` scripts add them to the cache-access rows and print the result as a third column, `NET (CVA6)`, next to `NET`, so a gem5 table reads against a CVA6 one row for row. The two forms are exclusive, blocking charging the first and accept-and-charge the other two, so summing all three covers either and matches `cva6ComparableDemandAccesses`.

### What each change models, briefly

**Instruction-side miss acceptance.** The L1I holds two MSHRs, a stock parameter. With one, the line Fetch1 requests during a miss is refused and retried off the clock edge, a tax CVA6 never pays: its icache takes no request during a miss and the frontend presents the next line the cycle the first returns (`cva6_icache.sv` MISS state). With two, the request coalesces or queues at the memory port, and miss chains land at CVA6's one fill per five cycles. The harness reads `overallMshrMisses` on both caches, the refill count the PMU counts.

**Fetch cadence.** CVA6's icache accepts a hit request every cycle in its READ state (`cva6_icache.sv` 263 to 287). Minor's Fetch2 with `fetch2CycleInput` false takes the next line a cycle after exhausting one (`fetch2.cc` 526), half the rate. The configuration sets it true. A stock parameter, not a patch, and the published empirical configuration already carried it.

**Front end.** CVA6 computes direct-branch and jump targets in the fetch path and consults its BTB only for JALR, whose entries are tagless and written on a mispredict (`frontend.sv`, `btb.sv`). The patch adds the decode-target model, and the configuration then drops the indirect predictor and the BTB tag and signals fetch2 predictions to fetch1 in the same cycle, matching CVA6's one-bubble re-steer against Minor's two.

**Store forwarding.** CVA6 has no store-to-load forwarding path. Its load unit parks a load in `WAIT_PAGE_OFFSET` until the store buffer drains whenever the address collides with a pending store (`load_unit.sv`, and `page_offset_matches_o` in `store_buffer.sv`, an eight-byte granule). Restarting that load costs two more cycles, since neither `IDLE` nor `WAIT_PAGE_OFFSET` asserts `data_req`.

**The memory port.** The testbench adapter (`axi2mem.sv`) is single-ported and holds one transaction end to end, testing `ar_valid` before `aw_valid` so reads always win. It adds no latency when uncontended, so contention appears only as admission wait.

**Eviction phase.** The HPDcache selects its victim and issues the dirty writeback at MSHR allocation, not at fill (`hpdcache_miss_handler.sv`). That readout occupies the data array for `clWords / accessWords` cycles, 2 for the 16-byte line, and the array is single-ported across five requesters (`hpdcache_memctrl.sv`).

**Victim policy.** The build configures `HPDCACHE_VICTIM_RANDOM`, not the PLRU branch: one global LFSR shared by the whole cache, shifting only when the random tier fires. Validated against a VCD probe at 7,406 of 7,406 selections, and it predicts the real machine's writeback counts to within one percent at 16, 32 and 64 KiB and at 2-way.

**Readable victim.** CVA6's directory update is pipelined, so an access one cycle behind an allocation still hits the line being displaced. gem5 re-tags synchronously and would lose it. Without this a random policy costs about 514 spurious misses on daxpy.

**Fill instant.** CVA6's clean misses complete around 9 cycles and its dirty-eviction misses later by the victim readout, 2 cycles for the 16-byte line, plus a class term per trigger: +1 for a load with no other miss outstanding, +4 for a store through the replay table (`hpdcache_rtab.sv` POP_TRY, `hpdcache_flush.sv`). The configuration now charges nothing flat and lets the readout window carry the base and its extras on the triggering miss's own fill. A request arriving inside an open window takes the overlap as its own latency, as the HPDcache stalls it in stage 0 (`hpdcache_ctrl_pe.sv` 338 to 348), and the port never refuses, since a refusal in Minor costs a rounded-up retry cycle and freezes the LSQ (`base.cc` 184, `lsq.cc` 1247), which the RTL does not do.

**Integer divider turnaround.** `serdiv.sv` returns to IDLE the cycle after FINISH clears (lines 178 to 215), so consecutive independent divides issue 12 apart where the data-dependent latency alone gives 11. `issueLat 3` on the divide unit carries it.

**Fence squash.** A committed full fence squashes the pipeline and restarts fetch at the next PC, rule F5 (`controller.sv` 123 to 136). On this configuration the re-fetch completes inside the flush walk, so the tables are unchanged by it.

**Fence flush.** A fence flushes the D-cache when `DcacheFlushOnFence` is set, which it is for this build (`controller.sv`). The core drives that as a dedicated wire rather than a bus transaction, so `executeLSQFenceSignalsDcache` sends it functionally and `fence_flushes_dcache` decides whether the cache acts on it. The walk costs 2 cycles per line (`hpdcache_cmo.sv`), counted during the walk so it scales with cache geometry.

**Instruction cache policy.** A separate module from the HPDcache with its own two-tier policy and its own LFSR (`cva6_icache.sv` plus PULP's `lfsr.sv`), advancing only on a fill into an already full set. This buys exactness rather than accuracy, since gem5's stock `RandomRP` is already in the same class.

### Files changed

`src/cpu/minor/` for `BaseMinorCPU.py`, `execute.cc`, `execute.hh`, `lsq.cc` and `lsq.hh`. `src/cpu/pred/` for `BranchPredictor.py`, `bpred_unit.hh`, `bpred_unit.cc`, `ras.hh` and `ras.cc`. `src/mem/` for the adapter and its `SConscript` entry. `src/mem/cache/` for `Cache.py`, `base.hh`, `base.cc`, `cache.hh`, `cache_blk.hh`, `mshr.hh` and `mshr.cc`. `src/mem/cache/tags/` for the fill-time replacement hook, in `base.hh` and `base_set_assoc.hh`. `src/mem/cache/replacement_policies/` for the three policies and their registrations.

## Known limitations

Six divergences remain, each with a named mechanism and priced where a fix exists and was declined.

**The FP divider's short path.** The hardware divides and takes square roots of small-mantissa operands in 10 cycles where full-mantissa operands take 15 and 22, the general law the model carries. The trigger is the mantissa length of both divide operands and of the radicand for the root, and a seven-bit radicand still runs short, by 5 and 4. Two probes measured it across fifteen chain blocks, and it is absent from `control_mvp.sv` and `preprocess_mvp.sv` at cvfpu revision 272e6e5, the one the hardware runs, so it is not transcribed.

**The fetch-cadence residue, a priced queue depth.** `basic_test`'s uncompressed sections recovered about 38 of the 49 cycles per pass the cadence fix predicted. The remaining 11 are a second beat: the fetch round trip is 3 cycles, and with `fetch1FetchLimit` and `fetch2InputBufferSize` both at 2 the requests go out two lines every three cycles. Depth 3 was tested and declined: `basic_test` recovered 835 cycles while `btb_pressure` paid 3,505 and the run-ahead gauge moved 4,100 fetches past the hardware. The queues stay at 2 and the row keeps the residue.

**daxpy's miss count under the fill split.** With the readout window charging the trigger's own fill instead of a flat delay on every fill, the relative phase of the three streams inside a set changes and the transcribed random policy names a different way on its third visit to each set: 6,595 misses against the hardware's 6,147, worth 379 cycles because Minor's single outstanding miss overlaps most of each with the FP chain. The tier probe shows the same tiers firing at the same rates, so the difference is the LFSR phase.

**Miss-level parallelism at one.** Minor serialises demand misses where the HPDcache overlaps a second. Its visible cost on this suite is gone with the fill split, `fetch2_probe` at +0.19, but the structure stands and the port model's calibration absorbs it.

**Instruction-side pair timing under two MSHRs.** Isolated queued miss pairs land about two cycles faster than the hardware, the second fill arriving at the port's occupancy behind the first rather than CVA6's full five-cycle re-present, which is why `int_div` reads -1.86 and `btb_pressure` -1.77. Chains match and pairs undershoot. The residue is the port model's occupancy against the icache's re-present interval, documented rather than tuned.

**Instruction-side access counts.** CVA6's PMU counts every fetch it presents, including the wrong-path lines its deeper run-ahead issues and kills, which gem5 never issues. The cadence fix widens that gap slightly, since faster instruction flow resolves branches sooner and fetches fewer wrong-path lines. I-miss counts match on every row. I-access counts are a behavioural difference, reported rather than compared.

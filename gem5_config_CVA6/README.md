# gem5_config_CVA6

The gem5 MinorCPU configuration matched to CVA6, and the patch it depends on.

## Layout

| Path | What it is |
| --- | --- |
| `gem5/gem5_config_CVA6.py` | The matched configuration, for a **stock** gem5 |
| `gem5/gem5_config_CVA6_Patch.py` | The matched configuration, for a **patched** gem5 |
| `gem5/gem5_config_CVA6_testing.py` | The calibration harness: the stock core as a table of single-knob perturbations |
| `gem5/gem5_config_CVA6_Patch_testing.py` | The same table for the patched core. This is the sweep's `DEFAULT_CONFIG` |
| `gem5/run_CVA6_testing_sweep.py` | Replays that table, sweeping its `DEFAULT_CONFIG`. See the main [README](../README.md#the-calibration-sweep) |
| `gem5/MinorCPU_CVA6.patch` | Every gem5 change the patched configuration depends on, CPU, front end and caches, in one verified file |
| `gem5/tests/` | The gem5 tests side |
| `CVA6/tests/` | The CVA6 tests side |

The comparison runs over the fourteen benchmarks `DEFAULT_ALL_TESTS` names in the sweep: `atomic_fence`, `basic_test`, `branch_full_test`, `btb_pressure`, `daxpy`, `daxpy_unrolling_4`, `fetch2_probe`, `fp_addmul`, `fp_divsqrt`, `full_test`, `icache_pressure`, `int_div`, `matmul_small` and `store_fwd`. They live in [benchmarks/gem5/](../benchmarks/gem5/) and [benchmarks/CVA6/](../benchmarks/CVA6/).

## Results

Across the fourteen pairs the patched configuration lands at a mean absolute cycle error of 9.4 percent, and 3.8 excluding the two smallest programs, whose absolute gaps are a scaffold-dominated 131 and 467 cycles. The two composite tests, `full_test` and `branch_full_test`, read -0.35 and +0.24 percent. The stock-gem5 version, which keeps every calibrated value but none of the transcribed mechanisms, reads 21.4 percent on the same pairs, which is the argument for the patch in one number.

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
| `--no-cva6-icache-policy` | The transcribed L1I policy, back to gem5 RandomRP |
| `--no-cva6-direct-targets` | Decode-computed direct targets, and with them the JALR-only tagless BTB |
| `--no-store-forwarding-model` | CVA6 having no store-to-load forwarding, and the replay delay with it |

### The calibration table

`gem5_config_CVA6_Patch_testing.py` is the campaign in one file. `TEST 1` is the frozen CPU-side baseline, `TEST 99` is the full production configuration, and every other entry is a single-knob perturbation. `gem5_config_CVA6_testing.py` carries the same table minus the entries that need the patch.

| # | What it changes | Workload | Stock too |
| --- | --- | --- | --- |
| 1 | adopted baseline | all | yes |
| | **replacement policies** | | |
| 2 | L1D PLRU -> true LRU | full_test |  |
| 3 | L1I random -> LRU | full_test | yes |
| | **fetch geometry (the two-sided bound)** | | |
| 4 | fetch1FetchLimit 2 -> 1 | matmul_small | yes |
| 5 | fetch1FetchLimit 2 -> 3 | matmul_small | yes |
| 6 | fetch 8B/8B, fetch2 buffer 8 | all | yes |
| 7 | fetch2InputBufferSize 2 -> 4 | fetch2_probe | yes |
| 8 | L1I response_latency 0 -> 1 | daxpy | yes |
| | **decode buffer (structural hypothesis refuted)** | | |
| 9 | decodeInputBufferSize 1 -> 4 | daxpy, full_test | yes |
| 10 | decodeInputBufferSize 1 -> 8 | daxpy, full_test | yes |
| | **LSQ queue geometry (mechanism A exclusion set)** | | |
| 11 | requests queue 2 -> 4 | store_fwd | yes |
| 12 | requests queue 2 -> 8 | store_fwd | yes |
| 13 | store buffer 4 -> 8 | store_fwd | yes |
| 14 | requests 8, store buffer 8 | store_fwd | yes |
| | **branch prediction** | | |
| 15 | Morillas 2025 predictor sizing | branch_full_test, btb_pressure, full_test | yes |
| 16 | BTB 32 -> 512 | branch_full_test, btb_pressure, full_test | yes |
| 17 | BTB 32 -> 4096 | branch_full_test, btb_pressure, full_test | yes |
| | **functional units** | | |
| 18 | int_mul opLat 2 -> 1 | daxpy, full_test | yes |
| 19 | fp_divsqrt legacy (2, flat +2) | fp_divsqrt | yes |
| 20 | serdiv base 1 -> 0 | int_div | yes |
| 21 | fp_addmul without the double mask | fp_addmul | yes |
| 22 | FP mem classes back on vec_mem_fast | daxpy | yes |
| 23 | atomic occupancy entries removed | atomic_fence | yes |
| | **memory path** | | |
| 24 | response_latency 4 -> 5 | daxpy | yes |
| 25 | response_latency 4 -> 6 | daxpy | yes |
| 26 | response_latency 4 -> 3 | daxpy | yes |
| 27 | membus width 8 -> 16 | daxpy | yes |
| 28 | membus width 8 -> 4 | daxpy | yes |
| 29 | write_buffers 8 -> 2 | daxpy | yes |
| 30 | memory bandwidth 12.8GiB/s -> 0.4GiB/s | daxpy | yes |
| 31 | threadPolicy -> RoundRobin | daxpy | yes |
| 32 | mem latency 0 -> 60ns | daxpy | yes |
| 33 | L1D 16KiB | daxpy | yes |
| 34 | L1D 64KiB | daxpy | yes |
| 35 | L1D assoc 8 -> 2 | daxpy | yes |
| 36 | L1I 4KiB | daxpy | yes |
| 37 | L1D mshrs 8 -> 1 | daxpy | yes |
| 38 | L1D hit lat +1 | daxpy | yes |
| 39 | L1I resp 0 -> 2 | daxpy | yes |
| | **memory-mechanism campaigns** | | |
| 40 | store forwarding re-enabled | store_fwd |  |
| 41 | replay delay 2 -> 0 | store_fwd |  |
| 42 | port model alone | daxpy |  |
| 43 | port model + evict-on-allocate | daxpy |  |
| 44 | + victim readout stall | daxpy |  |
| 45 | + HPDcache bit-PLRU (counterfactual) | daxpy |  |
| 46 | + HPDcache random (configured branch) | daxpy |  |
| 47 | + victim readable until fill | daxpy |  |
| 48 | + fill phase, the production stack | daxpy |  |
| 49 | production stack, L1D 16 KiB | daxpy |  |
| 50 | production stack, L1D 64 KiB | daxpy |  |
| 51 | production minus the port model | daxpy |  |
| 52 | production minus the readout stall | daxpy |  |
| 53 | production with bit-PLRU instead | daxpy |  |
| 54 | production minus the fill phase | daxpy |  |
| 55 | fill delay without the random policy | daxpy |  |
| | **fence, instruction-cache policy, front end** | | |
| 56 | + fence flushes the L1D | atomic_fence |  |
| 57 | + transcribed L1I policy (IG1) | all |  |
| 58 | production minus direct targets (BG) | btb_pressure |  |
| | **grounded frontend candidates, bilateral bubble measurement** | | |
| 59 | same-cycle fetch2 redirect (adopted) | all |  |
| 60 | BTB as the JALR store | all |  |
| 62 | tagless BTB | all |  |
| | **full patch baseline** | | |
| 99 | full production | all |  |

## The patch

`MinorCPU_CVA6.patch` is the whole gem5 side in one file, verified to apply cleanly on pristine v25.0.0.1 with both `git apply` and `patch`, and to revert to a byte-identical tree. Every behaviour it adds is a transcription of a specific RTL rule, every one is behind a parameter that defaults to the stock behaviour, and every one carries its citation in the source comments. A patched gem5 runs unpatched configurations unchanged.

It touches 28 files under `src/`: 19 edited in place and 9 created.

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

Feed the same file back with `-R`. Both tools restore the 19 edited files and delete the 9 created ones, leaving a tree that `git status` reports as clean.

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
| `evict_on_allocate` | Cache | `False` | Selects the victim and issues its writeback at MSHR allocation |
| `victim_readout_stall` | Cache | `False` | Charges the dirty-victim data-array readout, `blkSize / 8` cycles |
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

### What each change models, briefly

**Front end.** CVA6 computes direct-branch and jump targets in the fetch path and consults its BTB only for JALR, whose entries are tagless and written on a mispredict (`frontend.sv`, `btb.sv`). The patch adds the decode-target model, and the configuration then removes the indirect predictor, drops the BTB tag, and signals fetch2 predictions to fetch1 in the same cycle, matching CVA6's measured one-bubble re-steer against Minor's stock two.

**Store forwarding.** CVA6 has no store-to-load forwarding path. Its load unit parks a load in `WAIT_PAGE_OFFSET` until the store buffer drains whenever the address collides with a pending store (`load_unit.sv`, and `page_offset_matches_o` in `store_buffer.sv`, which compares `page_offset[11:3]`, an eight-byte granule). Restarting that load costs two more cycles, since neither `IDLE` nor `WAIT_PAGE_OFFSET` asserts `data_req`.

**The memory port.** The testbench adapter (`axi2mem.sv`) is single-ported and holds one transaction end to end, testing `ar_valid` before `aw_valid` so reads always win. The model adds zero latency when uncontended, so contention appears only as admission wait.

**Eviction phase.** The HPDcache selects its victim and issues the dirty writeback at MSHR allocation, not at fill (`hpdcache_miss_handler.sv`). The readout of that victim occupies the data array for `clWords / accessWords` cycles, which is 2 for the 16-byte line, and the array is single-ported across five requesters, asserted in `hpdcache_memctrl.sv`.

**Victim policy.** The build configures `HPDCACHE_VICTIM_RANDOM`, not the PLRU branch: one global LFSR shared by the whole cache, shifting only when the random tier fires. Validated against a VCD probe at 7,406 of 7,406 selections, and it predicts the real machine's writeback counts to within one percent at 16, 32 and 64 KiB and at 2-way.

**Readable victim.** CVA6's directory update is pipelined, so an access one cycle behind an allocation still hits the line being displaced. gem5 re-tags synchronously and would lose it. Without this, a random policy costs about 514 spurious misses on daxpy.

**Fill instant.** CVA6's refill lands 7 cycles after the victim selection where the stock model fills at 5. Those 2 cycles are moved into `fill_delay` on the L1D alone and taken back out of its response latency, so the CPU-visible miss latency is unchanged and the L1I is untouched.

**Fence flush.** A fence flushes the D-cache when `DcacheFlushOnFence` is set, which it is for this build (`controller.sv`). The core drives that as a dedicated wire rather than a bus transaction, so `executeLSQFenceSignalsDcache` sends it functionally, at no port bandwidth, and `fence_flushes_dcache` decides whether the cache acts on it. The walk costs 2 cycles per line, one to check the directory entry and one to update it, which `hpdcache_cmo.sv` states outright. The duration is counted during the walk, so it scales with cache geometry automatically.

**Instruction cache policy.** A separate module from the HPDcache with its own two-tier policy and its own LFSR (`cva6_icache.sv` plus PULP's `lfsr.sv`), advancing only on a fill into an already full set. This one buys exactness rather than accuracy, since gem5's stock `RandomRP` is already in the same class.

### Files changed

`src/cpu/minor/` for `BaseMinorCPU.py`, `execute.cc`, `lsq.cc` and `lsq.hh`. `src/cpu/pred/` for `BranchPredictor.py`, `bpred_unit.hh` and `bpred_unit.cc`. `src/mem/` for the adapter and its `SConscript` entry. `src/mem/cache/` for `Cache.py`, `base.hh`, `base.cc`, `cache.hh`, `cache_blk.hh`, `mshr.hh` and `mshr.cc`. `src/mem/cache/tags/` for the fill-time replacement hook. `src/mem/cache/replacement_policies/` for the three policies and their registrations.

## Known limitations

Three divergences remain, each with a named mechanism.

**Store-buffer residency.** gem5's store buffer drains faster than CVA6's two-queue structure, so the collision stall fires on 3 loads where CVA6 stalls on 128. Its dependent chain also costs about 2 cycles more per iteration, and the two errors partly cancel, so correcting either alone makes the agreement worse.

**Miss-path parallelism.** Minor serializes demand misses where the HPDcache overlaps them, and no queue or MSHR parameter lifts it. The miss-chasing stress test carries the cost at about 2 cycles per miss.

**Eviction cost accounting.** CVA6 charges 2 and 6 extra cycles when a dirty eviction is triggered by the second load or the store, against gem5's zero, while gem5's baseline window is 2 cycles longer than CVA6's. The terms have opposite signs and nearly cancel, and the residual is predictable from cache geometry alone to within a quarter of a percent.

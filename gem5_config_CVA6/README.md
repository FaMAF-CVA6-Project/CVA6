# gem5_config_CVA6

The gem5 MinorCPU configuration matched to CVA6, and the paired runs that show how close the match is.

## Layout

| Path | What it is |
| --- | --- |
| `gem5/gem5_config_CVA6.py` | The matched configuration, for a **stock** gem5 |
| `gem5/gem5_config_CVA6_Patch.py` | The matched configuration, for a **patched** gem5 |
| `gem5/gem5_config_CVA6_testing.py` | The calibration harness: the stock core as a table of single-knob perturbations |
| `gem5/gem5_config_CVA6_Patch_testing.py` | The same table for the patched core. This is the sweep's `DEFAULT_CONFIG` |
| `gem5/run_CVA6_testing_sweep.py` | Replays that table, sweeping its `DEFAULT_CONFIG`. See the main [README](../README.md#the-calibration-sweep) |
| the gem5 patch | Every gem5 change the patched configuration depends on, CPU and caches. Being reworked into a single file, so it is not in the tree at the moment |
| `gem5/tests/` | The gem5 side: debug trace, measured region and MinorFlow JSON per benchmark |
| `verilator/tests/` | The CVA6 side: VCD, listing, measured region and CVA6Flow JSON per benchmark |

Both `tests/` folders carry the same ten benchmarks, `atomic_fence`, `basic_test`, `branch_full_test`, `daxpy`, `fp_addmul`, `fp_divsqrt`, `full_test`, `int_div`, `matmul_small` and `store_fwd`, which is the set `DEFAULT_ALL_TESTS` names in the sweep. Each side also has a `*_create_all_jsons.py` that runs its tracer over every trace in the folder, so the JSONs can be regenerated in one go.

The measured region and the metrics table live in `<test>_report.txt` on both sides, each in its own banner-delimited section, and the tables have the same columns. That file is the quickest way to compare a benchmark: open the two and read down. Each table's title names the simulator, the program and the L1 geometry the run used, so two tables can be compared without having to remember which cache configuration produced them.

## The matched configuration

It comes in two versions. `gem5_config_CVA6.py` runs on a **stock gem5**, using only what upstream already provides, so it works against an unmodified build. `gem5_config_CVA6_Patch.py` runs on a **patched gem5** and adds the mechanisms the patch makes available. Each has a `_testing` twin carrying the calibration table.

Both target `cv64a6_imafdc_sv39_hpdcache_wb` at 50 MHz, with a 16 KiB L1I and a 32 KiB L1D. Every value is either derived from a CVA6 RTL localparam or is a gem5-side estimate where CVA6 has no clean counterpart. Two functional-unit latencies, `int_div` and `fp_divsqrt`, are representative stand-ins for iterative units that are data-dependent in the RTL and off every calibrated kernel's hot path.

Run it like any other gem5 config:

```bash
python3 run_gem5.py gem5_config_CVA6.py <test>
```

Every transcribed mechanism is on by default and each has a `--no-` switch that turns it off, so the configuration doubles as its own ablation harness. Passing all of them reproduces the stock MinorCPU behaviour the calibration started from.

| Switch | Turns off |
| --- | --- |
| `--no-port-model` | The single-ported memory adapter |
| `--no-evict-on-allocate` | Victim selection and writeback at MSHR allocation |
| `--no-victim-readout-stall` | The dirty-victim data-array occupancy |
| `--no-cva6-victim-policy` | The transcribed L1D victim policy, back to gem5 TreePLRU |
| `--no-victim-readable-until-fill` | The victim staying readable until its refill |
| `--no-fill-phase` | The L1D fill-instant correction |
| `--no-fence-flush` | A fence flushing the L1D |
| `--no-cva6-icache-policy` | The transcribed L1I policy, back to gem5 RandomRP |

## The patch

`MinorCPU_CVA6.patch` is the whole gem5 side in one file. Every behaviour it adds is a transcription of a specific RTL rule, every one is behind a parameter that defaults to the stock behaviour, and every one carries its citation in the source comments. A patched gem5 runs unpatched configurations unchanged.

```bash
git apply MinorCPU_CVA6.patch
scons build/RISCV/gem5.opt -j$(nproc)
```

The `manuel313/gem5_v25` image ships with the patch already applied.

### New parameters

| Parameter | Object | Default | What it does |
| --- | --- | --- | --- |
| `executeLSQNoStoreForwarding` | MinorCPU | `False` | Disables store-to-load forwarding from the store buffer |
| `executeLSQStoreCollisionReplayDelay` | MinorCPU | `0` | Cycles a load waits after a store collision clears |
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
| `HPDcachePLRURP` | The L1D bit-PLRU branch the build does **not** configure, kept as the lab's counterfactual |
| `CVA6IcacheRandomRP` | The L1I policy: lowest-index invalid way, else an 8-bit Galois LFSR, polynomial `0xFA` |

### What each change models, briefly

**Store forwarding.** CVA6 has no store-to-load forwarding path. Its load unit parks a load in `WAIT_PAGE_OFFSET` until the store buffer drains whenever the address collides with a pending store (`load_unit.sv`, and `page_offset_matches_o` in `store_buffer.sv`, which compares `page_offset[11:3]`, an eight-byte granule). Restarting that load costs two more cycles, since neither `IDLE` nor `WAIT_PAGE_OFFSET` asserts `data_req`.

**The memory port.** The testbench adapter (`axi2mem.sv`) is single-ported and holds one transaction end to end, testing `ar_valid` before `aw_valid` so reads always win. The model adds zero latency when uncontended, so contention appears only as admission wait.

**Eviction phase.** The HPDcache selects its victim and issues the dirty writeback at MSHR allocation, not at fill (`hpdcache_miss_handler.sv`). The readout of that victim occupies the data array for `clWords / accessWords` cycles, which is 2 for the 16-byte line, and the array is single-ported across five requesters, asserted in `hpdcache_memctrl.sv`.

**Victim policy.** The build configures `HPDCACHE_VICTIM_RANDOM`, not the PLRU branch: one global LFSR shared by the whole cache, shifting only when the random tier fires. Validated against a VCD probe at 7,406 of 7,406 selections, and it predicts the real machine's writeback counts to within one percent at 16, 32 and 64 KiB and at 2-way.

**Readable victim.** CVA6's directory update is pipelined, so an access one cycle behind an allocation still hits the line being displaced. gem5 re-tags synchronously and would lose it. Without this, a random policy costs about 514 spurious misses on daxpy.

**Fill instant.** CVA6's refill lands 7 cycles after the victim selection where the stock model fills at 5. Those 2 cycles are moved into `fill_delay` on the L1D alone and taken back out of its response latency, so the CPU-visible miss latency is unchanged and the L1I is untouched.

**Fence flush.** A fence flushes the D-cache when `DcacheFlushOnFence` is set, which it is for this build (`controller.sv`). The walk costs 2 cycles per line, one to check the directory entry and one to update it, which `hpdcache_cmo.sv` states outright. The duration is counted during the walk, so it scales with cache geometry automatically.

**Instruction cache policy.** A separate module from the HPDcache with its own two-tier policy and its own LFSR (`cva6_icache.sv` plus PULP's `lfsr.sv`), advancing only on a fill into an already full set. This one buys exactness rather than accuracy, since gem5's stock `RandomRP` is already in the same class.

### Files changed

`src/cpu/minor/` for `BaseMinorCPU.py`, `execute.cc`, `lsq.cc` and `lsq.hh`. `src/mem/` for the adapter and its `SConscript` entry. `src/mem/cache/` for `Cache.py`, `base.hh`, `base.cc`, `cache.hh`, `cache_blk.hh`, `mshr.hh` and `mshr.cc`. `src/mem/cache/tags/` for the fill-time replacement hook. `src/mem/cache/replacement_policies/` for the three policies and their registrations.

## Known limitations

Three divergences remain, each with a named mechanism rather than an open question.

**Store-buffer residency.** gem5's store buffer drains faster than CVA6's two-queue structure, so the collision stall fires on 3 loads where CVA6 stalls on 128. Its dependent chain also costs about 2 cycles more per iteration, and the two errors partly cancel, so correcting either alone makes the agreement worse.

**Front-end prediction.** gem5 mispredicts more than CVA6 on branch-heavy and dispatch-heavy code, which also inflates its instruction-cache misses through wrong-path fetches. This is the largest single error in the suite and it is a BTB and indirect-branch issue, not a cache one.

**Eviction cost accounting.** CVA6 charges 2 and 6 extra cycles when a dirty eviction is triggered by the second load or the store, against gem5's zero, while gem5's baseline window is 2 cycles longer than CVA6's. The terms have opposite signs and nearly cancel, and the residual is predictable from cache geometry alone to within a quarter of a percent.

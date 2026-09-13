# gem5_config_CVA6

The gem5 MinorCPU configuration matched to CVA6, and the patch it depends on.

## Layout

| Path                                                                | What it is                                                                                                                                                                                                                                |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gem5/configs/gem5_config_CVA6.py`                                  | The matched configuration, for a **stock** gem5                                                                                                                                                                                           |
| `gem5/configs/gem5_config_CVA6_patch.py`                            | The matched configuration, for a **patched** gem5                                                                                                                                                                                         |
| `gem5/configs/gem5_config_CVA6_testing.py`                          | The calibration harness: the stock core as a table of single-knob perturbations, `TEST 1` to `TEST 39` Beside that grid it carries `CACHE_TESTS`, `TEST 201` to `TEST 217`, cache geometry only.                                          |
| `gem5/configs/gem5_config_CVA6_patch_testing.py`                    | The same 39 entries under the same numbers, then the ones that need the patch, `TEST 40` to `TEST 95` and `TEST 99`. This is the sweep's `DEFAULT_CONFIG` It carries the same `TEST 201` to `TEST 217` cache list under the same numbers. |
| `../scripts/run_gem5_config_sweep.py`                               | Replays that table, sweeping its `DEFAULT_CONFIG`. See the main [README](../README.md#the-calibration-sweep)                                                                                                                              |
| `gem5/configs/MinorCPU_CVA6.patch`                                  | Every gem5 change the patched configuration depends on, CPU, front end and caches, in one verified file                                                                                                                                   |
| `CVA6/configs/cv64a6_imafdc_sv39_hpdcache_wb_config_testing_pkg.sv` | The same package with the cache geometry table and its `CVA6_CONFIG_SEL` selector                                                                                                                                                         |
| `../scripts/run_CVA6_config_sweep.py`                               | Runs that table on the real core, the RTL side of the cache question                                                                                                                                                                      |
| `gem5/tests/`                                                       | The gem5 tests side                                                                                                                                                                                                                       |
| `CVA6/tests/`                                                       | The CVA6 tests side                                                                                                                                                                                                                       |

`DEFAULT_ALL_TESTS` in the sweep names **sixteen** programs, and every entry whose workload is `all` runs all sixteen. Fourteen of them are the comparison suite: `atomic_fence`, `basic_test`, `branch_full_test`, `btb_pressure`, `daxpy`, `daxpy_unrolling_4`, `fetch2_probe`, `fp_addmul`, `fp_divsqrt`, `full_test`, `icache_pressure`, `int_div`, `matmul_small` and `store_fwd`.

The other two, `fp_divsqrt_probe` and `fp_divsqrt_probe2`, are **not** suite members and are left out of the comparison. They are diagnostic programs written to measure one limitation rather than to be matched: each drives the FP divider with operands chosen so the hardware's short path fires and the model's general law does not, which is what turns that divergence into a number instead of a suspicion.

They all live in [gem5/benchmarks/](gem5/benchmarks/) and [CVA6/benchmarks/](CVA6/benchmarks/).

## The matched configuration

It comes in two versions. `gem5_config_CVA6.py` runs on a **stock gem5**, using only what upstream already provides, so it works against an unmodified build. `gem5_config_CVA6_patch.py` runs on a **patched gem5** and adds the mechanisms the patch makes available. Each has a `_testing` twin carrying the calibration table.

Both target `cv64a6_imafdc_sv39_hpdcache_wb` at 50 MHz, with a 16 KiB L1I and a 32 KiB L1D. Every value is either derived from a CVA6 RTL localparam or is a gem5-side estimate where CVA6 has no clean counterpart.

Run either like any other gem5 config:

```bash
python3 run_gem5.py gem5_config_CVA6.py <test>         # stock gem5
python3 run_gem5.py gem5_config_CVA6_patch.py <test>   # patched gem5
```

In the patched version every transcribed mechanism is on by default and each has a `--no-` switch that turns it off, so it doubles as its own ablation harness. `--no-patch` is all of them at once, which reproduces the stock MinorCPU behaviour the calibration started from. It turns the mechanisms off, not the geometry: the fetch queues stay at 3 where the stock configuration uses 2. The stock configuration takes no switches, since it carries none of these mechanisms.

**The two arms differ by geometry as well as by mechanism, and the comparison should say so.** `fetch1FetchLimit` and `fetch2InputBufferSize` are both 2 in `gem5_config_CVA6.py` and both 3 in `gem5_config_CVA6_patch.py`, while the TEST grid states its deltas against a baseline of `fetch1FetchLimit 2` (rows 2, 3, 75, 76). The 3/3 value is defensible on RTL grounds, since the I-cache holds three lines in flight with a three-deep Fetch2 buffer, but it means the patched and unpatched figures are not separated by the mechanisms alone. It is not a small effect, and on this suite it is not a second-order one either.

| Switch                            | Turns off                                                                                                 |
| --------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `--no-patch`                      | Every mechanism below, at once                                                                            |
| `--no-port-model`                 | The single-ported memory adapter                                                                          |
| `--no-evict-on-allocate`          | Victim selection and writeback at MSHR allocation                                                         |
| `--no-victim-readout-stall`       | The dirty-victim data-array occupancy                                                                     |
| `--no-cva6-victim-policy`         | The transcribed L1D victim policy, back to gem5 TreePLRU                                                  |
| `--no-victim-readable-until-fill` | The victim staying readable until its refill                                                              |
| `--no-fill-phase`                 | The L1D fill-instant correction                                                                           |
| `--no-fence-flush`                | A fence flushing the L1D, both the core's signal and the cache acting on it                               |
| `--no-fence-squash`               | The rule F5 pipeline squash on a committed full fence                                                     |
| `--no-icache-hold`                | Fetch1 holding a line at the ready line, back to a refusal and a retry                                    |
| `--no-kill-on-redirect`           | Killed lines freeing their fetch slots at the redirect, back to holding them until their responses return |
| `--no-icache-structure`           | The L1I fill being readable at the fill instant and the full-MSHR retry waiting for it                    |
| `--no-window-charge`              | The accept-and-charge form of the readout window and its class extras, back to the flat fill split        |
| `--no-cva6-icache-policy`         | The transcribed L1I policy, back to gem5 RandomRP                                                         |
| `--no-cva6-direct-targets`        | Decode-computed direct targets, and with them the JALR-only tagless BTB                                   |
| `--no-ras-decay`                  | The unrecovered speculative RAS, back to gem5's repair on squash. Independent of the switches above       |
| `--no-store-forwarding-model`     | CVA6 having no store-to-load forwarding, and the replay delay with it                                     |

### The calibration table

`gem5_config_CVA6_patch_testing.py` is the campaign in one file. `TEST 1` is the frozen CPU-side baseline, `TEST 99` is the full production configuration, and every other entry is a single-knob perturbation.

The table is ordered by what an entry needs to run, then by the part of the machine it touches, front of the pipeline first. `gem5_config_CVA6_testing.py` carries the first tier, `TEST 1` to `TEST 39`, under the same numbers, so a row means the same thing in both files.

**TESTS 1 to 39 run on a stock gem5.**

| #   | What it changes                        | Workload                                  |
| --- | -------------------------------------- | ----------------------------------------- |
| 1   | adopted baseline                       | all                                       |
|     | **fetch geometry**                     |                                           |
| 2   | fetch1FetchLimit 2 -> 1                | matmul_small                              |
| 3   | fetch1FetchLimit 2 -> 3                | matmul_small                              |
| 4   | fetch 8B/8B, fetch2 buffer 8           | all                                       |
| 5   | fetch2InputBufferSize 2 -> 4           | fetch2_probe                              |
|     | **instruction cache**                  |                                           |
| 6   | L1I random -> LRU                      | full_test                                 |
| 7   | L1I response_latency 0 -> 1            | daxpy                                     |
| 8   | L1I response_latency 0 -> 2            | daxpy                                     |
| 9   | L1I 4KiB                               | daxpy                                     |
|     | **decode buffer**                      |                                           |
| 10  | decodeInputBufferSize 1 -> 4           | daxpy, full_test                          |
| 11  | decodeInputBufferSize 1 -> 8           | daxpy, full_test                          |
|     | **branch prediction**                  |                                           |
| 12  | Morillas 2025 predictor sizing         | branch_full_test, btb_pressure, full_test |
| 13  | BTB 32 -> 512                          | branch_full_test, btb_pressure, full_test |
| 14  | BTB 32 -> 4096                         | branch_full_test, btb_pressure, full_test |
|     | **LSQ queue geometry**                 |                                           |
| 15  | requests queue 2 -> 4                  | store_fwd                                 |
| 16  | requests queue 2 -> 8                  | store_fwd                                 |
| 17  | store buffer 4 -> 8                    | store_fwd                                 |
| 18  | requests 8, store buffer 8             | store_fwd                                 |
|     | **functional units**                   |                                           |
| 19  | int_mul opLat 2 -> 1                   | daxpy, full_test                          |
| 20  | fp_divsqrt legacy                      | fp_divsqrt                                |
| 21  | serdiv base 1 -> 0                     | int_div                                   |
| 22  | fp_addmul without the double mask      | fp_addmul                                 |
| 23  | FP mem classes back on vec_mem_fast    | daxpy                                     |
| 24  | atomic occupancy entries removed       | atomic_fence                              |
|     | **data cache**                         |                                           |
| 25  | L1D PLRU -> true LRU                   | full_test                                 |
| 26  | response_latency 4 -> 5                | daxpy                                     |
| 27  | response_latency 4 -> 6                | daxpy                                     |
| 28  | response_latency 4 -> 3                | daxpy                                     |
| 29  | L1D 16KiB                              | daxpy                                     |
| 30  | L1D 64KiB                              | daxpy                                     |
| 31  | L1D assoc 8 -> 2                       | daxpy                                     |
| 32  | L1D mshrs 8 -> 1                       | daxpy                                     |
| 33  | L1D write_buffers 8 -> 2               | daxpy                                     |
| 34  | L1D hit lat +1                         | daxpy                                     |
|     | **memory system**                      |                                           |
| 35  | membus width 8 -> 16                   | daxpy                                     |
| 36  | membus width 8 -> 4                    | daxpy                                     |
| 37  | memory bandwidth 12.8GiB/s -> 0.4GiB/s | daxpy                                     |
| 38  | mem latency 0 -> 60ns                  | daxpy                                     |
|     | **core-wide**                          |                                           |
| 39  | threadPolicy -> RoundRobin             | daxpy                                     |

**TESTS 40 to 95 and TEST 99 need the patch.**

| #   | What it changes                                     | Workload     |
| --- | --------------------------------------------------- | ------------ |
|     | **store-to-load forwarding**                        |              |
| 40  | store forwarding re-enabled                         | store_fwd    |
| 41  | replay delay 2 -> 0                                 | store_fwd    |
|     | **data-cache stack**                                |              |
| 42  | port model alone                                    | daxpy        |
| 43  | + evict-on-allocate                                 | daxpy        |
| 44  | + victim readout stall                              | daxpy        |
| 45  | + HPDcache bit-PLRU                                 | daxpy        |
| 46  | + HPDcache random                                   | daxpy        |
| 47  | + victim readable until fill                        | daxpy        |
| 48  | + fill phase, the production stack                  | daxpy        |
|     | **production stack, ablations and geometry**        |              |
| 49  | production stack, L1D 16 KiB                        | daxpy        |
| 50  | production stack, L1D 64 KiB                        | daxpy        |
| 51  | production minus the port model                     | daxpy        |
| 52  | production minus the readout stall                  | daxpy        |
| 53  | production with bit-PLRU instead                    | daxpy        |
| 54  | production minus the fill phase                     | daxpy        |
| 55  | fill delay without the random policy                | daxpy        |
|     | **fence and instruction-cache policy**              |              |
| 56  | + fence flushes the L1D                             | atomic_fence |
| 57  | + transcribed L1I policy                            | all          |
|     | **front end, direct targets and the BTB**           |              |
| 58  | production minus direct targets                     | btb_pressure |
| 59  | same-cycle fetch2 redirect                          | all          |
| 60  | BTB as the JALR store                               | all          |
| 61  | tagless BTB                                         | all          |
|     | **fill timing**                                     |              |
| 62  | dirty-only fill delay                               | all          |
|     | **refill window**                                   |              |
| 63  | refill window + clean fill                          | all          |
| 64  | refill window alone, isolation                      | all          |
| 65  | fence pipeline squash, rule F5                      | all          |
| 66  | RAS no-recovery                                     | all          |
| 67  | store-class readout extra, isolation                | all          |
| 68  | the tier 0 plus 2 pair                              | all          |
| 69  | all candidates together                             | all          |
| 70  | pair + class x and z                                | all          |
|     | **accept-and-charge**                               |              |
| 71  | accept-and-charge, dirty-only fill                  | all          |
| 72  | accept-and-charge with the class law                | all          |
| 73  | accept-and-charge, the full pair                    | all          |
| 74  | accept-and-charge refill window                     | all          |
|     | **the fetch supply beat, basic_test's owner**       |              |
| 75  | fetch1FetchLimit 2 -> 4                             | all          |
| 76  | fetch1FetchLimit 4, fetch2 buffer 2 -> 1            | all          |
| 77  | fetch limit 4, fetch2 buffer 2 -> 4                 | all          |
|     | **the per-line cadence, the beat's real owner**     |              |
| 78  | fetch2CycleInput False -> True                      | all          |
| 79  | fetch2CycleInput True, fetch & buffer 2             | all          |
|     | **the class law without the fill-0 phase artefact** |              |
| 80  | flat fill, accept-and-charge                        | all          |
| 81  | TEST 72 stack on the 79 frontend                    | all          |
| 82  | adopted stack plus the serdiv turnaround            | all          |
| 83  | adopted stack plus the divsqrt format law           | all          |
| 84  | adopted stack plus all                              | all          |
|     | **the final-check probes, on the adopted stack**    |              |
| 85  | L1I mshrs 2 -> 1, the I-side retry tax              | all          |
| 86  | fetch limit 3, fetch2 buffer 3                      | all          |
| 87  | fetch limit 4, fetch2 buffer 3                      | all          |
| 88  | L1I reopen at ready                                 | all          |
|     | **the structural I-side**                           |              |
| 89  | mshrs 1, reopen at ready, fetch1 holds              | all          |
| 90  | ablation of 89 without reopen at ready              | all          |
| 91  | the 89 with fetch limit 3 and buffer 3              | all          |
| 92  | the 90 with fetch limit 3 and buffer 3              | all          |
| 93  | the 92 with the fill readable at the fill           | all          |
| 94  | the 93 with kill on redirect                        | all          |
| 95  | the whole structural I-side, TEST 99's stack        | all          |
|     | **full patch baseline**                             |              |
| 99  | full production                                     | all          |

### The cache geometry list

`CACHE_TESTS` is a second table in both harnesses, kept apart from the grid above. Nothing in it touches the CPU: it varies only L1I and L1D size and associativity, and each entry runs over more of the benchmark set than a single-knob calibration row does. The ids start at 201, so a number says which table it came from, and a plain sweep leaves them out.

```bash
python3 scripts/run_gem5_config_sweep.py --configs cache        # the list below
python3 scripts/run_gem5_config_sweep.py --configs grid         # the table above
python3 scripts/run_gem5_config_sweep.py --configs all          # both
python3 scripts/run_gem5_config_sweep.py --configs 208-213      # part of one
```

Both harnesses carry the same seventeen entries under the same numbers, so a cut can be measured on a stock gem5 and on the patched build and the two compared.

| #   | What it changes                 | Workload                                     |
| --- | ------------------------------- | -------------------------------------------- |
| 201 | L1I 4KiB                        | icache_pressure, matmul_small, full_test     |
| 202 | L1I 8KiB                        | icache_pressure, full_test                   |
| 203 | L1I 32KiB                       | icache_pressure, full_test                   |
| 204 | L1I 64KiB                       | icache_pressure, matmul_small                |
| 205 | L1I direct mapped, assoc 4 -> 1 | icache_pressure, full_test, branch_full_test |
| 206 | L1I assoc 4 -> 2                | icache_pressure, full_test                   |
| 207 | L1I assoc 4 -> 8                | icache_pressure, full_test                   |
| 208 | L1D 8KiB                        | matmul_small, daxpy, store_fwd               |
| 209 | L1D 16KiB                       | matmul_small, store_fwd                      |
| 210 | L1D 64KiB                       | matmul_small, daxpy                          |
| 211 | L1D direct mapped, assoc 8 -> 1 | matmul_small, store_fwd, atomic_fence        |
| 212 | L1D assoc 8 -> 2                | matmul_small, daxpy, store_fwd               |
| 213 | L1D assoc 8 -> 4                | matmul_small, store_fwd                      |
| 214 | L1I 4KiB and L1D 8KiB           | icache_pressure, matmul_small                |
| 215 | L1I 64KiB and L1D 64KiB         | icache_pressure, matmul_small                |
| 216 | both direct mapped              | icache_pressure, matmul_small, store_fwd     |
| 217 | L1I 32KiB and L1D 64KiB         | icache_pressure, matmul_small, daxpy         |

### The same list on the real core

`CVA6/configs/cv64a6_imafdc_sv39_hpdcache_wb_config_testing_pkg.sv` is the RTL counterpart. It is the production configuration package with a table of the same geometries and one selector, `CVA6_CONFIG_SEL`, and its four cache fields read the selected values. The cuts are in the same order as the gem5 list, so **a CFG id plus 199 is the gem5 TEST id**: `CFG_ICACHE_4K` is 2 here and `TEST 201` there.

```bash
python3 scripts/run_CVA6_config_sweep.py --list          # the eighteen, and their workloads
python3 scripts/run_CVA6_config_sweep.py --configs 2-8   # the instruction cache cuts
```

That sweep installs the package over `core/include/`, rebuilds the model, runs each entry's workloads and restores the live package afterwards, on success, on failure and on interrupt. One caution: not every corner has to elaborate. A direct-mapped HPDcache, for instance, may be refused by the RTL, and the sweep reports that configuration as failed and carries on rather than stopping.

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

[`run_gem5.py`](../viewers/MinorFlow/scripts/run_gem5.py) takes `--variant stock`, the default, or `--variant patch`, which picks the binary and the overhead profile together and names the build in the table header. `--build` runs any other build directory without changing the profile.

Since every added parameter defaults off, the patched binary running `gem5_config_CVA6.py` should reproduce the stock binary exactly. Diffing the two `stats.txt` files is the test of that, and any line that differs is a mechanism leaking when it should be inert. `gem5_config_CVA6_patch.py --no-patch` is the same test from the other direction, holding the configuration fixed and turning the mechanisms off.

### TO DO

- **No entry isolates the direct-target knob against today's stack.** `TEST 58`, "production minus direct targets", was written before the RAS model existed, so its era's production stack had no unrecovered RAS and its empty `bp_overrides` was right then. `--no-cva6-direct-targets` no longer implies `--no-ras-decay`, so measuring that switch against the current stack needs a row carrying `rasNoRecovery` without `directTargetsFromDecode`. Nothing is wrong in the table as it stands, it just no longer covers that one ablation.
- **Measure the assembly overhead profile on a patched build.** `OVERHEAD_SUITES["config"]["patch"]` in [run_gem5.py](../viewers/MinorFlow/scripts/run_gem5.py) has identical numbers for C and assembly, on all eight entries. The stock profile differs between the two languages on four of them, and the two paths link different startup code, so one measurement was most likely copied rather than two taken. It moves the NET figures on every assembly benchmark if it is wrong.

### New parameters

| Parameter                             | Object          | Default | What it does                                                                                                                                                                                                                                                                                        |
| ------------------------------------- | --------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `executeLSQNoStoreForwarding`         | MinorCPU        | `False` | Disables store-to-load forwarding from the store buffer                                                                                                                                                                                                                                             |
| `executeLSQStoreCollisionReplayDelay` | MinorCPU        | `0`     | Cycles a load waits after a store collision clears                                                                                                                                                                                                                                                  |
| `executeLSQFenceSignalsDcache`        | MinorCPU        | `False` | A fence signals the data cache, modelling the core's flush wire                                                                                                                                                                                                                                     |
| `directTargetsFromDecode`             | BranchPredictor | `False` | Taken direct control takes its target from the decoded instruction and never installs in the BTB                                                                                                                                                                                                    |
| `executeFenceSquashesPipeline`        | MinorCPU        | `False` | A committed full fence squashes the pipeline and restarts fetch at the next PC                                                                                                                                                                                                                      |
| `rasNoRecovery`                       | BranchPredictor | `False` | Speculative RAS pushes and pops stand uncorrected on a squash, as CVA6's scan-driven stack                                                                                                                                                                                                          |
| `evict_on_allocate`                   | Cache           | `False` | Selects the victim and issues its writeback at MSHR allocation                                                                                                                                                                                                                                      |
| `victim_readout_stall`                | Cache           | `False` | Charges the dirty-victim data-array readout, `blkSize / 8` cycles                                                                                                                                                                                                                                   |
| `victim_readout_store_extra`          | Cache           | `0`     | Extra readout-window cycles when a store triggered the eviction                                                                                                                                                                                                                                     |
| `victim_readout_first_load_extra`     | Cache           | `0`     | Extra readout-window cycles when a lone load triggered the eviction                                                                                                                                                                                                                                 |
| `refill_window_blocks`                | Cache           | `False` | Blocks the CPU side for `blkSize / 8` cycles while a refill writes the data array. **Not enabled in either production configuration**: it is set only in `gem5_config_CVA6_patch_testing.py`, where four entries use it, and `window_accept_and_charge` carries the delivered form of the same cost |
| `window_accept_and_charge`            | Cache           | `False` | The accept-and-charge form of both windows: the port never blocks, a request inside a window takes the overlap as latency, the miss that opens a readout window takes it on its own fill                                                                                                            |
| `victim_readable_until_fill`          | Cache           | `False` | Keeps the victim answering hits until its refill lands                                                                                                                                                                                                                                              |
| `fill_delay`                          | Cache           | `0`     | Extra cycles from response arrival to fill, without touching shared memory latency                                                                                                                                                                                                                  |
| `fence_flushes_dcache`                | Cache           | `False` | A fence writes back every dirty line and holds the cache 2 cycles per line                                                                                                                                                                                                                          |
| `fetch1WaitsForIcache`                | MinorCPU        | `False` | Fetch1 holds a line at the ready line instead of paying a refusal and a retry, since `cva6_icache.sv` asserts `dreq_o.ready` only in IDLE and READ                                                                                                                                                  |
| `fetch1KillsOnRedirect`               | MinorCPU        | `False` | Every in-flight line frees its fetch slot at the redirect, the frontend side of `kill_s1` and `kill_s2`                                                                                                                                                                                             |
| `fill_ready_at_fill`                  | Cache           | `False` | A block is readable at the fill instant, since the icache writes the line in the fill-ack cycle, so the bus terms are not charged twice                                                                                                                                                             |
| `reopen_at_ready`                     | Cache           | `False` | Defers the full-MSHR retry until that block is readable                                                                                                                                                                                                                                             |

### New SimObjects

| Object               | What it is                                                                                                                          |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `Axi2MemPort`        | The CVA6 testbench memory adapter: one transaction at a time, fixed read priority, `1 + N` cycle occupancy for `N` eight-byte beats |
| `HPDcacheRandomRP`   | The L1D victim policy the build configures: four tiers, with an 8-bit Galois LFSR, polynomial `0xE1`                                |
| `HPDcachePLRURP`     | The L1D bit-PLRU branch the build does **not** configure                                                                            |
| `CVA6IcacheRandomRP` | The L1I policy: lowest-index invalid way, else an 8-bit Galois LFSR, polynomial `0xFA`                                              |

### New statistics

The patch leaves every stock counter untouched and adds its own beside them.

| Statistic                                                        | Object           | What it counts                                                                                     |
| ---------------------------------------------------------------- | ---------------- | -------------------------------------------------------------------------------------------------- |
| `preemptionBlockedCycles`                                        | Cache            | Cycles blocked by a CVA6 preemption cause: victim readout, fence flush or refill window            |
| `cva6ComparableDemandAccesses`                                   | Cache            | Demand accesses plus the preemption and window cycles below, the count the HPDcache PMU reports    |
| `earlyReservations`                                              | Cache            | Victims reserved at miss time by evict-on-allocate                                                 |
| `reservationFallbacks`                                           | Cache            | Misses that fell back to stock fill-time allocation                                                |
| `inPlaceReservations`                                            | Cache            | Reservations that kept the victim readable                                                         |
| `reservationRedirties`                                           | Cache            | In-place victims dirtied again before their refill landed, so written back twice                   |
| `fenceFlushes`                                                   | Cache            | Full flushes a fence triggered                                                                     |
| `fenceFlushWritebacks`                                           | Cache            | Dirty lines those flushes wrote back                                                               |
| `windowTriggerCharges`, `windowTriggerCycles`                    | Cache            | Misses charged their own readout window under accept-and-charge, and the cycles                    |
| `windowOverlapCharges`, `windowOverlapCycles`                    | Cache            | Requests charged a window overlap, and the cycles                                                  |
| `reservationUpgradeFallbacks`                                    | Cache            | In-place reservations released at fill time because an upgrade on the victim was still outstanding |
| `unusedTier`, `randomTier`, `cleanTier`, `dirtyTier`, `noVictim` | HPDcacheRandomRP | Which tier of the victim policy supplied each selection                                            |
| `readsAdmitted`, `writesAdmitted`                                | Axi2MemPort      | Transactions admitted to the single port, by class                                                 |
| `passThrough`                                                    | Axi2MemPort      | Packets with no AXI equivalent, forwarded without occupancy                                        |
| `readWaitCycles`, `writeWaitCycles`                              | Axi2MemPort      | Admission wait histograms, by class                                                                |

The metrics table uses three of these: `preemptionBlockedCycles`, `windowTriggerCycles` and `windowOverlapCycles`. `run_gem5.py` adds them to the cache-access rows and prints the result as a third column, `NET (CVA6)`, next to `NET`, so a gem5 table reads against a CVA6 one row for row.

The three count disjoint cycles, so summing them is right whichever form is configured, and the sum is what `cva6ComparableDemandAccesses` reports. Accept-and-charge replaces the **readout and refill-window** blocks specifically, causes 3 and 5. The other blocking causes, no-MSHRs, no-write-buffers, no-targets and the fence flush, still block under either form, so a single run carries both kinds.

### What each change models, briefly

**Instruction-side miss acceptance.** The L1I holds two MSHRs, a stock parameter. With one, the line Fetch1 requests during a miss is refused and retried off the clock edge, a tax CVA6 never pays: its icache takes no request during a miss and the frontend presents the next line the cycle the first returns (`cva6_icache.sv` MISS state). With two, the request coalesces or queues at the memory port, and miss chains land at CVA6's one fill per five cycles. Two was a stand-in for structure the model lacked, replaced below. The harness reads `overallMshrMisses` on both caches, the refill count the PMU counts.

**The structural instruction side.** Four parameters replace that MSHR count with the shape the RTL has, all four on by default. `fetch1WaitsForIcache` holds a line at the ready line instead of paying a refusal and a retry, since `cva6_icache.sv` asserts `dreq_o.ready` only in IDLE and READ. `fetch1KillsOnRedirect` frees every in-flight line's fetch slot at the redirect, the frontend side of `kill_s1` and `kill_s2` (327 to 348). `fill_ready_at_fill` makes a block readable at the fill instant, since the icache writes the line in the fill-ack cycle (316 to 325), so the bus terms are not charged twice. `reopen_at_ready` defers the full-MSHR retry until that block is readable. The L1I then runs at one MSHR, the hardware's number, and `TESTS 89` to `95` separate the four.

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

Six divergences remain, each with a named mechanism.

> **The prices below are not current.** Each was measured against the results table that used to head this file, which the shipped configuration does not reproduce, so every figure quoted as an error against the hardware has been removed from this section and the remaining cycle counts need re-reading. They return with the table.

**The FP divider's short path.** The hardware divides and takes square roots of small-mantissa operands in 10 cycles where full-mantissa operands take 15 and 22, the general law the model carries. The trigger is the mantissa length of both divide operands and of the radicand for the root, and a seven-bit radicand still runs short, by 5 and 4. Two probes measured it across fifteen chain blocks, and it is absent from `control_mvp.sv` and `preprocess_mvp.sv` at cvfpu revision 272e6e5, the one the hardware runs, so it is not transcribed.

**The fetch-cadence residue, a priced queue depth.** `basic_test`'s uncompressed sections recovered about 38 of the 49 cycles per pass the cadence fix predicted. The remaining 11 are a second beat: the fetch round trip is 3 cycles, and with `fetch1FetchLimit` and `fetch2InputBufferSize` both at 2 the requests go out two lines every three cycles. Depth 3 was tested and declined on the stack of the day, `basic_test` recovering cycles while `btb_pressure` paid more and the run-ahead gauge moved past the hardware. The structural I-side reopened it, since holding at the ready line and killing on a redirect both bound the run-ahead that reading paid for, and the adopted depth is now 3. `TEST 86` and `TEST 91` separate the depth from the mechanisms, and this residue needs re-reading against them.

**daxpy's miss count under the fill split.** With the readout window charging the trigger's own fill instead of a flat delay on every fill, the relative phase of the three streams inside a set changes and the transcribed random policy names a different way on its third visit to each set: 6,595 misses against the hardware's 6,147, worth 379 cycles because Minor's single outstanding miss overlaps most of each with the FP chain. The tier probe shows the same tiers firing at the same rates, so the difference is the LFSR phase.

**Miss-level parallelism at one.** Minor serialises demand misses where the HPDcache overlaps a second. Its visible cost on this suite is gone with the fill split, but the structure stands and the port model's calibration absorbs it.

**Instruction-side pair timing under two MSHRs.** Isolated queued miss pairs land about two cycles faster than the hardware, the second fill arriving at the port's occupancy behind the first rather than CVA6's full five-cycle re-present. Chains match and pairs undershoot. This entry is written for the two-MSHR stack and the shipped configuration runs at one, so it needs re-reading against the structural I-side as well as against the new table. The residue is the port model's occupancy against the icache's re-present interval, documented rather than tuned.

**Instruction-side access counts.** CVA6's PMU counts every fetch it presents, including the wrong-path lines its deeper run-ahead issues and kills, which gem5 never issues. The cadence fix widens that gap slightly, since faster instruction flow resolves branches sooner and fetches fewer wrong-path lines. I-miss counts match on every row. I-access counts are a behavioural difference, reported rather than compared.

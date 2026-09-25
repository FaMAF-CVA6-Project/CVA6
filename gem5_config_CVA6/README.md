# gem5_config_CVA6

The gem5 MinorCPU configuration matched to CVA6, and the patch it depends on.

## Layout

| Path                                                                | What it is                                                                                                                                                                                                                                                                                                                           |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `gem5/configs/gem5_config_CVA6.py`                                  | The matched configuration, for a **stock** gem5                                                                                                                                                                                                                                                                                      |
| `gem5/configs/gem5_config_CVA6_patch.py`                            | The matched configuration, for a **patched** gem5                                                                                                                                                                                                                                                                                    |
| `gem5/configs/gem5_config_CVA6_testing.py`                          | The calibration harness: the stock core as a table of perturbations, most of them single-knob, `TEST 1` to `TEST 39`. Beside that grid it carries `CACHE_TESTS`, `TEST 201` to `TEST 217`, cache geometry only, laid over `TEST 1`.                                                                                                  |
| `gem5/configs/gem5_config_CVA6_patch_testing.py`                    | The same 39 entries on the same stock baseline, then full production as `TEST 40` and the entries that set patch parameters, `TEST 41` to `TEST 101`, all laid over `PATCH_BASE`. This is the sweep's `DEFAULT_CONFIG`. It carries the same `TEST 201` to `TEST 217` cache list under the same numbers, laid over `TEST 40` instead. |
| `../scripts/run_gem5_config_sweep.py`                               | Replays that table, sweeping its `DEFAULT_CONFIG`. See the main [README](../README.md#the-calibration-sweep)                                                                                                                                                                                                                         |
| `gem5/configs/MinorCPU_CVA6.patch`                                  | Every gem5 change the patched configuration depends on, CPU, front end, memory port and caches, in one verified file                                                                                                                                                                                                                 |
| `CVA6/configs/cv64a6_imafdc_sv39_hpdcache_wb_config_testing_pkg.sv` | The production `cv64a6_imafdc_sv39_hpdcache_wb` configuration package with a cache geometry table and its `CVA6_CONFIG_SEL` selector                                                                                                                                                                                                 |
| `../scripts/run_CVA6_config_sweep.py`                               | Runs that table on the real core, the RTL side of the cache question                                                                                                                                                                                                                                                                 |
| `gem5/benchmarks/`                                                  | The calibration programs, gem5 side, measured between `m5ops` markers                                                                                                                                                                                                                                                                |
| `CVA6/benchmarks/`                                                  | The same programs, CVA6 side, measured between PMU counter snapshots                                                                                                                                                                                                                                                                 |

`DEFAULT_ALL_TESTS` in the sweep names **seventeen** programs, and every entry whose workload is `all` runs all seventeen. Fourteen of them are the comparison suite: `atomic_fence`, `basic_test`, `branch_full_test`, `btb_pressure`, `daxpy`, `daxpy_unrolling_4`, `fetch2_probe`, `fp_addmul`, `fp_divsqrt`, `full_test`, `icache_pressure`, `int_div`, `matmul_small` and `store_fwd`.

The other three, `fp_divsqrt_probe`, `fp_divsqrt_probe2` and `fp_divsqrt_probe3`, are **not** suite members and are left out of the comparison. They are diagnostic programs written to measure one limitation rather than to be matched: beside full-mantissa control blocks, each drives the FP divider with operands chosen so the hardware's short path fires and the model's general law does not, which is what turns that divergence into a number instead of a suspicion. The third walks every branch of the C910 divider law, block by block, and is what validated it on the RTL.

They all live in [gem5/benchmarks/](gem5/benchmarks/) and [CVA6/benchmarks/](CVA6/benchmarks/).

## The matched configuration

It comes in two versions. `gem5_config_CVA6.py` runs on a **stock gem5**, using only what upstream already provides, so it works against an unmodified build. `gem5_config_CVA6_patch.py` runs on a **patched gem5** and adds the mechanisms the patch makes available. Each has a `_testing` twin carrying the calibration table.

Both target `cv64a6_imafdc_sv39_hpdcache_wb` at 50 MHz, with a 16 KiB L1I and a 32 KiB L1D. Every value is either derived from a CVA6 RTL localparam or is a gem5-side estimate where CVA6 has no clean counterpart.

Run either like any other gem5 config:

```bash
python3 run_gem5.py gem5_config_CVA6.py <test>                        # stock gem5
python3 run_gem5.py gem5_config_CVA6_patch.py <test> --variant patch  # patched gem5
```

In the patched version every transcribed mechanism is on by default and each has a `--no-` switch that turns it off, so it doubles as its own ablation harness. `--no-patch` is all of them at once, which reproduces the stock MinorCPU behaviour the calibration started from. It turns the mechanisms off, not the geometry: the fetch queues stay at 3 where the stock configuration uses 2. It also still needs the patched build, for its imports. The stock configuration has none of the `--no-` switches, only the `--fetch-limit`, `--fetch2-buffer` and `--ddr3` options both versions share.

**The two arms differ by geometry as well as by mechanism, and the comparison should say so.** `fetch1FetchLimit` and `fetch2InputBufferSize` are both 2 in `gem5_config_CVA6.py` and both 3 in `gem5_config_CVA6_patch.py`, while the TEST grid states its deltas against a baseline of 2 for both (rows 2, 3, 5, 76, 77, 78). The 3/3 value is defensible on RTL grounds, since the I-cache holds three lines in flight with a three-deep Fetch2 buffer, but it means the patched and unpatched figures are not separated by the mechanisms alone.

| Switch                            | Turns off                                                                                                 |
| --------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `--no-patch`                      | Every mechanism below, at once                                                                            |
| `--no-port-model`                 | The single-ported memory adapter                                                                          |
| `--no-evict-on-allocate`          | Victim selection and writeback at MSHR allocation                                                         |
| `--no-victim-readout-stall`       | The dirty-victim data-array occupancy                                                                     |
| `--no-cva6-victim-policy`         | The transcribed L1D victim policy, back to gem5 RandomRP                                                  |
| `--no-victim-readable-until-fill` | The victim staying readable until its refill                                                              |
| `--no-fill-phase`                 | The L1D fill-instant correction                                                                           |
| `--no-fence-flush`                | A fence flushing the L1D, both the core's signal and the cache acting on it                               |
| `--no-fence-squash`               | The rule F5 pipeline squash on a committed full fence                                                     |
| `--no-icache-hold`                | Fetch1 holding a line at the ready line, back to a refusal and a retry                                    |
| `--no-kill-on-redirect`           | Killed lines freeing their fetch slots at the redirect, back to holding them until their responses return |
| `--no-drop-killed-lines`          | Killed lines leaving Fetch1 at once, back to spending a cycle on each                                     |
| `--no-icache-structure`           | The L1I fill being readable without the bus delays, and the full-MSHR retry waiting for it                |
| `--no-window-charge`              | The accept-and-charge form of the readout window and its class extras, back to the flat fill split        |
| `--no-cva6-icache-policy`         | The transcribed L1I policy, back to gem5 RandomRP                                                         |
| `--no-cva6-direct-targets`        | Decode-computed direct targets, and with them the dropped indirect predictor and the tagless BTB          |
| `--no-fill-at-response`           | The L1D fill held to the core-response cycle, back to filling `response_latency` cycles before it         |
| `--no-c910-divider`               | The C910 divider law on the operands, back to a flat 15 and 22 cycles                                     |
| `--no-divider-queue`              | The FP divider's input register and out-of-order writeback, back to stalling issue behind it              |
| `--no-ras-decay`                  | The unrecovered speculative RAS, back to gem5's repair on squash. Independent of the switches above       |
| `--no-store-forwarding-model`     | CVA6 having no store-to-load forwarding, and the replay delay with it                                     |

Two switches need others: `--no-victim-readout-stall` needs `--no-window-charge`, and `--no-evict-on-allocate` needs `--no-victim-readout-stall` and `--no-victim-readable-until-fill`, so `--no-window-charge` as well. Without them the configuration stops with an error.

One switch adds rather than removes. `--l1d-plru` gives the L1D gem5's `TreePLRURP` in place of the transcribed victim policy, a counterfactual: the HPDcache's PLRU branch is not elaborated in `cv64a6_imafdc_sv39_hpdcache_wb`, and the harness measures the transcribed `HPDcachePLRURP` instead.

### The calibration table

`gem5_config_CVA6_patch_testing.py` is the campaign in one file. `TEST 1` is the frozen CPU-side baseline, which is `gem5_config_CVA6.py` parameter for parameter, `TEST 40` is the full production configuration, `gem5_config_CVA6_patch.py` parameter for parameter, and every other entry is a perturbation, most of them single-knob. Eight entries reduce to another entry's configuration and are labelled duplicates in the table, the grid and their names: 55, 59, 66, 79, 80, 82, 83 and 85.

Both harnesses also carry `USE_MORILLAS`. Set to `True`, it ignores `TEST` and builds the configuration of Pau Morillas's 2025 bachelor's thesis at UPC, _Open-source RISC-V in-order processor model for a hardware event-driven simulator_, transcribed from its tables: its CPU and functional units, each unit's latency two cycles longer for the two stages CVA6 has over MinorCPU, its caches with gem5's default 64-byte line and crossbar latencies, and `SingleChannelDDR3_1600`. That work matched gem5 to a CVA6 on a Genesys 2 FPGA board with DDR3 memory, not to this testbench, so it is a point of reference rather than a configuration to tune.

The table is ordered by what an entry needs to run, then by the part of the machine it touches. `gem5_config_CVA6_testing.py` carries the first tier, `TEST 1` to `TEST 39`, under the same numbers, with the same overrides and on the same baseline, so a row measures the same machine in both files, the patched build running with every switch off. From `TEST 40` on, every entry is laid over `PATCH_BASE`, the patch parameters the campaign adopted before it varied anything else: `executeLSQNoStoreForwarding`, `executeLSQStoreCollisionReplayDelay 2`, `executeLSQFenceSignalsDcache`, `executeFenceSquashesPipeline` and two L1I MSHRs. An entry's own overrides win, so an ablation sets the value it takes away.

**TESTS 1 to 39 set no patch parameter, and run the same in both harnesses.**

| #   | What it changes                          | Workload                                  |
| --- | ---------------------------------------- | ----------------------------------------- |
| 1   | adopted baseline                         | all                                       |
|     | **fetch geometry**                       |                                           |
| 2   | fetch1FetchLimit 2 -> 1                  | matmul_small                              |
| 3   | fetch1FetchLimit 2 -> 3                  | matmul_small                              |
| 4   | fetch lines 8 bytes, fetch2 buffer 8     | all                                       |
| 5   | fetch2InputBufferSize 2 -> 4             | fetch2_probe                              |
|     | **instruction cache**                    |                                           |
| 6   | L1I random -> LRU                        | full_test                                 |
| 7   | L1I response_latency 0 -> 1              | daxpy                                     |
| 8   | L1I response_latency 0 -> 2              | daxpy                                     |
| 9   | L1I 4 KiB                                | daxpy                                     |
|     | **decode buffer**                        |                                           |
| 10  | decodeInputBufferSize 1 -> 4             | daxpy, full_test                          |
| 11  | decodeInputBufferSize 1 -> 8             | daxpy, full_test                          |
|     | **branch prediction**                    |                                           |
| 12  | Morillas 2025 predictor sizing           | branch_full_test, btb_pressure, full_test |
| 13  | BTB 32 -> 512                            | branch_full_test, btb_pressure, full_test |
| 14  | BTB 32 -> 4096                           | branch_full_test, btb_pressure, full_test |
|     | **LSQ queue geometry**                   |                                           |
| 15  | requests queue 2 -> 4                    | store_fwd                                 |
| 16  | requests queue 2 -> 8                    | store_fwd                                 |
| 17  | store buffer 4 -> 8                      | store_fwd                                 |
| 18  | requests 8, store buffer 8               | store_fwd                                 |
|     | **functional units**                     |                                           |
| 19  | int_mul opLat 2 -> 1                     | daxpy, full_test                          |
| 20  | fp_divsqrt legacy                        | fp_divsqrt                                |
| 21  | serdiv base 1 -> 0                       | int_div                                   |
| 22  | fp_addmul without the double mask        | fp_addmul                                 |
| 23  | FP mem classes back on vec_mem_fast      | daxpy                                     |
| 24  | LR/SC, AMO and fence occupancy removed   | atomic_fence                              |
|     | **data cache**                           |                                           |
| 25  | L1D random -> LRU                        | full_test                                 |
| 26  | response_latency 4 -> 5                  | daxpy                                     |
| 27  | response_latency 4 -> 6                  | daxpy                                     |
| 28  | response_latency 4 -> 3                  | daxpy                                     |
| 29  | L1D 16 KiB                               | daxpy                                     |
| 30  | L1D 64 KiB                               | daxpy                                     |
| 31  | L1D assoc 8 -> 2                         | daxpy                                     |
| 32  | L1D mshrs 8 -> 1                         | daxpy                                     |
| 33  | L1D write_buffers 8 -> 2                 | daxpy                                     |
| 34  | L1D hit lat +1                           | daxpy                                     |
|     | **memory system**                        |                                           |
| 35  | membus width 8 -> 16                     | daxpy                                     |
| 36  | membus width 8 -> 4                      | daxpy                                     |
| 37  | memory bandwidth 12.8 GiB/s -> 0.4 GiB/s | daxpy                                     |
| 38  | mem latency 0 -> 60 ns                   | daxpy                                     |
|     | **core-wide**                            |                                           |
| 39  | threadPolicy -> RoundRobin               | daxpy                                     |

**From `TEST 40` on, every entry is laid over `PATCH_BASE`, and `TEST 40` is full production.**

| #   | What it changes                                     | Workload     |
| --- | --------------------------------------------------- | ------------ |
|     | **full production**                                 |              |
| 40  | full production                                     | all          |
|     | **store-to-load forwarding**                        |              |
| 41  | store forwarding re-enabled                         | store_fwd    |
| 42  | replay delay 2 -> 0                                 | store_fwd    |
|     | **data-cache stack**                                |              |
| 43  | port model alone                                    | daxpy        |
| 44  | + evict-on-allocate                                 | daxpy        |
| 45  | + victim readout stall                              | daxpy        |
| 46  | + HPDcache bit-PLRU                                 | daxpy        |
| 47  | + HPDcache random, on 45 not 46                     | daxpy        |
| 48  | + victim readable until fill                        | daxpy        |
| 49  | + fill phase, the production stack                  | daxpy        |
|     | **production stack, ablations and geometry**        |              |
| 50  | production stack, L1D 16 KiB                        | daxpy        |
| 51  | production stack, L1D 64 KiB                        | daxpy        |
| 52  | production minus the port model                     | daxpy        |
| 53  | production minus the readout stall                  | daxpy        |
| 54  | production with bit-PLRU instead                    | daxpy        |
| 55  | duplicate of 48, minus the fill phase               | daxpy        |
| 56  | fill delay, gem5 RandomRP policy                    | daxpy        |
|     | **fence and instruction-cache policy**              |              |
| 57  | + fence flushes the L1D                             | atomic_fence |
| 58  | + transcribed L1I policy                            | all          |
|     | **front end, direct targets and the BTB**           |              |
| 59  | duplicate of 58, the delay is baseline              | btb_pressure |
| 60  | 59 + decode direct targets                          | all          |
| 61  | BTB as the JALR store, redirect delay 1             | all          |
| 62  | tagless BTB                                         | all          |
|     | **fill timing**                                     |              |
| 63  | dirty-only fill delay                               | all          |
|     | **refill window**                                   |              |
| 64  | refill window + clean fill                          | all          |
| 65  | refill window alone, isolation                      | all          |
| 66  | duplicate of 62, F5 squash is baseline              | all          |
| 67  | RAS no-recovery                                     | all          |
| 68  | store-class readout extra, isolation                | all          |
| 69  | clean fill + class z                                | all          |
| 70  | all candidates together                             | all          |
| 71  | pair + class x and z                                | all          |
|     | **accept-and-charge**                               |              |
| 72  | accept-and-charge, dirty-only fill                  | all          |
| 73  | accept-and-charge with the class law                | all          |
| 74  | accept-and-charge, the full pair                    | all          |
| 75  | accept-and-charge refill window                     | all          |
|     | **the fetch supply beat, basic_test's owner**       |              |
| 76  | fetch1FetchLimit 2 -> 4                             | all          |
| 77  | fetch1FetchLimit 4, fetch2 buffer 2 -> 1            | all          |
| 78  | fetch limit 4, fetch2 buffer 2 -> 4                 | all          |
|     | **the per-line cadence, already the baseline**      |              |
| 79  | duplicate of 78, cycle input is baseline            | all          |
| 80  | duplicate of 67, cycle input is baseline            | all          |
|     | **the class law without the fill-0 phase artefact** |              |
| 81  | flat fill, accept-and-charge                        | all          |
| 82  | duplicate of 73, 80 front end is baseline           | all          |
| 83  | duplicate of 73, turnaround is baseline             | all          |
| 84  | adopted stack + C910 divider law                    | all          |
| 85  | duplicate of 73, fence squash is baseline           | all          |
|     | **the final-check probes, on the adopted stack**    |              |
| 86  | L1I mshrs 2 -> 1, the I-side retry tax              | all          |
| 87  | fetch limit 3, fetch2 buffer 3                      | all          |
| 88  | fetch limit 4, fetch2 buffer 3                      | all          |
| 89  | L1I reopen at ready                                 | all          |
|     | **the structural I-side**                           |              |
| 90  | mshrs 1, reopen at ready, fetch1 holds              | all          |
| 91  | ablation of 90 without reopen at ready              | all          |
| 92  | the 90 with fetch limit 3 and buffer 3              | all          |
| 93  | the 91 with fetch limit 3 and buffer 3              | all          |
| 94  | the 93 with the fill readable at the fill           | all          |
| 95  | the 94 with kill on redirect                        | all          |
| 96  | previous full production                            | all          |
|     | **the final adoptions, each taken back out**        |              |
| 97  | production minus fill at the response               | all          |
| 98  | production minus the C910 divider law               | all          |
| 99  | production minus the divider queue                  | all          |
|     | **direct targets against today's stack**            |              |
| 100 | production minus direct targets                     | all          |
|     | **the killed-line drop against today's stack**      |              |
| 101 | production minus the killed-line drop               | all          |

### The cache geometry list

`CACHE_TESTS` is a second table in both harnesses, kept apart from the grid above. Nothing in it touches the CPU: it varies only L1I and L1D size and associativity, and each entry runs the suite's workloads its cut actually moves. The ids start at 201, so a number says which table it came from, and a plain sweep leaves them out.

Each entry is laid over `CACHE_BASE_TEST`, the entry named just above the table: `TEST 40`, the full production configuration, in the patched harness, and `TEST 1`, the stock baseline, in the stock one, since production needs the patch. The table holds only the cut, merged into the base's overrides when the harness runs, so a cut differs from the configuration it is compared against by the cut alone, and the list follows the base when it changes.

```bash
python3 scripts/run_gem5_config_sweep.py --configs cache        # the list below
python3 scripts/run_gem5_config_sweep.py --configs grid         # the table above
python3 scripts/run_gem5_config_sweep.py --configs all          # both
python3 scripts/run_gem5_config_sweep.py --configs 208-213      # part of one
```

Both harnesses carry the same seventeen entries under the same numbers, so a cut can be measured on a stock gem5 and on the patched build and the two compared. Each harness applies the cut to its own `CACHE_BASE_TEST`, production in the patched one and the stock baseline in the stock one, so the two lists compare the two finished configurations.

| #   | What it changes                         | Workload                                  |
| --- | --------------------------------------- | ----------------------------------------- |
| 201 | L1I 4 KiB                               | icache_pressure                           |
| 202 | L1I 8 KiB                               | icache_pressure                           |
| 203 | L1I 32 KiB                              | icache_pressure                           |
| 204 | L1I 64 KiB                              | icache_pressure                           |
| 205 | L1I direct mapped, assoc 4 -> 1         | icache_pressure                           |
| 206 | L1I assoc 4 -> 2                        | icache_pressure                           |
| 207 | L1I assoc 4 -> 8                        | icache_pressure                           |
| 208 | L1D 8 KiB                               | daxpy, full_test, atomic_fence            |
| 209 | L1D 16 KiB                              | full_test, fetch2_probe                   |
| 210 | L1D 64 KiB                              | daxpy, full_test, atomic_fence            |
| 211 | L1D direct mapped, assoc 8 -> 1         | daxpy, daxpy_unrolling_4, fetch2_probe    |
| 212 | L1D assoc 8 -> 2                        | daxpy, daxpy_unrolling_4, fetch2_probe    |
| 213 | L1D assoc 8 -> 4                        | daxpy, fetch2_probe                       |
| 214 | both small, L1I 4 KiB and L1D 8 KiB     | icache_pressure, full_test                |
| 215 | both large, L1I 64 KiB and L1D 64 KiB   | icache_pressure, full_test                |
| 216 | both direct mapped                      | icache_pressure, daxpy, daxpy_unrolling_4 |
| 217 | both doubled, L1I 32 KiB and L1D 64 KiB | icache_pressure, full_test, daxpy         |

### The same list on the real core

`CVA6/configs/cv64a6_imafdc_sv39_hpdcache_wb_config_testing_pkg.sv` is the RTL counterpart. It is the production configuration package with a table of the same geometries and one selector, `CVA6_CONFIG_SEL`, and its four cache fields read the selected values. The cuts are in the same order as the gem5 list, so **a CFG id plus 199 is the gem5 TEST id** for ids 2 to 18: `CFG_ICACHE_4K` is 2 here and `TEST 201` there. `CFG_BASELINE`, id 1, has no gem5 row.

```bash
python3 scripts/run_CVA6_config_sweep.py --dry-run       # the eighteen, and their workloads
python3 scripts/run_CVA6_config_sweep.py --configs 2-8   # the instruction cache cuts
```

That sweep installs the package over `core/include/`, rebuilds the model, runs each entry's workloads and restores the live package afterwards, on success, on failure and on interrupt. One caution: not every corner has to elaborate. A direct-mapped HPDcache, for instance, may be refused by the RTL, and the sweep reports that configuration as failed and carries on rather than stopping.

## The patch

`MinorCPU_CVA6.patch` is the whole gem5 side in one file, verified to apply cleanly on pristine v25.0.0.1 with both `git apply` and `patch`, and to revert to a byte-identical tree. Most behaviours it adds transcribe a specific RTL rule and cite it in the source comments. `fill_delay` has no RTL citation, and the readout class extras take their values from a measured law. Every one is behind a parameter that defaults to the stock behaviour, so a patched gem5 runs unpatched configurations unchanged.

### The script

[`patch_gem5.py`](../scripts/patch_gem5.py) is the loop for working on the patch, and the gem5 image carries it as `/gem5/scripts/patch_gem5.py`. Run it from the gem5 root. It reads the copy under `gem5_configs/config/`, the one that mirrors this folder.

```bash
python3 scripts/patch_gem5.py status    # in the tree or not, and which builds carry it
python3 scripts/patch_gem5.py revert    # take it back out
python3 scripts/patch_gem5.py apply     # put it back in
python3 scripts/patch_gem5.py create    # write the patch from the tree, new files included
python3 scripts/patch_gem5.py build     # rebuild, asking RISCV_PATCH or RISCV_EXP
```

Edit the sources under `src/`, `create`, `build`, measure. `create` needs no git history, which the image does not keep: it diffs `src/` against `.pristine_src.tar.xz`, the pristine sources the image archived before the patch went in, and falls back to `git diff` in a checkout that still has one. It leaves out what gem5's own `.gitignore` does, so a `parsetab.py` or a `.orig` from a failed apply cannot leak into the patch.

A patch being worked on belongs in `build/RISCV_EXP`, since `build/RISCV_PATCH` is what every TEST in the table is measured against. `build` writes the patch's hash beside the tree as `.built_patch_sha1`, which [`run_gem5.py`](https://github.com/FaMAF-CVA6-Project/MinorFlow/blob/main/scripts/run_gem5.py) reads to catch a patch edited but not rebuilt, and it writes that marker for `RISCV_PATCH` only, the build the tables rest on.

The two sections below are the same work by hand, for a tree without the script.

### Applying it

Run from the gem5 source root. The paths carry `a/` and `b/` prefixes, so `git apply` needs no `-p` flag and `patch` takes `-p1`.

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

Feed the same file back with `-R`. Both tools restore the 29 edited files and delete the 9 created ones, leaving a tree that `git status` reports as clean.

```bash
cd /gem5
git apply -R MinorCPU_CVA6.patch          # or: patch -R -p1 < MinorCPU_CVA6.patch
scons build/RISCV_PATCH/gem5.opt -j$(nproc)
```

That rebuild turns `build/RISCV_PATCH` back into a stock binary, which is rarely what you want. If a stock binary is all you need, `build/RISCV` already is one and nothing has to be rebuilt.

[`run_gem5.py`](https://github.com/FaMAF-CVA6-Project/MinorFlow/blob/main/scripts/run_gem5.py) takes `--variant stock`, the default, or `--variant patch`, which picks the binary and the overhead profile together and names the build in the table header. `--build` runs any other build directory without changing the profile.

Since every added parameter defaults off, the patched binary running `gem5_config_CVA6.py` should reproduce the stock binary exactly. Diffing the two `stats.txt` files is the test of that: apart from the patch's own counters, which only a patched build writes, any line that differs is a mechanism leaking when it should be inert. `gem5_config_CVA6_patch.py --no-patch --fetch-limit 2 --fetch2-buffer 2` on the patched binary is the same test from the other direction, holding the configuration fixed and turning the mechanisms off.

### New parameters

| Parameter                             | Object          | Default | What it does                                                                                                                                                                                                                                                                                        |
| ------------------------------------- | --------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `executeLSQNoStoreForwarding`         | MinorCPU        | `False` | Disables store-to-load forwarding from the store buffer                                                                                                                                                                                                                                             |
| `executeLSQStoreCollisionReplayDelay` | MinorCPU        | `0`     | Cycles a load waits after a store collision clears                                                                                                                                                                                                                                                  |
| `executeLSQFenceSignalsDcache`        | MinorCPU        | `False` | A fence signals the data cache, modelling the core's flush wire                                                                                                                                                                                                                                     |
| `directTargetsFromDecode`             | BranchPredictor | `False` | Taken direct control takes its target from the decoded instruction, never the BTB's, and never enters the BTB, which serves only indirect control that is not a return, as CVA6's `frontend.sv` (242 to 248 and 337)                                                                                |
| `consumersWaitForCommit`              | MinorFUTiming   | `False` | Holds a matching instruction's consumers until it commits, as memory references are held, since a latency set by `extraCommitLatExpr` is unknown to the scoreboard at issue                                                                                                                         |
| `holdWhileBusy`                       | MinorFU         | `False` | Accepts one more instruction while the unit is busy and holds it in an input register until the unit frees, so younger instructions keep issuing, as fpnew's divider holds a second operation                                                                                                       |
| `heldLatencyOverlap`                  | MinorFU         | `0`     | Cycles of a held instruction's latency that pass while it waits, taken off its commit delay                                                                                                                                                                                                         |
| `extraCommitLatFromFUEnd`             | MinorFU         | `False` | Counts an instruction's extra commit latency from the cycle it reached the end of the unit, not from the cycle it became the oldest in flight, as a unit that writes back out of order                                                                                                              |
| `executeFenceSquashesPipeline`        | MinorCPU        | `False` | A committed full fence squashes the pipeline and restarts fetch at the next PC                                                                                                                                                                                                                      |
| `rasNoRecovery`                       | BranchPredictor | `False` | Speculative RAS pushes and pops stand uncorrected on a squash, as CVA6's scan-driven stack                                                                                                                                                                                                          |
| `evict_on_allocate`                   | Cache           | `False` | Selects the victim and issues its writeback at MSHR allocation                                                                                                                                                                                                                                      |
| `victim_readout_stall`                | Cache           | `False` | Charges the dirty-victim data-array readout, `blkSize / 8` cycles                                                                                                                                                                                                                                   |
| `victim_readout_store_extra`          | Cache           | `0`     | Extra readout-window cycles when a store triggered the eviction                                                                                                                                                                                                                                     |
| `victim_readout_first_load_extra`     | Cache           | `0`     | Extra readout-window cycles when a lone load triggered the eviction                                                                                                                                                                                                                                 |
| `refill_window_blocks`                | Cache           | `False` | Blocks the cpu side for `blkSize / 8` cycles while a refill writes the data array. **Not enabled in either production configuration**: it is set only in `gem5_config_CVA6_patch_testing.py`, where four entries use it, and `window_accept_and_charge` carries the delivered form of the same cost |
| `window_accept_and_charge`            | Cache           | `False` | The accept-and-charge form of both windows: the port never blocks, a request inside a window takes the overlap as latency, the miss that opens a readout window takes it on its own fill                                                                                                            |
| `victim_readable_until_fill`          | Cache           | `False` | Keeps the victim answering hits until its refill lands                                                                                                                                                                                                                                              |
| `fill_at_response`                    | Cache           | `False` | Holds a miss's fill, and with it the in-place victim, to the cycle its response reaches the core, as the HPDcache rewrites the directory with the last refill word. Miss latency is unchanged, since `response_latency` moves into the hold                                                         |
| `fill_delay`                          | Cache           | `0`     | Extra cycles from response arrival to fill, without touching shared memory latency                                                                                                                                                                                                                  |
| `fence_flushes_dcache`                | Cache           | `False` | A fence writes back every dirty line and holds the cache 2 cycles per line                                                                                                                                                                                                                          |
| `fetch1WaitsForIcache`                | MinorCPU        | `False` | Fetch1 holds a line at the ready line instead of paying a refusal and a retry, since `cva6_icache.sv` asserts `dreq_o.ready` only in IDLE and READ                                                                                                                                                  |
| `fetch1KillsOnRedirect`               | MinorCPU        | `False` | Every in-flight line frees its fetch slot at the redirect, the front-end side of `kill_s1` and `kill_s2`                                                                                                                                                                                            |
| `fetch1DropsKilledLines`              | MinorCPU        | `False` | A killed line leaves Fetch1 as it returns, and a killed request before it is sent, without taking the cycle's line slot, as `cva6_icache.sv` withholds a killed response and takes the next request in the same cycle                                                                               |
| `fill_ready_at_fill`                  | Cache           | `False` | A filled block is readable `data_latency` cycles after the fill, without the response's bus delays, since the I-cache writes the line in the fill-ack cycle, so the bus terms are not charged twice                                                                                                 |
| `reopen_at_ready`                     | Cache           | `False` | Defers the full-MSHR retry until that block is readable                                                                                                                                                                                                                                             |

### New SimObjects

| Object               | What it is                                                                                                                          |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `Axi2MemPort`        | The CVA6 testbench memory adapter: one transaction at a time, fixed read priority, `1 + N` cycle occupancy for `N` eight-byte beats |
| `HPDcacheRandomRP`   | The L1D victim policy the build configures: four tiers, with an 8-bit Galois LFSR, polynomial `0xE1`                                |
| `HPDcachePLRURP`     | The L1D bit-PLRU branch the build does **not** configure                                                                            |
| `CVA6IcacheRandomRP` | The L1I policy: lowest-index invalid way, else an 8-bit Galois LFSR, polynomial `0xFA`                                              |

### New statistics

The patch adds its own counters beside the stock ones. It also extends `blockedCycles`, `blockedCauses` and `avgBlocked` with the three new causes, and counts `replacements` on the in-place reservation path, which bypasses the stock code that counts it.

| Statistic                                                        | Object           | What it counts                                                                                                                                                             |
| ---------------------------------------------------------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `preemptionBlockedCycles`                                        | Cache            | Each blocked stretch whose last cause to clear was a CVA6 preemption (victim readout, fence flush or refill window), counted whole, as the stock `blockedCycles` counts it |
| `cva6ComparableDemandAccesses`                                   | Cache            | Demand accesses plus the preemption and window cycles below, the count the HPDcache PMU reports                                                                            |
| `earlyReservations`                                              | Cache            | Victims reserved at miss time by evict-on-allocate                                                                                                                         |
| `reservationFallbacks`                                           | Cache            | Misses that fell back to stock fill-time allocation                                                                                                                        |
| `inPlaceReservations`                                            | Cache            | Reservations that kept the victim readable                                                                                                                                 |
| `reservationRedirties`                                           | Cache            | In-place victims dirtied again before their refill landed, so written back twice                                                                                           |
| `fenceFlushes`                                                   | Cache            | Full flushes a fence triggered                                                                                                                                             |
| `fenceFlushWritebacks`                                           | Cache            | Dirty lines those flushes wrote back                                                                                                                                       |
| `windowTriggerCharges`, `windowTriggerCycles`                    | Cache            | Misses charged their own readout window under accept-and-charge, and the cycles                                                                                            |
| `windowOverlapCharges`, `windowOverlapCycles`                    | Cache            | Requests charged a window overlap, and the cycles                                                                                                                          |
| `reservationUpgradeFallbacks`                                    | Cache            | In-place reservations released at fill time because an upgrade on the victim was still outstanding                                                                         |
| `unusedTier`, `randomTier`, `cleanTier`, `dirtyTier`, `noVictim` | HPDcacheRandomRP | Which tier of the victim policy supplied each selection                                                                                                                    |
| `readsAdmitted`, `writesAdmitted`                                | Axi2MemPort      | Transactions admitted to the single port, by class                                                                                                                         |
| `passThrough`                                                    | Axi2MemPort      | Packets with no AXI equivalent, forwarded without occupancy                                                                                                                |
| `readWaitCycles`, `writeWaitCycles`                              | Axi2MemPort      | Admission wait histograms, by class                                                                                                                                        |

The metrics table uses three of these: `preemptionBlockedCycles`, `windowTriggerCycles` and `windowOverlapCycles`. `run_gem5.py` adds them to the cache-access rows and prints the result as a third column, `NET (CVA6)`, next to `NET`, so a gem5 table reads against a CVA6 one row for row.

The blocked count holds cycles in which the cache refused requests, and the two window counts hold latency charged to accepted ones, so summing them is right whichever form is configured. `cva6ComparableDemandAccesses` reports the demand accesses plus that sum. Accept-and-charge replaces the **readout and refill-window** blocks specifically, causes 3 and 5. The other blocking causes, no-MSHRs, no-write-buffers, no-targets and the fence flush, still block under either form, so a single run carries both kinds. `preemptionBlockedCycles` credits a whole blocked span to the cause that clears last.

### What each change models, briefly

**Instruction-side miss acceptance.** The L1I held two MSHRs, a stock parameter, until the structural I-side below. With one, the line Fetch1 requests during a miss is refused and retried off the clock edge, a tax CVA6 never pays: its I-cache takes no request during a miss and the front end presents the next line the cycle the first returns (`cva6_icache.sv` MISS state). With two, the request coalesces or queues at the memory port, and miss chains land at CVA6's one fill per five cycles. Two was a stand-in for structure the model lacked, replaced below. `run_gem5.py` reads `overallMshrMisses` on both caches, the refill count the PMU counts.

**The structural instruction side.** Four parameters replace that MSHR count with the shape the RTL has, all four on by default. `fetch1WaitsForIcache` holds a line at the ready line instead of paying a refusal and a retry, since `cva6_icache.sv` asserts `dreq_o.ready` only in IDLE and READ. `fetch1KillsOnRedirect` frees every in-flight line's fetch slot at the redirect, the front-end side of `kill_s1` and `kill_s2`. `fill_ready_at_fill` makes a block readable `data_latency` cycles after the fill, without the bus delays, since the I-cache writes the line in the fill-ack cycle, so the bus terms are not charged twice. `reopen_at_ready` defers the full-MSHR retry until that block is readable. The L1I then runs at one MSHR, the hardware's number, and `TESTS 90` to `96` separate the four.

**Killed lines.** At a redirect the lines fetched down the old path still return, and Minor's Fetch1 spent its one line per cycle on each, sent or returned, so the new path's first line waited a cycle behind them and every line after it stayed a cycle late until the next redirect. CVA6's I-cache withholds a killed response and takes the next request in the same cycle. `fetch1DropsKilledLines` drops them at once. At fetch depth 3 two old-path lines are in flight at each taken branch, one more than at depth 2, which is why `btb_pressure` read near exact at depth 2 and 15 percent slow at 3. It now runs its three-instruction loop at the hardware's 4 cycles per iteration and 300 of its 511 blocks to the cycle.

**Fetch cadence.** CVA6's I-cache accepts a hit request every cycle in its READ state. Minor's Fetch2 with `fetch2CycleInput` false takes the next line a cycle after exhausting one, half the rate. The configuration sets it true. A stock parameter, not a patch, and the published empirical configuration already carried it.

**Front end.** CVA6 computes direct-branch and jump targets in the fetch path and consults its BTB only for JALR, whose entries are tagless and written on a mispredict. The patch adds the decode-target model, and the configuration then drops the indirect predictor and the BTB tag and signals fetch2 predictions to fetch1 in the same cycle, matching CVA6's one-bubble re-steer against Minor's two. Direct control never takes a BTB target and never enters the BTB, as CVA6 reads its prediction only for a JALR that is not a return and writes it only on a JumpR mispredict. The BTB is still looked up for every branch, as CVA6 reads it on every fetch, which keeps the Branches count unchanged.

**Store forwarding.** CVA6 has no store-to-load forwarding path. Its load unit parks a load in `WAIT_PAGE_OFFSET` until the store buffer drains whenever the address collides with a pending store (`load_unit.sv`, and `page_offset_matches_o` in `store_buffer.sv`, an eight-byte granule). Restarting that load costs two more cycles, since neither `IDLE` nor `WAIT_PAGE_OFFSET` asserts `data_req`.

**The memory port.** The testbench adapter (`axi2mem.sv`) is single-ported and holds one transaction end to end, testing `ar_valid` before `aw_valid` so reads always win. It adds no latency when uncontended, so contention appears only as admission wait.

**Eviction phase.** The HPDcache selects its victim and issues the dirty writeback at MSHR allocation, not at fill (`hpdcache_miss_handler.sv`). That readout occupies the data array for `clWords / accessWords` cycles, 2 for the 16-byte line, and the array is single-ported across five requesters (`hpdcache_memctrl.sv`).

**Victim policy.** The build configures `HPDCACHE_VICTIM_RANDOM`, not the PLRU branch: one global LFSR shared by the whole cache, shifting only when the random tier fires. Validated against a VCD probe at 7,406 of 7,406 selections, and it predicts the real machine's writeback counts to within one percent at 16, 32 and 64 KiB and at 2-way.

**Readable victim.** CVA6's directory update is pipelined, so an access one cycle behind an allocation still hits the line being displaced. gem5 re-tags synchronously and would lose it. The victim stays readable until the directory rewrite, which the HPDcache does with the last refill word, in the core-response cycle, so `fill_at_response` holds the fill to that cycle without changing miss latency. Filled `response_latency` cycles earlier, the victim died before the loads behind a store miss reached it.
**Fill instant.** CVA6's clean misses complete around 9 cycles and its dirty-eviction misses later by the victim readout, 2 cycles for the 16-byte line, plus a class term per trigger: +1 for a load with no other miss outstanding, +4 for a store through the replay table (`hpdcache_rtab.sv` POP_TRY, `hpdcache_flush.sv`). The configuration now charges nothing flat and lets the readout window carry the base and its extras on the triggering miss's own fill. A request arriving inside an open window takes the overlap as its own latency, as the HPDcache stalls it in stage 0 (`hpdcache_ctrl_pe.sv` 338 to 348), and the port never refuses, since a refusal in Minor costs a rounded-up retry cycle and freezes the LSQ (`base.cc` 184, `lsq.cc` 1247), which the RTL does not do.

**Integer divider turnaround.** `serdiv.sv` returns to IDLE the cycle after FINISH clears (lines 178 to 215), so consecutive independent divides issue 12 apart where the data-dependent latency alone gives 11. `issueLat 3` on the divide unit carries it.

**FP divider.** This build's FP divider is the T-Head C910 radix-16 SRT unit: `fpnew_top.sv` defaults `DivSqrtSel` to `THMULTI` and `fpu_wrap.sv` keeps it. Its loop stops one round after the partial remainder reaches zero, so issue to writeback is 9 + m cycles, m = min(k, 13) for FP64 and min(k, 6) for FP32, with k the hex digits the exact result needs. Only an exact short result runs short. 1.0 / 2.0 takes 10, and a full or inexact result takes 15 or 22 however short its operands. The divider unit carries it as a timing expression on the operand values, with `consumersWaitForCommit`, since the scoreboard cannot see a latency set at commit.

**Divider queue.** fpnew's divider has an input register ahead of the C910 unit, so a divide or square root that arrives while one is running is accepted and issue carries on. It starts in the running one's WB cycle and writes back 6 + m cycles after it, 3 sooner than a start at that writeback, and a third finds the register full and stalls issue. `holdWhileBusy` gives the unit that one-entry register, and `heldLatencyOverlap` takes the 3 cycles off the held operation, which is why the configuration moves them out of `opLat` into the timing expression. `extraCommitLatFromFUEnd` runs a divide's extra latency from the unit's end, not from the commit head, since the unit writes back out of order and older instructions committing late do not delay it.

**Fence squash.** A committed full fence squashes the pipeline and restarts fetch at the next PC, rule F5 (`controller.sv` 123 to 136). On this configuration the re-fetch completes inside the flush walk, so the tables are unchanged by it.

**Fence flush.** A fence flushes the D-cache when `DcacheFlushOnFence` is set, which it is for this build (`controller.sv`). The core drives that as a dedicated wire rather than a bus transaction, so `executeLSQFenceSignalsDcache` sends it functionally and `fence_flushes_dcache` decides whether the cache acts on it. The walk costs 2 cycles per line (`hpdcache_cmo.sv`), counted during the walk so it scales with cache geometry.

**Instruction cache policy.** A separate module from the HPDcache with its own two-tier policy and its own LFSR (`cva6_icache.sv` plus PULP's `lfsr.sv`), advancing only on a fill into an already full set. This buys exactness rather than accuracy, since gem5's stock `RandomRP` is already in the same class.

### Files changed

`src/cpu/minor/` for `BaseMinorCPU.py`, `dyn_inst.hh`, `execute.cc`, `execute.hh`, `fetch1.cc`, `fetch1.hh`, `func_unit.cc`, `func_unit.hh`, `lsq.cc` and `lsq.hh`. `src/cpu/pred/` for `BranchPredictor.py`, `bpred_unit.hh`, `bpred_unit.cc`, `ras.hh` and `ras.cc`. `src/mem/` for the adapter, its `SConscript` entry and the ready-line query in `port.hh`. `src/mem/cache/` for `Cache.py`, `base.hh`, `base.cc`, `cache.hh`, `cache.cc`, `cache_blk.hh`, `mshr.hh` and `mshr.cc`. `src/mem/cache/tags/` for the fill-time replacement hook, in `base.hh` and `base_set_assoc.hh`. `src/mem/cache/replacement_policies/` for the three policies and their registrations.

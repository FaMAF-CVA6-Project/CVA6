# The CVA6 container

The real-hardware side of the FaMAF CVA6 Project: the frozen CORE-V CVA6 fork, a built RISC-V toolchain, Verilator, Spike, the run drivers and the CVA6Flow viewer, in one image. Everything lives under `/CVA6`, which is the working directory of every shell the image starts.

![CVA6Flow rendering the CVA6 pipeline](CVA6Flow/docs/CVA6Flow_intro.png)

This file describes what is **inside the container**, so every path below is a container path. The repository this image was built from is at https://github.com/FaMAF-CVA6-Project/CVA6.

## What is in here

| Path                  | What it is                                                                                                                              |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `core/`, `corev_apu/` | The CVA6 core RTL and its SoC wrapper, upstream's work                                                                                  |
| `verif/`              | The verification harness. `verif/sim/cva6.py` is what the drivers call, through `verif/sim/setup-env.sh`                                |
| `tools/`              | The toolchain built into the image: `riscv-none-elf-gcc` 13.1.0, Verilator 5.008 and Spike 1.1.1-dev                                    |
| `scripts/`            | The drivers, the two sweeps, the batch JSON converter, the cleaner, the VCD window tool and the viewer server                           |
| `CVA6_configs/`       | The three configuration packages: the production one, the viewer's swept copy and `..._config_testing_pkg.sv`, the cache geometry table |
| `benchmarks/config/`  | The calibration set, the programs the gem5 comparison is measured on                                                                    |
| `benchmarks/viewer/`  | The set written while developing the viewer, one core behaviour per program                                                             |
| `CVA6Flow/`           | The viewer: `CVA6Flow.html`, its tracer, `index.html`, `docs/` and an empty `tests/`                                                    |
| `verilator_changes/`  | `custom_size_vcds/`, the windowed waveform dump, applied and reverted by `scripts/patch_vcd_window.py`                                  |
| `results/`            | Where every run writes. Empty in a fresh container                                                                                      |
| `Makefile`, `Flist.*` | Upstream's build entry points, which the harness drives                                                                                 |

The target built here is `cv64a6_imafdc_sv39_hpdcache_wb`, a 64-bit CVA6 with the HPDcache writeback data cache, a 16 KiB 4-way instruction cache and a 32 KiB 8-way data cache.

## Run one benchmark

```bash
python3 scripts/run_CVA6.py benchmarks/config/store_fwd.S --no-vcd
```

The first run compiles the Verilated model into `work-ver/`, which took about a minute and a half on a 16-thread machine. Every run after that can reuse it with `--keep-build`, as long as the configuration package and the testbench are unchanged.

What it prints is a metrics table with two figures per metric: `OFFICIAL` is what the hardware counters read, and `NET` subtracts the fixed instrumentation overhead of the suite the program belongs to, which is the number the gem5 side is compared against.

Output lands under `results/`: the files worth keeping in `results/run/`, and the simulator's own output folder moved to `results/verif/out_<date>/` when the run survives to the end.

| Option         | What it does                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `--no-vcd`     | No VCD. Verilator writes up to about 63 KB of VCD per simulated cycle, so a long run is huge                              |
| `--keep-build` | Reuse `work-ver` instead of rebuilding the model                                                                          |
| `--suite`      | Force the overhead table. Normally read from the `.overhead_suite` file beside the program, and the run stops without one |
| `--lang`       | Force C or assembly handling instead of deciding by extension                                                             |
| `--cva6-root`  | Point at another checkout. Defaults to `/CVA6`                                                                            |

## The other drivers

| Script                                 | What it does                                                                                                                                                                |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/run_all_CVA6_benchmarks.py`   | A whole folder in one go, writing to `results/batch/`, keeping a failed run rather than hiding it                                                                           |
| `scripts/run_CVA6Flow_sweep.py`        | The **viewer's** sweep: the configuration cuts used while developing CVA6Flow. It swaps a package into `core/include/`, runs, and restores it afterwards                    |
| `scripts/create_all_CVA6Flow_jsons.py` | Every VCD in a folder to a JSON, passing `--strict`, so a degraded VCD ends the batch with exit 3, its JSON still written                                                   |
| `scripts/measure_CVA6_overhead.py`     | Measures the overhead profiles `run_CVA6.py` subtracts, from each suite's empty template, and with `--write` puts them into it                                              |
| `scripts/clean_CVA6_runs.py`           | Deletes what a run writes. It asks about `work-ver` on its own, since rebuilding it is slow                                                                                 |
| `scripts/run_CVA6_config_sweep.py`     | The **matched configuration** search on the real core: seventeen cuts of L1I and L1D size and associativity plus the baseline, the RTL side of what the gem5 harness sweeps |
| `scripts/patch_vcd_window.py`          | Applies or reverts the windowed waveform dump                                                                                                                               |
| `scripts/serve_CVA6Flow.py`            | Serves the viewer over HTTP, since the image has no browser                                                                                                                 |

Every one of them answers `--help`. `patch_vcd_window.py` and `measure_CVA6_overhead.py` take `-n` for a dry run, `clean_CVA6_runs.py` and `run_all_CVA6_benchmarks.py` take `--dry-run`, and both sweeps take `--dry-run` to print the plan without running it.

## Use the viewer

```bash
python3 scripts/serve_CVA6Flow.py
```

It listens on port 8000 inside the container, which `make_containers.py` publishes as **8001** on the host, so open `http://localhost:8001/CVA6Flow/CVA6Flow.html` there. The gem5 container takes 8000, so both can serve at the same time.

The viewer loads the JSON the tracer makes from a VCD:

```bash
python3 CVA6Flow/CVA6Flow_tracer.py results/run/daxpy.vcd -o results/run/daxpy.json
```

The page opens a JSON from the host's disk, dropped onto it or chosen with Load JSON, so either copy the JSON out to the host, with `docker cp` or the fork's `scripts/docker_sync.py pull`, or make a sample of it inside the container, which the served page then offers by name:

```bash
python3 scripts/make_CVA6Flow_sample.py results/run/daxpy.json -n 0
```

`-n 0` keeps every record, and the script refuses a JSON of more than the 500,000 records the page renders at once. Without `-n` it keeps the first 3,000. The sample lands in `CVA6Flow/tests/` as `daxpy.sample.js`, listed in `CVA6Flow/tests/samples.js`, and the page `scripts/serve_CVA6Flow.py` serves offers it in its sample picker.

The tracer finds the disassembly listing on its own when it sits beside the VCD under the same name, and `--disasm-list` names it otherwise. With `--strict` the tracer exits with 3 on a **degraded** VCD, the JSON still written: one missing the signals of a mechanism the tracer follows, so that mechanism could not be observed at all, or one that was cut, holds no value changes, no rising clock edge, no instruction or no commit, starts part way through the run, as a windowed dump does, or ends at a timestamp that disagrees with its cycle count. `metadata.degraded` always names each one, whether or not `--strict` is passed. The viewer refuses a JSON whose `metadata.schema_version` is not 3 and asks for it to be regenerated, rather than drawing silent nulls.

`CVA6Flow/tests/` is empty in a fresh image. The page offers only the samples its `tests/samples.js` lists that its tracer wrote at schema 3, so a sample made on the host with the viewer's own `scripts/make_CVA6Flow_sample.py` appears too once its `.sample.js` and `samples.js` are copied into `CVA6Flow/tests/`.

## Windowed waveforms

An unwindowed VCD of a long benchmark reaches tens of gigabytes. The two modified copies in `verilator_changes/custom_size_vcds/` bound the dump to a window of clock cycles, whose VCD timestamps are twice the cycle numbers:

```bash
python3 scripts/patch_vcd_window.py apply
export trace_start=100000 trace_end=200000
python3 scripts/run_CVA6.py benchmarks/viewer/daxpy.S
python3 scripts/patch_vcd_window.py revert
```

The window is a compile-time define, and it has to be exported: the driver's build runs `make verilate` again, which drops a window given only on an earlier `make verilate` command line, while an exported one reaches that build too. `apply` keeps the file it replaces beside it as `<name>.upstream`, which is how `revert` puts it back, since this container has no git history to restore from.

## Benchmarks and configurations

Each benchmark folder carries a one-line `.overhead_suite` file naming the overhead table its programs belong to, so the right fixed cost is subtracted wherever the folder is copied. `benchmarks/config/` is the calibration set and `benchmarks/viewer/` the set written while developing the viewer.

`CVA6_configs/` holds three packages, and the live copy the build elaborates is `core/include/cv64a6_imafdc_sv39_hpdcache_wb_config_pkg.sv`:

| Package                                        | What it is                                                                                                                                      |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `cv64a6_imafdc_sv39_hpdcache_wb_config_pkg.sv` | The production configuration, unmodified, the same file as the live one                                                                         |
| `..._config_CVA6Flow_pkg.sv`                   | The cuts CVA6Flow was developed on, run by `scripts/run_CVA6Flow_sweep.py`                                                                      |
| `..._config_testing_pkg.sv`                    | The cache geometries, run by `scripts/run_CVA6_config_sweep.py`, matching `CACHE_TESTS` on the gem5 side where a CFG id plus 199 is the TEST id |

A sweep writes its package over the live one, runs, and restores the live one afterwards, on success, on failure and on interrupt. A sweep killed outright leaves `core/include/cv64a6_imafdc_sv39_hpdcache_wb_config_pkg.sv.sweep_backup` behind, and the next sweep restores the live package from it first. Until then a plain `run_CVA6.py` builds whichever configuration the killed sweep had installed, so copy the backup back by hand if a run comes first.

## Cleaning up

```bash
python3 scripts/clean_CVA6_runs.py --dry-run    # list, delete nothing
python3 scripts/clean_CVA6_runs.py              # list, ask about work-ver, then ask
```

It deletes `results/run/`, `results/batch/`, `results/sweep_CVA6Flow/`, `results/sweep_CVA6_config/`, `results/verif/`, the dated `verif/sim/out_*` folders, `work-ver/` and every `__pycache__` it finds. `work-ver` is asked about separately because a run that leaves the configuration alone can reuse it, and `--keep-build` spares it without asking.

## What is upstream and what is not

The core, its SoC wrapper, the verification harness and the vendored dependencies are the work of the OpenHW Group and contributors, under the licences preserved in the image: `LICENSE`, `LICENSE.Berkeley` and `LICENSE.SiFive`.

What this project adds is listed in `LICENSE.FaMAF`, which also carries the MIT terms it is offered under. `CITATION.cff` is how to cite the image. The two files in `verilator_changes/custom_size_vcds/` are modified copies of upstream files and each carries a notice of what was changed, as their licences require.

## Built with

`riscv-none-elf-gcc` 13.1.0, Verilator 5.008, Spike 1.1.1-dev, Python 3.12 on Ubuntu 24.04, the same base as the gem5 image. The toolchain is built from the fork's own `util/toolchain-builder`, and Verilator and Spike from the harness's install scripts, so the versions are the ones the flow expects rather than whatever a distribution ships.

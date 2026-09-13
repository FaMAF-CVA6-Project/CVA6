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
| `scripts/`            | The drivers, the sweep, the cleaner, the VCD window tool and the viewer server                                                          |
| `CVA6_configs/`       | The three configuration packages: the production one, the viewer's swept copy and `..._config_testing_pkg.sv`, the cache geometry table |
| `benchmarks/config/`  | The calibration set, the programs the gem5 comparison is measured on                                                                    |
| `benchmarks/viewer/`  | The set written while developing the viewer, one core behaviour per program                                                             |
| `CVA6Flow/`           | The viewer: `CVA6Flow.html`, its tracer, `index.html` and `tests/` for a sample                                                         |
| `verilator_changes/`  | `custom_size_vcds/`, the windowed waveform dump, applied and reverted by `scripts/patch_vcd_window.py`                                  |
| `results/`            | Where every run writes. Empty in a fresh container                                                                                      |
| `Makefile`, `Flist.*` | Upstream's build entry points, which the harness drives                                                                                 |

The target built here is `cv64a6_imafdc_sv39_hpdcache_wb`, a 64-bit CVA6 with the HPDcache write-back data cache, a 16 KiB 4-way instruction cache and a 32 KiB 8-way data cache.

## Run one benchmark

```bash
python3 scripts/run_CVA6.py benchmarks/config/store_fwd.S --no-vcd
```

The first run compiles the Verilated model into `work-ver/`, which takes about twelve minutes. Every run after that can reuse it with `--keep-build`, as long as the configuration package and the testbench are unchanged.

What it prints is a metrics table with three columns: `OFFICIAL` is what the hardware counters read, `NET` subtracts the fixed instrumentation overhead of the suite the program belongs to, and that is the number the gem5 side is compared against.

Output lands under `results/`: the files worth keeping in `results/run/`, and the simulator's own output folder moved to `results/verif/out_<date>/` when the run survives to the end.

| Option         | What it does                                                                                |
| -------------- | ------------------------------------------------------------------------------------------- |
| `--no-vcd`     | No waveform. Verilator writes about 63 KB of VCD per simulated cycle, so a long run is huge |
| `--keep-build` | Reuse `work-ver` instead of rebuilding the model                                            |
| `--suite`      | Force the overhead table. Normally read from the `.overhead_suite` file beside the program  |
| `--lang`       | Force C or assembly handling instead of deciding by extension                               |
| `--cva6-root`  | Point at another checkout. Defaults to `/CVA6`                                              |

## The other drivers

| Script                                 | What it does                                                                                                                                             |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/run_all_CVA6_benchmarks.py`   | A whole folder in one go, writing to `results/batch/`, keeping a failed run rather than hiding it                                                        |
| `scripts/run_CVA6Flow_sweep.py`        | The **viewer's** sweep: the configuration cuts used while developing CVA6Flow. It swaps a package into `core/include/`, runs, and restores it afterwards |
| `scripts/create_all_CVA6Flow_jsons.py` | Every VCD in a folder to viewer JSON, passing `--strict` so a degraded VCD fails the batch                                                               |
| `scripts/clean_CVA6_runs.py`           | Deletes what a run writes. It asks about `work-ver` on its own, since rebuilding it is slow                                                              |
| `scripts/run_CVA6_config_sweep.py`     | The **matched configuration** search on the real core: eighteen cuts of L1I and L1D size and associativity, the RTL side of what the gem5 harness sweeps |
| `scripts/patch_vcd_window.py`          | Applies or reverts the windowed waveform dump                                                                                                            |
| `scripts/serve_CVA6Flow.py`            | Serves the viewer over HTTP, since the image has no browser                                                                                              |

Every one of them answers `--help`, and the destructive ones take `-n` for a dry run.

## Use the viewer

```bash
python3 scripts/serve_CVA6Flow.py
```

It listens on port 8000 inside the container. `make_containers.py` publishes that as **8001** on the host, so open `http://localhost:8001/CVA6Flow/CVA6Flow.html` there. The gem5 container takes 8000, so both can serve at the same time.

The viewer reads a JSON the tracer produces from a VCD:

```bash
python3 CVA6Flow/CVA6Flow_tracer.py results/verif/out_<date>/daxpy.vcd -o daxpy.json
```

The tracer finds the disassembly listing on its own when it sits beside the VCD under the same name, and `--disasm-list` names it otherwise. `--strict` fails on a **degraded** VCD, which means either that a signal the tracer needs is missing from the dump, so a mechanism could not be observed at all, or that the dump itself is unusable: cut mid-record, no value changes, no rising clock edge, or no committed instruction. `metadata.degraded` always names each one, whether or not `--strict` is passed. The viewer refuses a JSON whose `schema_version` is not 1 and asks for it to be regenerated, rather than drawing silent nulls.

`CVA6Flow/tests/` is where samples go. The page is served here, so it reads that folder and offers every `.js` sample in it by name. `scripts/make_CVA6Flow_sample.py` in the viewer's own repository is what trims a full JSON down to one.

## Windowed waveforms

An unwindowed dump of a long benchmark reaches tens of gigabytes. The two modified copies in `verilator_changes/custom_size_vcds/` bound the dump to a window of simulation time:

```bash
python3 scripts/patch_vcd_window.py apply
make verilate trace_start=100000 trace_end=200000
python3 scripts/run_CVA6.py benchmarks/viewer/daxpy.S --keep-build
python3 scripts/patch_vcd_window.py revert
```

The window is a compile-time define, so it only takes effect on a rebuilt model, and the run that follows needs `--keep-build` or the driver rebuilds without it. `apply` keeps the file it replaces beside it as `<name>.upstream`, which is how `revert` puts it back, since this container has no git history to restore from.

## Benchmarks and configurations

Each benchmark folder carries a one-line `.overhead_suite` file naming the overhead table its programs belong to, so the right fixed cost is subtracted wherever the folder is copied. `benchmarks/config/` is the calibration set and `benchmarks/viewer/` the set written while developing the viewer.

`CVA6_configs/` holds three packages, and the live copy the build elaborates is `core/include/cv64a6_imafdc_sv39_hpdcache_wb_config_pkg.sv`:

| Package                                        | What it is                                                                                                                                      |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `cv64a6_imafdc_sv39_hpdcache_wb_config_pkg.sv` | The production configuration, unmodified, the same file as the live one                                                                         |
| `..._config_viewer_pkg.sv`                     | The cuts CVA6Flow was developed on, run by `scripts/run_CVA6Flow_sweep.py`                                                                      |
| `..._config_testing_pkg.sv`                    | The cache geometries, run by `scripts/run_CVA6_config_sweep.py`, matching `CACHE_TESTS` on the gem5 side where a CFG id plus 199 is the TEST id |

A sweep writes its package over the live one, runs, and restores the live one afterwards, on success, on failure and on interrupt.

## Cleaning up

```bash
python3 scripts/clean_CVA6_runs.py -n    # list, delete nothing
python3 scripts/clean_CVA6_runs.py       # list, ask about work-ver, then ask
```

It removes `results/`, the dated `verif/sim/out_*` folders, the stray files the harness leaves in `verif/sim/`, and every `__pycache__` it finds. `work-ver` is asked about separately because a run that leaves the configuration alone can reuse it.

## What is upstream and what is not

The core, its SoC wrapper, the verification harness and the vendored dependencies are the work of the OpenHW Group and contributors, under the licences preserved in the image: `LICENSE`, `LICENSE.Berkeley` and `LICENSE.SiFive`.

What this project adds is listed in `LICENSE.FaMAF`, which also carries the MIT terms it is offered under. `CITATION.cff` is how to cite the image. The two files in `verilator_changes/custom_size_vcds/` are modified copies of upstream files and each carries a notice of what was changed, as their licences require.

## Built with

`riscv-none-elf-gcc` 13.1.0, Verilator 5.008, Spike 1.1.1-dev, Python 3.12 on Ubuntu 24.04, the same base as the gem5 image. The toolchain is built from the fork's own `util/toolchain-builder`, and Verilator and Spike from the harness's install scripts, so the versions are the ones the flow expects rather than whatever a distribution ships.

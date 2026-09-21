# The gem5 container

The simulator side of the FaMAF CVA6 Project: gem5 v25.0.0.1 built three times, the MinorCPU configuration matched to CVA6, the calibration benchmarks, the run drivers and the MinorFlow viewer, in one image. Everything lives under `/gem5`, which is the working directory of every shell the image starts.

![MinorFlow rendering the MinorCPU pipeline](https://raw.githubusercontent.com/FaMAF-CVA6-Project/MinorFlow/main/docs/MinorFlow_intro.png)

This file describes what is **inside the container**, so every path below is a container path. gem5's own README is kept beside this one as `README.gem5.md`. The repository this image was built from is at https://github.com/FaMAF-CVA6-Project/CVA6.

## What is in here

| Path                       | What it is                                                                                                                 |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `src/`, `configs/`, `ext/` | gem5 v25.0.0.1 with `MinorCPU_CVA6.patch` applied in the tree, and no git history, like the CVA6 image                     |
| `build/RISCV/`             | The **stock** build, from the pristine sources, before the patch                                                           |
| `build/RISCV_PATCH/`       | The **patched** build. Every calibration TEST is measured against this one                                                 |
| `build/RISCV_EXP/`         | The same patched sources again, for working on the patch without disturbing the reference build                            |
| `scripts/`                 | The drivers, the two sweeps, the parity check, the patch tool, the batch JSON converter, the cleaner and the viewer server |
| `gem5_configs/config/`     | The matched configurations and the patch itself: stock, patched, and a calibration harness for each                        |
| `gem5_configs/viewer/`     | The configurations used while developing the viewer                                                                        |
| `gem5_configs/CARLA2026/`  | The frozen configuration the CARLA 2026 paper used                                                                         |
| `benchmarks/config/`       | The calibration set, the programs the CVA6 comparison is measured on                                                       |
| `benchmarks/viewer/`       | The set written while developing the viewer, one core behaviour per program                                                |
| `MinorFlow/`               | The viewer: `MinorFlow.html`, its tracer, `index.html`, `docs/` and an empty `tests/`                                      |
| `results/`                 | Where every run writes. Empty in a fresh container                                                                         |
| `.built_patch_sha1`        | The hash of the patch the builds were made from, which the driver checks                                                   |
| `.pristine_src.tar.xz`     | gem5's own `src/` from before the patch, kept in place of its git history for `patch_gem5.py create` to diff against       |

The bare-metal toolchain is `riscv64-unknown-elf-gcc` 13.2.0, and the benchmarks are built for the extension set the CVA6 target implements, `rv64gc_zba_zbb_zbs_zbc_zbkb_zbkx_zkne_zknd_zknh` with the `lp64d` ABI.

## Run one benchmark

```bash
python3 scripts/run_gem5.py gem5_config_CVA6_patch.py store_fwd.S --variant patch
```

A bare name is enough for both arguments. Configurations are looked up in `gem5_configs/config/`, `gem5_configs/viewer/` and `gem5_configs/CARLA2026/`, and programs in `benchmarks/config/` and `benchmarks/viewer/`, so the full path is only needed for a file kept somewhere else.

What it prints is a metrics table with three columns: `OFFICIAL` is what gem5's counters read, `NET` subtracts the fixed instrumentation overhead of the suite the program belongs to, and `NET (CVA6)` is the same number under the filter the hardware side applies, which is what the two sides are compared on.

Output lands under `results/`: gem5's own output in `results/m5out/` and the files worth keeping in `results/run/`.

| Option               | What it does                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `--variant`          | `stock` for `build/RISCV`, `patch` for `build/RISCV_PATCH`. It must match the configuration used                          |
| `--build`            | Name another build directory, such as `RISCV_EXP` while working on the patch                                              |
| `--no-trace`         | Skip the debug trace, which the tracer turns into the JSON the viewer loads, and which makes a run slow and large         |
| `--suite`            | Force the overhead table. Normally read from the `.overhead_suite` file beside the program, and the run stops without one |
| `--skip-build-check` | Run even when the binary does not match `--variant`, which is otherwise refused. The NET figures then do not apply        |

## The other drivers

| Script                                  | What it does                                                                                                                                                         |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/run_all_gem5_benchmarks.py`    | A whole folder in one go, writing to `results/batch/`, keeping a failed run rather than hiding it                                                                    |
| `scripts/run_MinorFlow_sweep.py`        | The **viewer's** sweep: the configuration cuts used while developing MinorFlow, one run per configuration and workload pair                                          |
| `scripts/run_gem5_config_sweep.py`      | The **matched configuration** search: it rewrites the `TEST` selector in the harness and runs it. `--configs cache` runs the cache geometry list instead of the grid |
| `scripts/check_patch_parity.py`         | Stock build with the stock configuration against the patched build with every switch off. The numbers must match                                                     |
| `scripts/patch_gem5.py`                 | The patch loop: `status`, `create`, `apply`, `revert` and `build`                                                                                                    |
| `scripts/create_all_MinorFlow_jsons.py` | Every trace in a folder to a JSON, passing `--strict`, so a degraded trace ends the batch with exit 3, its JSON still written                                        |
| `scripts/measure_gem5_overhead.py`      | Measures the overhead profiles `run_gem5.py` subtracts, from each suite's empty template on both builds, and with `--write` puts them into it                        |
| `scripts/clean_gem5_runs.py`            | Deletes what a run writes, plus every `__pycache__` it finds                                                                                                         |
| `scripts/serve_MinorFlow.py`            | Serves the viewer over HTTP, since the image has no browser                                                                                                          |

Every one of them answers `--help`. `clean_gem5_runs.py` takes `--dry-run` to list without deleting, `check_patch_parity.py -n`, `measure_gem5_overhead.py -n` and `patch_gem5.py build -n` print the commands without running them, `run_all_gem5_benchmarks.py` takes `--dry-run`, and both sweeps take `--dry-run` to print the plan without running it.

## The three builds and the patch

`MinorCPU_CVA6.patch` is what turns gem5's MinorCPU into the matched core. It is applied in the tree, so `src/` here is patched and `build/RISCV` was made before it went in. `gem5_configs/config/MinorCPU_CVA6.patch` is the copy to read and to edit.

```bash
python3 scripts/patch_gem5.py status     # applied or not, and which builds exist
python3 scripts/patch_gem5.py revert     # take it out of the tree
python3 scripts/patch_gem5.py create     # turn the current tree into the patch file
python3 scripts/patch_gem5.py build      # rebuild, asking PATCH or EXP
```

`create` diffs `src/` against `.pristine_src.tar.xz`, so the image needs no git history for it, and a new file is picked up without a `git add`. It writes git's own patch format, one file at a time in git's order, and leaves out Python caches, editor swap files and the `.orig` and `.rej` a failed patch leaves.

An edited patch belongs in `build/RISCV_EXP` until it is worth adopting, because `build/RISCV_PATCH` is the reference every TEST is measured against. `run_gem5.py` compares the patch's hash against `.built_patch_sha1` and warns when the patch was edited but not rebuilt, since that run does not carry the patch being read. Separately, it refuses a binary that does not match `--variant`, which `--skip-build-check` overrides.

`check_patch_parity.py` is the guard for the one failure an ablation cannot catch: a patch that changes behaviour even with every switch off. It runs the stock build on the stock configuration and the patched build with the mechanisms disabled, and the two must agree.

## Use the viewer

```bash
python3 scripts/serve_MinorFlow.py
```

It listens on port 8000 inside the container, which `make_containers.py` publishes as **8000** on the host, so open `http://localhost:8000/MinorFlow/MinorFlow.html` there. The CVA6 container takes 8001, so both can serve at the same time.

The viewer loads the JSON the tracer makes from a gem5 debug trace:

```bash
python3 MinorFlow/MinorFlow_tracer.py results/run/daxpy_trace.txt -o results/run/daxpy.json
```

The page opens a JSON from the host's disk, dropped onto it or chosen with Load JSON, so either copy the JSON out to the host, with `docker cp` or the fork's `scripts/docker_sync.py pull`, or make a sample of it inside the container, which the served page then offers by name:

```bash
python3 scripts/make_MinorFlow_sample.py results/run/daxpy.json -n 0
```

`-n 0` keeps every record, and the script refuses a JSON of more than the 500,000 records the page renders at once. Without `-n` it keeps the first 3,000. The sample lands in `MinorFlow/tests/` as `daxpy.sample.js`, listed in `MinorFlow/tests/samples.js`, and the page `scripts/serve_MinorFlow.py` serves offers it in its sample picker.

A trace has to be captured with the debug flags the tracer needs. With `--strict` the tracer exits with 3 on a **degraded** trace: one missing a family of those lines, the L1 cache or LSQ lines for instance, so a mechanism could not be observed at all, one cut part way through a line, or one that holds no instruction or no commit. `metadata.degraded` always names each one, whether or not `--strict` is passed. The viewer refuses a JSON whose `metadata.schema_version` is not 7 and asks for it to be regenerated, rather than drawing silent nulls.

`MinorFlow/tests/` already holds a full sample of every program in `benchmarks/viewer/`, one per program and every record of its run, made while this image was built, so Load sample works before anything has been run here. The page offers only what `tests/samples.js` lists that its tracer wrote at schema 7, so a sample made later appears too once its `.sample.js` and the manifest are in `MinorFlow/tests/`. On the host, `python3 scripts/docker_sync.py push gem5` replaces the folder with the checkout's own.

## Benchmarks and configurations

Each benchmark folder carries a one-line `.overhead_suite` file naming the overhead table its programs belong to, so the right fixed cost is subtracted wherever the folder is copied. `benchmarks/config/` is the calibration set and `benchmarks/viewer/` the set written while developing the viewer.

Each harness holds two tables: the calibration grid, which a plain sweep runs, and `CACHE_TESTS` beside it, seventeen entries varying only L1I and L1D size and associativity over more of the benchmark set, laid over the full production configuration in the patched harness and the stock baseline in the stock one. Their ids start at 201 and `--configs cache` is how to ask for them.

The configurations under `gem5_configs/` are kept one folder per origin. `gem5_config_CVA6.py` is the matched configuration for a stock gem5 and `gem5_config_CVA6_patch.py` the one for the patched build. `gem5_config_CVA6_testing.py` and `gem5_config_CVA6_patch_testing.py` are their calibration harnesses, each a table of single-knob perturbations selected by a `TEST` number, and the sweep runs the patched one.

## Cleaning up

```bash
python3 scripts/clean_gem5_runs.py --dry-run    # list, delete nothing
python3 scripts/clean_gem5_runs.py              # list, then ask
```

It deletes `results/m5out/`, `results/run/`, `results/batch/`, `results/sweep_gem5_config/`, `results/sweep_MinorFlow/`, `results/parity/` and every `__pycache__` in the tree, including the ones scons leaves behind. It never touches `build/`, so the three builds survive.

## What is upstream and what is not

gem5 is the work of the gem5 developers and stays under its own terms, preserved in the image as `LICENSE` and `COPYING`, with its own README as `README.gem5.md`. `MinorCPU_CVA6.patch` is a set of changes to gem5's sources: the changes are this project's, and the files they produce remain gem5's under gem5's licence.

What this project adds is listed in `LICENSE.FaMAF`, which also carries the MIT terms it is offered under. `CITATION.cff` is how to cite the image.

## Built with

gem5 v25.0.0.1 at commit `ddd4ae35`, `riscv64-unknown-elf-gcc` 13.2.0, Python 3.12 on Ubuntu 24.04. The three builds are `gem5.opt`, which keeps assertions and the debug flags the traces depend on.

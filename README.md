<img src="assets/FaMAF_CVA6_header.svg" alt="FaMAF CVA6 Project" width="820">

# FaMAF CVA6 Project

The reference RISC-V core for the FaMAF CVA6 Project, and the starting point for new members.

This repository is a frozen fork of the [OpenHW Group CORE-V CVA6](https://github.com/openhwgroup/cva6), a 64-bit, 6-stage RISC-V processor written in SystemVerilog. It is used as the real-hardware side of a thesis at FaMAF, Universidad Nacional de Córdoba, on how closely a gem5 configuration can be made to match a real RISC-V core. The thesis will be published here once it is defended.

Everything runs inside Docker, so you do not have to install CVA6's or gem5's dependencies on your own machine.

## Prerequisites

- A **Debian-based Linux** system (Debian or Ubuntu).
- Enough disk space for the Docker images.

## The project at a glance

The project has two sides. Each one runs a test and records it, as a gem5 debug trace or a CVA6 VCD, which a tracer turns into the JSON a viewer draws as a cycle-by-cycle pipeline view:

- **CVA6 (this repo)**: the real core, simulated in Verilator. `run_CVA6.py` runs a test and writes a VCD, which [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow) renders once its tracer has made a JSON of it.
- **gem5**: the MinorCPU RISC-V model. `run_gem5.py` runs the same test and writes a debug trace, which [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow) renders once its tracer has made a JSON of it.

Both run scripts also print the same metrics table (cycles, instructions, cache misses and accesses, branches, mispredictions, time and IPC), so the two cores can be compared directly. That comparison is the whole point of the project.

## About this fork

- Based on CVA6 **v5.3.0**. `git describe --tags` names the commit a checkout is at, and each published image carries a `sha-<short>` tag naming the commit it was built from.
- A **frozen fork** of CVA6. The upstream dependency submodules have been vendored into the repository, so the core builds without fetching anything external and the exact RTL is pinned.
- **The two viewers are bundled as submodules** under `viewers/`, so a recursive clone gives you the whole toolchain in one place:
  - `viewers/MinorFlow` points to [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow)
  - `viewers/CVA6Flow` points to [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow)
- Target configuration: `cv64a6_imafdc_sv39_hpdcache_wb`.

Clone with the submodules to get the viewers too:

```bash
git clone --recursive https://github.com/FaMAF-CVA6-Project/CVA6.git
# or, if already cloned:
git submodule update --init --recursive
```

## Repository contents

Most of the tree is the standard CORE-V CVA6 layout. The pieces most relevant to this project:

| Path                                                | What it is                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `core/`                                             | The CVA6 core RTL (SystemVerilog).                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `corev_apu/`                                        | The SoC wrapper and testbench infrastructure.                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `verif/`                                            | Verification and simulation harness (Verilator under `verif/sim`).                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `vendor/`                                           | Vendored upstream dependencies, pinned so nothing is fetched.                                                                                                                                                                                                                                                                                                                                                                                                                            |
| [`gem5_config_CVA6/`](gem5_config_CVA6/README.md)   | The gem5 configuration matched to CVA6 and the patch it depends on. `gem5/` holds the configurations, the benchmarks and `MinorCPU_CVA6.patch`, `CVA6/` the same benchmarks for the real core and the target's configuration package, and each side has a `tests/` folder where local, untracked JSONs go.                                                                                                                                                                               |
| [`dockerfiles/`](dockerfiles/gem5/README.md)        | The two image recipes. The container copier is `scripts/docker_sync.py` and each viewer ships the small HTTP server that puts it in the host's browser, `viewers/MinorFlow/scripts/serve_MinorFlow.py` and `viewers/CVA6Flow/scripts/serve_CVA6Flow.py`. Each side also holds the documents its image installs at the container root: a README for the container, `LICENSE.FaMAF`, `CITATION.cff` and the container's ignore list.                                                       |
| `verilator_changes/`                                | Modified copies of two upstream files, each carrying a notice of change. `custom_size_vcds/` windows the waveform dump so the VCD of a long benchmark stays small enough to keep, and has [its own README](verilator_changes/custom_size_vcds/README.md).                                                                                                                                                                                                                                |
| [`viewers/MinorFlow/`](viewers/MinorFlow/README.md) | The MinorFlow viewer, as a submodule.                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| [`viewers/CVA6Flow/`](viewers/CVA6Flow/README.md)   | The CVA6Flow viewer, as a submodule.                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `viewers/FlowCompare.html`                          | The side-by-side comparison viewer, a tracked file of this repository rather than a submodule.                                                                                                                                                                                                                                                                                                                                                                                           |
| [`assets/`](assets/README.md)                       | The project's mark, in the three sizes the documents use, and the palette every page and mark shares. `assets/README.md` says what the mark means and how `scripts/make_logos.py` redraws it.                                                                                                                                                                                                                                                                                            |
| `scripts/`                                          | The repository-wide tools: `check_CVA6_repo.py`, `format_CVA6_repo.py`, `docker_sync.py`, `make_containers.py`, `docker_run.py`, `docker_publish.py`, `check_patch_parity.py`, `patch_gem5.py`, `patch_vcd_window.py`, `create_all_CVA6_repo_jsons.py`, `clean_CVA6_repo.py`, `ignore_big_CVA6_repo_jsons.py`, `get_CVA6_files.py`, `get_gem5_files.py`, `run_gem5_config_sweep.py` and `run_CVA6_config_sweep.py`.                                                                      |
| `scripts/check_CVA6_repo.py`                        | Checks this fork's own files: the scripts, the calibration tables, the patch, the Dockerfiles, the viewer pages, the shared blocks against `scripts/shared_blocks.json` and the viewers' copies, the links, the comment prose and the formatting. `--write-shared-manifest` rewrites the manifest after a deliberate change to a block. Each viewer has the same tool for itself, `check_MinorFlow_repo.py` and `check_CVA6Flow_repo.py`, sharing this one's helpers and check protocol. |
| `scripts/clean_CVA6_repo.py`                        | Deletes the `.list`, `.vcd`, `.fst`, traces and `__pycache__` left in this repository, then offers to run each viewer's own cleaner.                                                                                                                                                                                                                                                                                                                                                     |
| `scripts/ignore_big_CVA6_repo_jsons.py`             | Lists the JSONs too big for GitHub in `.gitignore`.                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `scripts/make_containers.py`                        | Creates both containers, or one, with CPU and memory limits and the viewer port published. Reads what the Docker daemon actually has, picks a build job count that fits, and refuses rather than failing partway.                                                                                                                                                                                                                                                                        |
| `scripts/docker_run.py`                             | Works inside a container without typing the docker commands: `status`, `shell`, `run` through the side's own driver, `exec`, `serve` for the viewer, and `stop`. A stopped container is started first, and nothing is copied, which is `docker_sync.py push`.                                                                                                                                                                                                                            |
| `scripts/docker_publish.py`                         | Rebuilds the images and pushes them to Docker Hub. The build decides what changed, so there is no path list to keep in step with `.dockerignore`. `master` publishes `latest`, every other branch publishes `testing`, and both also get `sha-<short>`.                                                                                                                                                                                                                                  |
| `scripts/check_patch_parity.py`                     | Runs the config benchmarks twice in the gem5 container, once on the stock build with the unpatched config and once on the patched build with every switch off, and compares gem5's own counters. A difference means a patch mechanism is live with its switch off, which no ablation would show, since every TEST is measured against the patched build.                                                                                                                                 |
| `scripts/patch_gem5.py`                             | The loop for working on `MinorCPU_CVA6.patch` inside the gem5 container: `status`, `create` the patch from the tree with its new files, `apply`, `revert` and `build`, which asks whether to remake `RISCV_PATCH` or `RISCV_EXP`.                                                                                                                                                                                                                                                        |
| `scripts/run_CVA6_config_sweep.py`                  | Runs the cache geometry table on the real core, driving `viewers/CVA6Flow/scripts/run_CVA6Flow_sweep.py` with this side's package, benchmarks and results folder.                                                                                                                                                                                                                                                                                                                        |
| `scripts/patch_vcd_window.py`                       | Applies or reverts the windowed waveform dump in `verilator_changes/custom_size_vcds/`, keeping the file it replaces beside it so a container with no git repository can put it back.                                                                                                                                                                                                                                                                                                    |
| `scripts/format_CVA6_repo.py`                       | Formats this fork's own Python with autopep8 at 79 columns, its Markdown with Prettier, and the benchmarks with `.editorconfig`'s trailing whitespace and final newline on both languages, plus operand alignment on the assembly. Scope is the same `OWN_PATHS` the checker uses, so upstream files are never touched, and C++ and Makefiles are out of scope. `--check` reports without changing, which is what `check_CVA6_repo.py`'s `formatter` check runs.                         |
| `scripts/get_CVA6_files.py`                         | Flattens the RTL the Flist manifests name into one folder, `CVA6_files/` by default, which is what the RTL readers expect.                                                                                                                                                                                                                                                                                                                                                               |
| `scripts/make_logos.py`                             | Draws the project's mark into `assets/` and each viewer's into its `docs/`, and with `--patch` puts them into the three pages. Needs `fontTools` and the fonts in `assets/fonts/`.                                                                                                                                                                                                                                                                                                       |
| `scripts/get_gem5_files.py`                         | Fetches the pristine gem5 sources of the RISC-V MinorCPU into `gem5_files/` by default, at the version the gem5 image builds, read from its Dockerfile. The tree is mirrored rather than flattened so `MinorCPU_CVA6.patch` applies to it as it is, and `--check-patch` dry-runs the patch there.                                                                                                                                                                                        |
| `LICENSE.FaMAF`                                     | MIT licence covering this project's own work.                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `LICENSE`, `LICENSE.Berkeley`, `LICENSE.SiFive`     | Upstream licences, preserved.                                                                                                                                                                                                                                                                                                                                                                                                                                                            |

Everything else (`common/`, `util/`, `pd/`, `spyglass/`, `ci/`, `docs/` and so on) is standard upstream CVA6.

## The benchmarks

Each side keeps its test programs in a `benchmarks/` folder of its own, and each viewer repository holds the driver that runs them on its simulator. Both drivers accept the same C and assembly tests and print the same metrics table, so results from CVA6 and gem5 can be compared directly.

- `gem5_config_CVA6/CVA6/benchmarks/`: the CVA6 tests, run by `viewers/CVA6Flow/scripts/run_CVA6.py` on the CVA6 core.
- `gem5_config_CVA6/gem5/benchmarks/`: the gem5 tests, run by `viewers/MinorFlow/scripts/run_gem5.py` on the gem5 MinorCPU RISC-V model.

A run leaves what is worth keeping in `results/run/` under the root: the trace or VCD its tracer turns into a JSON, the `.list` the tracer needs, and `<test>_report.txt` with the measured region and the metrics table. The gem5 side adds `<test>_stats.txt`, gem5's own `stats.txt` renamed after the program. The rest stays in the simulator's own output folder: `results/m5out/` on the gem5 side, and on the CVA6 side `verif/sim/out_<date>/`, which moves to `results/verif/out_<date>/` when the run survives.

The `_report.txt` has two labelled sections, so either can be read or extracted on its own:

```
======================================================================
DISASSEMBLED CODE
======================================================================
   ... the measured region ...
======================================================================
END OF DISASSEMBLED CODE
======================================================================

======================================================================
RESULTS TABLE gem5 daxpy.S  I-cache: 16KiB/4  D-cache: 32KiB/8
Config: gem5_config_CVA6.py
======================================================================
   ... the metrics table, then the clean arrays ...
```

The title names the simulator, the program and the L1 geometries the run used. The line under it names the gem5 configuration and its flags, or the CVA6 target.

When a run **fails**, nothing is deleted. gem5's whole stdout and stderr go to `<test>_error.log` beside that run's output, and the CVA6 build and simulation go to `verif/sim/out_<date>/<test>_run.log`.

Each folder carries a `test_template.c` and a `test_template.S` to start from. Both bracket the region to measure between `MAIN PROGRAM` and `END OF MAIN PROGRAM` markers: the CVA6 side reads the hardware counters around it into `s2` to `s10`, the gem5 side wraps it in `m5_reset_stats` and `m5_dump_stats`. That region is what gets measured and disassembled, so a new test means filling it in.

Each folder also has a batch runner, for when you want the whole set instead of a single test:

```bash
python3 scripts/run_all_CVA6_benchmarks.py [folder] [--target T] [--no-vcd]   # defaults to benchmarks/viewer/ under the CVA6 root
python3 scripts/run_all_gem5_benchmarks.py <config>.py [folder] [-j N] [--variant patch|stock] [--no-trace]   # defaults to the first of benchmarks/viewer/, benchmarks/config/, benchmarks/
```

They collect the C and assembly tests in the folder, skip the templates, run each through the matching driver, and print a pass/fail summary. Tests sharing a name are warned about up front, since outputs are named after the test. `-r` includes subfolders, `--dry-run` lists without running.

Every test that passes has its files moved into `results/batch/` and its leftovers deleted, so the batch lands in one folder rather than spread across the tree. `--out-dir` picks another. It also gathers every run's table and clean arrays into one file there, in the order the tests were listed. The file is named after the run that produced it, `metrics_<config>_<variant>_<build>_<suite>_<flags>.txt` on the gem5 side and `metrics_<target>_<suite>.txt` on the CVA6 side, each part left out when it was not given, so two batches of different builds cannot land on the same name and be mistaken for each other later. Each table inside carries a `Build:` line naming the binary and the overhead table subtracted from it.

A test that **fails** keeps everything, and the closing lines say where. An interrupted test counts as failed, with code 130, and keeps its output too.

On the Verilator side only the first test builds the core. The rest reuse it through `--keep-build`, which is safe because the target and the VCD setting are the same for the whole batch. Pass `--rebuild-each` to rebuild before every test.

The **gem5 batch runs several tests at once**: gem5 is single-threaded, so `-j` (4 by default) gives that many simulations in parallel, each in its own folder under `results/m5out/` and `results/run/` so they cannot overwrite each other's `stats.txt`.

### The calibration sweep

Matching the gem5 model to CVA6 meant perturbing one part of the pipeline at a time and comparing the result against the core. [gem5_config_CVA6/gem5/configs/gem5_config_CVA6_testing.py](gem5_config_CVA6/gem5/configs/gem5_config_CVA6_testing.py) holds that as a table of configurations, `TEST 1` being the matched baseline and every other entry a single-knob change, grouped by the part of the machine it touches, with the workloads that localise it:

```
#   1   adopted baseline                          workload: all
#   2   fetch1FetchLimit 2 -> 1                   workload: matmul_small
#  22   fp_addmul without the double mask         workload: fp_addmul
```

`scripts/run_gem5_config_sweep.py` replays the patched twin of that table, `gem5_config_CVA6_patch_testing.py`, which is its `DEFAULT_CONFIG` and the file it is written for, unless `--config` names another. Run it from `/gem5`:

```bash
python3 scripts/run_gem5_config_sweep.py [-j N] [--configs 1,4-6|grid|cache|all] [--tests daxpy,full_test] [--variant patch|stock] [--no-trace] [--dry-run]
```

It defaults to `--variant patch`, since `DEFAULT_CONFIG` sets parameters only the patch provides. For each configuration it sets `TEST`, runs that entry's workloads through `run_gem5.py`, and moves the results into `results/sweep_gem5_config/` tagged `.config<N>`, plus one gathered metrics file named after the sweep, `metrics_<config>_<variant>...txt`. An entry whose workload is `all` runs `DEFAULT_ALL_TESTS`, the set the baseline was calibrated against, which is wider than what the perturbation rows name.

The harness holds a second table beside the calibration grid, `CACHE_TESTS`, which varies only L1I and L1D size and associativity over more of the benchmark set, each cut laid over the full production configuration, `TEST 40`. Its ids start at 201 and a plain run leaves them out, so `--configs cache` is how to ask for the seventeen of them, `--configs grid` for the table above and `--configs all` for both. The same seventeen cuts exist on the real core in `gem5_config_CVA6/CVA6/configs/cv64a6_imafdc_sv39_hpdcache_wb_config_testing_pkg.sv`, run by `scripts/run_CVA6_config_sweep.py`, where a CFG id plus 199 is the gem5 TEST id. See [gem5_config_CVA6/README.md](gem5_config_CVA6/README.md#the-cache-geometry-list) for the list itself.

The sweep runs `-j` at once, 4 by default, each in its own folder under `results/m5out/` and `results/run/`, deleted once collected. A run that **fails** keeps its folder, under `results/m5out/config<N>_<test>/`, together with the configuration copy it ran. Both parent folders are removed only if the sweep leaves them empty, since a plain `run_gem5.py` run writes into them too.

The sweep never edits the file you point it at: it writes one temporary copy per configuration and deletes them at the end, so an interrupted sweep leaves nothing to restore. `--dry-run` prints the plan without touching anything, and `--tests` takes a bare name, a file name or a path.

### Cleaning up

A VCD or a gem5 trace runs to hundreds of megabytes, and a sweep writes one per configuration per test. Each side has a script that deletes everything its run scripts generate, and nothing else:

```bash
python3 scripts/clean_gem5_runs.py [folders...] [-y] [--dry-run]
python3 scripts/clean_CVA6_runs.py [folders...] [-y] [--dry-run] [--keep-build]
```

`clean_gem5_runs.py` takes `results/m5out/`, `results/run/`, `results/batch/`, the sweep result folders, `results/parity/`, `results/overhead/`, and `__pycache__/`. `clean_CVA6_runs.py` takes `verif/sim/out_<date>/`, `work-ver/`, `results/batch/`, `results/sweep_CVA6Flow/`, `results/sweep_CVA6_config/`, `results/run/`, `results/verif/`, and `__pycache__/`. Extra folders can be named on the command line, for a run made with a custom `--gem5-out-dir` or `--out-dir`.

Both list what they found with its size and ask before deleting. `-y` skips the question, `--dry-run` only lists, and `--keep-build` spares `work-ver/`. Only those fixed names are matched, so nothing tracked in git is ever caught, and cleaning one side never touches the other's results.

Those two clear a run tree. `scripts/clean_CVA6_repo.py` clears what piles up in this repository's own folders afterwards: every `.list`, `.vcd`, `.fst` and debug trace, and every `__pycache__`. A trace is matched on `_trace.` and `.txt`, so a sweep's `<test>_trace.config<N>.txt` goes with the plain `<test>_trace.txt`. The `_report.txt` and `_stats.txt` beside them are the summaries and stay.

```bash
python3 scripts/clean_CVA6_repo.py [-y] [--dry-run] [-v] [--no-viewers]
```

It only ever opens `gem5_config_CVA6/`, `verilator_changes/` and `scripts/`, and a local notes folder when the checkout has one. The two viewers are separate repositories with their own artefacts and their own rules, so it does not walk into them: it offers to run their cleaners afterwards instead, and each decides what to keep on its own side. `--no-viewers` skips the offer.

There are five cleaning scripts in all, and the names say which tree each one touches:

| Script                                              | Where              | What it deletes                                                                                                                   |
| --------------------------------------------------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/clean_CVA6_repo.py`                        | this checkout      | Run artefacts in this checkout's own folders, then offers the two below it                                                        |
| `viewers/MinorFlow/scripts/clean_MinorFlow_repo.py` | MinorFlow checkout | The same, in that repository, keeping `docs/` whole                                                                               |
| `viewers/CVA6Flow/scripts/clean_CVA6Flow_repo.py`   | CVA6Flow checkout  | The same, in that repository, keeping `docs/` whole                                                                               |
| `scripts/clean_gem5_runs.py`                        | gem5 container     | What a gem5 run leaves: `results/m5out/`, `results/run/`, `results/batch/`, sweep folders, `results/parity/`, `results/overhead/` |
| `scripts/clean_CVA6_runs.py`                        | CVA6 container     | What a CVA6 run leaves: `out_<date>/`, `work-ver/`, `results/run/`, `results/batch/`, sweep folders, `results/verif/`             |

A JSON survives all of that, since it is what the viewers load, but it is too big to commit: GitHub warns above 50 MiB and refuses above 100 MiB, and a full run leaves several over 200.

```bash
python3 scripts/ignore_big_CVA6_repo_jsons.py [-y] [--dry-run] [-v] [-l MIB] [--prune]
```

Run it after a sweep. Without `--prune` it only adds, so a second run changes nothing. `--prune` drops the entries whose file has gone or shrunk, and `-l` sets a different threshold in MiB. A file git already tracks is reported rather than ignored, since an ignore rule has no effect on a file git is already carrying.

---

## The matched gem5 configuration

[gem5_config_CVA6/](gem5_config_CVA6/) is where the comparison lands. It holds the gem5 MinorCPU configuration matched to `cv64a6_imafdc_sv39_hpdcache_wb`, in which every value is either derived from a CVA6 RTL localparam or is a gem5-side estimate where CVA6 has no clean counterpart.

It comes in two versions, so the same core can be run on either gem5 build:

- `gem5_config_CVA6/gem5/configs/gem5_config_CVA6.py` runs on a **stock gem5**, using only what upstream already provides.
- `gem5_config_CVA6/gem5/configs/gem5_config_CVA6_patch.py` runs on a **patched gem5** and adds the mechanisms the patch makes available.

Each has a `_testing` twin, `gem5_config_CVA6_testing.py` and `gem5_config_CVA6_patch_testing.py`, which is the same core wrapped in the calibration table of single-knob perturbations that `run_gem5_config_sweep.py` replays.

### Why there is a patch

Some of what CVA6 does has no counterpart in stock gem5, and no parameter that comes close. A fence that walks the data cache writing back every dirty line, a load-store unit with no store-to-load forwarding, a cache that picks its victim and starts its writeback at miss time rather than at fill, direct branch targets computed in the fetch path instead of read from a BTB: each is a rule in the RTL, and each changes the cycle count by more than the calibration's error bar.

`gem5_config_CVA6/gem5/configs/MinorCPU_CVA6.patch` adds them, one gem5 parameter per rule, every one defaulting to the stock behaviour so a patched binary runs an unpatched configuration unchanged. That is what makes the difference measurable: the same binary runs with a mechanism on and off, and the gap is what that rule is worth.

The config [README](gem5_config_CVA6/README.md#the-patch) has the whole of it: what each change models and which RTL line it comes from, the new parameters, SimObjects and statistics, how to apply and revert the patch, and the six divergences that remain.

---

## Docker setup

### Installing Docker

```bash
sudo apt-get update
sudo apt-get install -y docker.io
```

Verify the installation:

```bash
sudo docker version
```

### Enabling graphical applications

To run graphical tools (for example GTKWave) from inside the container:

```bash
xhost +
socat TCP-LISTEN:6000,reuseaddr,fork UNIX-CLIENT:/tmp/.X11-unix/X0
```

### Optional configuration

Recommended, to make working with Docker easier.

**Start Docker automatically on boot:**

```bash
sudo systemctl enable docker
```

**Run Docker without `sudo`.** Replace `<user_name>` with your username (run `whoami` to get it):

```bash
sudo groupadd docker
sudo usermod -aG docker <user_name>
newgrp docker
```

Then this should work without `sudo`:

```bash
docker run hello-world
```

**Access the container from VSCode:** install the `Docker` extension from the Extensions panel.

### Managing the Docker service

```bash
sudo systemctl start docker # start
sudo systemctl status docker # check
sudo systemctl stop docker # stop
```

---

## Getting the images

Two ways: pull the published image, or build it from this working tree.

### Pulling

Two images are published on Docker Hub. Check the tags and pull the latest.

**CVA6 + Verilator** ([manuel313/famaf_cva6](https://hub.docker.com/r/manuel313/famaf_cva6/tags)):

```bash
docker pull manuel313/famaf_cva6:latest
```

**gem5 (MinorCPU)** ([manuel313/famaf_gem5](https://hub.docker.com/r/manuel313/famaf_gem5/tags)):

```bash
docker pull manuel313/famaf_gem5:latest
```

Verify:

```bash
docker images
```

### Building

The recipes in [dockerfiles/](dockerfiles/) build the same images from **this working tree**, which is the point: both drivers run against the container's root by default, `/CVA6` and `/gem5`, so an RTL file or a configuration edited on the host only reaches the simulation by being copied in. Building is how you run a modified core rather than the one the published image was made from.

Both build from the repository **root**, not from the recipe's own folder:

```bash
docker build -f dockerfiles/CVA6/Dockerfile -t manuel313/famaf_cva6:build .
docker build -f dockerfiles/gem5/Dockerfile -t manuel313/famaf_gem5:build .
```

`.dockerignore` keeps the traces, VCDs, JSONs and git history out of the build context, so what is uploaded to the daemon is about a hundred megabytes rather than the whole tree.

**These are heavy builds.** The cost is three full gem5 builds on the gem5 side, and on the CVA6 side Verilator, Spike and the samples, since `util/toolchain-builder` fetches a prebuilt RISC-V toolchain rather than compiling one.

The figures below were measured on 20 September, building both from scratch with no layer cache on a 16-core laptop with 15 GB of memory, at the job counts named.

|                              | Disk while building | Finished image | Time             | Memory per job |
| ---------------------------- | ------------------- | -------------- | ---------------- | -------------- |
| `manuel313/famaf_cva6:build` | ~30 GB              | 12.4 GB        | 50 min at 5 jobs | ~2 GB          |
| `manuel313/famaf_gem5:build` | ~45 GB              | 25.4 GB        | 3 h 15 at 2 jobs | ~4 GB          |

The last step of each recipe is the viewer's samples, and it is a real run of each of that viewer's programs that fits the page's record limit: 6 minutes on the gem5 side, and 18 on the CVA6 side, where the Verilator model is built first and each run writes a waveform of a few gigabytes. Every trace, waveform and intermediate JSON is deleted in the same layer, so what the image keeps is the samples themselves, 0.5 GB on the gem5 side and 0.7 GB on the CVA6 side. The CVA6 tracer is the one step that wants memory rather than cores: reading the largest waveform peaks near 10 GB, so a machine with less should build that image with the sample list shortened through `--build-arg CVA6FLOW_OVER_LIMIT`. On the run measured here the gem5 side came closest to the edge, at 1.6 GB free while linking the first `gem5.opt`, which is why two jobs rather than three.

Memory is what actually fails a build, and it fails as a compiler killed with no useful message. Both recipes take a `JOBS` argument, and it should be no higher than your RAM in GB divided by the per-job figure above:

```bash
docker build --build-arg JOBS=2 -f dockerfiles/gem5/Dockerfile -t manuel313/famaf_gem5:build .
```

On Docker Desktop the VM has its own memory cap, in Settings, Resources, and it is what the build sees rather than the host's. The Linux engine has no such cap. `docker system prune` frees the space earlier attempts left behind.

The two images carry different halves of the project on purpose. `manuel313/famaf_cva6:build` has the RTL, the CVA6 benchmarks and CVA6Flow, with the gem5 configurations, the gem5 benchmarks and MinorFlow removed. `manuel313/famaf_gem5:build` has gem5 built three times, the matched configurations and their harnesses, the gem5 benchmarks and MinorFlow. Both keep the drivers in `scripts/` and run them from the root, which is where the commands below are run from.

---

## Moving files in and out

The images carry their own copy of the repository, `/CVA6` in the CVA6 image and `/gem5` in the gem5 one, so a benchmark you edit on the host is not the one the container runs. `docker cp` moves it either way, with the container stopped or running:

```bash
# host -> container: a test and the driver that runs it
docker cp gem5_config_CVA6/CVA6/benchmarks/daxpy.S CVA6:/CVA6/benchmarks/config/
docker cp viewers/CVA6Flow/scripts/run_CVA6.py     CVA6:/CVA6/scripts/
docker cp gem5_config_CVA6/gem5/benchmarks/daxpy.S gem5:/gem5/benchmarks/config/
docker cp viewers/MinorFlow/scripts/run_gem5.py    gem5:/gem5/scripts/
docker cp gem5_config_CVA6/gem5/configs/.          gem5:/gem5/gem5_configs/config/

# container -> host: what a run produced, all of it under results/
docker cp CVA6:/CVA6/results/run/         ./results/run/
docker cp gem5:/gem5/results/batch/       ./results/batch/
docker cp gem5:/gem5/results/sweep_gem5_config/ ./
```

A trailing `/.` on the source copies the contents of a folder rather than the folder itself.

`scripts/docker_sync.py` does both directions without the paths. Four things to do, one word each, and the container is `CVA6`, `gem5`, or left out for both:

```bash
python3 scripts/docker_sync.py push      # send this checkout in
python3 scripts/docker_sync.py pull      # bring the results back
python3 scripts/docker_sync.py jsons     # pull, then make the JSONs
python3 scripts/docker_sync.py list      # show the run output inside, copy nothing

python3 scripts/docker_sync.py push gem5 # one container
python3 scripts/docker_sync.py jsons -y  # take every folder without asking
python3 scripts/docker_sync.py push -n   # say what would be copied
```

**push** sends, per container:

| What                                                                                                   | Where it lands                                                                                  |
| ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| The drivers, the sweeps, the cleaner, the viewer's own server and the batch JSON converter             | `scripts/`, whichever folder they come from here                                                |
| The gem5 configurations                                                                                | `gem5_configs/config/`, `gem5_configs/viewer/` and `gem5_configs/CARLA2026/` by origin          |
| The CVA6 configuration packages                                                                        | `CVA6_configs/`, and the production one also to `/CVA6/core/include/`, where the build reads it |
| The calibration benchmarks                                                                             | `benchmarks/config/`                                                                            |
| The programs written while developing the viewer                                                       | `benchmarks/viewer/`                                                                            |
| The viewer page and its tracer                                                                         | `MinorFlow/` or `CVA6Flow/`                                                                     |
| The container's own `README.md`, `LICENSE.FaMAF` and `CITATION.cff`, plus the CVA6 side's `.gitignore` | the container root                                                                              |

It is the one to remember: a container keeps its own copy of everything, so editing `run_gem5.py` here changes nothing inside until it is pushed.

A gem5 configuration given by name alone is looked up in `gem5_configs/`, a sweep's package in `CVA6_configs/`, and a benchmark in either `benchmarks/` folder, so `python3 scripts/run_gem5.py gem5_config_CVA6.py daxpy.S` works from `/gem5` without any paths.

The gem5 one is `gem5_configs/` rather than `configs/` because gem5's own tree already has a `configs/`. Overlaying it would mix this project's files into gem5's own, where a repository made in the container later would list them as untracked and `git clean -fd` would take them.

Everything a run keeps goes under `results/`: `results/m5out/`, `run/`, `batch/`, `sweep_*/` and `parity/`, plus `verif/` on the CVA6 side, which is where a surviving `out_<date>/` is moved at the end of a run. Only `work-ver/` and a failed run's `verif/sim/out_<date>/` stay outside it. One `.dockerignore` line covers `results/`, and **pull** still offers each of them separately so a 17 GB folder can be left behind.

The production package pushed into `/CVA6/core/include/` is the same file as the one already there, so a push leaves the build unchanged. The CVA6Flow and testing packages stay in `CVA6_configs/`, and each sweep installs its own over the live one only while it runs, restoring it afterwards.

**pull** lists the run-output folders that actually exist, with their sizes and what produced them, and asks which to bring back. That list comes from the cleaners' folder tables, so a folder a cleaner learns to delete shows up here too. Folders land in `container_results/<container>/`. **jsons** is `pull` followed by the viewer's batch JSON converter over whatever came back.

## Working with the CVA6 image

### Create the container

Create a container named `CVA6` with a Bash terminal and permission to run graphical applications:

```bash
docker run -it --name CVA6 -p 8001:8000 \
           -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix \
           manuel313/famaf_cva6:latest bash
```

Type `exit` to leave.

`-p 8001:8000` is what lets `serve_CVA6Flow.py` put CVA6Flow in the host's browser later. The CVA6 side takes host port 8001 and the gem5 side 8000, so both containers can serve their viewer at the same time.

Or let [`scripts/make_containers.py`](scripts/make_containers.py) do it. It reads what the Docker daemon actually has, publishes the port, passes the display through, and caps CPU and memory so a simulation cannot take the machine down with it:

```bash
python3 scripts/make_containers.py --check    # what this machine can do
python3 scripts/make_containers.py --pull     # both containers
python3 scripts/make_containers.py CVA6       # just this one
```

It refuses rather than failing partway when memory or disk is short, leaves an existing container alone unless `--force` says otherwise, and `-n` prints the commands without running them. With `--build` it builds from this working tree instead of pulling, choosing a `JOBS` value from the daemon's memory rather than the default in the recipe.

### Start, enter and stop

[`scripts/docker_run.py`](scripts/docker_run.py) does this without the paths and flags. Six things to do, one word each, and a stopped container is started first:

```bash
python3 scripts/docker_run.py status         # what is up, its image, its URL
python3 scripts/docker_run.py shell CVA6     # a shell at the container root
python3 scripts/docker_run.py serve CVA6     # start the viewer server, print its URL
python3 scripts/docker_run.py stop           # stop both

python3 scripts/docker_run.py run gem5 -- gem5_config_CVA6.py daxpy.S --no-trace
python3 scripts/docker_run.py exec CVA6 -- ls benchmarks
```

`run` puts the side's own driver in front of what follows `--`, so which driver a side uses is one less thing to remember. `exec` runs the command as given. Neither copies anything in, which is what `docker_sync.py push` is for.

The same thing by hand:

```bash
docker start CVA6 # start
docker exec -e DISPLAY=$DISPLAY -it CVA6 bash # enter
docker stop CVA6 # stop
```

### Rebuild and publish the images

After the first build, [`scripts/docker_publish.py`](scripts/docker_publish.py) rebuilds and pushes to Docker Hub:

```bash
python3 scripts/docker_publish.py --check    # what would be rebuilt and pushed
python3 scripts/docker_publish.py            # both sides
python3 scripts/docker_publish.py gem5       # one side
```

Which image a change affects is not listed anywhere. The build decides it: a cached rebuild reuses every layer above the edit, so an untouched image comes out with the same ID and is not pushed. That is why there is no list of paths to keep in step with `.dockerignore`, and why a script or benchmark edit republishes in minutes while a change to `MinorCPU_CVA6.patch` pays for gem5's double build again.

`master` publishes `latest`, every other branch publishes `testing`, and both also get `sha-<short>` so a moving tag stays traceable to a commit. Asking for `latest` off `master` needs `--force`. It refuses when neither the local build nor the published image is here, since that would be the cold build rather than a rebuild, and it pushes with inline cache so a later pull can seed one.

### Run a test

Optionally sanity-check that the C compiles on the host first:

```bash
gcc -Wall -Wextra -O3 -g -std=c99 -o <executable_name> <program_name>.c
./<executable_name>
```

Then run it on the Verilated CVA6 to produce the VCD and the metrics table:

```bash
python3 scripts/run_CVA6.py [target] <test> [--lang auto|c|asm] [--no-vcd] [--keep-build]
```

- `[target]`: the CVA6 configuration. Optional, and defaults to `cv64a6_imafdc_sv39_hpdcache_wb`, the one this fork targets and the one the overhead tables were measured on. The cache geometry printed in the table's title is read from that target's `core/include/<target>_config_pkg.sv`.
- `<test>`: a `.c` or `.S/.s/.asm` file. The type is auto-detected from the extension, and `--lang` forces it.
- `--no-vcd`: do not write the VCD, and report metrics only.
- `--keep-build`: reuse the Verilated model in `work-ver` instead of rebuilding it. The model does not depend on the test, so this turns a rebuild into a plain run. Only reuse it across runs with the same target and the same VCD setting, since both are compiled into the model.

It compiles the test, runs it on the Verilated CVA6, disassembles it, and prints a metrics table (cycles, instructions, cache misses and accesses, branches, mispredictions, time and IPC) with a configurable "net" column that discounts the fixed cost of the measurement code.

The simulation writes to `verif/sim/out_<date>/` as usual, which moves to `results/verif/out_<date>/` when the run survives, and the three files worth keeping, the VCD, the `.list` and the `<test>_report.txt` with the measured region and the table, are gathered in `results/run/` under the root, the VCD moved rather than copied so a large one never needs its size twice.

A VCD is written by default. **The viewer does not read it directly.** Turn it into a JSON first. The tracer takes the instruction text from the `.list` beside the VCD, which it finds on its own under the same name, and `--disasm-list` names a listing kept anywhere else:

```bash
python3 CVA6Flow/CVA6Flow_tracer.py results/run/daxpy.vcd -o results/run/daxpy.json
```

Then open `daxpy.json` in [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow). `python3 scripts/create_all_CVA6Flow_jsons.py results/run` does a whole folder at a time. On the host, `scripts/create_all_CVA6_repo_jsons.py` does the whole checkout, skipping a VCD without its `.list` as the viewer's batch does, and then offers each viewer's own batch over that viewer's `tests/`.

To use the viewer from inside the container, serve it and open the page on the host, which needs no browser in the image and no X11:

```bash
python3 scripts/serve_CVA6Flow.py    # then open http://localhost:8001/CVA6Flow/CVA6Flow.html
```

The page opens a JSON from the host's disk, so bring it out first: on the host, `python3 scripts/docker_sync.py pull CVA6` offers `results/run/`, the JSON with it, among the folders to bring back. The container listens on port 8000 and publishes it on host port 8001. Publishing the port at creation, `docker run -p 8001:8000 ...`, is the portable way and the one [`scripts/make_containers.py`](scripts/make_containers.py) uses. A container already made without it is not a dead end: where the host routes to the container network, which is the normal Linux bridge, the page is reachable at the container's own address instead. `python3 scripts/docker_run.py serve` starts the server and prints whichever of the two applies, so an existing container does not have to be remade and its results lost.

### Limitations and considerations

**C programs:**

- Only `stdio.h`, `stdint.h` and `string.h` are available.
- `malloc` and `free` cannot be used.

**`veri-testharness` simulator:**

- The core runs for at most 2 million cycles or 500 seconds, whichever comes first.

---

## Working with the gem5 image

### Create the container

Create a container named `gem5` with a Bash terminal and permission to run graphical applications:

```bash
docker run -it --name gem5 -p 8000:8000 \
           -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix \
           manuel313/famaf_gem5:latest bash
```

Type `exit` to leave.

### Start, enter and stop

```bash
docker start gem5 # start
docker exec -e DISPLAY=$DISPLAY -it gem5 bash # enter
docker stop gem5 # stop
```

### Run a test

From `/gem5`, run a test to produce its debug trace and the metrics table:

```bash
python3 scripts/run_gem5.py <config>.py <test> [--variant patch|stock] [--lang auto|c|asm] [--no-trace]
```

- `<config>.py`: the gem5 MinorCPU configuration script.
- `<test>`: a `.c` or `.S/.s/.asm` file, auto-detected as above (`--lang` to force).
- `--variant`: which build to run, `stock` (default) or `patch`. It picks both the binary, `build/RISCV/` or `build/RISCV_PATCH/`, and the overhead profile measured on that build, which `measure_gem5_overhead.py` in the container measures again from the empty templates. The chosen build is named in the table header.
- The two builds are indistinguishable from the outside, so before each run the script greps the binary for a SimObject only the patch adds and refuses to start when it does not match `--variant`. `--skip-build-check` runs anyway, for a deliberate cross-check where the NET figures are known not to apply.
- `--build`: run any other build instead, by directory name under `build/`, by path to one, or by path to the binary. The overhead profile still follows `--variant`.
- `--no-trace`: do not write the trace, and report metrics only.
- anything else: passed on to the configuration script, so a configuration that defines its own options gets them here. Put them after a `--` when a flag takes a value or its name collides with one of the above.

It compiles the test (linking gem5's `m5op.S` so the test can call `m5_reset_stats` and `m5_dump_stats`), runs gem5 into `results/m5out/`, disassembles the test, and prints the same metrics table as the CVA6 side, read from gem5's `stats.txt`.

On a patched build the table carries a third column, `NET (CVA6)`, beside `NET`. The HPDcache PMU re-presents a demand on every cycle it holds a request off, so the core's access counts run above gem5's. The patch counts those cycles, under whichever of its two forms is configured: blocking charges `preemptionBlockedCycles`, and accept-and-charge, which the production configuration uses, charges `windowTriggerCycles` and `windowOverlapCycles` instead. The column adds all three to the two cache-access rows, which is what the patch's own `cva6ComparableDemandAccesses` adds up, so the gem5 table can be read against the CVA6 one row for row.

gem5 writes to `results/m5out/`, and the test is compiled there too, so a run is self-contained. The four keepers, the trace, the `.list`, `<test>_report.txt` and `<test>_stats.txt`, are copied to `results/run/` under the root. `--gem5-out-dir` and `--results-dir` move either folder, which is how concurrent runs stay apart.

The trace is `results/run/<test>_trace.txt`. **The viewer does not read it directly.** Turn it into a JSON first, which is what MinorFlow loads:

```bash
python3 MinorFlow/MinorFlow_tracer.py results/run/daxpy_trace.txt -o results/run/daxpy.json
```

Then open `daxpy.json` in [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow). Parsing the trace once on disk is what lets a multi-gigabyte run open in a browser at all. `python3 scripts/create_all_MinorFlow_jsons.py results/run` does a whole folder at a time. On the host, `scripts/create_all_CVA6_repo_jsons.py` does the whole checkout, and then offers each viewer's own batch over that viewer's `tests/`.

To use the viewer from inside the container, serve it and open the page on the host, which needs no browser in the image and no X11:

```bash
python3 scripts/serve_MinorFlow.py    # then open http://localhost:8000/MinorFlow/MinorFlow.html
```

The page opens a JSON from the host's disk, so bring it out first: on the host, `python3 scripts/docker_sync.py pull gem5` offers `results/run/`, the JSON with it, among the folders to bring back. The container listens on port 8000 and publishes it on host port 8000. Publishing the port at creation, `docker run -p 8000:8000 ...`, is the portable way and the one [`scripts/make_containers.py`](scripts/make_containers.py) uses. A container already made without it is not a dead end: where the host routes to the container network, which is the normal Linux bridge, the page is reachable at the container's own address instead. `python3 scripts/docker_run.py serve` starts the server and prints whichever of the two applies, so an existing container does not have to be remade and its results lost.

---

## The viewers

Both are dependency-free HTML pages with a live demo on GitHub Pages:

- [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow): renders the JSON `CVA6Flow_tracer.py` makes from the VCD `run_CVA6.py` writes.
- [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow): renders the JSON `MinorFlow_tracer.py` makes from the debug trace `run_gem5.py` writes.

Neither reads a raw trace or VCD: a run leaves gigabytes and a browser cannot hold that, so the tracer does the parsing once on disk and the viewer loads the result.

Each image makes a full sample of every one of that viewer's own programs while it is being built, so the page's Load sample button works in a fresh container with nothing run in it. They land in `MinorFlow/tests/` and `CVA6Flow/tests/`, one file per program holding every record of its run, and the four CVA6Flow programs that run past the 500,000 records a page renders at once are left out. `python3 scripts/docker_sync.py push` replaces a container's folder with this checkout's, and each viewer's `scripts/make_<Viewer>_sample.py` writes a sample from a JSON, with `-n 0` for the whole run.

`viewers/FlowCompare.html` puts the two side by side and measures the drift between them. It takes one JSON of each kind, dropped onto the page together or chosen slot by slot, and `metadata.tool` decides which slot each belongs in. Served from `viewers/`, it also offers **Load sample pair** for every program both viewers have a sample of, which is what the pair of `tests/` folders is for:

```bash
python3 viewers/MinorFlow/scripts/serve_MinorFlow.py --root viewers    # then open /FlowCompare.html
```

---

## Licensing and attribution

The CVA6 core and its dependencies are the work of the [OpenHW Group](https://github.com/openhwgroup/cva6) and contributors, under their original licences (see `LICENSE`, `LICENSE.Berkeley` and `LICENSE.SiFive`), which are preserved here.

Everything added by this project is the work of the FaMAF CVA6 Project and remains the copyright of its authors, released under the MIT License in [LICENSE.FaMAF](LICENSE.FaMAF):

- the tools under `scripts/`,
- the dockerfiles and the container documents under `dockerfiles/`,
- the gem5 configuration that matches CVA6, its patch and the benchmarks on both sides, under `gem5_config_CVA6/`,
- the changes in `verilator_changes/`, whose files stay under their upstream licences,
- the comparison viewer, `viewers/FlowCompare.html`,
- the documentation written for this fork, starting with this README,
- and the two viewer submodules, [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow) and [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow), which carry the same MIT licence in their own repositories.

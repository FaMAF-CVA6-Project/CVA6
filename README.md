# FaMAF CVA6 Project

The reference RISC-V core for the FaMAF CVA6 Project, and the starting point for new members.

This repository is a frozen fork of the [OpenHW Group CORE-V CVA6](https://github.com/openhwgroup/cva6), a 64-bit, 6-stage RISC-V processor written in SystemVerilog. It is used as the real-hardware side of an undergraduate thesis at FaMAF, Universidad Nacional de Córdoba, on how closely a gem5 configuration can be made to match a real RISC-V core. The full thesis will be published here after the defence (August 2026).

Everything runs inside Docker, so you do not have to install CVA6's or gem5's dependencies on your own machine.

## Prerequisites

- A **Debian-based Linux** system (Debian or Ubuntu).
- Enough disk space for the Docker images.

## The project at a glance

The project has two sides. Each one runs a test and produces a trace that a visualizer turns into a cycle-by-cycle pipeline view:

- **CVA6 (this repo)**: the real core, simulated in Verilator. `run_CVA6.py` runs a test and writes a VCD, which [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow) renders.
- **gem5**: the MinorCPU RISC-V model. `run_gem5.py` runs the same test and writes a debug trace, which [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow) renders.

Both run scripts also print the same metrics table (cycles, instructions, cache misses and accesses, branches, mispredictions and IPC), so the two cores can be compared directly. That comparison is the whole point of the project.

## About this fork

- Based on CVA6 **v5.3.0**. This repository is pinned at commit `0ea2362e`, and the Docker image at `v5.3.0-89-g272e6e51`.
- A **frozen fork** of CVA6. The upstream dependency submodules have been vendored into the repository, so the core builds without fetching anything external and the exact RTL is pinned.
- **The two visualizers are bundled as submodules** under `viewers/`, so a recursive clone gives you the whole toolchain in one place:
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

| Path                                            | What it is                                                                                         |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `core/`                                         | The CVA6 core RTL (SystemVerilog).                                                                 |
| `corev_apu/`                                    | The SoC wrapper and testbench infrastructure.                                                      |
| `verif/`                                        | Verification and simulation harness (Verilator under `verif/sim`).                                 |
| `vendor/`                                       | Vendored upstream dependencies, pinned so nothing is fetched.                                      |
| `benchmarks/CVA6/`                              | The CVA6 tests, `run_CVA6.py`, `run_all_CVA6_benchmarks.py` and `clean_CVA6.py`.                    |
| `benchmarks/gem5/`                              | gem5 benchmarks, `run_gem5.py`, `run_all_gem5_benchmarks.py` and `clean_gem5.py`. |
| `viewers/MinorFlow`                             | The MinorFlow visualizer, as a submodule.                                                          |
| `viewers/CVA6Flow`                              | The CVA6Flow visualizer, as a submodule.                                                           |
| `gem5_config_CVA6/`                             | The gem5 configuration matched to CVA6, and the paired runs from both sides.                       |
| `verilator_changes/`                            | Local changes to the Verilator harness. The memory-latency experiment under it is set aside for now and is untracked. |
| `dockerfiles/`                                  | Docker files used to create the images.                                                                   |
| `LICENSE.FaMAF`                                 | MIT licence covering this project's own work.                                                      |
| `LICENSE`, `LICENSE.Berkeley`, `LICENSE.SiFive` | Upstream licences, preserved.                                                                      |

Everything else (`common/`, `util/`, `pd/`, `spyglass/`, `ci/`, `cva6_docs/` and so on) is standard upstream CVA6.

## The benchmarks

`benchmarks/` holds the test programs used in the project plus the driver scripts that run them on each simulator. Both drivers accept the same C and assembly tests and print the same metrics table, so results from CVA6 and gem5 can be compared directly.

- `benchmarks/CVA6/`: the CVA6 tests and `run_CVA6.py` (runs on the CVA6 core).
- `benchmarks/gem5/`: the gem5 tests and `run_gem5.py` (runs on the gem5 MinorCPU RISC-V model).

Whichever driver you use, a run leaves the files worth keeping in a `run_results/` folder next to the script: the trace the viewer renders, the disassembly listing its tracer needs, and the `<test>_report.txt` with the measured region and the metrics table. The gem5 side adds a fourth, `<test>_stats.txt`, gem5's own `stats.txt` renamed after the program. Everything else stays where the simulator put it, `verif/sim/out_<date>/` on the CVA6 side and `m5out/` on the gem5 side.

The `_report.txt` is written in two labelled sections, so the code and the numbers can be told apart at a glance and either can be pulled out by a script:

```
======================================================================
DISASSEMBLED CODE
======================================================================
   ... the measured region ...
======================================================================
END OF DISASSEMBLED CODE
======================================================================

======================================================================
RESULTS TABLE gem5 daxpy.S  ICache: 16KiB/4  DCache: 32KiB/8
Config: gem5_config_CVA6.py
======================================================================
   ... the metrics table, then the clean arrays ...
```

The title line names the simulator, the program and the two L1 geometries the run actually used. The line under it names what was simulated: the gem5 configuration file with the flags it was given, or the CVA6 target on the Verilator side.

Each folder also carries a `test_template.c` and a `test_template.S` to start a new test from. The template brackets the region to measure between `MAIN PROGRAM` and `END OF MAIN PROGRAM` comment markers: on the CVA6 side it reads the hardware performance counters around that region and leaves the deltas in `s2`–`s10`, and on the gem5 side it wraps the region in `m5_reset_stats` and `m5_dump_stats`. That region is what each driver measures and what it prints as disassembly, so writing a new test means filling it in.

Each folder also has a batch runner, for when you want the whole set instead of a single test:

```bash
python3 run_all_CVA6_benchmarks.py <target> [folder] [--no-vcd]   # defaults to /cva6/benchmarks/
python3 run_all_gem5_benchmarks.py <config>.py [folder] [-j N] [--no-trace]   # defaults to /gem5/benchmarks/
```

They collect the C and assembly tests in the folder, skip the templates, run each one through the corresponding driver, and print a pass/fail summary with per-test timings at the end. A failing test does not stop the batch. Tests that share a name are reported up front as a warning, since the drivers name their outputs after the test and would overwrite each other. Add `-r` to include subfolders, or `--dry-run` to see the list and the name clashes without running anything.

Every test that passes has its files moved into a `batch_results/` folder and its leftovers deleted, so the whole batch lands in one folder instead of a trace per test spread across the tree. `--out-dir` picks a different folder.

The batch also writes a `metrics.txt` into that folder, holding every run's metrics table and clean arrays in the order the tests were listed, so the whole batch can be read without opening one `_report.txt` per test.

A test that **fails** is the exception: nothing of its is collected or deleted, so its output stays where the simulator wrote it and is still there when the batch ends. The final line says where.

On the Verilator side only the first test builds the core. The rest reuse it through `--keep-build`, which is safe because the target and the trace setting are the same for the whole batch. Pass `--rebuild-each` to rebuild before every test.

The **gem5 batch runs several tests at once**. gem5 is single-threaded, so `-j` (4 by default) gives you that many simulations in parallel, each working in its own folder under `m5out/` and `run_results/` so they cannot overwrite each other's `stats.txt`. `-j 1` goes back to one at a time with the output streaming live. Above that, each test's output is printed as one block when it finishes, and the summary is still in the order the tests were listed.

### The calibration sweep

Matching the gem5 model to CVA6 meant perturbing one part of the pipeline at a time and comparing the result against the core. [gem5_config_CVA6/gem5/gem5_config_CVA6_testing.py](gem5_config_CVA6/gem5/gem5_config_CVA6_testing.py) holds that as a table of configurations, `TEST 1` being the matched baseline and every other entry a single-knob change, with the workloads that localize it:

```
#   1   adopted baseline                            workload: all
#   4   fetch1FetchLimit 2 -> 1 (starvation)        workload: matmul_small
#  21   fp_addmul without the double mask           workload: fp_addmul
```

`run_CVA6_testing_sweep.py`, next to it, replays the whole thing. It always sweeps its own `DEFAULT_CONFIG`, the file it is written for. Run it from `/gem5`:

```bash
python3 run_CVA6_testing_sweep.py [-j N] [--configs 1,4-6] [--tests-dir programs] [--no-trace] [--list]
```

For each configuration it sets `TEST`, runs that entry's workloads through `run_gem5.py`, and moves the files out of `run_results/` into `CVA6_testing_sweep_results/` as `<test>_trace.config<N>.txt`, `<test>_report.config<N>.txt`, `<test>_stats.config<N>.txt` and `<test>.config<N>.list`. Every metrics table is also gathered into one `metrics.txt` in that folder, labelled by configuration and test. An entry whose workload is `all` runs the `DEFAULT_ALL_TESTS` list at the top of the script, the set the baseline was calibrated against, which is wider than what the perturbation rows name.

The sweep runs `-j` simulations at once, 4 by default, so a full sweep of every configuration is worth starting. Each run works in its own folder under `m5out/` and `run_results/`, which is what makes that safe, and once collected that folder is deleted. A run that **fails** is the exception: nothing of its is collected or deleted, so its output stays under `m5out/config<N>_<test>/` and is still there at the end. Both parent folders are removed if the sweep leaves them empty, and left alone otherwise, since a plain `run_gem5.py` run writes into them too.

The sweep never edits the file you point it at: it writes one temporary copy per configuration with the selector set, runs those, and deletes them at the end. So an interrupted sweep leaves nothing to restore, and two sweeps can run at once. `--list` prints the plan without touching anything. A workload matching no file is reported with the closest filenames, and any configuration left with nothing to run is called out rather than skipped in silence.

### Cleaning up

Runs pile up: a VCD or a gem5 trace runs to hundreds of megabytes, and a sweep writes one per configuration per test. Each side has a script that deletes everything its run scripts generate, and nothing else:

```bash
python3 clean_gem5.py [folders...] [-y] [--dry-run]                    # from the gem5 root
python3 clean_CVA6.py [folders...] [-y] [--dry-run] [--keep-build]
```

`clean_gem5.py` takes `m5out/`, `batch_results/`, the sweep result folders, the `run_results/` beside each runner, and `__pycache__/`. `clean_CVA6.py` takes `verif/sim/out_<date>/`, `work-ver/`, `batch_results/`, `CVA6Flow_sweep_results`, `run_results/`, and `__pycache__/`. Extra folders can be named on the command line, for a run made with a custom `--gem5-out-dir` or `--out-dir`.

Both list what they found with its size and ask before deleting; `-y` skips the question and `--dry-run` only lists. `--keep-build` spares `work-ver/`, so the next Verilator run can still reuse the model with `--keep-build`.

The benchmark scripts are kept here for version control, but each one is run inside its own Docker image, from the "Run a test" sections below.

---

## The matched gem5 configuration

[gem5_config_CVA6/](gem5_config_CVA6/) is where the comparison lands. It holds the gem5 MinorCPU configuration matched to `cv64a6_imafdc_sv39_hpdcache_wb`, in which every value is either derived from a CVA6 RTL localparam or is a gem5-side estimate where CVA6 has no clean counterpart.

It comes in two versions, so the same core can be run on either gem5 build:

- `gem5/gem5_config_CVA6.py` runs on a **stock gem5**, using only what upstream already provides.
- `gem5/gem5_config_CVA6_Patch.py` runs on a **patched gem5** and adds the mechanisms the patch makes available.

Each has a `_testing` twin, `gem5_config_CVA6_testing.py` and `gem5_config_CVA6_Patch_testing.py`, which is the same core wrapped in the calibration table of single-knob perturbations that `run_CVA6_testing_sweep.py` replays.

#### TO DO: Explain the patch and its purpose
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

Two images are published on Docker Hub. Check the tags and pull the latest.

**CVA6 + Verilator** ([manuel313/cva6](https://hub.docker.com/r/manuel313/cva6/tags)):

```bash
docker pull manuel313/cva6:latest
```

**gem5 (MinorCPU)** ([manuel313/gem5_v25](https://hub.docker.com/r/manuel313/gem5_v25/tags)):

```bash
docker pull manuel313/gem5_v25:latest
```

Verify:

```bash
docker images
```

---

## Working with the CVA6 image

### Create the container

Create a container (replace `<container_name>`) with a Bash terminal and permission to run graphical applications:

```bash
docker run -it --name <container_name> -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix manuel313/cva6:latest bash
```

Type `exit` to leave.

### Start, enter and stop

```bash
docker start <container_name> # start
docker exec -e DISPLAY=host.docker.internal:0 -it <container_name> bash # enter
docker stop <container_name> # stop
```

### Run a test

Optionally sanity-check that the C compiles on the host first:

```bash
gcc -Wall -Wextra -O3 -g -std=c99 -o <executable_name> <program_name>.c
./<executable_name>
```

Then run it on the Verilated CVA6 to produce the VCD trace and the metrics table:

```bash
python3 run_CVA6.py <target> <test> [--lang c|asm] [--no-vcd] [--keep-build]
```

- `<target>`: the CVA6 configuration, for example `cv64a6_imafdc_sv39_hpdcache_wb`, the one this fork targets. The cache geometry printed in the table's title is read from that target's `core/include/<target>_config_pkg.sv`.
- `<test>`: a `.c` or `.S/.s/.asm` file. The type is auto-detected from the extension, and `--lang` forces it.
- `--no-vcd`: skip the trace and report metrics only.
- `--keep-build`: reuse the Verilated model in `work-ver` instead of rebuilding it. The model does not depend on the test, so this turns a rebuild into a plain run. Only reuse it across runs with the same target and the same trace setting, since both are compiled into the model.

It compiles the test, runs it on the Verilated CVA6, disassembles it, and prints a metrics table (cycles, instructions, cache misses and accesses, branches, mispredictions, time and IPC) with a configurable "net" column that discounts the fixed cost of the measurement code.

The simulation writes to `verif/sim/out_<date>/` as usual, and the three files worth keeping, the VCD, the `.list` and the `<test>_report.txt` with the measured region and the table, are copied to a `run_results/` folder next to the script.

A VCD is written by default. Load it in [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow).

### Limitations and considerations

**C programs:**

- Only `stdio.h`, `stdint.h` and `string.h` are available.
- `malloc` and `free` cannot be used.

**`veri-testharness` simulator:**

- The core runs for at most 2 million cycles or 500 seconds, whichever comes first.

---

## Working with the gem5 image

### Create the container

Create a container (replace `<container_name>`) with a Bash terminal

```bash
docker run -it --name <container_name> manuel313/gem5_v25 bash
```

Type `exit` to leave.

### Start, enter and stop

```bash
docker start <container_name> # start
docker exec -e DISPLAY=$DISPLAY -it <container_name> bash # enter
docker stop <container_name> # stop
```

### Run a test

From `/gem5`, run a test to produce its debug trace and the metrics table:

```bash
python3 run_gem5.py <config>.py <test> [--lang c|asm] [--no-trace]
```

- `<config>.py`: the gem5 MinorCPU configuration script.
- `<test>`: a `.c` or `.S/.s/.asm` file, auto-detected as above (`--lang` to force).
- `--no-trace`: skip the trace and report metrics only.
- anything else: passed on to the configuration script, so a configuration that defines its own options gets them here. Put them after a `--` when a flag takes a value or its name collides with one of the above.

It compiles the test (linking gem5's `m5op.S` so the test can call `m5_reset_stats` and `m5_dump_stats`), runs gem5 into `m5out/`, disassembles the test, and prints the same metrics table as the CVA6 side, read from gem5's `stats.txt`.

gem5 writes to `m5out/` and the test is compiled there too, so a run is self-contained. The four files worth keeping, the trace, the `.list`, the `<test>_report.txt` with the measured region and the table, and `<test>_stats.txt` with the statistics behind that table, are copied to a `run_results/` folder next to the script. `--gem5-out-dir` and `--results-dir` move either folder, which is how concurrent runs are kept apart.

The trace is `run_results/<test>_trace.txt`. Load it in [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow).

---

## The visualizers

Both are single, dependency-free HTML files with a live demo on GitHub Pages and a "Load sample" button, so you can try them without building anything:

- [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow): for the VCD produced by `run_CVA6.py`.
- [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow): for the trace produced by `run_gem5.py`.

---

## Licensing and attribution

The CVA6 core and its dependencies are the work of the [OpenHW Group](https://github.com/openhwgroup/cva6) and contributors, under their original licences (see `LICENSE`, `LICENSE.Berkeley` and `LICENSE.SiFive`), which are preserved here.

Everything added by this project is the work of the FaMAF CVA6 Project and remains the copyright of its authors, released under the MIT Licence in [LICENSE.FaMAF](LICENSE.FaMAF):

- the benchmarks and run scripts under `benchmarks/`,
- the dockerfiles under `dockerfiles/`,
- the gem5 configuration that matches CVA6 under `gem5_config_CVA6`,
- the verilator changes under `verilator_changes`, 
- the documentation written for this fork, starting with this README,
- and the two visualizer submodules, [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow) and [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow), which carry the same MIT licence in their own repositories.
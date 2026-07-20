# FaMAF CVA6 Project

The reference RISC-V core for the FaMAF CVA6 Project, and the starting point for new members.

This repository is a frozen fork of the [OpenHW Group CORE-V CVA6](https://github.com/openhwgroup/cva6), a 64-bit, 6-stage RISC-V processor written in SystemVerilog. It is used as the real-hardware side of an undergraduate thesis at FaMAF, Universidad Nacional de Córdoba, on how closely a gem5 configuration can be made to match a real RISC-V core.

Everything runs inside Docker, so you do not have to install CVA6's or gem5's dependencies on your own machine.

## The project at a glance

The project has two sides. Each one runs a test and produces a trace that a visualizer turns into a cycle-by-cycle pipeline view:

- **CVA6 (this repo)**: the real core, simulated in Verilator. `run_verilator.py` runs a test and writes a VCD, which [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow) renders.
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
| `config/`                                       | Core configuration, including the `cv64a6_imafdc_sv39_hpdcache_wb` target.                         |
| `verif/`                                        | Verification and simulation harness (Verilator under `verif/sim`).                                 |
| `vendor/`                                       | Vendored upstream dependencies, pinned so nothing is fetched.                                      |
| `benchmarks/verilator/`                         | Verilator benchmarks and `run_verilator.py` (runs a test on CVA6, writes the VCD, prints metrics). |
| `benchmarks/gem5/`                              | gem5 benchmarks and `run_gem5.py` (runs the same test on gem5, writes the trace, prints metrics).  |
| `viewers/MinorFlow`                             | The MinorFlow visualizer, as a submodule.                                                          |
| `viewers/CVA6Flow`                              | The CVA6Flow visualizer, as a submodule.                                                           |
| `our_docs/`                                     | The project's own documentation.                                                                   |
| `LICENSE`, `LICENSE.Berkeley`, `LICENSE.SiFive` | Upstream licences, preserved.                                                                      |

Everything else (`common/`, `util/`, `pd/`, `spyglass/`, `ci/`, `cva6_docs/` and so on) is standard upstream CVA6.

## Prerequisites

- A **Debian-based Linux** system (Debian or Ubuntu).
- Enough disk space for the Docker images.

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
python3 run_verilator.py cv64a6_imafdc_sv39_hpdcache <test>.c
```

`.S`, `.s` and `.asm` tests are auto-detected, and you can force the type with `--lang c|asm`. Add `--no-vcd` if you only want the metrics. Load the resulting VCD in [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow).

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

From the gem5 root, run a test to produce its debug trace and the metrics table:

```bash
python3 run_gem5.py <config>.py <test>.c
```

`<config>.py` is the gem5 MinorCPU configuration script. `.S`, `.s` and `.asm` tests are auto-detected, and `--no-trace` gives metrics only. The trace is written to `results/<test>_trace.txt`. Load it in [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow).

---

## The visualizers

Both are single, dependency-free HTML files with a live demo on GitHub Pages and a "Load sample" button, so you can try them without building anything:

- [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow): for the VCD produced by `run_verilator.py`.
- [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow): for the trace produced by `run_gem5.py`.

---

## Licensing and attribution

The CVA6 core and its dependencies are the work of the [OpenHW Group](https://github.com/openhwgroup/cva6) and contributors, under their original licences (see `LICENSE`, `LICENSE.Berkeley` and `LICENSE.SiFive`), which are preserved here.

Everything added by this project is the work of the FaMAF CVA6 Project and remains the copyright of its authors:

- the benchmarks and run scripts under `benchmarks/`,
- the documentation under `our_docs/`,
- and the two visualizer submodules, [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow) and [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow), which are MIT-licensed in their own repositories.

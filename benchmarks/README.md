# Benchmarks

The test programs used in the project, plus the driver scripts that run them on each simulator. Both drivers accept the same C and assembly tests and print the same metrics table, so results from CVA6 and gem5 can be compared directly.

The scripts are kept here for version control, but each is run inside its own Docker image. See the [main README](../README.md) for how to set up the containers.

## Layout

- `verilator/`: Verilator benchmarks and `run_verilator.py` (runs on the CVA6 core).
- `gem5/`: gem5 benchmarks and `run_gem5.py` (runs on the gem5 MinorCPU RISC-V model).

## Running on CVA6 (Verilator)

Inside the `manuel313/cva6` image, from the `verilator/` folder:

```bash
python3 run_verilator.py <target> <test> [--lang c|asm] [--no-vcd]
```

- `<target>`: the CVA6 configuration, for example `cv64a6_imafdc_sv39_hpdcache`.
- `<test>`: a `.c` or `.S/.s/.asm` file. The type is auto-detected, and `--lang` forces it.
- By default it writes a VCD trace. Load it in [CVA6Flow](https://github.com/FaMAF-CVA6-Project/CVA6Flow). Add `--no-vcd` for metrics only.

It compiles the test, runs it on the Verilated CVA6, disassembles it, and prints a metrics table (cycles, instructions, cache misses and accesses, branches, mispredictions, time and IPC) with an overhead-corrected "net" column.

## Running on gem5 (MinorCPU)

Inside the `manuel313/gem5_v25` image, from the **gem5 root** (the script uses the current directory as the gem5 root):

```bash
python3 run_gem5.py <config>.py <test> [--lang c|asm] [--no-trace]
```

- `<config>.py`: the gem5 MinorCPU configuration script.
- `<test>`: a `.c` or `.S/.s/.asm` file, auto-detected (`--lang` to force).
- By default it writes `results/<test>_trace.txt`. Load it in [MinorFlow](https://github.com/FaMAF-CVA6-Project/MinorFlow). Add `--no-trace` for metrics only.

It compiles the test (linking gem5's `m5op.S` so the test can call `m5_dump_stats`), runs gem5, disassembles the test, and prints the same metrics table as the CVA6 side.

## Licence

The contents of this directory are the work of the FaMAF CVA6 Project, under the MIT Licence. See [LICENSE](LICENSE).

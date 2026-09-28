# ddr3_memory

A DDR3-1600 device and controller for the Verilated CVA6 testbench, in place of the single-transaction `axi2mem` and its flat array, so the RTL sees the kind of memory an FPGA CVA6 sees and the same device gem5 models with `SingleChannelDDR3_1600`. Every timing parameter is gem5's `DDR3_1600_8x8`, and the controller follows gem5's `MemCtrl`: read and write queues, first-ready first-come-first-served scheduling, an open page policy, write draining and merging, bus turnaround and per-rank refresh.

## What is here

| Path                    | What it is                                                                                                                                                        |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ddr3_memory.patch`     | The change to three upstream files: `ariane_testharness.sv` swaps `axi2mem` for the model, `ariane_tb.cpp` calls `top->final()`, and the `Makefile` lists the RTL |
| `rtl/ddr3_pkg.sv`       | Device geometry, timing in picoseconds, gem5's `RoRaBaCoCh` address decode and the statistics record                                                              |
| `rtl/ddr3_scheduler.sv` | The controller and device: queues, bank and rank state, tFAW, bus turnaround, write draining and merging, refresh                                                 |
| `rtl/axi_ddr3_slave.sv` | The AXI slave front end, on `axi2mem`'s ports and array, wrapping the scheduler                                                                                   |
| `tb/`                   | A standalone Verilator testbench that checks the timing against DDR3-1600 theory in about a minute                                                                |

## Using it

From the CVA6 root, which is `/CVA6` in the container, put it in, run, and take it out. The first run afterwards rebuilds the model, so it goes without `--keep-build`:

```bash
python3 scripts/patch_CVA6_testbench.py apply --ddr3
python3 scripts/run_CVA6.py benchmarks/config/daxpy.S --no-vcd
python3 scripts/patch_CVA6_testbench.py revert --ddr3
```

It combines with the VCD window, `apply --vcd-window --ddr3`, see [the overview](../README.md). The statistics print from a SystemVerilog `final` block at the end of every run, into the run's log, `verif/sim/out_<date>/veri-testharness_sim/<test>.*.log.iss`, since `run_CVA6.py` filters the simulator's own output. The stock testbench never calls `top->final()`, and Verilator runs no `final` block until it does, which is why the change adds the call.

The standalone testbench builds only the DDR3 sources, the AXI interface and the array, with the Verilator on the path, `/CVA6/tools/verilator/bin` in the container:

```bash
cd verilator_changes/ddr3_memory/tb
make            # build and run
make lint       # lint the DDR3 sources with nothing waived
```

It covers write and read back with multi-beat bursts, the three row buffer cases to the picosecond, bank parallelism against serial issue, row conflicts accumulating, tFAW holding off the fifth activate, the refresh rate against tREFI, and bus turnaround.

## The model

**Device.** 64-byte burst, 8 KiB row buffer, 8 banks, 2 ranks, tCK 1.25 ns, tRCD 13.75, tCL 13.75, tRP 13.75, tRAS 35, tRC 48.75, tBURST 5, tRRD 6, tFAW 30, tWTR 7.5, tRTW 2.5, tCS 2.5, tWR 15, tRTP 7.5, tRFC 260 and tREFI 7.8 us.

**Address decode.** gem5's `RoRaBaCoCh`, the `MemCtrl` default, from `DRAMInterface::decodePacket` with one channel. The column is the lowest field, "to ensure that sequential cache lines occupy the same row", so an 8 KiB stretch is one row of one bank. It is the first thing to check if the two sides' row hit rates disagree, since the closed page mapping, `RoCoRaBaCh`, takes the bank from the bits just above the burst and spreads code and data over the same banks.

```
col  = (addr / 64) % 128        +64 B    same bank, next column
bank = (addr / 8 KiB) % 8       +8 KiB   next bank
rank = (addr / 64 KiB) % 2      +64 KiB  next rank
row  = addr / 128 KiB           +128 KiB same bank, next row
```

**Timing is analytic, not cycle by cycle.** The harness clock is 20 ns and a row miss, tRP + tRCD + tCL, is 41.25 ns in three commands, so a model issuing one command a harness cycle would take 60 ns over it. As gem5 does, the scheduler works out a request's whole command sequence in picoseconds from the bank and bus state and records when the data is ready, and nothing is rounded until the response goes back on a clock edge. tRCD and tRP are each below one harness cycle, so a single conflict can land on the same cycle count as a closed bank, while the cost still accumulates, since the picosecond clock runs on between accesses.

**Why `axi2mem` is replaced, not wrapped.** `axi2mem` takes one transaction at a time, so a DDR3 model behind it could never show bank parallelism, row hits across banks or tFAW, and an FPGA CVA6 talks to a controller with real queues. `i_sram` keeps its instance name and hierarchy, since `ariane_tb.cpp` preloads the ELF straight into its storage. The array is 256 MiB where `DRAMLength` and the model's range are 1 GiB, stock behaviour that no program here goes near.

**Writes.** Answered once buffered, as gem5 and a controller with a write buffer do, the data reaching the array as the W beats arrive. A posted write to a burst already queued merges into it. The bus turns to writes past the high water mark, 54 of 64, or with no read waiting past the low one, 32, and back to reads when the queue empties, falls 16 below the low mark, or has sent 16 writes with a read waiting, gem5's `processNextReqEvent` rule for rule.

**Parameters on `ariane_testharness`.**

| Parameter           | Default | Effect                                                                                                    |
| ------------------- | ------- | --------------------------------------------------------------------------------------------------------- |
| `DDR3NumRdSlots`    | 8       | AXI reads open at once. It caps the concurrency the model can show, so keep it at the HPDcache's or above |
| `DDR3NumWrSlots`    | 4       | AXI writes open at once                                                                                   |
| `DDR3PostedWrites`  | 1       | 0 holds the B response until the DRAM write completes                                                     |
| `DDR3EnableRefresh` | 1       | 0 removes refresh, as a sensitivity check                                                                 |
| `DDR3TckPs`         | 20000   | The harness clock period in picoseconds                                                                   |
| `DDR3BackendPs`     | 10000   | The controller pipeline after the access, gem5's `static_backend_latency`                                 |

## The gem5 side

`gem5_config_CVA6.py` and `gem5_config_CVA6_patch.py` both take `--ddr3`, which replaces the flat memory with `SingleChannelDDR3_1600`, the same device, so there is no configuration of its own to drift. The patched one keeps the `Axi2MemPort` model in front of the controller unless `--no-port-model`, and takes `--ddr3-frontend-ns`, the controller's front-end latency, gem5's 10 by default. 30 matches this model: its AXI front end takes a row hit 5 cycles from the address handshake to the first data beat, about three more than `axi2mem`, where gem5 puts 10 ns before the device and 10 after, about two.

```bash
python3 scripts/run_gem5.py gem5_configs/config/gem5_config_CVA6_patch.py \
    benchmarks/config/daxpy.S --variant patch -- --ddr3 --ddr3-frontend-ns 30
```

| This model                       | gem5                                      |
| -------------------------------- | ----------------------------------------- |
| `row buffer hits` over the total | `mem_ctrl.dram.readRowHits / readBursts`  |
| `refreshes`                      | `mem_ctrl.dram.numRefreshes`              |
| `mean device access`             | `mem_ctrl.dram.avgMemAccLat`              |
| `read bursts`, `write bursts`    | `mem_ctrl.dram.readBursts`, `writeBursts` |

`mean device access` is the DRAM alone, before rounding and with no queueing, the number to set against DDR3 theory, and `mean read latency` is what the core waits, with queueing, rounding and the backend in it. The model counts row hits over reads and writes together, and gem5 per direction.

Two differences stay on the RTL side whatever the memory. The testbench's `axi_riscv_lrsc` adapter keeps one read and one write outstanding, so a read waits for the one before it to return, where `Axi2MemPort` frees the port after its fixed occupancy and gem5 overlaps a second miss with the first. And the HPDcache sends every atomic to memory, where the testbench's adapter performs it, so on this memory each one pays the DRAM latency, which gem5, performing atomics in the L1D, does not.

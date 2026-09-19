# custom_size_vcds

A windowed waveform dump, so the VCD of a long benchmark stays small enough to keep.

Verilator writes up to about 63 KB of VCD per simulated cycle on this core, and how much depends on the program. `store_fwd` at 1,602 cycles is 100 MB, about 63 KB per cycle, and `btb_pressure` at 21,945 cycles is 442 MB, about 20 KB per cycle, so `branch_full_test` at 542,216 cycles would land between 11 and 34 GB. Upstream dumps from cycle zero to the end of the run, so the long rows of the comparison suite cannot be dumped whole without this.

## What is here

Both code files are **modified copies of upstream files**, not new work. Each carries a notice of change, as its licence requires: section 4(b) of Apache 2.0 for `ariane_tb.cpp`, and section 4 of the repository's Solderpad Hardware License 0.51 for the `Makefile`. The unmodified originals stay tracked in git, and `scripts/patch_vcd_window.py` keeps a copy of each file it replaces.

| File            | Original                            | Change                                                            |
| --------------- | ----------------------------------- | ----------------------------------------------------------------- |
| `ariane_tb.cpp` | `corev_apu/tb/ariane_tb.cpp`        | The four dump sites are gated on a simulation-time window         |
| `Makefile`      | the Makefile at the repository root | Adds `trace_start` and `trace_end`, passed to the Verilator build |

## Using it

Inside the CVA6 container, from `/CVA6`, put both in place, export the window, run, and take them back out:

```bash
python3 scripts/patch_vcd_window.py apply
export trace_start=100000 trace_end=200000
python3 scripts/run_CVA6.py benchmarks/viewer/daxpy.S
python3 scripts/patch_vcd_window.py revert
```

`trace_start` and `trace_end` count clock cycles from the start of reset, the testbench's `main_time`, whose VCD timestamps are twice that, and they reach the testbench as the `START_TRACE_CYCLE` and `END_TRACE_CYCLE` defines. Both default to the full run, so an unset window behaves as upstream does.

The window is a **compile-time** define, so it takes effect only on a rebuilt model, and it has to be exported rather than given on a `make verilate` command line. `cva6.py` runs the model through `verif/sim/Makefile`'s `veri-testharness` target, which calls `make verilate` again with no window of its own, so a model built by hand with `make verilate trace_start=... trace_end=...` is rebuilt without the defines and the dump covers the whole run, `--keep-build` or not. Exported, `trace_start` and `trace_end` reach that inner `make verilate`, since the windowed Makefile sets them only when they are unset, and the driver's own rebuild carries the window. A different window is another export and another run. A windowed dump starts part way through the run, so CVA6Flow's tracer marks its JSON `windowed`, and Main Code finds no region when the window leaves out the counter reads.

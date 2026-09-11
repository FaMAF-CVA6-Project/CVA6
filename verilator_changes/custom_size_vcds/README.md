# custom_size_vcds

A windowed waveform dump, so a long benchmark can be traced at all.

Verilator writes about 63 KB of VCD per simulated cycle on this core. `store_fwd` at 1,602 cycles is 100 MB, `btb_pressure` at 21,945 is 442 MB, and `branch_full_test` at 542,216 would be roughly 34 GB. Upstream dumps from cycle zero to the end of the run, so the long rows of the comparison suite cannot be traced without this.

## What is here

Both files are **modified copies of upstream files**, not new work. Each carries a notice of change, as Apache 2.0 section 4(b) requires. The unmodified originals stay where they are.

| File            | Original                            | Change                                                            |
| --------------- | ----------------------------------- | ----------------------------------------------------------------- |
| `ariane_tb.cpp` | `corev_apu/tb/ariane_tb.cpp`        | The four dump sites are gated on a simulation-time window         |
| `Makefile`      | the Makefile at the repository root | Adds `trace_start` and `trace_end`, passed to the Verilator build |

## Using it

Copy both over their originals, then pass the window to `make`:

```bash
cp ariane_tb.cpp ../../corev_apu/tb/ariane_tb.cpp
cp Makefile ../../Makefile
make verilate trace_start=100000 trace_end=200000
```

`trace_start` and `trace_end` are simulation time, not cycles, and they reach the testbench as the `START_TRACE_CYCLE` and `END_TRACE_CYCLE` defines. Both default to the full run, so an unset window behaves as upstream does.

The window is a **compile-time** define. Changing it rebuilds the model, so `run_CVA6.py --keep-build` is only safe while the window stays fixed.

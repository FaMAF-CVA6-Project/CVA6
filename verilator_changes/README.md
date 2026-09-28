# verilator_changes

Two changes to the CVA6 testbench, each a diff against the upstream files, put in and taken out by [`scripts/patch_CVA6_testbench.py`](../scripts/patch_CVA6_testbench.py), alone or together.

| Change                         | What it does                                                            | What it edits                                                                                                 |
| ------------------------------ | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| [`vcd_window/`](vcd_window/)   | Bounds the waveform dump to a window of clock cycles                    | `corev_apu/tb/ariane_tb.cpp` and the `Makefile`                                                               |
| [`ddr3_memory/`](ddr3_memory/) | Replaces the single-transaction `axi2mem` with a DDR3-1600 memory model | `corev_apu/tb/ariane_testharness.sv`, `ariane_tb.cpp` and the `Makefile`, and adds its RTL to `corev_apu/tb/` |

```bash
python3 scripts/patch_CVA6_testbench.py status
python3 scripts/patch_CVA6_testbench.py apply --vcd-window --ddr3
python3 scripts/patch_CVA6_testbench.py revert --ddr3
python3 scripts/patch_CVA6_testbench.py revert
```

`apply` adds the named changes to those already in, and `revert` takes the named ones out, or both with none named. Each time it starts from the upstream files, which the first `apply` keeps beside each as `<name>.upstream`, puts the diffs in, the window first, and writes a notice at the top of each edited file naming the changes that edited it, as those files' Apache 2.0 and Solderpad 0.51 licences require. The last `revert` puts the upstream copies back byte for byte. Either change needs the model rebuilt, which the next `run_CVA6.py` without `--keep-build` does.

The CVA6 image carries both, not applied, and the script at `/CVA6/scripts/patch_CVA6_testbench.py`, acting on `/CVA6`.

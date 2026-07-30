# gem5_config_CVA6

The gem5 MinorCPU configuration matched to CVA6, and the paired runs that show how close the match is.

## Layout

| Path | What it is |
| --- | --- |
| `gem5/gem5_config_CVA6.py` | The matched configuration. |
| `gem5/gem5_config_CVA6_testing.py` | The calibration harness: the same core as a table of single-knob perturbations |
| `gem5/run_CVA6_testing_sweep.py` | Replays that table. See the main [README](../README.md#the-calibration-sweep) |
| `gem5/MinorCPU_CVA6.patch` | The MinorCPU changes the configuration depends on |
| `gem5/tests/` | The gem5 side: debug trace, measured region and MinorFlow JSON per benchmark |
| `verilator/tests/` | The CVA6 side: VCD, listing, measured region and CVA6Flow JSON per benchmark |

Both `tests/` folders carry the same ten benchmarks, `atomic_fence`, `basic_test`, `branch_full_test`, `daxpy`, `fp_addmul`, `fp_divsqrt`, `full_test`, `int_div`, `matmul_small` and `store_fwd`, which is the set `DEFAULT_ALL_TESTS` names in the sweep. Each side also has a `*_create_all_jsons.py` that runs its tracer over every trace in the folder, so the JSONs can be regenerated in one go.

The measured region and the metrics table live in `<test>_clean.txt` on both sides, and the tables have the same columns. That file is the quickest way to compare a benchmark: open the two and read down.

## The matched configuration

`gem5_config_CVA6.py` targets `cv64a6_imafdc_sv39_hpdcache_wb` at 50 MHz, with a 16 KiB L1I and a 32 KiB L1D. Every value is either derived from a CVA6 RTL localparam or is a gem5-side estimate where CVA6 has no clean counterpart. Two functional-unit latencies, `int_div` and `fp_divsqrt`, are representative stand-ins for iterative units that are data-dependent in the RTL and off every calibrated kernel's hot path.

Run it like any other gem5 config:

```bash
python3 run_gem5.py gem5_config_CVA6.py <test>
```

## The MinorCPU patch

`MinorCPU_CVA6.patch` adds two parameters to gem5's MinorCPU, because CVA6's load-store unit behaves in a way stock MinorCPU cannot express. Without them the model forwards store data to loads that CVA6 would have stalled, and the divergence lands squarely on the store-heavy benchmarks.

| Parameter | Default | What it does |
| --- | --- | --- |
| `executeLSQNoStoreForwarding` | `False` | Disables store-to-load forwarding from the store buffer. A load that fully overlaps a pending store waits for that store to drain and then reads the cache, instead of taking the data from the buffer. |
| `executeLSQStoreCollisionReplayDelay` | `0` | Cycles a load waits after a blocking store collision clears, before it may access the cache. Models the cost of restarting the load in the LSU. Only meaningful with the above set. |

Both defaults are the stock behaviour, so a patched gem5 runs unpatched configurations unchanged.

**Why CVA6 needs them.** CVA6 has no store-to-load forwarding path. Its load unit parks a load in `WAIT_PAGE_OFFSET` until the store buffer drains whenever the address collides with a pending store (`load_unit.sv`, and `page_offset_matches_o` in `store_buffer.sv`). Restarting that load then costs two more cycles: neither `IDLE` nor `WAIT_PAGE_OFFSET` asserts `data_req`, so the offset clearing only moves the state to `WAIT_GNT`, which raises the request the cycle after, whereas an unblocked load raises it directly from `IDLE`.

**How it is implemented.** In `LSQ::StoreBuffer::canForwardDataToLoad`, a full address-range hit is downgraded to a partial one when `noStoreForwarding` is set, which makes `tryToSendToTransfers` take the wait path instead of the forward path, so the load retries until the store has drained and then reads the cache. This is the same mechanism the LSQ already applies to masked requests. The downgrade sits there rather than in `containsAddrRangeOf` so that the `FullAddrRangeCoverage` assertion in `forwardStoreData` keeps its meaning, and so that the non-bufferable ordering check, which only tests `NoAddrRangeCoverage`, is unaffected. The replay countdown is re-armed on every blocked cycle and spent once the collision clears, so it is fully loaded at the moment the load is unblocked.

Four files change: `src/cpu/minor/BaseMinorCPU.py` for the parameters, `src/cpu/minor/execute.cc` to pass them to the LSQ, and `src/cpu/minor/lsq.cc` and `lsq.hh` for the behaviour.

**Applying it.** From the `/gem5` :

```bash
git apply MinorCPU_CVA6.patch
scons build/RISCV/gem5.opt -j$(nproc)
```

The `manuel313/gem5_v25` image ships with the patch already applied, so nothing is needed there.

To run `gem5_config_CVA6.py` against an unpatched gem5, delete the two `executeLSQNoStoreForwarding` and `executeLSQStoreCollisionReplayDelay` lines from it. The rest of the configuration is stock MinorCPU, and the store-heavy benchmarks will read optimistic.

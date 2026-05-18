# CVA6 pipeline diagnostic reference and tool specification

**Bottom line: your VCD diagnostic is tractable, but only if you anchor on two specific RTL invariants rather than trying to reconstruct the whole pipeline.** First, every in-flight instruction lives in scoreboard slot `N = trans_id`, and that slot's lifecycle (`mem_q[N].issued` 0→1, `mem_q[N].sbe.valid` 0→1, then `mem_q[N].issued` 1→0) is a three-edge state machine that completely encodes fetch-to-retire for any instruction whose *issue* edge falls inside the window. Second, for instructions whose fetch/issue happened before the window opened, the only sound ground truth is the **RVFI** channel (`rvfi_probes_o` → `cva6_rvfi` → `rvfi_o[NrCommitPorts]`), whose `rvfi_valid + rvfi_order + rvfi_pc_rdata` triple is speculation-free and gapless. Everything else in CVA6 — the frontend PC chain, the I-cache FSM, the scoreboard forwarding logic, even the 5-port writeback bus — is useful corroboration but will produce misleading results at the crop boundary if used alone. This report pins down signal-by-signal semantics for each pipeline stage, maps the VCD-observable flags to the three-edge lifecycle, and gives a concrete Python tool spec that explicitly separates "cold-start orphan" instructions from fully-observed ones.

## Part 1A — Frontend and I-cache

**The frontend is three sub-stages (PC_SEL / FE1 / FE2) feeding a ring-buffer instruction queue.** PC_SEL chooses `npc_d` from a 7-way priority mux (BP → default PC+4 → replay → mispredict → eret → exception → `set_pc_commit_i` → `set_debug_pc_i`, lowest wins). FE1 drives the I-cache request; FE2 latches the response, runs `instr_realign` and `instr_scan` (early branch detection), and pushes up to 2 instructions per cycle into `instr_queue`. `instr_queue` pops one instruction per cycle to `id_stage` via `fetch_entry_valid_o / fetch_entry_ready_i`. The user manual calls this "the fetch FIFO"; it "fully decouples the processor's front-end and its back-end."

The **I-cache handshake** uses two packed structs (defined in `core/cva6.sv`, verified from GitHub source):

```systemverilog
localparam type icache_dreq_t = struct packed {
  logic                    req;      // request a new word
  logic                    kill_s1;  // kill the current request (FE1)
  logic                    kill_s2;  // kill the last request (FE2)
  logic                    spec;     // request is speculative
  logic [VLEN-1:0]         vaddr;    // 1st cycle: 12-bit index used for lookup
};
localparam type icache_drsp_t = struct packed {
  logic                    ready;    // icache ready to accept
  logic                    valid;    // signals a valid read
  logic [FETCH_WIDTH-1:0]  data;     // 2+ cycle out: tag + data
  logic [FETCH_USER_WIDTH-1:0] user;
};
```

**Ready is driven by the I-cache (subordinate side); valid is driven by the I-cache when data is ready; req and kill_s1/s2 are driven by the frontend.** This is *not* a standard ready/valid pair — it is a three-signal pipe: cycle N the frontend asserts `req` and `vaddr`, cycle N+1 is the tag compare (during which the frontend may assert `kill_s1`), cycle N+2 the data appears with `valid=1` on a hit (during which the frontend may assert `kill_s2` to discard it). On a **hit**, the Pulp-Platform detailed deck puts the minimum latency at one cycle after grant; measured in RTL you will see `req` pulse at cycle N, `valid` come back at N+1 (one-cycle tag+data SRAM). On a **miss**, the cva6_icache FSM enters `WAIT_REFILL_GNT` (wait for AXI `ar_ready`), then `WAIT_CRITICAL_WORD` (the first 64-bit beat returns via AXI `r_valid`), then `WAIT_REFILL_VALID` for the remaining beats, then back to `IDLE`. `miss_o` pulses for the duration the FSM is out of `IDLE`/`READ`. Typical miss-to-first-data latency in the APU testbench is ~15–25 cycles dominated by AXI interconnect and DRAM model. PlanV's RTL dive documents the `KILL_*` states that exist to drain in-flight AXI beats when a flush arrives mid-miss — important for your tool because during these states you will see `dreq_o.req=0` but `miss_o=1` and AXI `r_valid` still toggling.

**`instr_realign` produces a 2-bit `valid` vector** precisely because CVA6's 32-bit fetch word can contain up to two RVC (16-bit compressed) instructions. Bit 0 = lower halfword, bit 1 = upper halfword; `realign_compressed[i]` tells you whether slot `i` is a compressed instruction (16 bits) or the low half of a 32-bit instruction whose high half comes from the next fetch. The module "stores incomplete instructions internally until the second half is fetched"; on flush the stored fragment is discarded. The doc summarizes: "It is possible to fetch up to 2 instructions per cycle when C extension is used. A not-compressed instruction can be misaligned on the block size, interleaved with two cache blocks. In that case, two cache accesses are needed to get the whole instruction."

**`instr_queue`** is a ring buffer parameterized by depth (default ~8 entries). Each entry carries `{instruction[31:0], pc[VLEN-1:0], branch_predict, ex}`. Two independent push ports (one per realign slot), **one pop port** to `id_stage`. The critical VCD-semantics point: the fetch→decode handshake signals out of the frontend are `fetch_entry_o`, `fetch_entry_valid_o`, `fetch_entry_ready_i` — and when both `valid` and `ready` are high, the instruction is **popped out** of `instr_queue` and enters decode. This is a POP, not a push. To detect the PUSH side (instruction arriving at IQ) you need the per-slot realign_valid ANDed with `instr_queue`'s internal `push_ptr_q` advancing, or the combinational push_valid signal internal to the IQ.

**Flush behavior in the frontend** comes from three consumers of controller outputs: `flush_i` (alias `flush_ctrl_if`) clears `instr_queue` and zeroes all outstanding-icache bookkeeping (the frontend tracks up to 2 outstanding I-cache transactions and will use `kill_s1`/`kill_s2` to discard any in-flight responses); `flush_bp_i` invalidates BHT/RAS in-flight update state but **does not** clear BTB storage; `set_pc_commit_i` forces `npc_d = pc_commit + (is_compressed ? 2 : 4)` — this is the post-drain redirect used for FENCE.I, SFENCE.VMA, CSR-with-side-effects, and MRET/SRET/DRET (the latter via `eret_i` path at priority 4 of the `npc_select` mux).

```
ICACHE HIT (isolated)                    ICACHE MISS (isolated, standard cache)
cycle:   0    1    2    3                cycle:   0   1   2   ...    N   N+1  N+2
req    : ‾‾‾\___________                 req    : ‾‾‾\____________________________
vaddr  : [A  ][X  ]                      vaddr  : [A ][X  ]
ready  : ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾                 miss_o : ____/‾‾‾‾‾‾‾‾‾‾‾‾‾‾\________
valid  : ________/‾‾‾\___                ar_valid:____/‾‾\________________________
data   :         [I  ]                   ar_ready:_______/‾‾\_______________________
                                         r_valid: _______________/‾\__/‾\__/‾\__/‾\
                                         valid  : _______________________________/‾
```

## Part 1B — Issue and scoreboard (authoritative)

**The scoreboard is the heart of your diagnostic.** Parameter `CVA6Cfg.NR_SB_ENTRIES` (historically `NR_ENTRIES`) is typically **8**, with **`TRANS_ID_BITS = $clog2(NR_SB_ENTRIES) = 3`**. The RTL asserts `NR_SB_ENTRIES == 2**TRANS_ID_BITS`. Each slot is an `sb_mem_t`:

```systemverilog
typedef struct packed {
    logic              issued;         // slot allocated, instruction in-flight
    logic              cancelled;      // speculative-SB only: slot killed
    logic              is_rd_fpr_flag; // redundant meta for timing
    scoreboard_entry_t sbe;            // the instruction payload
} sb_mem_t;
sb_mem_t [NR_SB_ENTRIES-1:0] mem_q, mem_n;
```

`scoreboard_entry_t` contains `pc`, `trans_id`, `fu`, `op`, `rs1`, `rs2`, `rd`, `result` (pre-WB: immediate; post-WB: result), `valid` (= writeback-done flag, distinct from `.issued`), `ex`, `bp`, `is_compressed`, plus macro-instruction flags.

**TID is the slot index.** `trans_id_o = issue_pointer[i]` is assigned at issue. Width = `TRANS_ID_BITS`. It is injected into `issue_instr_o[i].trans_id`, rides with every `fu_data` down to each FU, and returns on `trans_id_i[wb_port]` to index `mem_n[trans_id_i[k]]` for writeback.

**The three-edge lifecycle of slot `N` is**: (1) at the issue-decision cycle, `decoded_instr_valid_i && decoded_instr_ack_o && !flush_unissued_instr_i && issue_pointer_q==N` — the next posedge sets `mem_q[N].issued=1`, latches `mem_q[N].sbe=decoded_instr_i`, and advances `issue_pointer_q` by `num_issue`; (2) when the FU completes, `wt_valid_i[k]=1 && trans_id_i[k]==N` — the next posedge sets `mem_q[N].sbe.valid=1` and captures `mem_q[N].sbe.result=wbdata_i[k]`; (3) when commit asserts `commit_ack_i[i]=1 && commit_pointer_q[i]==N` — the next posedge clears `mem_q[N].issued=0`, `mem_q[N].sbe.valid=0`, and advances `commit_pointer_q[0]` by `num_commit`. **There is no 1-hot "slot allocated" signal; you must edge-detect `mem_q[N].issued` or re-derive it combinationally.**

The issue handshake — `decoded_instr_valid_i` (ID→SB) and `decoded_instr_ack_o = issue_ack_i & ~issue_full` (SB→ID) — and the SB→IRO handshake — `issue_instr_valid_o = decoded_instr_valid_i & ~issue_full` and `issue_ack_i` back from issue_read_operands — are the same-cycle condition that triggers slot allocation. When both fire, three things happen in one clock edge: the slot is allocated, the FU is dispatched (via registered `*_valid_q` pulse that appears next cycle), and `issue_pointer_q` advances. The per-FU valid signals (`alu_valid_o`, `branch_valid_o`, `lsu_valid_o`, `mult_valid_o`, `fpu_valid_o`, `csr_valid_o`, `aes_valid_o`, `cvxif_valid_o`) are each **registered one-cycle pulses** — declared `*_valid_n` combinationally in the `case(issue_instr_i[i].fu)` block, then flopped to `*_valid_q = *_valid_o`. On `flush_i` they are gated to 0. For VCD diagnostics, **treat these as exact 1-cycle pulses marking FU dispatch**.

**Flushes clear everything at one edge.** `flush_i` resets all `mem_q[*].issued`, `.cancelled`, `.sbe.valid`, `.sbe.ex.valid` to 0 and drives `issue_pointer_q` and `commit_pointer_q[*]` to 0. `flush_unissued_instr_i` only blocks new allocations (leaves in-flight slots alone) — used during unresolved-branch windows. The scoreboard has hard RTL assertions you can exploit as VCD sanity checks: `issue_ack_i[i] |-> issue_instr_valid_o[i]`, "no two WB ports asserting the same trans_id in the same cycle," and "never more than one in-flight instruction targeting the same rd (except x0)."

**Commit reads the two oldest slots every cycle:** `commit_instr_o[i] = mem_q[commit_pointer_q[i]].sbe` with `commit_pointer_q[1] = commit_pointer_q[0]+1` (mod NR_SB_ENTRIES). Commit is **strictly program order** because retirement only touches `commit_pointer_q[0..1]` — never an out-of-order "oldest ready" search. Writeback can arrive out of order but commit drains in order.

## Part 1C — Execute, and the 5-port writeback bus

**Five writeback ports with fixed indices, defined in `core/include/ariane_pkg.sv`:**

```systemverilog
localparam FLU_WB   = 0;   // Fast-LSU/FLU: ALU + CTRL_FLOW + CSR + MULT (fused port)
localparam STORE_WB = 1;
localparam LOAD_WB  = 2;
localparam FPU_WB   = 3;
localparam ACC_WB   = 4;
localparam X_WB     = 4;   // CVXIF shares port 4 with accelerator
```

So `wt_valid_i[5]`, `trans_id_i[5][TRANS_ID_BITS]`, `wbdata_i[5][XLEN]`, `ex_i[5]` are 5-port arrays into the scoreboard. **Port 0 is shared among ALU, branch/CTRL, CSR and MULT because they never retire simultaneously** (a single FLU-WB arbiter inside `ex_stage` grants the bus one cycle at a time). In `core/cva6.sv` the aggregation is literally `assign wt_valid_ex_id = {flu_valid_ex_id, load_valid_ex_id, store_valid_ex_id, fpu_valid_ex_id}` (order varies; always check your config).

**Per-FU source TIDs exist and are named `flu_trans_id`, `load_trans_id`, `store_trans_id`, `fpu_trans_id`, `x_trans_id`.** They feed into the aggregated `trans_id_i` bus through muxing in `ex_stage`. **For VCD diagnostics, prefer the per-FU sources** — the aggregated `trans_id_i[k]` bus holds X (undefined) when `wt_valid_i[k]=0`, which will poison any attempt to decode the last valid TID on an inactive port. The per-FU signals carry stable values registered inside each FU and are much safer to sample.

**ALU is combinational**: the result appears in the same cycle as `alu_valid_i=1`, and `flu_valid_o` pulses one cycle later (registered through FLU-WB arbiter). The doc confirms the design goal: "execute two ALU instructions back to back with no bubble in between."

**Branch unit exposes `resolved_branch_o` (struct `bp_resolve_t`)** with fields `valid`, `pc`, `target_address`, `is_mispredict`, `is_taken`, `cf_type`. `resolved_branch_o.valid=1` fires every retiring branch; `is_mispredict=1` is the subset that triggers `flush_if_o + flush_unissued_instr_o` in the controller and redirects `npc_d = target_address` the *same* cycle. The mispredicted branch itself still commits normally.

**Load unit FSM** (`load_unit.sv`, verified from RTL issue #430 reference): states are `IDLE`, `WAIT_GNT` (request sent, cache hasn't granted), `SEND_TAG` (physical tag arriving after translation, cycle after grant), and the error/abort states `ABORT_TRANSACTION` / `WAIT_FLUSH`. Separately, the cache controller runs `IDLE → READ → MISS → WAIT_REFILL_GNT → IDLE` per PlanV's dive. **Typical load-hit latency** in CV64A6 with the write-back (standard) cache is **3 cycles from issue to `load_valid_o`** (doc: "data RAM accesses have a longer latency of 3 cycles on a hit"), because address generation and translation eat two cycles before the cache lookup. A miss adds the refill cost — typically 10–30 cycles depending on AXI topology. **`load_valid_o` pulses for one cycle** when the load result is available and goes to scoreboard via LOAD_WB (port 2).

**Store unit FSM** has three main states `IDLE`, `VALID_STORE`, `WAIT_TRANSLATION`. From the pipeline's POV a store "completes" when it enters the **speculative store buffer** — that is one cycle after issue on the fast path. `store_valid_o` pulses then, and STORE_WB (port 1) writes `mem_q[N].sbe.valid=1`. Actual memory write happens later from the commit-side store buffer, controlled by the `commit_lsu_o / commit_lsu_ready_i` handshake and optionally gated by `dcache_wbuffer_not_ni_i` for non-idempotent regions.

**MUL is pipelined, typically 2 cycles** (MUL), **DIV/REM is iterative, typically 33–65 cycles** depending on XLEN. MULT uses FLU_WB (port 0) sharing with ALU. **FPU latencies** (FPnew-based `fpu_wrap`): FADD/FMUL ~3–4 cycles, FDIV double-precision **iterative ~18–25 cycles**, FSQRT similar. FPU uses FPU_WB (port 3).

## Part 1D — Commit, flushes, and RVFI

**Commit (`commit_stage.sv`, `NrCommitPorts=2`):** `commit_instr_i[0]` is oldest, `commit_instr_i[1]` is next. Port 1 only retires if port 0 retired cleanly and the pair avoids structural conflicts (no CSR, fence, AMO, ECALL/EBREAK/WFI, no MRET/SRET/DRET, no exception, at most one store). In practice you'll see dual retire mostly for ALU-ALU or ALU-LOAD pairs. **`commit_instr_i[0].pc` is the PC retiring this cycle when `commit_ack_o[0]=1`**; `.is_compressed` determines the +2 vs +4 advance. **`dcache_wbuffer_not_ni_i`** is asserted when the write buffer contains no non-idempotent (I/O) entries; it gates commit of NI stores to preserve ordering of MMIO writes. On `cv32a65x`/`cv32a60x` (write-through cache) it is tied to 0.

**Flush family is centralized in `controller.sv`**: it generates `flush_if_o`, `flush_unissued_instr_o`, `flush_ctrl_id` (scoreboard nuclear), `flush_ctrl_ex` (FU state), `flush_ctrl_bp` (BHT/RAS in-flight), `flush_tlb_o`, `flush_icache_o` (FENCE.I), `flush_dcache_o` (FENCE, AMO side-effect). A **mispredict** fires just `flush_if + flush_unissued` for one cycle (the issued mispredicted branch still retires). A **CSR-side-effect / FENCE.I / exception / eret** fires the *full set* and then drains via `set_pc_commit_o → npc_d = pc_commit + (2|4)` (or `epc_i` for eret, `trap_vector_base_i` for exception, `DmBaseAddress` for debug).

**RVFI is your ground truth.** `core/cva6.sv` emits `rvfi_probes_o` (an opaque struct bundle, gated by macro `RVFI_TRACE`); the separate module `core/cva6_rvfi.sv` converts this into `rvfi_instr_t [NrCommitPorts-1:0] rvfi_o`. Per-commit-port fields: `valid`, `order` (monotonic 64-bit), `insn` (32-bit, compressed zero-extended with `insn[1:0]!=2'b11`), `trap`, `cause`, `halt`, `intr`, `mode` (2-bit priv), `ixl`, `rs1_addr`, `rs1_rdata`, `rs2_addr`, `rs2_rdata`, `rd_addr`, `rd_wdata`, `pc_rdata`, `pc_wdata`, `mem_addr`, `mem_rmask`, `mem_wmask`, `mem_rdata`, `mem_wdata`, `mem_paddr`. In the typical UVM TB the path is `uvmt_cva6_tb.cva6_tb_wrapper_i.rvfi_instance.rvfi_o[i]`; in the APU Verilator harness it is `ariane_testharness.rvfi_instance.rvfi_o[i]`. **Because `rvfi_valid` fires only at architectural commit, every RVFI record is non-speculative.** This is exactly the invariant you need for a cropped trace.

**`common/local/util/instr_tracer.sv` is simulation-only `$fwrite`** to `trace_hart_<id>.dasm`. It samples `fetch_valid/ack`, `issue_ack`, `commit_ack`, etc., maintains SV queues keyed by transaction order, and emits Spike-DASM lines at commit. It is not VCD-observable, only log-file-observable, and it does not dump per-stage cycle timestamps (just `$time` and `clk_ticks` at commit). **Do not rely on the tracer for cycle-accurate per-stage retiming** — use RVFI for retirement order and the RTL state signals (mem_q, wt_valid, commit_ack) for per-stage.

## Part 2 — VCD signal mapping gaps to close

Your existing VCD extractor has the dreq pair and the basic commit signals. The five signals most likely missing that will materially improve your diagnostic:

1. **`rvfi_o[*].valid`, `rvfi_o[*].order`, `rvfi_o[*].pc_rdata`, `rvfi_o[*].insn`, `rvfi_o[*].trap`, `rvfi_o[*].mode`** at the UVM TB level (or `rvfi_probes_o` at the core pin if your dump is core-scoped). This is the single biggest win — it converts any orphan commit into ground truth.
2. **`issue_pointer_q` and `commit_pointer_q[0..1]`** from the scoreboard. With these plus `mem_q[*].issued` you can completely reconstruct slot allocation order without edge-detection heuristics. Also exported as `rvfi_issue_pointer_o` and `rvfi_commit_pointer_o` if RVFI is enabled.
3. **Per-FU source TIDs**: `flu_trans_id`, `load_trans_id`, `store_trans_id`, `fpu_trans_id`, `x_trans_id` out of `ex_stage`. Prefer these over the aggregated `trans_id_i[5]` bus because the aggregated bus is X on inactive ports.
4. **Controller flush outputs**: `flush_ctrl_if`, `flush_unissued_instr_ctrl_id`, `flush_ctrl_id`, `flush_ctrl_ex`, `flush_ctrl_bp`, `set_pc_ctrl_pcgen`. These let you distinguish mispredict (2 signals) from full pipeline flush (all signals).
5. **`instr_queue` internal push and pop pointers, plus `realign_valid[1:0]`** out of `instr_realign`. Without these, correlating fetch-to-issue is heuristic.

There is **no per-slot "just committed" signal**. You must compute it as `commit_ack_o[i] & (commit_pointer_q[i]==N)` and detect the combination per cycle. Fortunately commit_pointer_q advances in simple `+num_commit` fashion so you can run it as a local state machine in your Python tool.

## Part 3 — Cropped-VCD strategy

A cropped VCD violates three assumptions a naive reconstruction would make: (a) the first `mem_q[N].issued=1` you see may already be held from before the window (so no 0→1 edge exists), (b) the first commit event may target a slot you never saw allocated, (c) the first branch resolution may refer to a fetch PC you never saw. The robust handling:

**Cold-start scan.** At cycle T0 (first sampled cycle), record `mem_q[*].issued`, `mem_q[*].sbe.valid`, `mem_q[*].sbe.pc`, `issue_pointer_q`, `commit_pointer_q[*]`. These already-occupied slots are **cold slots**; mark them with `cold=true`, no fetch_ticket, no issue_cycle. When one retires, emit an "ORPHAN COMMIT: slot N, pc=X, rvfi_order=Y" record rather than attempting to correlate to fetch.

**Use RVFI order as the primary key for retirement.** `rvfi_order[i]` is gapless and monotonic across the entire simulation (it starts at 0 at reset but you will see some N0 > 0 at your crop). Use `rvfi_order - N0` as a zero-based retirement index only if you need one; otherwise keep the absolute order.

**Newly-allocated slots inside the window are fully observable.** Once you see a `mem_q[N].issued` transition 0→1 (inside the window), you can record a `fetch_ticket` bound to the PC in `mem_q[N].sbe.pc`; then watch for the `mem_q[N].sbe.valid` 0→1 (writeback) and `commit_ack & commit_pointer_q==N` (retirement). These are your **warm-path instructions** — they get full per-stage timing.

**For the fetch-side correlation specifically**: record every `dreq_o.req=1` rising edge with its `vaddr`, stamp a fetch_ticket number, put it in a pending-fetch queue; pop entries from the queue on `drsp.valid=1` rising edge; further correlate to IQ pushes via `realign_valid` rising edges (with `fetch_vaddr + 2` or `+0` depending on which halfword). When a warm-path slot allocates with pc=X, match X against the most recent fetch_ticket whose vaddr matches — that binds the fetch cycle to the issue cycle. Cold-start slots are never matched this way; just log them as orphans.

**At a trap boundary** (`rvfi_trap=1` or `rvfi_intr=1`), treat `rvfi_pc_wdata` as the new architectural PC origin and reset the fetch-ticket match window — all in-flight speculative fetches are squashed by the flush.

## Part 4 — Python diagnostic tool specification

The tool is a single-pass VCD stream processor keyed on clock posedges. Use **`pyvcd` or `vcdvcd`** for the parser (pyvcd has simpler streaming; vcdvcd is heavier but handles signal-hierarchy lookup well). The main data structure is a `PipelineState` class that owns `slots[NR_SB_ENTRIES]`, `pending_fetches[]`, `in_flight_rvfi[]`, and the current values of ~30 tracked signals.

### Signal table to resolve (VCD ID → logical name)

| Logical name | Typical path | Width | Role |
|---|---|---|---|
| `clk_i` | top.clk | 1 | cycle tick (posedge drives update) |
| `rst_ni` | top.rst_ni | 1 | reset for baseline |
| `dreq_o.req` | frontend.icache_dreq_o.req | 1 | frontend→icache request |
| `dreq_o.vaddr` | frontend.icache_dreq_o.vaddr | VLEN | request vaddr |
| `dreq_o.kill_s1`, `kill_s2` | frontend.icache_dreq_o.{kill_s1,kill_s2} | 1 each | aborts |
| `drsp_i.valid`, `.ready`, `.data` | icache.dreq_o.{valid,ready,data} | 1,1,FETCH_WIDTH | response |
| `miss_o` | icache.miss_o | 1 | icache miss in progress |
| `realign_valid[1:0]`, `realign_pc[1:0]`, `realign_compressed[1:0]` | frontend.instr_realign | 2, 2×VLEN, 2 | IQ push slots |
| `fetch_entry_valid_o`, `fetch_entry_ready_i`, `fetch_entry_o.address` | frontend→id_stage | 1,1,VLEN | IQ pop to decode |
| `decoded_instr_valid_i`, `decoded_instr_ack_o` | id→issue | NrIssuePorts | decode→SB handshake |
| `issue_instr_valid_o`, `issue_ack_i` | SB→IRO | NrIssuePorts | SB→exec handshake |
| `alu_valid_o`, `branch_valid_o`, `lsu_valid_o`, `mult_valid_o`, `fpu_valid_o`, `csr_valid_o` | IRO outputs | NrIssuePorts each | 1-cycle FU dispatch pulses |
| `mem_q[0..7].issued`, `.sbe.valid`, `.sbe.pc`, `.sbe.fu`, `.sbe.rd` | scoreboard | 1,1,VLEN,4,5 | scoreboard state per slot |
| `issue_pointer_q` | scoreboard | TRANS_ID_BITS | allocation head |
| `commit_pointer_q[0..1]` | scoreboard | TRANS_ID_BITS each | retirement heads |
| `wt_valid_i[0..4]`, `trans_id_i[0..4]`, `wbdata_i[0..4]` | scoreboard inputs | 5×{1, TRANS_ID_BITS, XLEN} | 5-port writeback bus |
| `flu_trans_id`, `load_trans_id`, `store_trans_id`, `fpu_trans_id`, `x_trans_id` | ex_stage outputs | TRANS_ID_BITS each | per-FU source TIDs (preferred over aggregate) |
| `resolved_branch_o.valid`, `.is_mispredict`, `.pc`, `.target_address` | branch_unit | {1,1,VLEN,VLEN} | branch resolution |
| `commit_instr_i[0..1].pc`, `.is_compressed`, `commit_ack_o[0..1]` | commit_stage | 2×{VLEN,1,1} | retire |
| `flush_ctrl_if`, `flush_unissued_instr_ctrl_id`, `set_pc_ctrl_pcgen` | controller | 1 each | redirect family |
| `rvfi_o[0..1].valid`, `.order`, `.pc_rdata`, `.insn`, `.trap`, `.mode` | rvfi_instance | 2×{1,64,VLEN,32,1,2} | ground-truth retirement |

### Pseudocode

```python
from collections import deque
from dataclasses import dataclass, field

NR_SB = 8                   # match your config
COLD, WARM = 0, 1

@dataclass
class Slot:
    occupied: bool = False
    state: str   = 'EMPTY'   # EMPTY|ISSUED|WB_DONE
    pc: int      = 0
    fu: int      = 0
    rd: int      = 0
    kind: int    = COLD      # COLD if seen already-occupied at T0
    fetch_ticket: int = -1
    cycle_issued:  int = -1
    cycle_wb:      int = -1
    cycle_commit:  int = -1
    rvfi_order:    int = -1

@dataclass
class FetchTicket:
    tid_counter: int
    cycle_req:   int
    vaddr:       int
    cycle_valid: int = -1
    hit:         bool = False   # True if valid came within 1-2 cycles & miss_o never asserted
    pc_matched:  int = -1       # PC of the slot it bound to

class PipelineState:
    def __init__(self):
        self.slots = [Slot(kind=COLD) for _ in range(NR_SB)]
        self.pending_fetches = deque()         # FetchTicket, FIFO by cycle_req
        self.completed_fetches = []            # once valid returns
        self.rvfi_seen = []                    # list of (cycle, port, order, pc, insn)
        self.cycle = 0
        self.cold_start_done = False
        self.fetch_ticket_ctr = 0

    def on_posedge(self, signals):
        # signals is a dict: current values of every tracked signal
        self.cycle += 1
        if not self.cold_start_done:
            self._cold_start(signals); self.cold_start_done = True
            return
        self._handle_fetch(signals)
        self._handle_issue(signals)
        self._handle_writeback(signals)
        self._handle_commit(signals)
        self._handle_rvfi(signals)
        self._handle_flush(signals)
        self._print_cycle(signals)

    def _cold_start(self, s):
        # Record already-occupied slots; they are ORPHANS
        for n in range(NR_SB):
            if s[f'mem_q[{n}].issued']:
                sl = self.slots[n]
                sl.occupied = True
                sl.state = 'WB_DONE' if s[f'mem_q[{n}].sbe.valid'] else 'ISSUED'
                sl.pc = s[f'mem_q[{n}].sbe.pc']
                sl.kind = COLD

    def _handle_fetch(self, s):
        # New icache request: record a FetchTicket
        if s['dreq_o.req'] and not s.prev['dreq_o.req']:
            self.fetch_ticket_ctr += 1
            self.pending_fetches.append(
                FetchTicket(self.fetch_ticket_ctr, self.cycle, s['dreq_o.vaddr']))
        # Response valid: stamp the head ticket
        if s['drsp_i.valid'] and not s.prev['drsp_i.valid']:
            if self.pending_fetches:
                t = self.pending_fetches.popleft()
                t.cycle_valid = self.cycle
                t.hit = (self.cycle - t.cycle_req <= 2)
                self.completed_fetches.append(t)

    def _handle_issue(self, s):
        # Detect mem_q[N].issued 0->1 (WARM allocation)
        for n in range(NR_SB):
            was = s.prev[f'mem_q[{n}].issued']
            now = s[f'mem_q[{n}].issued']
            if now and not was:
                sl = self.slots[n]
                sl.occupied = True; sl.state = 'ISSUED'
                sl.kind = WARM
                sl.pc = s[f'mem_q[{n}].sbe.pc']
                sl.fu = s[f'mem_q[{n}].sbe.fu']
                sl.rd = s[f'mem_q[{n}].sbe.rd']
                sl.cycle_issued = self.cycle
                # Match to most recent fetch_ticket with vaddr matching pc aligned
                sl.fetch_ticket = self._match_fetch(sl.pc)

    def _match_fetch(self, pc):
        # Search completed_fetches for a vaddr whose 32b aligned block contains pc
        for t in reversed(self.completed_fetches[-16:]):
            if (t.vaddr & ~0x3) == (pc & ~0x3) and t.pc_matched == -1:
                t.pc_matched = pc
                return t.tid_counter
        return -1

    def _handle_writeback(self, s):
        # Prefer per-FU source TIDs
        for port, (valid_name, tid_name) in [
            ('FLU', ('flu_valid_o', 'flu_trans_id')),
            ('STORE', ('store_valid_o','store_trans_id')),
            ('LOAD', ('load_valid_o', 'load_trans_id')),
            ('FPU',  ('fpu_valid_o',  'fpu_trans_id')),
            ('ACC',  ('x_valid_o',    'x_trans_id')),
        ]:
            if s.get(valid_name):
                n = s[tid_name]
                sl = self.slots[n]
                if sl.occupied and sl.state == 'ISSUED':
                    sl.state = 'WB_DONE'
                    sl.cycle_wb = self.cycle

    def _handle_commit(self, s):
        for i in (0, 1):
            if s[f'commit_ack_o[{i}]']:
                n = s[f'commit_pointer_q[{i}]']
                sl = self.slots[n]
                sl.cycle_commit = self.cycle
                # Validate: PC matches?
                assert sl.pc == s[f'commit_instr_i[{i}].pc']
                sl.occupied = False; sl.state = 'EMPTY'

    def _handle_rvfi(self, s):
        for i in (0, 1):
            if s.get(f'rvfi_o[{i}].valid'):
                self.rvfi_seen.append((
                    self.cycle, i,
                    s[f'rvfi_o[{i}].order'],
                    s[f'rvfi_o[{i}].pc_rdata'],
                    s[f'rvfi_o[{i}].insn']))

    def _handle_flush(self, s):
        # On full flush, clear all slots
        if s['flush_ctrl_id']:
            for sl in self.slots: sl.occupied=False; sl.state='EMPTY'
            self.pending_fetches.clear()

    def _print_cycle(self, s):
        print(f"CYC {self.cycle:4d} | "
              f"iss_ptr={s['issue_pointer_q']} "
              f"cmt_ptr={s['commit_pointer_q[0]']}")
        occ = [n for n,sl in enumerate(self.slots) if sl.occupied]
        print(f"  SB occupied: {occ}")
        for n in occ:
            sl = self.slots[n]
            tag = 'COLD' if sl.kind==COLD else f"tkt#{sl.fetch_ticket}"
            print(f"    slot[{n}] {sl.state:8s} pc=0x{sl.pc:08x} "
                  f"fu={sl.fu} rd={sl.rd} {tag} "
                  f"is={sl.cycle_issued} wb={sl.cycle_wb} cm={sl.cycle_commit}")
        # Fetch pipeline snapshot
        if s['dreq_o.req']:
            print(f"  FE1: req@vaddr=0x{s['dreq_o.vaddr']:08x}")
        if s['drsp_i.valid']:
            print(f"  FE2: valid data returned (miss_o={s['miss_o']})")
        # RVFI retirements this cycle
        for cyc,i,order,pc,insn in self.rvfi_seen[-4:]:
            if cyc==self.cycle:
                print(f"  RVFI[{i}]: order={order} pc=0x{pc:08x} insn=0x{insn:08x}")
```

### Output at each cycle (first 50–100)

Example target output layout (one cycle block):

```
CYC   42 | iss_ptr=4 cmt_ptr=1
  SB occupied: [1, 2, 3]
    slot[1] WB_DONE  pc=0x80001020 fu=ALU    rd=10 tkt#17  is=35 wb=38 cm=-1
    slot[2] ISSUED   pc=0x80001024 fu=LOAD   rd=11 tkt#18  is=38 wb=-1 cm=-1
    slot[3] ISSUED   pc=0x80001028 fu=BRANCH rd=0  COLD    is=-1 wb=-1 cm=-1
  FE1: req@vaddr=0x8000102c
  RVFI[0]: order=421 pc=0x80001020 insn=0x00b50533
```

### The sanity-check validation

Add an assertion layer that checks, for every WARM retirement, that **`rvfi_order[port]`, `rvfi_pc_rdata[port]`, and the slot's tracked `pc` all agree**. For COLD retirements, only the RVFI pair is validated (the slot has no fetch ticket). Also assert: if `oldest slot's cycle_issued == X and slot's pc == Y`, the most recent matched fetch ticket for PC Y should have `cycle_req <= X` and `cycle_valid <= X` — this is your "does our architectural understanding match hardware?" check. If any assertion fails, dump the last 20 cycles of state to a debug log.

## Conclusion

The scoreboard is a circular FIFO with a three-edge per-slot lifecycle, writeback aggregates into a fixed 5-port bus with indices `{FLU=0, STORE=1, LOAD=2, FPU=3, ACC=4}` defined in `ariane_pkg.sv`, and commit enforces strict program order while allowing dual-retire under narrow conditions. The one non-obvious architectural fact that trips up diagnostic tools: **`mem_q[N].issued` means "slot in-flight" and `mem_q[N].sbe.valid` means "result back" — they are different flags with 1+ cycles between them on every multi-cycle FU**. For cropped traces, accept that anything already in `mem_q` at T0 is an orphan and only bind fetch tickets to slots whose issue edge you witnessed; for everything else, lean on RVFI as speculation-free ground truth. With these two disciplines and the signal table above, your tool can validate "oldest fetch ticket = issuing slot's PC" as a warm-path invariant while gracefully handling the cold-start tail. The single highest-leverage thing you can do before running the tool is confirm `RVFI_TRACE` was defined for the simulation and that `rvfi_o[*]` is in the VCD dump scope — without it, your orphan-handling has no ground truth, and cropped traces become epistemically much weaker.
// Copyright 2026 Universidad Nacional de Cordoba, FaMAF.
// Testbench only. Not for synthesis.
//
// DDR3 controller and device timing model.
//
// This is the gem5 MemCtrl plus DRAMInterface pair rewritten in SystemVerilog:
// a read queue and a write queue scheduled first ready first come first served,
// in front of a rank and bank state machine that charges tRCD, tRP, tRAS, tRC,
// tRRD, tFAW, tCL, tBURST, the read to write and write to read bus
// turnarounds, and per rank refresh.
//
// ---------------------------------------------------------------------------
// Why the timing is computed analytically rather than cycle by cycle
// ---------------------------------------------------------------------------
// The harness clock is 20 ns. A DDR3 row miss is tRP + tRCD + tCL = 41.25 ns,
// which is three commands: PRE, ACT, RD. A model that issued one command per
// harness cycle would spend three cycles, 60 ns, on a sequence the device
// finishes in 41.25 ns, and the error would grow with every constraint in the
// path.
//
// So this model does what gem5 does. When the scheduler picks a request it
// computes the whole command sequence in picoseconds from the current bank and
// bus state, advances that state, and records the tick at which the data is
// ready. Nothing is quantised until the front end hands the response back on a
// clock edge. One transaction therefore carries at most one harness cycle of
// rounding, instead of one per constraint.
//
// The one place a cycle boundary still shows is request issue: at most
// IssuePerCycle requests can start in a single harness cycle. That bound does
// not bind here. Four bursts of 64 bytes in 20 ns is 12.8 GB/s, the full
// DDR3-1600 data rate, whereas the harness moves 64 bits per cycle at 50 MHz,
// which is 400 MB/s. The AXI bus saturates 32 times over before the command
// bus does.
//
// ---------------------------------------------------------------------------
// Assignment discipline
// ---------------------------------------------------------------------------
// The bank, rank, bus and queue state is written with blocking assignments
// inside one always_ff, because an access issued second in a cycle has to see
// the state left by the access issued first, which is exactly what blocking
// assignment gives. Nothing outside the block reads that state.
//
// Everything another module does read, the handshake and the statistics, is a
// separate register written non blocking at the end of the block. That keeps
// the module boundary free of the read during write race that reading the
// working state directly would create.
module ddr3_scheduler #(
    parameter int unsigned AddrWidth   = 64,
    parameter int unsigned TagWidth    = 8,
    /// Harness clock period in picoseconds. 20000 is the 50 MHz testharness.
    parameter int unsigned TckHostPs   = 20000,
    /// Rows per bank, from the memory size. gem5 computes this the same way:
    ///   size / (rowBufferSize * banksPerRank * ranksPerChannel)
    /// 1 GiB gives 1GiB / (8KiB * 8 * 2) = 8192.
    parameter int unsigned RowsPerBank = 8192,
    /// Requests that may start in one harness cycle. See the note above.
    parameter int unsigned IssuePerCycle = 4,
    /// Accesses issued to the device but not yet returned.
    parameter int unsigned MaxInFlight = 16,
    /// gem5 answers a write as soon as it enters the write queue. Set to 0 to
    /// hold the answer until the data actually reaches the array.
    parameter int unsigned PostedWrites = 1,
    /// Set to 0 to remove refresh, as a sensitivity check.
    parameter int unsigned EnableRefresh = 1,
    /// Controller pipeline after the device access, gem5's
    /// static_backend_latency. The AXI front end adds about three cycles of its
    /// own, so reduce this to match gem5 end to end rather than model both.
    parameter int unsigned BackendPs = ddr3_pkg::BackendPs,
    parameter int unsigned RdQDepth = ddr3_pkg::ReadBufferSize,
    parameter int unsigned WrQDepth = ddr3_pkg::WriteBufferSize
) (
    input  logic                  clk_i,
    input  logic                  rst_ni,

    // Request in.
    input  logic                  req_valid_i,
    output logic                  req_ready_o,
    input  logic [AddrWidth-1:0]  req_addr_i,
    input  logic                  req_we_i,
    input  logic [TagWidth-1:0]   req_tag_i,

    // Read completion, and write completion when PostedWrites is 0.
    output logic                  done_valid_o,
    output logic [TagWidth-1:0]   done_tag_o,

    // Posted write acknowledge. Its own port so it never has to queue behind a
    // read completion.
    output logic                  wack_valid_o,
    output logic [TagWidth-1:0]   wack_tag_o,

    output ddr3_pkg::ddr3_stats_t stats_o
);

  import ddr3_pkg::*;

  localparam int unsigned NumBanks = RanksPerChan * BanksPerRank;
  localparam int unsigned RankIdxW = $clog2(RanksPerChan);
  localparam int unsigned BankIdxW = $clog2(BanksPerRank);

  localparam int unsigned WrHighThresh = (WrQDepth * WriteHighThreshPc) / 100;
  localparam int unsigned WrLowThresh  = (WrQDepth * WriteLowThreshPc) / 100;

  // Flat bank index. Rank major, so rank r bank b is at r*BanksPerRank + b.
  function automatic int unsigned bank_idx(input logic [RankIdxW-1:0] r,
                                           input logic [BankIdxW-1:0] b);
    return (int'(r) * BanksPerRank) + int'(b);
  endfunction

  function automatic ps_t ps_max(input ps_t a, input ps_t b);
    return (a > b) ? a : b;
  endfunction

  // ---------------------------------------------------------------------------
  // Working state, blocking assignment only
  // ---------------------------------------------------------------------------
  ps_t                  now_q;

  logic                 bk_open_q  [NumBanks];
  logic [31:0]          bk_row_q   [NumBanks];
  ps_t                  bk_act_at_q[NumBanks];  // earliest ACT
  ps_t                  bk_pre_at_q[NumBanks];  // earliest PRE
  ps_t                  bk_col_at_q[NumBanks];  // earliest RD or WR

  // tFAW: the last ActLimit activate times in each rank, as a ring.
  ps_t                  act_hist_q [RanksPerChan][ActLimit];
  logic [$clog2(ActLimit)-1:0] act_ptr_q[RanksPerChan];

  // Data bus.
  ps_t                  bus_free_q;
  logic                 bus_is_wr_q;
  logic [RankIdxW-1:0]  bus_rank_q;
  ps_t                  last_rd_end_q;
  ps_t                  last_wr_end_q;

  // Refresh, per rank.
  ps_t                  ref_due_q [RanksPerChan];

  // Queues. Compact: entries 0 to count-1 are live and 0 is the oldest, so
  // first come first served is just the lowest index.
  logic [AddrWidth-1:0] rdq_addr_q[RdQDepth];
  logic [TagWidth-1:0]  rdq_tag_q [RdQDepth];
  ps_t                  rdq_arr_q [RdQDepth];
  int unsigned          rdq_cnt_q;

  logic [AddrWidth-1:0] wrq_addr_q[WrQDepth];
  logic [TagWidth-1:0]  wrq_tag_q [WrQDepth];
  int unsigned          wrq_cnt_q;

  // Issued but not yet due. Scanned for the earliest due entry, because with
  // bank parallelism a later access can legitimately finish first and a strict
  // queue here would reintroduce head of line blocking by hand.
  logic                 fl_val_q[MaxInFlight];
  ps_t                  fl_due_q[MaxInFlight];
  logic [TagWidth-1:0]  fl_tag_q[MaxInFlight];
  ps_t                  fl_arr_q[MaxInFlight];
  logic                 fl_we_q [MaxInFlight];
  int unsigned          fl_cnt_q;

  logic                 serve_wr_q;
  int unsigned          wr_run_q;

  ddr3_stats_t          st_q;

  // ---------------------------------------------------------------------------
  // Registered module boundary
  // ---------------------------------------------------------------------------
  logic                 done_val_r;
  logic [TagWidth-1:0]  done_tag_r;
  logic                 wack_val_r;
  logic [TagWidth-1:0]  wack_tag_r;
  int unsigned          rdq_cnt_r, wrq_cnt_r, fl_cnt_r;
  ddr3_stats_t          st_r;

  assign done_valid_o = done_val_r;
  assign done_tag_o   = done_tag_r;
  assign wack_valid_o = wack_val_r;
  assign wack_tag_o   = wack_tag_r;
  assign stats_o      = st_r;

  // Room for the request, judged on the state as it stood at this clock edge.
  logic rd_room, wr_room;
  assign rd_room     = (rdq_cnt_r < RdQDepth) && (fl_cnt_r < MaxInFlight);
  assign wr_room     = (wrq_cnt_r < WrQDepth) &&
                       ((PostedWrites != 0) || (fl_cnt_r < MaxInFlight));
  assign req_ready_o = req_we_i ? wr_room : rd_room;

  // ---------------------------------------------------------------------------
  // Access timing. Mirrors gem5 DRAMInterface::doDRAMAccess.
  // ---------------------------------------------------------------------------
  task automatic do_access(input logic [AddrWidth-1:0] addr,
                           input logic                 is_wr,
                           output ps_t                 ready_at);
    dram_loc_t   loc;
    int unsigned bi;
    ps_t         act_at, pre_at, cmd_at, burst_end, oldest_act;
    logic        hit;

    loc = decode_addr(64'(addr), RowsPerBank);
    bi  = bank_idx(loc.rank, loc.bank);

    hit = bk_open_q[bi] && (bk_row_q[bi] == loc.row);

    if (hit) begin
      st_q.row_hits = st_q.row_hits + 1;
    end else begin
      if (bk_open_q[bi]) begin
        // A different row is open. Close it, then wait tRP.
        pre_at = ps_max(now_q, bk_pre_at_q[bi]);
        act_at = pre_at + ps_t'(TrpPs);
        st_q.row_conflicts = st_q.row_conflicts + 1;
      end else begin
        act_at = now_q;
        st_q.row_empty = st_q.row_empty + 1;
      end

      // tRC from this bank's own last activate, and tRRD from any activate in
      // this rank, are both already folded into bk_act_at_q.
      act_at = ps_max(act_at, bk_act_at_q[bi]);

      // tFAW. act_ptr_q points at the oldest of the last ActLimit activates in
      // this rank, so a fifth activate cannot start until tXAW after it. The
      // zero test keeps the window from applying before the ring has filled.
      oldest_act = act_hist_q[loc.rank][act_ptr_q[loc.rank]];
      if (oldest_act != 64'd0) begin
        act_at = ps_max(act_at, oldest_act + ps_t'(TxawPs));
      end
      act_hist_q[loc.rank][act_ptr_q[loc.rank]] = act_at;
      act_ptr_q[loc.rank] = ($clog2(ActLimit))'((int'(act_ptr_q[loc.rank]) + 1) % ActLimit);

      // Bank constraints created by this activate.
      bk_open_q[bi]   = 1'b1;
      bk_row_q[bi]    = loc.row;
      bk_col_at_q[bi] = act_at + ps_t'(TrcdPs);
      bk_pre_at_q[bi] = act_at + ps_t'(TrasPs);
      bk_act_at_q[bi] = act_at + ps_t'(TrcPs);

      // tRRD holds off activates to every other bank in the same rank.
      for (int unsigned ob = 0; ob < BanksPerRank; ob++) begin
        int unsigned obi;
        obi = bank_idx(loc.rank, BankIdxW'(ob));
        if (obi != bi) begin
          bk_act_at_q[obi] = ps_max(bk_act_at_q[obi], act_at + ps_t'(TrrdPs));
        end
      end
    end

    // Column command. Gated by tRCD or tCCD from this bank, then by the data
    // bus: turnaround if the direction changed, tCS if the rank changed.
    cmd_at = ps_max(now_q, bk_col_at_q[bi]);

    if (is_wr && !bus_is_wr_q && (last_rd_end_q != 64'd0)) begin
      cmd_at = ps_max(cmd_at, last_rd_end_q + ps_t'(TrtwPs));
      st_q.rd_to_wr_switch = st_q.rd_to_wr_switch + 1;
    end else if (!is_wr && bus_is_wr_q && (last_wr_end_q != 64'd0)) begin
      cmd_at = ps_max(cmd_at, last_wr_end_q + ps_t'(TwtrPs));
      st_q.wr_to_rd_switch = st_q.wr_to_rd_switch + 1;
    end

    if (loc.rank != bus_rank_q) begin
      cmd_at = ps_max(cmd_at, bus_free_q + ps_t'(TcsPs));
    end
    cmd_at = ps_max(cmd_at, bus_free_q);

    burst_end        = cmd_at + ps_t'(TburstPs);
    bus_free_q       = burst_end;
    bus_is_wr_q      = is_wr;
    bus_rank_q       = loc.rank;
    st_q.bus_busy_ps = st_q.bus_busy_ps + ps_t'(TburstPs);

    // tCCD between column commands to the same bank.
    bk_col_at_q[bi] = cmd_at + ps_t'(TburstPs);

    if (is_wr) begin
      // The row cannot close until the write recovers: tCWL + tBURST + tWR.
      bk_pre_at_q[bi] = ps_max(bk_pre_at_q[bi],
                               cmd_at + ps_t'(TcwlPs) + ps_t'(TburstPs) + ps_t'(TwrPs));
      last_wr_end_q   = burst_end;
      ready_at        = cmd_at + ps_t'(TcwlPs) + ps_t'(TburstPs);
      st_q.writes     = st_q.writes + 1;
    end else begin
      // tRTP from the read command before the row may close.
      bk_pre_at_q[bi] = ps_max(bk_pre_at_q[bi], cmd_at + ps_t'(TrtpPs));
      last_rd_end_q   = burst_end;
      ready_at        = cmd_at + ps_t'(TclPs) + ps_t'(TburstPs);
      st_q.reads      = st_q.reads + 1;
    end

    // gem5 charges its controller pipeline either side of the device access.
    st_q.dev_lat_ps_sum = st_q.dev_lat_ps_sum + (ready_at - now_q);
    st_q.dev_accesses   = st_q.dev_accesses + 1;
    ready_at = ready_at + ps_t'(BackendPs);
  endtask

  // Lowest indexed, so oldest, entry whose row is open, else index 0, first
  // come first served. Written once per queue, since Verilator 5.008 cannot
  // bind a fixed-size unpacked array to an unsized array port.
  function automatic int unsigned pick_rd();
    for (int unsigned i = 0; i < RdQDepth; i++) begin
      if (i < rdq_cnt_q) begin
        dram_loc_t   l;
        int unsigned b;
        l = decode_addr(64'(rdq_addr_q[i]), RowsPerBank);
        b = bank_idx(l.rank, l.bank);
        if (bk_open_q[b] && (bk_row_q[b] == l.row)) return i;
      end
    end
    return 0;
  endfunction

  function automatic int unsigned pick_wr();
    for (int unsigned i = 0; i < WrQDepth; i++) begin
      if (i < wrq_cnt_q) begin
        dram_loc_t   l;
        int unsigned b;
        l = decode_addr(64'(wrq_addr_q[i]), RowsPerBank);
        b = bank_idx(l.rank, l.bank);
        if (bk_open_q[b] && (bk_row_q[b] == l.row)) return i;
      end
    end
    return 0;
  endfunction

  // ---------------------------------------------------------------------------
  // Main process
  // ---------------------------------------------------------------------------
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      now_q         = '0;
      bus_free_q    = '0;
      bus_is_wr_q   = 1'b0;
      bus_rank_q    = '0;
      last_rd_end_q = '0;
      last_wr_end_q = '0;
      rdq_cnt_q     = 0;
      wrq_cnt_q     = 0;
      fl_cnt_q      = 0;
      serve_wr_q    = 1'b0;
      wr_run_q      = 0;
      st_q          = '0;
      for (int unsigned i = 0; i < NumBanks; i++) begin
        bk_open_q[i]   = 1'b0;
        bk_row_q[i]    = '0;
        bk_act_at_q[i] = '0;
        bk_pre_at_q[i] = '0;
        bk_col_at_q[i] = '0;
      end
      for (int unsigned r = 0; r < RanksPerChan; r++) begin
        act_ptr_q[r] = '0;
        // Stagger the ranks so they do not stall together, as a real
        // controller does.
        ref_due_q[r] = (ps_t'(TrefiPs) / ps_t'(RanksPerChan)) * (ps_t'(r) + 64'd1);
        for (int unsigned k = 0; k < ActLimit; k++) act_hist_q[r][k] = '0;
      end
      for (int unsigned i = 0; i < MaxInFlight; i++) fl_val_q[i] = 1'b0;

      done_val_r <= 1'b0;
      done_tag_r <= '0;
      wack_val_r <= 1'b0;
      wack_tag_r <= '0;
      rdq_cnt_r  <= 0;
      wrq_cnt_r  <= 0;
      fl_cnt_r   <= 0;
      st_r       <= '0;
    end else begin
      automatic ps_t         t_now;
      automatic logic        did_issue;
      automatic logic        wr_merged;
      automatic int unsigned pick;
      automatic ps_t         ready_at;
      automatic int unsigned slot;
      automatic int unsigned best;
      automatic ps_t         best_due;
      automatic logic        nx_done_val;
      automatic logic [TagWidth-1:0] nx_done_tag;
      automatic logic        nx_wack_val;
      automatic logic [TagWidth-1:0] nx_wack_tag;
      automatic ps_t         inflight;

      t_now = now_q + ps_t'(TckHostPs);
      now_q = t_now;

      nx_done_val = 1'b0;
      nx_done_tag = '0;
      nx_wack_val = 1'b0;
      nx_wack_tag = '0;

      // ---------------------------------------------------------------------
      // Refresh. Every bank in the rank closes, then the rank is unavailable
      // for tRFC. Per rank, as gem5 models it.
      // ---------------------------------------------------------------------
      if (EnableRefresh != 0) begin
        for (int unsigned r = 0; r < RanksPerChan; r++) begin
          if (t_now >= ref_due_q[r]) begin
            automatic ps_t pre_done, ref_start, ref_stop;
            automatic int unsigned bi2;
            pre_done = t_now;
            for (int unsigned b = 0; b < BanksPerRank; b++) begin
              bi2 = bank_idx(RankIdxW'(r), BankIdxW'(b));
              if (bk_open_q[bi2]) begin
                pre_done = ps_max(pre_done, bk_pre_at_q[bi2] + ps_t'(TrpPs));
              end
            end
            ref_start = ps_max(t_now, pre_done);
            ref_stop  = ref_start + ps_t'(TrfcPs);
            for (int unsigned b = 0; b < BanksPerRank; b++) begin
              bi2 = bank_idx(RankIdxW'(r), BankIdxW'(b));
              bk_open_q[bi2]   = 1'b0;
              bk_act_at_q[bi2] = ps_max(bk_act_at_q[bi2], ref_stop);
              bk_col_at_q[bi2] = ps_max(bk_col_at_q[bi2], ref_stop);
              bk_pre_at_q[bi2] = ps_max(bk_pre_at_q[bi2], ref_stop);
            end
            ref_due_q[r]          = ref_due_q[r] + ps_t'(TrefiPs);
            st_q.refreshes        = st_q.refreshes + 1;
            st_q.refresh_stall_ps = st_q.refresh_stall_ps + (ref_stop - ref_start);
          end
        end
      end

      // ---------------------------------------------------------------------
      // Accept one request
      // ---------------------------------------------------------------------
      if (req_valid_i && req_ready_o) begin
        if (req_we_i) begin
          // A posted write merges into one queued for the same burst and never
          // reaches the DRAM alone, as gem5's MemCtrl::addToWriteQueue does.
          wr_merged = 1'b0;
          if (PostedWrites != 0) begin
            for (int unsigned i = 0; i < WrQDepth; i++) begin
              if ((i < wrq_cnt_q) &&
                  ((wrq_addr_q[i] / AddrWidth'(BurstBytes)) ==
                   (req_addr_i / AddrWidth'(BurstBytes)))) begin
                wr_merged = 1'b1;
              end
            end
          end
          if (!wr_merged) begin
            wrq_addr_q[wrq_cnt_q] = req_addr_i;
            wrq_tag_q [wrq_cnt_q] = req_tag_i;
            wrq_cnt_q             = wrq_cnt_q + 1;
          end
          if (PostedWrites != 0) begin
            // gem5 answers the write the moment it is buffered. The front end
            // has already placed the data in the array, so this is a posted
            // write, not an early answer to an unfinished one.
            nx_wack_val = 1'b1;
            nx_wack_tag = req_tag_i;
          end
        end else begin
          rdq_addr_q[rdq_cnt_q] = req_addr_i;
          rdq_tag_q [rdq_cnt_q] = req_tag_i;
          rdq_arr_q [rdq_cnt_q] = t_now;
          rdq_cnt_q             = rdq_cnt_q + 1;
        end
      end

      // ---------------------------------------------------------------------
      // Bus direction, as gem5's processNextReqEvent: writes drain past the high
      // water mark, or past the low one with nothing to read, and reads return
      // when the queue empties, falls 16 below the low mark or has sent 16.
      // ---------------------------------------------------------------------
      if (!serve_wr_q) begin
        if ((wrq_cnt_q > WrHighThresh) ||
            ((rdq_cnt_q == 0) && (wrq_cnt_q > WrLowThresh))) begin
          serve_wr_q = 1'b1;
          wr_run_q   = 0;
        end
      end else begin
        if ((wrq_cnt_q == 0) ||
            (wrq_cnt_q + MinWritesPerSwitch < WrLowThresh) ||
            ((rdq_cnt_q > 0) && (wr_run_q >= MinWritesPerSwitch))) begin
          serve_wr_q = 1'b0;
        end
      end

      // ---------------------------------------------------------------------
      // Issue
      // ---------------------------------------------------------------------
      for (int unsigned k = 0; k < IssuePerCycle; k++) begin
        did_issue = 1'b0;

        if (serve_wr_q && (wrq_cnt_q > 0) &&
            ((PostedWrites != 0) || (fl_cnt_q < MaxInFlight))) begin

          pick = pick_wr();
          do_access(wrq_addr_q[pick], 1'b1, ready_at);

          if (PostedWrites == 0) begin
            slot = MaxInFlight;
            for (int unsigned i = 0; i < MaxInFlight; i++) begin
              if ((slot == MaxInFlight) && !fl_val_q[i]) slot = i;
            end
            fl_val_q[slot] = 1'b1;
            fl_due_q[slot] = ready_at;
            fl_tag_q[slot] = wrq_tag_q[pick];
            fl_we_q [slot] = 1'b1;
            fl_arr_q[slot] = t_now;
            fl_cnt_q       = fl_cnt_q + 1;
          end

          for (int unsigned i = 0; i < WrQDepth - 1; i++) begin
            if (i >= pick) begin
              wrq_addr_q[i] = wrq_addr_q[i+1];
              wrq_tag_q [i] = wrq_tag_q [i+1];
            end
          end
          wrq_cnt_q = wrq_cnt_q - 1;
          wr_run_q  = wr_run_q + 1;
          did_issue = 1'b1;

        end else if (!serve_wr_q && (rdq_cnt_q > 0) && (fl_cnt_q < MaxInFlight)) begin

          pick = pick_rd();
          do_access(rdq_addr_q[pick], 1'b0, ready_at);

          slot = MaxInFlight;
          for (int unsigned i = 0; i < MaxInFlight; i++) begin
            if ((slot == MaxInFlight) && !fl_val_q[i]) slot = i;
          end
          fl_val_q[slot] = 1'b1;
          fl_due_q[slot] = ready_at;
          fl_tag_q[slot] = rdq_tag_q[pick];
          fl_we_q [slot] = 1'b0;
          fl_arr_q[slot] = rdq_arr_q[pick];
          fl_cnt_q       = fl_cnt_q + 1;

          for (int unsigned i = 0; i < RdQDepth - 1; i++) begin
            if (i >= pick) begin
              rdq_addr_q[i] = rdq_addr_q[i+1];
              rdq_tag_q [i] = rdq_tag_q [i+1];
              rdq_arr_q [i] = rdq_arr_q [i+1];
            end
          end
          rdq_cnt_q = rdq_cnt_q - 1;
          did_issue = 1'b1;
        end

        if (!did_issue) break;
      end

      // ---------------------------------------------------------------------
      // Retire the earliest due access.
      // ---------------------------------------------------------------------
      best     = MaxInFlight;
      best_due = '1;
      for (int unsigned i = 0; i < MaxInFlight; i++) begin
        if (fl_val_q[i] && (fl_due_q[i] <= t_now) && (fl_due_q[i] < best_due)) begin
          best     = i;
          best_due = fl_due_q[i];
        end
      end
      if (best != MaxInFlight) begin
        nx_done_val    = 1'b1;
        nx_done_tag    = fl_tag_q[best];
        fl_val_q[best] = 1'b0;
        fl_cnt_q       = fl_cnt_q - 1;
        if (!fl_we_q[best]) begin
          automatic ps_t lat;
          lat = t_now - fl_arr_q[best];
          st_q.read_lat_ps_sum = st_q.read_lat_ps_sum + lat;
          if (lat > st_q.read_lat_ps_max) st_q.read_lat_ps_max = lat;
        end
      end

      // ---------------------------------------------------------------------
      // Memory level parallelism, sampled every cycle: how many reads the
      // system keeps in flight, which decides whether added memory latency is
      // hidden or shows up as stall.
      // ---------------------------------------------------------------------
      inflight = ps_t'(fl_cnt_q) + ps_t'(rdq_cnt_q);
      if (inflight > 0) begin
        st_q.mlp_sum     = st_q.mlp_sum + inflight;
        st_q.mlp_samples = st_q.mlp_samples + 1;
        if (inflight > st_q.mlp_max) st_q.mlp_max = inflight;
      end

      done_val_r <= nx_done_val;
      done_tag_r <= nx_done_tag;
      wack_val_r <= nx_wack_val;
      wack_tag_r <= nx_wack_tag;
      rdq_cnt_r  <= rdq_cnt_q;
      wrq_cnt_r  <= wrq_cnt_q;
      fl_cnt_r   <= fl_cnt_q;
      st_r       <= st_q;
    end
  end

endmodule

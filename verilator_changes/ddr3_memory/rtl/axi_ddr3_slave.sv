// Copyright 2026 Universidad Nacional de Cordoba, FaMAF.
// Testbench only. Not for synthesis.
//
// AXI slave with a DDR3 timing model in front of the behavioural array.
//
// Drop in replacement for axi2mem in ariane_testharness.sv. The port list is
// axi2mem's, so the array below it is untouched: i_sram keeps its instance
// name and hierarchy, which matters because ariane_tb.cpp preloads the ELF by
// writing straight into
//   ariane_testharness__DOT__i_sram__DOT__gen_cut__BRA__0__KET__...m_storage
// and that path has to keep resolving.
//
// ---------------------------------------------------------------------------
// Why axi2mem had to go rather than be wrapped
// ---------------------------------------------------------------------------
// axi2mem is a single transaction state machine: IDLE to READ or WRITE and
// back, one address at a time, reads winning arbitration. Whatever memory sits
// behind it, the memory level parallelism it presents is 1. A DDR3 model
// behind axi2mem would compute bank parallelism, row hits across banks and
// tFAW throttling that nothing could ever exercise, because a second request
// cannot reach it until the first has fully retired.
//
// That matters for this experiment specifically. The HPDcache sustains more
// than one miss, and gem5 SingleChannelDDR3_1600 serves several outstanding
// requests in parallel. Leaving axi2mem in place would have held the RTL at
// MLP 1 while gem5 ran at its natural MLP, and the resulting disagreement
// would have been read as a memory model difference when it was really the
// adapter. An FPGA CVA6 talks to a MIG controller with genuine queues, so
// queues here are also the more faithful answer.
//
// The scheduler reports the MLP it actually observed, so if something further
// upstream, the crossbar or the atomics adapter, is still serialising, the
// statistics say so directly instead of leaving it to be inferred.
module axi_ddr3_slave #(
    parameter int unsigned AXI_ID_WIDTH   = 10,
    parameter int unsigned AXI_ADDR_WIDTH = 64,
    parameter int unsigned AXI_DATA_WIDTH = 64,
    parameter int unsigned AXI_USER_WIDTH = 10,
    /// Base of the DRAM region. Subtracted before the DDR3 address decode so
    /// rank, bank and row are counted from the start of the device, the way
    /// gem5 counts them from the start of its range.
    parameter logic [63:0] MemBase = 64'h8000_0000,
    /// Device size, for rows per bank. 1 GiB matches gem5 size="1GiB".
    parameter longint unsigned MemSizeBytes = 64'h4000_0000,
    /// Harness clock period in picoseconds. 20000 is 50 MHz.
    parameter int unsigned TckHostPs = 20000,
    /// AXI transactions that may be open at once, each side.
    parameter int unsigned NumRdSlots = 8,
    parameter int unsigned NumWrSlots = 4,
    parameter int unsigned IssuePerCycle = 4,
    parameter int unsigned PostedWrites  = 1,
    parameter int unsigned EnableRefresh = 1,
    /// Controller pipeline after the device access, gem5's
    /// static_backend_latency. See the note on the scheduler parameter.
    parameter int unsigned BackendPs = ddr3_pkg::BackendPs,
    /// Cycles a write beat may be held off by reads before it takes the array
    /// port anyway. Only a starvation backstop, see the note below.
    parameter int unsigned WriteStarveLimit = 8
) (
    input  logic                          clk_i,
    input  logic                          rst_ni,
           AXI_BUS.Slave                  slave,
    // Array port, axi2mem's exactly.
    output logic                          req_o,
    output logic                          we_o,
    output logic [AXI_ADDR_WIDTH-1:0]     addr_o,
    output logic [AXI_DATA_WIDTH/8-1:0]   be_o,
    output logic [AXI_USER_WIDTH-1:0]     user_o,
    output logic [AXI_DATA_WIDTH-1:0]     data_o,
    input  logic [AXI_USER_WIDTH-1:0]     user_i,
    input  logic [AXI_DATA_WIDTH-1:0]     data_i,

    output ddr3_pkg::ddr3_stats_t         stats_o
);

  import ddr3_pkg::*;

  localparam int unsigned LogBytes = $clog2(AXI_DATA_WIDTH/8);
  localparam int unsigned LogBlk   = $clog2(BurstBytes);           // 6
  localparam int unsigned RowsPerBank =
      int'(MemSizeBytes / (RowBufferByte * BanksPerRank * RanksPerChan));

  // One tag space over both slot arrays: bit TagW-1 says which side.
  localparam int unsigned RdIdxW   = $clog2(NumRdSlots);
  localparam int unsigned WrIdxW    = $clog2(NumWrSlots);
  localparam int unsigned SlotIdxW = (RdIdxW > WrIdxW) ? RdIdxW : WrIdxW;
  localparam int unsigned TagW     = SlotIdxW + 1;

  typedef logic [AXI_ADDR_WIDTH-1:0] addr_t;
  typedef logic [AXI_ID_WIDTH-1:0]   id_t;

  // ---------------------------------------------------------------------------
  // Address helpers
  // ---------------------------------------------------------------------------
  // Beat address for an AXI burst, the three cases axi2mem handles. WRAP is a
  // mask rather than axi2mem's comparison chain, exact since the wrap length is
  // always a power of two.
  function automatic addr_t beat_addr(input addr_t       base,
                                      input logic [7:0]  len,
                                      input logic [1:0]  burst,
                                      input logic [8:0]  beat);
    addr_t aligned, cons, total, wrap_base;
    aligned = {base[AXI_ADDR_WIDTH-1:LogBytes], {LogBytes{1'b0}}};
    cons    = aligned + (addr_t'(beat) << LogBytes);
    unique case (burst)
      2'b00: return aligned;                       // FIXED
      2'b10: begin                                 // WRAP
        total     = (addr_t'(len) + 1) << LogBytes;
        wrap_base = aligned & ~(total - 1);
        return wrap_base + ((cons - wrap_base) & (total - 1));
      end
      default: return cons;                        // INCR
    endcase
  endfunction

  // 64 byte DDR3 blocks a burst touches. A CVA6 refill is a two beat 16 byte
  // burst and so is always one block, but the debug module and the DMA are not
  // bound by that, so the general case is computed rather than assumed.
  function automatic logic [8:0] blk_count(input addr_t      base,
                                           input logic [7:0] len,
                                           input logic [1:0] burst);
    addr_t aligned, total, first_blk, last_blk;
    aligned = {base[AXI_ADDR_WIDTH-1:LogBytes], {LogBytes{1'b0}}};
    total   = (addr_t'(len) + 1) << LogBytes;
    if (burst == 2'b00) return 9'd1;               // FIXED never leaves its word
    first_blk = aligned >> LogBlk;
    last_blk  = (aligned + total - 1) >> LogBlk;
    return 9'((last_blk - first_blk) + 1);
  endfunction

  function automatic addr_t blk_addr(input addr_t base, input logic [8:0] idx);
    addr_t aligned;
    aligned = {base[AXI_ADDR_WIDTH-1:LogBytes], {LogBytes{1'b0}}};
    return ((aligned >> LogBlk) + addr_t'(idx)) << LogBlk;
  endfunction

  // ---------------------------------------------------------------------------
  // Transaction slots
  // ---------------------------------------------------------------------------
  // Slots come from a free list and never move, with age stamps for order. A
  // compacted array lost a retire that landed in the cycle a new address came,
  // since both assign the count, and the queue leaked until it wedged.
  logic             rd_val_q  [NumRdSlots];
  logic [63:0]      rd_age_q  [NumRdSlots];
  id_t              rd_id_q   [NumRdSlots];
  addr_t            rd_addr_q [NumRdSlots];
  logic [7:0]       rd_len_q  [NumRdSlots];
  logic [1:0]       rd_bur_q  [NumRdSlots];
  logic [8:0]       rd_blkn_q [NumRdSlots];   // blocks the burst needs
  logic [8:0]       rd_blki_q [NumRdSlots];   // blocks handed to the scheduler
  logic [8:0]       rd_blkd_q [NumRdSlots];   // blocks the scheduler returned
  logic [8:0]       rd_beat_q [NumRdSlots];   // beats already put on R

  logic             wr_val_q  [NumWrSlots];
  logic [63:0]      wr_age_q  [NumWrSlots];
  id_t              wr_id_q   [NumWrSlots];
  addr_t            wr_addr_q [NumWrSlots];
  logic [7:0]       wr_len_q  [NumWrSlots];
  logic [1:0]       wr_bur_q  [NumWrSlots];
  logic [8:0]       wr_blkn_q [NumWrSlots];
  logic [8:0]       wr_blki_q [NumWrSlots];
  logic [8:0]       wr_blkd_q [NumWrSlots];
  logic [8:0]       wr_beat_q [NumWrSlots];
  logic             wr_wdone_q[NumWrSlots];   // w_last has been taken

  logic [63:0]      age_q;

  // R data stage. The array answers one cycle after the address, so the beat
  // put on R this cycle is the one whose address went out last cycle.
  logic             rs_val_q;
  id_t              rs_id_q;
  logic             rs_last_q;

  // ---------------------------------------------------------------------------
  // Scheduler
  // ---------------------------------------------------------------------------
  logic             sch_req_val, sch_req_rdy, sch_req_we;
  addr_t            sch_req_addr;
  logic [TagW-1:0]  sch_req_tag;
  logic             sch_done_val;
  logic [TagW-1:0]  sch_done_tag;
  logic             sch_wack_val;
  logic [TagW-1:0]  sch_wack_tag;

  ddr3_scheduler #(
      .AddrWidth    (AXI_ADDR_WIDTH),
      .TagWidth     (TagW),
      .TckHostPs    (TckHostPs),
      .RowsPerBank  (RowsPerBank),
      .IssuePerCycle(IssuePerCycle),
      .MaxInFlight  (NumRdSlots + NumWrSlots),
      .PostedWrites (PostedWrites),
      .EnableRefresh(EnableRefresh),
      .BackendPs    (BackendPs)
  ) i_sched (
      .clk_i,
      .rst_ni,
      .req_valid_i (sch_req_val),
      .req_ready_o (sch_req_rdy),
      .req_addr_i  (sch_req_addr),
      .req_we_i    (sch_req_we),
      .req_tag_i   (sch_req_tag),
      .done_valid_o(sch_done_val),
      .done_tag_o  (sch_done_tag),
      .wack_valid_o(sch_wack_val),
      .wack_tag_o  (sch_wack_tag),
      .stats_o     (stats_o)
  );

  // ---------------------------------------------------------------------------
  // Slot selection
  // ---------------------------------------------------------------------------
  // Free slots, and the one that will be allocated next.
  int unsigned rd_free, wr_free;
  logic        rd_has_free, wr_has_free;
  always_comb begin
    rd_free = 0; rd_has_free = 1'b0;
    for (int unsigned i = 0; i < NumRdSlots; i++) begin
      if (!rd_has_free && !rd_val_q[i]) begin rd_free = i; rd_has_free = 1'b1; end
    end
    wr_free = 0; wr_has_free = 1'b0;
    for (int unsigned i = 0; i < NumWrSlots; i++) begin
      if (!wr_has_free && !wr_val_q[i]) begin wr_free = i; wr_has_free = 1'b1; end
    end
  end

  // A read slot puts beats on R once every block it needs is back and no older
  // open slot holds its AXI id, and a completion arriving this cycle counts at
  // once rather than costing three cycles, more than the access at 20 ns.
  logic [8:0] rd_blkd_eff[NumRdSlots];
  always_comb begin
    for (int unsigned i = 0; i < NumRdSlots; i++) begin
      rd_blkd_eff[i] = rd_blkd_q[i] +
          ((sch_done_val && !sch_done_tag[TagW-1] &&
            (int'(sch_done_tag[RdIdxW-1:0]) == int'(i))) ? 9'd1 : 9'd0);
    end
  end

  int unsigned rd_pick;
  logic        rd_pick_val;
  always_comb begin
    logic [63:0] best_age;
    rd_pick = 0; rd_pick_val = 1'b0; best_age = '1;
    for (int unsigned i = 0; i < NumRdSlots; i++) begin
      logic ok;
      ok = rd_val_q[i] && (rd_blkd_eff[i] == rd_blkn_q[i]);
      for (int unsigned j = 0; j < NumRdSlots; j++) begin
        if (rd_val_q[j] && (j != i) && (rd_age_q[j] < rd_age_q[i]) &&
            (rd_id_q[j] == rd_id_q[i])) ok = 1'b0;
      end
      if (ok && (rd_age_q[i] < best_age)) begin
        rd_pick = i; rd_pick_val = 1'b1; best_age = rd_age_q[i];
      end
    end
  end

  // W beats belong to the AW bursts in order, so the oldest write slot that
  // has not yet taken w_last is the one the data on W is for.
  int unsigned wr_pick;
  logic        wr_pick_val;
  always_comb begin
    logic [63:0] best_age;
    wr_pick = 0; wr_pick_val = 1'b0; best_age = '1;
    for (int unsigned i = 0; i < NumWrSlots; i++) begin
      if (wr_val_q[i] && !wr_wdone_q[i] && (wr_age_q[i] < best_age)) begin
        wr_pick = i; wr_pick_val = 1'b1; best_age = wr_age_q[i];
      end
    end
  end

  // Oldest write slot whose blocks have all been acknowledged: the B response.
  int unsigned b_pick;
  logic        b_pick_val;
  always_comb begin
    logic [63:0] best_age;
    b_pick = 0; b_pick_val = 1'b0; best_age = '1;
    for (int unsigned i = 0; i < NumWrSlots; i++) begin
      if (wr_val_q[i] && wr_wdone_q[i] && (wr_blkn_q[i] != 0) &&
          (wr_blkd_q[i] == wr_blkn_q[i]) && (wr_age_q[i] < best_age)) begin
        b_pick = i; b_pick_val = 1'b1; best_age = wr_age_q[i];
      end
    end
  end

  // Block requests into the scheduler: oldest slot with a block still to hand
  // over, reads before writes.
  int unsigned bq_slot;
  logic        bq_val, bq_we, bq_bypass;
  always_comb begin
    logic [63:0] best_age;
    bq_slot = 0; bq_val = 1'b0; bq_we = 1'b0; bq_bypass = 1'b0; best_age = '1;
    for (int unsigned i = 0; i < NumRdSlots; i++) begin
      if (rd_val_q[i] && (rd_blki_q[i] < rd_blkn_q[i]) && (rd_age_q[i] < best_age)) begin
        bq_slot = i; bq_val = 1'b1; best_age = rd_age_q[i];
      end
    end
    if (!bq_val) begin
      for (int unsigned i = 0; i < NumWrSlots; i++) begin
        // A write is handed over only once every beat is in the array, so the
        // data the DDR3 access stands for is actually there.
        if (wr_val_q[i] && wr_wdone_q[i] && (wr_blki_q[i] < wr_blkn_q[i]) &&
            (wr_age_q[i] < best_age)) begin
          bq_slot = i; bq_val = 1'b1; bq_we = 1'b1; best_age = wr_age_q[i];
        end
      end
    end
    // An address with nothing older waiting goes to the scheduler this cycle, on
    // the slot it is about to take, and its block is recorded as sent.
    if (!bq_val && slave.ar_valid && slave.ar_ready) begin
      bq_slot = rd_free; bq_val = 1'b1; bq_bypass = 1'b1;
    end
  end

  assign sch_req_val  = bq_val;
  assign sch_req_we   = bq_we;
  assign sch_req_tag  = {bq_we, SlotIdxW'(bq_slot)};
  assign sch_req_addr = bq_bypass
      ? blk_addr(slave.ar_addr, 9'd0) - MemBase
      : (bq_we ? blk_addr(wr_addr_q[bq_slot], wr_blki_q[bq_slot]) - MemBase
               : blk_addr(rd_addr_q[bq_slot], rd_blki_q[bq_slot]) - MemBase);

  // ---------------------------------------------------------------------------
  // Array port and AXI channels
  // ---------------------------------------------------------------------------
  // Reads win the array, since read latency is what this harness measures, and
  // w_ready drops for that cycle. After WriteStarveLimit cycles of losing, a
  // waiting write beat takes the port, a backstop against a starved W channel.
  logic r_beat_go, w_beat_go, r_stage_free, w_wants, w_force;
  int unsigned w_starve_q;

  assign r_stage_free = !rs_val_q || slave.r_ready;
  assign w_wants      = wr_pick_val && slave.w_valid;
  assign w_force      = w_wants && (w_starve_q >= WriteStarveLimit);
  assign r_beat_go    = rd_pick_val && r_stage_free && !w_force;
  assign w_beat_go    = w_wants && !r_beat_go;

  always_comb begin
    req_o  = 1'b0;
    we_o   = 1'b0;
    addr_o = '0;
    be_o   = '1;
    data_o = slave.w_data;
    user_o = slave.w_user;
    if (r_beat_go) begin
      req_o  = 1'b1;
      addr_o = beat_addr(rd_addr_q[rd_pick], rd_len_q[rd_pick],
                         rd_bur_q[rd_pick], rd_beat_q[rd_pick]);
    end else if (w_beat_go) begin
      req_o  = 1'b1;
      we_o   = 1'b1;
      be_o   = slave.w_strb;
      addr_o = beat_addr(wr_addr_q[wr_pick], wr_len_q[wr_pick],
                         wr_bur_q[wr_pick], wr_beat_q[wr_pick]);
    end
  end

  assign slave.w_ready = w_beat_go;

  assign slave.r_valid = rs_val_q;
  assign slave.r_data  = data_i;
  assign slave.r_user  = user_i;
  assign slave.r_id    = rs_id_q;
  assign slave.r_last  = rs_last_q;
  assign slave.r_resp  = 2'b00;

  assign slave.b_valid = b_pick_val;
  assign slave.b_id    = wr_id_q[b_pick];
  assign slave.b_resp  = 2'b00;
  assign slave.b_user  = '0;

  assign slave.ar_ready = rd_has_free;
  assign slave.aw_ready = wr_has_free;

  // ---------------------------------------------------------------------------
  // Sequential
  // ---------------------------------------------------------------------------
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      age_q     <= 64'd0;
      rs_val_q  <= 1'b0;
      rs_id_q   <= '0;
      rs_last_q <= 1'b0;
      w_starve_q <= 0;
      for (int unsigned i = 0; i < NumRdSlots; i++) rd_val_q[i] <= 1'b0;
      for (int unsigned i = 0; i < NumWrSlots; i++) wr_val_q[i] <= 1'b0;
    end else begin

      // --- R data stage -----------------------------------------------------
      if (rs_val_q && slave.r_ready) rs_val_q <= 1'b0;
      if (r_beat_go) begin
        rs_val_q  <= 1'b1;
        rs_id_q   <= rd_id_q[rd_pick];
        rs_last_q <= (rd_beat_q[rd_pick] == 9'(rd_len_q[rd_pick]));
        rd_beat_q[rd_pick] <= rd_beat_q[rd_pick] + 1;
        // The slot frees as the last beat's address goes out. rs_id_q and
        // rs_last_q are captured, and r_stage_free keeps a new slot from
        // reading over data the master has not taken.
        if (rd_beat_q[rd_pick] == 9'(rd_len_q[rd_pick])) rd_val_q[rd_pick] <= 1'b0;
      end

      // --- W beats ----------------------------------------------------------
      w_starve_q <= (w_wants && !w_beat_go) ? (w_starve_q + 1) : 0;
      if (w_beat_go) begin
        wr_beat_q[wr_pick] <= wr_beat_q[wr_pick] + 1;
        if (slave.w_last) wr_wdone_q[wr_pick] <= 1'b1;
      end

      // --- block requests accepted by the scheduler -------------------------
      if (sch_req_val && sch_req_rdy && !bq_bypass) begin
        if (bq_we) wr_blki_q[bq_slot] <= wr_blki_q[bq_slot] + 1;
        else       rd_blki_q[bq_slot] <= rd_blki_q[bq_slot] + 1;
      end

      // --- completions ------------------------------------------------------
      if (sch_done_val) begin
        if (sch_done_tag[TagW-1]) begin
          wr_blkd_q[sch_done_tag[WrIdxW-1:0]] <= wr_blkd_q[sch_done_tag[WrIdxW-1:0]] + 1;
        end else begin
          rd_blkd_q[sch_done_tag[RdIdxW-1:0]] <= rd_blkd_q[sch_done_tag[RdIdxW-1:0]] + 1;
        end
      end
      if (sch_wack_val) begin
        wr_blkd_q[sch_wack_tag[WrIdxW-1:0]] <= wr_blkd_q[sch_wack_tag[WrIdxW-1:0]] + 1;
      end

      // --- B response -------------------------------------------------------
      if (slave.b_valid && slave.b_ready) wr_val_q[b_pick] <= 1'b0;

      // --- new AR -----------------------------------------------------------
      if (slave.ar_valid && slave.ar_ready) begin
        rd_val_q [rd_free] <= 1'b1;
        rd_age_q [rd_free] <= age_q;
        rd_id_q  [rd_free] <= slave.ar_id;
        rd_addr_q[rd_free] <= slave.ar_addr;
        rd_len_q [rd_free] <= slave.ar_len;
        rd_bur_q [rd_free] <= slave.ar_burst;
        rd_blkn_q[rd_free] <= blk_count(slave.ar_addr, slave.ar_len, slave.ar_burst);
        rd_blki_q[rd_free] <= (bq_bypass && sch_req_rdy) ? 9'd1 : 9'd0;
        rd_blkd_q[rd_free] <= '0;
        rd_beat_q[rd_free] <= '0;
        age_q <= age_q + 1;
      end

      // --- new AW -----------------------------------------------------------
      if (slave.aw_valid && slave.aw_ready) begin
        wr_val_q  [wr_free] <= 1'b1;
        wr_age_q  [wr_free] <= age_q + ((slave.ar_valid && slave.ar_ready) ? 64'd1 : 64'd0);
        wr_id_q   [wr_free] <= slave.aw_id;
        wr_addr_q [wr_free] <= slave.aw_addr;
        wr_len_q  [wr_free] <= slave.aw_len;
        wr_bur_q  [wr_free] <= slave.aw_burst;
        wr_blkn_q [wr_free] <= blk_count(slave.aw_addr, slave.aw_len, slave.aw_burst);
        wr_blki_q [wr_free] <= '0;
        wr_blkd_q [wr_free] <= '0;
        wr_beat_q [wr_free] <= '0;
        wr_wdone_q[wr_free] <= 1'b0;
        age_q <= age_q + ((slave.ar_valid && slave.ar_ready) ? 64'd2 : 64'd1);
      end
    end
  end

  // ---------------------------------------------------------------------------
  // End of simulation report
  // ---------------------------------------------------------------------------
  // Printed from a final block so it appears whichever way the run ends, and
  // shaped to line up with the gem5 stats it is meant to be read against:
  //   system.mem_ctrl.dram.readRowHits / readBursts   -> row hit rate
  //   system.mem_ctrl.dram.numRefreshes               -> refreshes
  //   system.mem_ctrl.avgMemAccLat                    -> mean read latency
  final begin
    automatic longint unsigned acc;
    acc = stats_o.row_hits + stats_o.row_conflicts + stats_o.row_empty;
    $display("");
    $display("=== DDR3 memory model =============================================");
    $display("  device            : DDR3-1600 8x8, %0d ranks x %0d banks, %0d KiB row",
             ddr3_pkg::RanksPerChan, ddr3_pkg::BanksPerRank,
             ddr3_pkg::RowBufferByte / 1024);
    $display("  read bursts       : %0d", stats_o.reads);
    $display("  write bursts      : %0d", stats_o.writes);
    if (acc != 0) begin
      $display("  row buffer hits   : %0d (%0d.%02d %%)", stats_o.row_hits,
               (stats_o.row_hits * 100) / acc,
               ((stats_o.row_hits * 10000) / acc) % 100);
      $display("  row conflicts     : %0d (%0d.%02d %%)", stats_o.row_conflicts,
               (stats_o.row_conflicts * 100) / acc,
               ((stats_o.row_conflicts * 10000) / acc) % 100);
      $display("  closed bank       : %0d (%0d.%02d %%)", stats_o.row_empty,
               (stats_o.row_empty * 100) / acc,
               ((stats_o.row_empty * 10000) / acc) % 100);
    end
    if (stats_o.reads != 0) begin
      $display("  mean read latency : %0d.%02d ns   (queueing and rounding included)",
               (stats_o.read_lat_ps_sum / stats_o.reads) / 1000,
               ((stats_o.read_lat_ps_sum / stats_o.reads) / 10) % 100);
      $display("  worst read latency: %0d.%02d ns",
               stats_o.read_lat_ps_max / 1000, (stats_o.read_lat_ps_max / 10) % 100);
    end
    if (stats_o.dev_accesses != 0)
      $display("  mean device access: %0d.%02d ns   (DRAM only, no queueing)",
               (stats_o.dev_lat_ps_sum / stats_o.dev_accesses) / 1000,
               ((stats_o.dev_lat_ps_sum / stats_o.dev_accesses) / 10) % 100);
    $display("  bus turnarounds   : %0d write to read, %0d read to write",
             stats_o.wr_to_rd_switch, stats_o.rd_to_wr_switch);
    $display("  refreshes         : %0d, banks blocked for %0d ns",
             stats_o.refreshes, stats_o.refresh_stall_ps / 1000);
    // The number the whole experiment turns on. If this sits at 1 the memory
    // latency is fully exposed and something upstream, the crossbar or the
    // atomics adapter, is serialising rather than the memory.
    if (stats_o.mlp_samples != 0)
      $display("  read concurrency  : mean %0d.%02d, peak %0d",
               stats_o.mlp_sum / stats_o.mlp_samples,
               ((stats_o.mlp_sum * 100) / stats_o.mlp_samples) % 100,
               stats_o.mlp_max);
    $display("===================================================================");
  end

endmodule

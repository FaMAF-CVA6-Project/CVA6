// Copyright 2026 Universidad Nacional de Cordoba, FaMAF.
// Testbench only. Not for synthesis.
//
// AXI address channel latency injector for the CVA6 memory latency sweep.
// Drop-in replacement for axi_delayer_intf in ariane_testharness.sv.
//
// ---------------------------------------------------------------------------
// Why not the stock PULP axi_delayer
// ---------------------------------------------------------------------------
// axi_delayer wraps all five AXI channels in stream_delay (common_cells,
// now a shim over cc_stream_delay). That FSM is Idle -> Valid -> Ready and it
// asserts ready_o only in the Ready state, so it handles exactly one handshake
// at a time and backpressures the upstream for the whole countdown. It is a
// stall element, not a latency element. Two consequences rule it out here.
//
//   1. Per handshake, not per transaction. A burst pays the delay on every
//      beat. The cv64a6_imafdc_sv39_hpdcache_wb configuration has a 128 bit
//      cache line (CVA6ConfigDcacheLineWidth) on a 64 bit AXI data bus
//      (CVA6ConfigAxiDataWidth), so a refill is a two beat R burst and a dirty
//      victim writeback is a two beat W burst. Delaying R or W throttles
//      bandwidth rather than adding latency, which is not how a DDR controller
//      behaves.
//
//   2. It serialises the channel it delays. Delaying AR would space concurrent
//      refill requests by the delay and so artificially lower the memory level
//      parallelism of the HPDcache. MLP is exactly the quantity this sweep must
//      hold fixed while latency varies, because the calibrated gem5 memory
//      latency absorbs the difference between MinorCPU MLP of 1 and HPDcache
//      MLP of 2. A delayer that erodes RTL MLP as the delay grows would bias
//      the experiment towards agreement and produce a false positive.
//
// Note that at FixedDelay of 0 with StallRandom off, cc_stream_delay takes its
// gen_pass_through branch, so the current testharness settings of 0 and 0 add
// nothing. The baseline is a true zero delay reference.
//
// ---------------------------------------------------------------------------
// What this module does instead
// ---------------------------------------------------------------------------
// Delays only the address channels (AW, AR) through a pipelined shift register.
// Handshakes are accepted at one per cycle, up to Depth transactions are in
// flight simultaneously, and each pays exactly Depth cycles. W, B and R are
// untouched, so burst beats stream at line rate once the address is granted.
// That is the DDR shape: latency up front, then full rate transfer, with
// request level parallelism preserved.
//
// Added read latency is exactly AR_LATENCY cycles. At the 50 MHz testharness
// clock that is 20 ns per unit, so AR_LATENCY of 5, 10 and 20 add 100, 200 and
// 400 ns respectively.

/// Pipelined valid/ready delay line. Depth transactions in flight, Depth cycles
/// each. Depth of 0 is a combinational pass through.
module axi_lat_shift #(
    parameter int unsigned Depth     = 0,
    parameter type         payload_t = logic
) (
    input  logic     clk_i,
    input  logic     rst_ni,
    input  payload_t payload_i,
    input  logic     valid_i,
    output logic     ready_o,
    output payload_t payload_o,
    output logic     valid_o,
    input  logic     ready_i
);

  if (Depth == 0) begin : gen_pass_through
    assign payload_o = payload_i;
    assign valid_o   = valid_i;
    assign ready_o   = ready_i;
  end else begin : gen_shift
    payload_t pl_q [Depth];
    logic     vld_q[Depth];
    logic     en;

    // The line advances when the final stage is empty or is draining this
    // cycle. Deliberately written with unpacked arrays and a descending loop
    // rather than a {vld_q[Depth-2:0], valid_i} concatenation, because that
    // part select is reversed and out of bounds at Depth of 1. This is the
    // same hazard class as RASDepth of 1 in ras.sv.
    assign en        = ~vld_q[Depth-1] | ready_i;
    assign ready_o   = en;
    assign valid_o   = vld_q[Depth-1];
    assign payload_o = pl_q[Depth-1];

    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        for (int unsigned i = 0; i < Depth; i++) begin
          vld_q[i] <= 1'b0;
          pl_q[i]  <= '0;
        end
      end else if (en) begin
        for (int unsigned i = Depth - 1; i > 0; i--) begin
          vld_q[i] <= vld_q[i-1];
          pl_q[i]  <= pl_q[i-1];
        end
        vld_q[0] <= valid_i;
        pl_q[0]  <= payload_i;
      end
    end
  end

endmodule

/// Structural mirror of axi_delayer: every channel goes through the same
/// element, so every field of mst_req_o and slv_resp_o has exactly one
/// continuous driver. The burst channels instantiate Depth of 0 and therefore
/// collapse to wires.
module axi_lat_delayer #(
    parameter type aw_chan_t = logic,
    parameter type w_chan_t = logic,
    parameter type b_chan_t = logic,
    parameter type ar_chan_t = logic,
    parameter type r_chan_t = logic,
    parameter type axi_req_t = logic,
    parameter type axi_resp_t = logic,
    /// Read address latency in cycles. This is the sweep knob.
    parameter int unsigned ArLatency = 0,
    /// Write address latency in cycles. Set equal to ArLatency to mirror the
    /// symmetric latency of gem5 SingleChannelSimpleMemory. Set to 0 as a
    /// sensitivity check to isolate the read path.
    parameter int unsigned AwLatency = 0
) (
    input  logic      clk_i,
    input  logic      rst_ni,
    input  axi_req_t  slv_req_i,
    output axi_resp_t slv_resp_o,
    output axi_req_t  mst_req_o,
    input  axi_resp_t mst_resp_i
);

  // AW: delayed
  axi_lat_shift #(
      .Depth    (AwLatency),
      .payload_t(aw_chan_t)
  ) i_lat_shift_aw (
      .clk_i,
      .rst_ni,
      .payload_i(slv_req_i.aw),
      .valid_i  (slv_req_i.aw_valid),
      .ready_o  (slv_resp_o.aw_ready),
      .payload_o(mst_req_o.aw),
      .valid_o  (mst_req_o.aw_valid),
      .ready_i  (mst_resp_i.aw_ready)
  );

  // AR: delayed
  axi_lat_shift #(
      .Depth    (ArLatency),
      .payload_t(ar_chan_t)
  ) i_lat_shift_ar (
      .clk_i,
      .rst_ni,
      .payload_i(slv_req_i.ar),
      .valid_i  (slv_req_i.ar_valid),
      .ready_o  (slv_resp_o.ar_ready),
      .payload_o(mst_req_o.ar),
      .valid_o  (mst_req_o.ar_valid),
      .ready_i  (mst_resp_i.ar_ready)
  );

  // W: pass through, so writeback burst beats stream at line rate
  axi_lat_shift #(
      .Depth    (0),
      .payload_t(w_chan_t)
  ) i_lat_shift_w (
      .clk_i,
      .rst_ni,
      .payload_i(slv_req_i.w),
      .valid_i  (slv_req_i.w_valid),
      .ready_o  (slv_resp_o.w_ready),
      .payload_o(mst_req_o.w),
      .valid_o  (mst_req_o.w_valid),
      .ready_i  (mst_resp_i.w_ready)
  );

  // B: pass through
  axi_lat_shift #(
      .Depth    (0),
      .payload_t(b_chan_t)
  ) i_lat_shift_b (
      .clk_i,
      .rst_ni,
      .payload_i(mst_resp_i.b),
      .valid_i  (mst_resp_i.b_valid),
      .ready_o  (mst_req_o.b_ready),
      .payload_o(slv_resp_o.b),
      .valid_o  (slv_resp_o.b_valid),
      .ready_i  (slv_req_i.b_ready)
  );

  // R: pass through, so refill burst beats stream at line rate
  axi_lat_shift #(
      .Depth    (0),
      .payload_t(r_chan_t)
  ) i_lat_shift_r (
      .clk_i,
      .rst_ni,
      .payload_i(mst_resp_i.r),
      .valid_i  (mst_resp_i.r_valid),
      .ready_o  (mst_req_o.r_ready),
      .payload_o(slv_resp_o.r),
      .valid_o  (slv_resp_o.r_valid),
      .ready_i  (slv_req_i.r_ready)
  );

endmodule

`include "axi/typedef.svh"
`include "axi/assign.svh"

/// Interface wrapper. Pin compatible with axi_delayer_intf on clk_i, rst_ni,
/// slv and mst, so the testharness instance changes module name and parameters
/// only.
module axi_lat_delayer_intf #(
    parameter int unsigned AXI_ID_WIDTH   = 0,
    parameter int unsigned AXI_ADDR_WIDTH = 0,
    parameter int unsigned AXI_DATA_WIDTH = 0,
    parameter int unsigned AXI_USER_WIDTH = 0,
    parameter int unsigned AR_LATENCY     = 0,
    parameter int unsigned AW_LATENCY     = 0
) (
    input logic   clk_i,
    input logic   rst_ni,
          AXI_BUS.Slave slv,
          AXI_BUS.Master mst
);

  typedef logic [AXI_ID_WIDTH-1:0] id_t;
  typedef logic [AXI_ADDR_WIDTH-1:0] addr_t;
  typedef logic [AXI_DATA_WIDTH-1:0] data_t;
  typedef logic [AXI_DATA_WIDTH/8-1:0] strb_t;
  typedef logic [AXI_USER_WIDTH-1:0] user_t;

  `AXI_TYPEDEF_AW_CHAN_T(aw_chan_t, addr_t, id_t, user_t)
  `AXI_TYPEDEF_W_CHAN_T(w_chan_t, data_t, strb_t, user_t)
  `AXI_TYPEDEF_B_CHAN_T(b_chan_t, id_t, user_t)
  `AXI_TYPEDEF_AR_CHAN_T(ar_chan_t, addr_t, id_t, user_t)
  `AXI_TYPEDEF_R_CHAN_T(r_chan_t, data_t, id_t, user_t)
  `AXI_TYPEDEF_REQ_T(axi_req_t, aw_chan_t, w_chan_t, ar_chan_t)
  `AXI_TYPEDEF_RESP_T(axi_resp_t, b_chan_t, r_chan_t)

  axi_req_t slv_req, mst_req;
  axi_resp_t slv_resp, mst_resp;

  `AXI_ASSIGN_TO_REQ(slv_req, slv)
  `AXI_ASSIGN_FROM_RESP(slv, slv_resp)

  `AXI_ASSIGN_FROM_REQ(mst, mst_req)
  `AXI_ASSIGN_TO_RESP(mst_resp, mst)

  axi_lat_delayer #(
      .aw_chan_t (aw_chan_t),
      .w_chan_t  (w_chan_t),
      .b_chan_t  (b_chan_t),
      .ar_chan_t (ar_chan_t),
      .r_chan_t  (r_chan_t),
      .axi_req_t (axi_req_t),
      .axi_resp_t(axi_resp_t),
      .ArLatency (AR_LATENCY),
      .AwLatency (AW_LATENCY)
  ) i_axi_lat_delayer (
      .clk_i,
      .rst_ni,
      .slv_req_i (slv_req),
      .slv_resp_o(slv_resp),
      .mst_req_o (mst_req),
      .mst_resp_i(mst_resp)
  );

  // pragma translate_off
`ifndef VERILATOR
  initial begin : p_assertions
    assert (AXI_ID_WIDTH >= 1)
    else $fatal(1, "AXI ID width must be at least 1!");
    assert (AXI_ADDR_WIDTH >= 1)
    else $fatal(1, "AXI ADDR width must be at least 1!");
    assert (AXI_DATA_WIDTH >= 1)
    else $fatal(1, "AXI DATA width must be at least 1!");
    assert (AXI_USER_WIDTH >= 1)
    else $fatal(1, "AXI USER width must be at least 1!");
  end
`endif
  // pragma translate_on

endmodule

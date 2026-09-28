// Copyright 2026 Universidad Nacional de Cordoba, FaMAF.
// Testbench only. Not for synthesis.
//
// Standalone harness for axi_ddr3_slave. Flat AXI ports, because Verilator
// cannot expose a SystemVerilog interface at the top level, so the AXI_BUS the
// slave expects is built here and driven from the C++ master in
// ddr3_tb_main.cpp.
//
// The array underneath is the same sram the testharness uses, at the same
// 1 cycle read latency, so a timing number measured here is the number the
// full core run will see.
module ddr3_tb_top #(
    parameter int unsigned AW = 64,
    parameter int unsigned DW = 64,
    parameter int unsigned IW = 5,
    parameter int unsigned UW = 1,
    parameter int unsigned NUM_WORDS = 2**20
) (
    input  logic          clk_i,
    input  logic          rst_ni,

    input  logic [IW-1:0] aw_id_i,
    input  logic [AW-1:0] aw_addr_i,
    input  logic [7:0]    aw_len_i,
    input  logic [2:0]    aw_size_i,
    input  logic [1:0]    aw_burst_i,
    input  logic          aw_valid_i,
    output logic          aw_ready_o,

    input  logic [DW-1:0] w_data_i,
    input  logic [DW/8-1:0] w_strb_i,
    input  logic          w_last_i,
    input  logic          w_valid_i,
    output logic          w_ready_o,

    output logic [IW-1:0] b_id_o,
    output logic          b_valid_o,
    input  logic          b_ready_i,

    input  logic [IW-1:0] ar_id_i,
    input  logic [AW-1:0] ar_addr_i,
    input  logic [7:0]    ar_len_i,
    input  logic [2:0]    ar_size_i,
    input  logic [1:0]    ar_burst_i,
    input  logic          ar_valid_i,
    output logic          ar_ready_o,

    output logic [IW-1:0] r_id_o,
    output logic [DW-1:0] r_data_o,
    output logic          r_last_o,
    output logic          r_valid_o,
    input  logic          r_ready_i,

    // Statistics, flattened so the C++ side can read them without knowing the
    // struct layout.
    output logic [63:0]   st_reads_o,
    output logic [63:0]   st_writes_o,
    output logic [63:0]   st_row_hits_o,
    output logic [63:0]   st_row_conflicts_o,
    output logic [63:0]   st_row_empty_o,
    output logic [63:0]   st_refreshes_o,
    output logic [63:0]   st_refresh_stall_ps_o,
    output logic [63:0]   st_read_lat_ps_sum_o,
    output logic [63:0]   st_read_lat_ps_max_o,
    output logic [63:0]   st_bus_busy_ps_o,
    output logic [63:0]   st_wr_to_rd_o,
    output logic [63:0]   st_rd_to_wr_o,
    output logic [63:0]   st_mlp_sum_o,
    output logic [63:0]   st_mlp_samples_o,
    output logic [63:0]   st_mlp_max_o,
    output logic [63:0]   st_dev_lat_ps_sum_o,
    output logic [63:0]   st_dev_accesses_o
);

  AXI_BUS #(
    .AXI_ADDR_WIDTH (AW),
    .AXI_DATA_WIDTH (DW),
    .AXI_ID_WIDTH   (IW),
    .AXI_USER_WIDTH (UW)
  ) bus();

  assign bus.aw_id     = aw_id_i;
  assign bus.aw_addr   = aw_addr_i;
  assign bus.aw_len    = aw_len_i;
  assign bus.aw_size   = aw_size_i;
  assign bus.aw_burst  = aw_burst_i;
  assign bus.aw_lock   = 1'b0;
  assign bus.aw_cache  = '0;
  assign bus.aw_prot   = '0;
  assign bus.aw_qos    = '0;
  assign bus.aw_atop   = '0;
  assign bus.aw_region = '0;
  assign bus.aw_user   = '0;
  assign bus.aw_valid  = aw_valid_i;
  assign aw_ready_o    = bus.aw_ready;

  assign bus.w_data    = w_data_i;
  assign bus.w_strb    = w_strb_i;
  assign bus.w_last    = w_last_i;
  assign bus.w_user    = '0;
  assign bus.w_valid   = w_valid_i;
  assign w_ready_o     = bus.w_ready;

  assign b_id_o        = bus.b_id;
  assign b_valid_o     = bus.b_valid;
  assign bus.b_ready   = b_ready_i;

  assign bus.ar_id     = ar_id_i;
  assign bus.ar_addr   = ar_addr_i;
  assign bus.ar_len    = ar_len_i;
  assign bus.ar_size   = ar_size_i;
  assign bus.ar_burst  = ar_burst_i;
  assign bus.ar_lock   = 1'b0;
  assign bus.ar_cache  = '0;
  assign bus.ar_prot   = '0;
  assign bus.ar_qos    = '0;
  assign bus.ar_region = '0;
  assign bus.ar_user   = '0;
  assign bus.ar_valid  = ar_valid_i;
  assign ar_ready_o    = bus.ar_ready;

  assign r_id_o        = bus.r_id;
  assign r_data_o      = bus.r_data;
  assign r_last_o      = bus.r_last;
  assign r_valid_o     = bus.r_valid;
  assign bus.r_ready   = r_ready_i;

  logic            req, we;
  logic [AW-1:0]   addr;
  logic [DW/8-1:0] be;
  logic [DW-1:0]   wdata, rdata;
  logic [UW-1:0]   wuser, ruser;

  ddr3_pkg::ddr3_stats_t stats;

  axi_ddr3_slave #(
    .AXI_ID_WIDTH  (IW),
    .AXI_ADDR_WIDTH(AW),
    .AXI_DATA_WIDTH(DW),
    .AXI_USER_WIDTH(UW),
    .MemBase       (64'h8000_0000),
    .MemSizeBytes  (64'h4000_0000),
    .TckHostPs     (20000)
  ) i_dut (
    .clk_i,
    .rst_ni,
    .slave  (bus),
    .req_o  (req),
    .we_o   (we),
    .addr_o (addr),
    .be_o   (be),
    .user_o (wuser),
    .data_o (wdata),
    .user_i (ruser),
    .data_i (rdata),
    .stats_o(stats)
  );

  sram #(
    .DATA_WIDTH(DW),
    .USER_WIDTH(UW),
    .USER_EN   (0),
    .SIM_INIT  ("none"),
    .NUM_WORDS (NUM_WORDS)
  ) i_sram (
    .clk_i,
    .rst_ni,
    .req_i  (req),
    .we_i   (we),
    .addr_i (addr[$clog2(NUM_WORDS)-1+$clog2(DW/8):$clog2(DW/8)]),
    .wuser_i(wuser),
    .wdata_i(wdata),
    .be_i   (be),
    .ruser_o(ruser),
    .rdata_o(rdata)
  );

  assign st_reads_o            = stats.reads;
  assign st_writes_o           = stats.writes;
  assign st_row_hits_o         = stats.row_hits;
  assign st_row_conflicts_o    = stats.row_conflicts;
  assign st_row_empty_o        = stats.row_empty;
  assign st_refreshes_o        = stats.refreshes;
  assign st_refresh_stall_ps_o = stats.refresh_stall_ps;
  assign st_read_lat_ps_sum_o  = stats.read_lat_ps_sum;
  assign st_read_lat_ps_max_o  = stats.read_lat_ps_max;
  assign st_bus_busy_ps_o      = stats.bus_busy_ps;
  assign st_wr_to_rd_o         = stats.wr_to_rd_switch;
  assign st_rd_to_wr_o         = stats.rd_to_wr_switch;
  assign st_mlp_sum_o          = stats.mlp_sum;
  assign st_mlp_samples_o      = stats.mlp_samples;
  assign st_mlp_max_o          = stats.mlp_max;
  assign st_dev_lat_ps_sum_o   = stats.dev_lat_ps_sum;
  assign st_dev_accesses_o     = stats.dev_accesses;

endmodule

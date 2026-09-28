// Copyright 2026 Universidad Nacional de Cordoba, FaMAF.
// Testbench only. Not for synthesis.
//
// DDR3 device and controller parameters for the CVA6 Verilator harness.
//
// Every value here is the gem5 DDR3_1600_8x8 DRAMInterface value, so that a
// run under Verilator and a gem5 SingleChannelDDR3_1600 run are looking at the
// same device. Times are held in picoseconds because the harness clock is 20 ns and
// almost every DDR3 constraint lands off that grid: tRCD is 13.75 ns, tRAS is
// 35 ns, tBURST is 5 ns. Rounding each constraint to a harness cycle as it is
// applied would compound the error across the four or five constraints that
// gate one access. Accumulating in picoseconds and rounding once, at the point
// where the response is handed back, bounds the error at one harness cycle per
// transaction, which is also the finest granularity the 50 MHz core can
// observe.
package ddr3_pkg;

  // ---------------------------------------------------------------------------
  // Device geometry: gem5 DDR3_1600_8x8
  // ---------------------------------------------------------------------------
  // device_bus_width 8, burst_length 8, devices_per_rank 8
  //   -> burst size = 8/8 * 8 * 8 = 64 bytes
  // device_rowbuffer_size 1KiB, devices_per_rank 8
  //   -> row buffer   = 8 KiB per rank
  localparam int unsigned BurstBytes    = 64;
  localparam int unsigned RowBufferByte = 8 * 1024;
  localparam int unsigned BanksPerRank  = 8;
  localparam int unsigned RanksPerChan  = 2;
  localparam int unsigned ActLimit      = 4;   // activation_limit, the tFAW window

  localparam int unsigned BurstsPerRow = RowBufferByte / BurstBytes;  // 128

  // ---------------------------------------------------------------------------
  // Timing, picoseconds. gem5 DDR3_1600_8x8.
  // ---------------------------------------------------------------------------
  localparam int unsigned TckPs    =    1250;  // 1.25 ns, DDR3-1600
  localparam int unsigned TburstPs =    5000;  // 5 ns, BL8 at 1600 MT/s
  localparam int unsigned TrcdPs   =   13750;
  localparam int unsigned TclPs    =   13750;
  localparam int unsigned TrpPs    =   13750;
  localparam int unsigned TrasPs   =   35000;
  localparam int unsigned TwrPs    =   15000;
  localparam int unsigned TrtpPs   =    7500;
  localparam int unsigned TwtrPs   =    7500;
  localparam int unsigned TrtwPs   =    2500;
  localparam int unsigned TcsPs    =    2500;  // rank to rank switch
  localparam int unsigned TrrdPs   =    6000;
  localparam int unsigned TxawPs   =   30000;  // tFAW
  localparam int unsigned TrfcPs   =  260000;
  localparam int unsigned TrefiPs  = 7800000;  // 7.8 us

  // tRC is not a separate gem5 parameter, it is tRAS + tRP by definition.
  localparam int unsigned TrcPs = TrasPs + TrpPs;

  // gem5 charges tCL for the write path as well as the read path, so the
  // default here mirrors that rather than the JEDEC CWL of 8 tCK (10 ns).
  // Override on the module if you want the JEDEC number.
  localparam int unsigned TcwlPs = TclPs;

  // gem5 MemCtrl static_frontend_latency and static_backend_latency, the
  // controller pipeline either side of the DRAM access itself.
  localparam int unsigned FrontendPs = 10000;
  localparam int unsigned BackendPs  = 10000;

  // ---------------------------------------------------------------------------
  // Controller queues: gem5 MemCtrl
  // ---------------------------------------------------------------------------
  localparam int unsigned ReadBufferSize    = 32;
  localparam int unsigned WriteBufferSize   = 64;
  localparam int unsigned WriteHighThreshPc = 85;
  localparam int unsigned WriteLowThreshPc  = 50;
  localparam int unsigned MinWritesPerSwitch = 16;

  // ---------------------------------------------------------------------------
  // Types
  // ---------------------------------------------------------------------------
  // 64 bits of picoseconds is 213 days of simulated time. The counter cannot
  // wrap in any run this harness will ever do.
  typedef logic [63:0] ps_t;

  typedef struct packed {
    logic [$clog2(RanksPerChan)-1:0] rank;
    logic [$clog2(BanksPerRank)-1:0] bank;
    logic [31:0]                     row;
  } dram_loc_t;

  // ---------------------------------------------------------------------------
  // Address decode: gem5 RoRaBaCoCh, the MemCtrl default
  // ---------------------------------------------------------------------------
  // gem5 DRAMInterface::decodePacket for RoRaBaCoCh, with one channel:
  //
  //   addr = paddr / burstSize
  //   addr = addr / burstsPerRowBuffer
  //   bank = addr % banksPerRank,  then addr /= banksPerRank
  //   rank = addr % ranksPerChan,  then addr /= ranksPerChan
  //   row  = addr % rowsPerBank
  //
  // The column is the lowest field, so an 8 KiB stretch is one row of one bank.
  // Taking the bank from the bits above the burst, gem5's closed page mapping,
  // spread code and data over the same banks, and their rows closed each other.
  //
  // Only rank, bank and row are returned, since the column selects bytes in an
  // open row with no effect on timing, and gem5 does not track it either.
  function automatic dram_loc_t decode_addr(input logic [63:0] byte_addr,
                                            input int unsigned rows_per_bank);
    logic [63:0] a;
    dram_loc_t   loc;
    a         = byte_addr / 64'(BurstBytes);
    a         = a / 64'(BurstsPerRow);
    loc.bank  = ($clog2(BanksPerRank))'(a % 64'(BanksPerRank));
    a         = a / 64'(BanksPerRank);
    loc.rank  = ($clog2(RanksPerChan))'(a % 64'(RanksPerChan));
    a         = a / 64'(RanksPerChan);
    loc.row   = 32'(a % 64'(rows_per_bank));
    return loc;
  endfunction

  // ---------------------------------------------------------------------------
  // Statistics
  // ---------------------------------------------------------------------------
  typedef struct packed {
    logic [63:0] reads;              // read bursts served
    logic [63:0] writes;             // write bursts served
    logic [63:0] row_hits;           // access found its row already open
    logic [63:0] row_conflicts;      // a different row was open, cost tRP + tRCD
    logic [63:0] row_empty;          // bank was closed, cost tRCD
    logic [63:0] refreshes;          // refresh commands issued
    logic [63:0] refresh_stall_ps;   // time banks were blocked by refresh
    logic [63:0] read_lat_ps_sum;    // for the mean read latency
    logic [63:0] read_lat_ps_max;
    // Device access time alone, before rounding onto a clock edge and with no
    // queueing: tCL+tBURST for a row hit, plus tRCD for a closed bank, plus
    // tRP+tRCD on a conflict, the number to compare against DDR3 theory.
    logic [63:0] dev_lat_ps_sum;
    logic [63:0] dev_accesses;
    logic [63:0] bus_busy_ps;        // data bus occupancy, for utilisation
    logic [63:0] wr_to_rd_switch;    // bus turnarounds, each costs tWTR
    logic [63:0] rd_to_wr_switch;
    logic [63:0] mlp_sum;            // in flight requests, sampled every cycle
    logic [63:0] mlp_samples;        // cycles with at least one in flight
    logic [63:0] mlp_max;            // deepest concurrency actually observed
  } ddr3_stats_t;

endpackage

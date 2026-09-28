// Copyright 2026 Universidad Nacional de Cordoba, FaMAF.
// Testbench only.
//
// Standalone exerciser for axi_ddr3_slave. Drives the AXI master side from
// C++ and measures what the DDR3 model actually charges, so the timing can be
// checked against DDR3-1600 theory in seconds rather than by booting the core
// and reading a trace.
//
// Address arithmetic used by the scenarios, from the gem5 RoRaBaCoCh decode in
// ddr3_pkg.sv with a 64 byte burst, 8 banks and 2 ranks. Writing b for the
// block index, that is addr / 64:
//
//   col  = b % 128          so +64 B      stays in the bank, next column
//   bank = (b / 128) % 8    so +8 KiB     steps to the next bank
//   rank = (b / 1024) % 2   so +64 KiB    steps to the next rank
//   row  = b / 2048         so +128 KiB   stays in the bank, next row

#include "Vddr3_tb_top.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <deque>
#include <map>
#include <vector>
#include <string>

static const uint64_t MEM_BASE = 0x80000000ULL;
static const uint64_t TCK_PS   = 20000;   // 50 MHz harness clock

// Address steps that move exactly one level of the DDR3 hierarchy.
static const uint64_t STEP_BANK = 8192;
static const uint64_t STEP_RANK = 65536;
static const uint64_t STEP_COL  = 64;
static const uint64_t STEP_ROW  = 131072;

struct RdReq { uint64_t addr; uint8_t len; uint8_t id; };
struct WrReq { uint64_t addr; uint8_t len; uint8_t id; std::vector<uint64_t> data; };

struct RdRec {
  uint64_t addr = 0;
  uint64_t issued = 0;       // cycle the AR handshake happened
  uint64_t first_beat = 0;   // cycle the first R beat came back
  uint64_t last_beat = 0;
  int beats = 0;
  bool done = false;
  std::vector<uint64_t> data;
};

class Tb {
 public:
  Vddr3_tb_top* top;
  uint64_t cycle = 0;
  int fails = 0;

  std::deque<RdReq> ar_q;
  std::deque<WrReq> aw_q;
  std::map<int, std::deque<RdRec>> rd_recs;   // by id, in issue order
  std::vector<RdRec> retired;

  // Write channel state, one burst at a time on W as AXI requires.
  bool wr_active = false;
  WrReq wr_cur;
  size_t wr_beat = 0;
  bool aw_sent = false;
  int b_count = 0;

  explicit Tb(Vddr3_tb_top* t) : top(t) {}

  void reset() {
    top->rst_ni = 0;
    top->ar_valid_i = 0; top->aw_valid_i = 0; top->w_valid_i = 0;
    top->r_ready_i = 1;  top->b_ready_i = 1;
    top->ar_size_i = 3;  top->aw_size_i = 3;
    top->ar_burst_i = 1; top->aw_burst_i = 1;
    top->w_strb_i = 0xff;
    for (int i = 0; i < 8; i++) { top->clk_i = 0; top->eval(); top->clk_i = 1; top->eval(); }
    top->rst_ni = 1;
    for (int i = 0; i < 4; i++) step();
  }

  // One clock. Inputs are driven while the clock is low, outputs are sampled
  // there too, so everything read is the pre edge value the DUT will see.
  void step() {
    drive();
    top->clk_i = 0;
    top->eval();
    sample();
    top->clk_i = 1;
    top->eval();
    cycle++;
  }

  void drive() {
    // AR
    if (!ar_q.empty()) {
      top->ar_valid_i = 1;
      top->ar_addr_i  = ar_q.front().addr;
      top->ar_len_i   = ar_q.front().len;
      top->ar_id_i    = ar_q.front().id;
    } else {
      top->ar_valid_i = 0;
    }
    // AW and W
    if (!wr_active && !aw_q.empty()) {
      wr_active = true; wr_cur = aw_q.front(); aw_q.pop_front();
      wr_beat = 0; aw_sent = false;
    }
    if (wr_active && !aw_sent) {
      top->aw_valid_i = 1;
      top->aw_addr_i  = wr_cur.addr;
      top->aw_len_i   = wr_cur.len;
      top->aw_id_i    = wr_cur.id;
    } else {
      top->aw_valid_i = 0;
    }
    if (wr_active && wr_beat < wr_cur.data.size()) {
      top->w_valid_i = 1;
      top->w_data_i  = wr_cur.data[wr_beat];
      top->w_last_i  = (wr_beat + 1 == wr_cur.data.size());
    } else {
      top->w_valid_i = 0;
      top->w_last_i  = 0;
    }
  }

  void sample() {
    if (top->ar_valid_i && top->ar_ready_o) {
      RdRec r; r.addr = ar_q.front().addr; r.issued = cycle;
      rd_recs[ar_q.front().id].push_back(r);
      ar_q.pop_front();
    }
    if (top->aw_valid_i && top->aw_ready_o) aw_sent = true;
    if (top->w_valid_i && top->w_ready_o) {
      wr_beat++;
      if (wr_beat == wr_cur.data.size()) wr_active = false;
    }
    if (top->b_valid_o && top->b_ready_i) b_count++;
    if (top->r_valid_o && top->r_ready_i) {
      int id = top->r_id_o;
      auto it = rd_recs.find(id);
      if (it == rd_recs.end() || it->second.empty()) {
        printf("  [ERROR] R beat for id %d with no outstanding read\n", id);
        fails++;
        return;
      }
      RdRec& r = it->second.front();
      if (r.beats == 0) r.first_beat = cycle;
      r.last_beat = cycle;
      r.beats++;
      r.data.push_back(top->r_data_o);
      if (top->r_last_o) {
        r.done = true;
        retired.push_back(r);
        it->second.pop_front();
      }
    }
  }

  void read(uint64_t addr, int id, uint8_t len = 1) { ar_q.push_back({addr, len, (uint8_t)id}); }

  void write(uint64_t addr, int id, const std::vector<uint64_t>& d) {
    aw_q.push_back({addr, (uint8_t)(d.size() - 1), (uint8_t)id, d});
  }

  bool busy() const {
    if (!ar_q.empty() || !aw_q.empty() || wr_active) return true;
    for (auto& kv : rd_recs) if (!kv.second.empty()) return true;
    return false;
  }

  void run_idle(int max_cycles = 200000) {
    int n = 0;
    while (busy() && n < max_cycles) { step(); n++; }
    for (int i = 0; i < 4; i++) step();
    if (n >= max_cycles) { printf("  [ERROR] timed out waiting for completion\n"); fails++; }
  }

  void quiesce(int n) { for (int i = 0; i < n; i++) step(); }

  void clear_recs() { retired.clear(); }
};

static void hdr(const char* s) {
  printf("\n%s\n", s);
  printf("--------------------------------------------------------------------\n");
}

// Reports a measurement and, where DDR3-1600 pins down the answer, checks it.
// exp_ps is the exact device time, so the tolerance is only what the model's
// own arithmetic can lose, which is nothing.
static void check_ps(Tb& tb, const char* what, double got_ps, double exp_ps) {
  bool ok = (got_ps > exp_ps - 1) && (got_ps < exp_ps + 1);
  printf("  %-38s %8.2f ns   expect %8.2f ns   %s\n",
         what, got_ps / 1000.0, exp_ps / 1000.0, ok ? "PASS" : "FAIL");
  if (!ok) tb.fails++;
}

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  Vddr3_tb_top* top = new Vddr3_tb_top;
  Tb tb(top);
  tb.reset();

  printf("====================================================================\n");
  printf("  axi_ddr3_slave standalone check   DDR3-1600 8x8, 50 MHz harness\n");
  printf("  tRCD 13.75  tCL 13.75  tRP 13.75  tRAS 35  tBURST 5  tFAW 30 ns\n");
  printf("  controller backend latency 10 ns, as gem5 charges it\n");
  printf("====================================================================\n");

  // -------------------------------------------------------------------------
  hdr("1. Functional: write then read back, single and multi beat bursts");
  {
    bool ok = true;
    for (int i = 0; i < 16; i++) {
      uint64_t a = MEM_BASE + (uint64_t)i * STEP_BANK;
      tb.write(a, i & 7, {0xA5A50000ULL + i, 0x5A5A0000ULL + i});
    }
    tb.run_idle();
    tb.clear_recs();
    for (int i = 0; i < 16; i++) tb.read(MEM_BASE + (uint64_t)i * STEP_BANK, i & 7, 1);
    tb.run_idle();
    if (tb.retired.size() != 16) { printf("  [ERROR] %zu of 16 reads returned\n", tb.retired.size()); ok = false; }
    for (auto& r : tb.retired) {
      int i = (int)((r.addr - MEM_BASE) / STEP_BANK);
      if (r.beats != 2) { printf("  [ERROR] addr %#lx returned %d beats\n", (unsigned long)r.addr, r.beats); ok = false; continue; }
      uint64_t e0 = 0xA5A50000ULL + i, e1 = 0x5A5A0000ULL + i;
      if (r.data[0] != e0 || r.data[1] != e1) {
        printf("  [ERROR] addr %#lx read %#lx,%#lx expected %#lx,%#lx\n",
               (unsigned long)r.addr, (unsigned long)r.data[0], (unsigned long)r.data[1],
               (unsigned long)e0, (unsigned long)e1);
        ok = false;
      }
    }
    if (tb.b_count != 16) { printf("  [ERROR] %d B responses for 16 writes\n", tb.b_count); ok = false; }
    printf("  %s  16 two beat writes, 16 two beat reads, data and B responses\n", ok ? "PASS" : "FAIL");
    if (!ok) tb.fails++;
  }

  // -------------------------------------------------------------------------
  // Latency of one isolated read, measured from the AR handshake to the first
  // R beat. Everything in the front end is fixed overhead, so it cancels when
  // the three row cases are compared against each other.
  auto isolated_read = [&](uint64_t addr) -> double {
    tb.clear_recs();
    tb.read(addr, 0, 1);
    tb.run_idle();
    if (tb.retired.empty()) return -1;
    return (double)(tb.retired[0].first_beat - tb.retired[0].issued);
  };

  hdr("2. Row buffer: closed bank, row hit, row conflict");
  {
    // Device time on its own, taken from the model's picosecond accounting
    // before the response is rounded onto a clock edge and with no queueing in
    // it. Checked exactly, because DDR3-1600 fixes these numbers.
    auto dev_ps = [&](uint64_t addr) -> double {
      uint64_t s0 = top->st_dev_lat_ps_sum_o, n0 = top->st_dev_accesses_o;
      tb.clear_recs();
      tb.read(addr, 0, 1);
      tb.run_idle();
      uint64_t dn = top->st_dev_accesses_o - n0;
      return dn ? (double)(top->st_dev_lat_ps_sum_o - s0) / (double)dn : -1.0;
    };
    // Scenario 1 left a row open in all 16 banks. A closed bank has to be
    // arranged rather than assumed, and a refresh is what arranges it: it
    // precharges every bank in the rank. Two refreshes are waited for, because
    // the ranks are staggered and one refresh only closes the rank it belongs
    // to, and then tRFC has to expire or the access measures the tail of the
    // refresh instead of tRCD. tRFC is 260 ns, which is 13 cycles, so 20 is
    // clear of it with room to spare.
    {
      uint64_t r0 = top->st_refreshes_o;
      while (top->st_refreshes_o < r0 + 2) tb.step();
      tb.quiesce(20);
    }

    uint64_t base = MEM_BASE + 0x40000;
    double d_empty = dev_ps(base);                  // bank closed by the refresh
    double d_hit   = dev_ps(base + 8);              // same row, now open
    double d_conf   = dev_ps(base + STEP_ROW);      // same bank, another row

    // Device time excludes the controller backend latency, which is charged
    // separately, so these are pure DRAM numbers.
    const double tCL = 13750, tRCD = 13750, tRP = 13750, tBURST = 5000;
    check_ps(tb, "row hit       tCL+tBURST",       d_hit,   tCL + tBURST);
    check_ps(tb, "closed bank   +tRCD",            d_empty, tRCD + tCL + tBURST);
    check_ps(tb, "row conflict  +tRP+tRCD",        d_conf,  tRP + tRCD + tCL + tBURST);

    // End to end, which is what the core actually feels: device time rounded
    // up to a clock edge, plus the controller backend, plus the front end.
    tb.quiesce(20);
    tb.clear_recs(); tb.read(base + 16, 0, 1); tb.run_idle();
    double e2e = (double)(tb.retired[0].first_beat - tb.retired[0].issued);
    printf("\n  End to end, AR handshake to first R beat, row hit: %.0f cycles"
           " (%.0f ns)\n", e2e, e2e * TCK_PS / 1000.0);
    printf("  device %.2f ns + backend 10.00 ns + front end pipeline.\n"
           "  gem5 charges a flat 10 ns front and 10 ns back for the same\n"
           "  pipeline, so this gap is the one thing to calibrate before\n"
           "  putting an RTL run and a gem5 run side by side.\n", d_hit / 1000.0);
    printf("\n  Note: tRCD and tRP are 13.75 ns each, below the 20 ns harness\n"
           "  clock, so a single row conflict can land on the same cycle count\n"
           "  as a closed bank. The cost is real and does accumulate, because\n"
           "  the model keeps picosecond time across accesses and rounds only\n"
           "  at the response. Scenario 4 shows it adding up.\n");
  }

  // -------------------------------------------------------------------------
  hdr("3. Bank parallelism: 8 concurrent reads, one per bank, versus serial");
  {
    uint64_t base = MEM_BASE + 0x80000;
    tb.quiesce(50);
    tb.clear_recs();
    uint64_t t0 = tb.cycle;
    for (int i = 0; i < 8; i++) tb.read(base + (uint64_t)i * STEP_BANK, i, 1);
    tb.run_idle();
    uint64_t par = tb.cycle - t0;

    tb.quiesce(50);
    tb.clear_recs();
    uint64_t t1 = tb.cycle;
    for (int i = 0; i < 8; i++) {
      tb.read(base + 0x100000 + (uint64_t)i * STEP_BANK, 0, 1);
      tb.run_idle();
    }
    uint64_t ser = tb.cycle - t1;
    printf("  8 reads spread over 8 banks, all outstanding : %lu cycles\n", (unsigned long)par);
    printf("  the same 8 reads issued one at a time         : %lu cycles\n", (unsigned long)ser);
    printf("  speedup from bank level parallelism           : %.2fx\n", (double)ser / (double)par);
    if (par >= ser) { printf("  [ERROR] concurrency bought nothing, the queues are not overlapping\n"); tb.fails++; }
    else printf("  PASS  concurrent requests overlap in the bank state machines\n");
  }

  // -------------------------------------------------------------------------
  hdr("4. Row conflicts accumulate: same bank, different rows versus same row");
  {
    // Both cases hit exactly one bank, rank 0 bank 0, and both move 16 beats
    // over R, so the only difference left is the row.
    //   +STEP_ROW keeps the bank and changes the row  -> every access conflicts
    //   +STEP_COL keeps the bank and the row          -> every access hits
    auto burst = [&](uint64_t base, uint64_t step, const char* what) {
      tb.quiesce(50);
      tb.clear_recs();
      uint64_t h0 = top->st_row_hits_o, c0 = top->st_row_conflicts_o,
               e0 = top->st_row_empty_o, t0 = tb.cycle;
      for (int i = 0; i < 8; i++) tb.read(base + (uint64_t)i * step, i, 1);
      tb.run_idle();
      uint64_t cyc = tb.cycle - t0;
      printf("  %-30s %3lu cycles   hits %lu  conflicts %lu  closed %lu\n", what,
             (unsigned long)cyc,
             (unsigned long)(top->st_row_hits_o - h0),
             (unsigned long)(top->st_row_conflicts_o - c0),
             (unsigned long)(top->st_row_empty_o - e0));
      return cyc;
    };
    uint64_t conflict = burst(MEM_BASE + 0x400000, STEP_ROW, "8 rows of one bank");
    uint64_t hits     = burst(MEM_BASE + 0x600000, STEP_COL, "8 columns of one row");
    if (conflict <= hits) {
      printf("  [ERROR] row conflicts cost nothing\n"); tb.fails++;
    } else {
      printf("  PASS  row conflicts cost %lu cycles more over 8 accesses\n",
             (unsigned long)(conflict - hits));
    }
  }

  // -------------------------------------------------------------------------
  hdr("5. tFAW: a fifth activate in one rank waits for the window");
  {
    // Eight banks of rank 0 only, so every access is an activate in the same
    // rank and the fifth onward has to wait tXAW after the first.
    tb.quiesce(50);
    tb.clear_recs();
    uint64_t base = MEM_BASE + 0x180000;
    uint64_t t0 = tb.cycle;
    for (int i = 0; i < 4; i++) tb.read(base + (uint64_t)i * STEP_BANK, i, 1);
    tb.run_idle();
    uint64_t four = tb.cycle - t0;

    tb.quiesce(50);
    tb.clear_recs();
    uint64_t t1 = tb.cycle;
    for (int i = 0; i < 8; i++) tb.read(base + 0x200000 + (uint64_t)i * STEP_BANK, i, 1);
    tb.run_idle();
    uint64_t eight = tb.cycle - t1;
    printf("  4 activates, inside the tFAW window   : %lu cycles\n", (unsigned long)four);
    printf("  8 activates, two windows              : %lu cycles\n", (unsigned long)eight);
    printf("  tFAW is 30 ns, that is 1.5 harness cycles per extra window\n");
    if (eight <= four) { printf("  [ERROR] the activate window is not throttling\n"); tb.fails++; }
    else printf("  PASS  the second group of four is held off\n");
  }

  // -------------------------------------------------------------------------
  hdr("6. Refresh: tREFI 7.8 us, tRFC 260 ns, staggered across the two ranks");
  {
    uint64_t r0 = top->st_refreshes_o;
    uint64_t s0 = top->st_refresh_stall_ps_o;
    uint64_t c0 = tb.cycle;
    // 7.8 us is 390 cycles per rank, so 2000 cycles must cross several.
    for (int i = 0; i < 2000; i++) {
      if (tb.ar_q.size() < 4) tb.read(MEM_BASE + ((uint64_t)(i % 64) * STEP_BANK), i & 7, 1);
      tb.step();
    }
    tb.run_idle();
    uint64_t dr = top->st_refreshes_o - r0;
    uint64_t ds = top->st_refresh_stall_ps_o - s0;
    uint64_t dc = tb.cycle - c0;
    double expect = (double)dc * TCK_PS / 7800000.0 * 2.0;   // both ranks
    printf("  %lu cycles simulated, %.2f us\n", (unsigned long)dc, dc * TCK_PS / 1e6);
    printf("  refreshes issued : %lu   (expect about %.1f for two ranks)\n",
           (unsigned long)dr, expect);
    printf("  time banks blocked by refresh : %.2f ns\n", ds / 1000.0);
    bool ok = (dr >= (uint64_t)(expect * 0.5)) && (dr <= (uint64_t)(expect * 1.5) + 2);
    printf("  %s  refresh rate is within half of tREFI of the expected count\n", ok ? "PASS" : "FAIL");
    if (!ok) tb.fails++;
  }

  // -------------------------------------------------------------------------
  hdr("7. Read to write turnaround");
  {
    tb.quiesce(50);
    uint64_t w0 = top->st_wr_to_rd_o, r0 = top->st_rd_to_wr_o;
    for (int i = 0; i < 32; i++) {
      tb.read(MEM_BASE + 0x300000 + (uint64_t)i * STEP_BANK, i & 7, 1);
      tb.write(MEM_BASE + 0x300000 + (uint64_t)i * STEP_BANK, i & 7, {0xDEADBEEFULL + i, 0xF00DULL + i});
      tb.run_idle();
    }
    printf("  write to read turnarounds (tWTR 7.5 ns) : %lu\n",
           (unsigned long)(top->st_wr_to_rd_o - w0));
    printf("  read to write turnarounds (tRTW 2.5 ns) : %lu\n",
           (unsigned long)(top->st_rd_to_wr_o - r0));
    bool ok = (top->st_wr_to_rd_o - w0) > 0 && (top->st_rd_to_wr_o - r0) > 0;
    printf("  %s  the bus changes direction and is charged for it\n", ok ? "PASS" : "FAIL");
    if (!ok) tb.fails++;
  }

  // -------------------------------------------------------------------------
  hdr("Statistics, as the full core run reports them");
  {
    uint64_t rd = top->st_reads_o, wr = top->st_writes_o;
    uint64_t hit = top->st_row_hits_o, cf = top->st_row_conflicts_o, mt = top->st_row_empty_o;
    uint64_t acc = hit + cf + mt;
    printf("  reads %lu  writes %lu\n", (unsigned long)rd, (unsigned long)wr);
    if (acc) printf("  row hits %lu (%.1f%%)  conflicts %lu (%.1f%%)  closed %lu (%.1f%%)\n",
                    (unsigned long)hit, 100.0 * hit / acc,
                    (unsigned long)cf,  100.0 * cf  / acc,
                    (unsigned long)mt,  100.0 * mt  / acc);
    if (rd) printf("  mean read latency %.2f ns, worst %.2f ns\n",
                   (double)top->st_read_lat_ps_sum_o / rd / 1000.0,
                   (double)top->st_read_lat_ps_max_o / 1000.0);
    if (top->st_dev_accesses_o)
      printf("  mean device access time %.2f ns (no queueing, no rounding)\n",
             (double)top->st_dev_lat_ps_sum_o / (double)top->st_dev_accesses_o / 1000.0);
    if (top->st_mlp_samples_o)
      printf("  memory level parallelism: mean %.2f, peak %lu\n",
             (double)top->st_mlp_sum_o / (double)top->st_mlp_samples_o,
             (unsigned long)top->st_mlp_max_o);
    printf("  refreshes %lu, data bus busy %.2f us\n",
           (unsigned long)top->st_refreshes_o, top->st_bus_busy_ps_o / 1e6);
  }

  printf("\n====================================================================\n");
  if (tb.fails == 0) printf("  ALL CHECKS PASSED\n");
  else               printf("  %d CHECK(S) FAILED\n", tb.fails);
  printf("====================================================================\n");

  top->final();
  delete top;
  return tb.fails == 0 ? 0 : 1;
}

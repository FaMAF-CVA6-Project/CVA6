// Copyright 2021 Thales DIS design services SAS
//
// Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
// You may obtain a copy of the License at https://solderpad.org/licenses/
//
// Original Author: Jean-Roch COULON - Thales
//
// Copyright 2023 Commissariat a l'Energie Atomique et aux Energies
//                Alternatives (CEA)
//
// Author: Cesar Fuguet - CEA
// Date: August, 2023
// Description: CVA6 configuration package using the HPDcache as cache
//              subsystem, with a cache geometry table for the sweep
//
// ---------------------------------------------------------------------------
// NOTICE OF MODIFICATION
//
// This file has been modified by the FaMAF CVA6 Project, Universidad Nacional
// de Cordoba, and is NOT the upstream file. The unmodified original is in this
// same repository at core/include/cv64a6_imafdc_sv39_hpdcache_wb_config_pkg.sv.
//
// What changed: a table of cache geometries and one selector, CVA6_CONFIG_SEL,
// were added, the four cache fields of the configuration struct read the
// selected values rather than the fixed ones, and the Description line above
// says so. Nothing else is touched, so CFG_BASELINE elaborates exactly the
// core the original does.
//
// This notice is required by Apache License 2.0 section 4(b), which governs the
// original file and requires modified files to carry prominent notices stating
// that they were changed.
// ---------------------------------------------------------------------------


package cva6_config_pkg;

  // Available cache geometries (id : parameter cut : workload), the RTL twin
  // of CACHE_TESTS in the gem5 harnesses in the same order: from 2 to 18, a
  // CFG id plus 199 is the gem5 TEST id, and CFG_BASELINE has no gem5 row.
  localparam int CFG_BASELINE      = 1;   // L1I 16 KiB 4-way, L1D 32 KiB 8-way : all
  localparam int CFG_ICACHE_4K     = 2;   // IcacheByteSize 16384 -> 4096   : icache_pressure
  localparam int CFG_ICACHE_8K     = 3;   // IcacheByteSize 16384 -> 8192   : icache_pressure
  localparam int CFG_ICACHE_32K    = 4;   // IcacheByteSize 16384 -> 32768  : icache_pressure
  localparam int CFG_ICACHE_64K    = 5;   // IcacheByteSize 16384 -> 65536  : icache_pressure
  localparam int CFG_ICACHE_DM     = 6;   // IcacheSetAssoc 4 -> 1          : icache_pressure
  localparam int CFG_ICACHE_ASSOC2 = 7;   // IcacheSetAssoc 4 -> 2          : icache_pressure
  localparam int CFG_ICACHE_ASSOC8 = 8;   // IcacheSetAssoc 4 -> 8          : icache_pressure
  localparam int CFG_DCACHE_8K     = 9;   // DcacheByteSize 32768 -> 8192   : daxpy, full_test, atomic_fence
  localparam int CFG_DCACHE_16K    = 10;  // DcacheByteSize 32768 -> 16384  : full_test, fetch2_probe
  localparam int CFG_DCACHE_64K    = 11;  // DcacheByteSize 32768 -> 65536  : daxpy, full_test, atomic_fence
  localparam int CFG_DCACHE_DM     = 12;  // DcacheSetAssoc 8 -> 1          : daxpy, daxpy_unrolling_4, fetch2_probe
  localparam int CFG_DCACHE_ASSOC2 = 13;  // DcacheSetAssoc 8 -> 2          : daxpy, daxpy_unrolling_4, fetch2_probe
  localparam int CFG_DCACHE_ASSOC4 = 14;  // DcacheSetAssoc 8 -> 4          : daxpy, fetch2_probe
  localparam int CFG_BOTH_SMALL    = 15;  // L1I 4 KiB and L1D 8 KiB        : icache_pressure, full_test
  localparam int CFG_BOTH_LARGE    = 16;  // L1I 64 KiB and L1D 64 KiB      : icache_pressure, full_test
  localparam int CFG_BOTH_DM       = 17;  // both direct mapped             : icache_pressure, daxpy, daxpy_unrolling_4
  localparam int CFG_BOTH_DOUBLED  = 18;  // L1I 32 KiB and L1D 64 KiB      : icache_pressure, full_test, daxpy

  // =========================================================================
  // Change this single constant to pick which geometry runs
  // =========================================================================
  localparam int CVA6_CONFIG_SEL = CFG_BASELINE;

  localparam CVA6ConfigXlen = 64;

  localparam CVA6ConfigRVF = 1;
  localparam CVA6ConfigRVD = 1;
  localparam CVA6ConfigF16En = 0;
  localparam CVA6ConfigF16AltEn = 0;
  localparam CVA6ConfigF8En = 0;
  localparam CVA6ConfigFVecEn = 0;

  localparam CVA6ConfigCvxifEn = 1;
  localparam CVA6ConfigCExtEn = 1;
  localparam CVA6ConfigZcbExtEn = 1;
  localparam CVA6ConfigZcmpExtEn = 0;
  localparam CVA6ConfigAExtEn = 1;
  localparam CVA6ConfigBExtEn = 1;
  localparam CVA6ConfigVExtEn = 0;
  localparam CVA6ConfigHExtEn = 0;
  localparam CVA6ConfigRVZiCond = 1;

  localparam CVA6ConfigAxiIdWidth = 4;
  localparam CVA6ConfigAxiAddrWidth = 64;
  localparam CVA6ConfigAxiDataWidth = 64;
  localparam CVA6ConfigFetchUserEn = 0;
  localparam CVA6ConfigFetchUserWidth = CVA6ConfigXlen;
  localparam CVA6ConfigDataUserEn = 0;
  localparam CVA6ConfigDataUserWidth = CVA6ConfigXlen;

  localparam CVA6ConfigIcacheByteSize = 16384;
  localparam CVA6ConfigIcacheSetAssoc = 4;
  localparam CVA6ConfigIcacheLineWidth = 128;
  localparam CVA6ConfigDcacheByteSize = 32768;
  localparam CVA6ConfigDcacheSetAssoc = 8;
  localparam CVA6ConfigDcacheLineWidth = 128;

  // The geometry the table above selects. The struct below reads these, so one
  // constant changes the build and every other parameter stays put.
  localparam int SwIcacheByteSize =
      (CVA6_CONFIG_SEL == CFG_ICACHE_4K || CVA6_CONFIG_SEL == CFG_BOTH_SMALL) ? 4096 :
      (CVA6_CONFIG_SEL == CFG_ICACHE_8K) ? 8192 :
      (CVA6_CONFIG_SEL == CFG_ICACHE_32K || CVA6_CONFIG_SEL == CFG_BOTH_DOUBLED) ? 32768 :
      (CVA6_CONFIG_SEL == CFG_ICACHE_64K || CVA6_CONFIG_SEL == CFG_BOTH_LARGE) ? 65536 :
      CVA6ConfigIcacheByteSize;
  localparam int SwIcacheSetAssoc =
      (CVA6_CONFIG_SEL == CFG_ICACHE_DM || CVA6_CONFIG_SEL == CFG_BOTH_DM) ? 1 :
      (CVA6_CONFIG_SEL == CFG_ICACHE_ASSOC2) ? 2 :
      (CVA6_CONFIG_SEL == CFG_ICACHE_ASSOC8) ? 8 :
      CVA6ConfigIcacheSetAssoc;
  localparam int SwDcacheByteSize =
      (CVA6_CONFIG_SEL == CFG_DCACHE_8K || CVA6_CONFIG_SEL == CFG_BOTH_SMALL) ? 8192 :
      (CVA6_CONFIG_SEL == CFG_DCACHE_16K) ? 16384 :
      (CVA6_CONFIG_SEL == CFG_DCACHE_64K || CVA6_CONFIG_SEL == CFG_BOTH_LARGE
       || CVA6_CONFIG_SEL == CFG_BOTH_DOUBLED) ? 65536 :
      CVA6ConfigDcacheByteSize;
  localparam int SwDcacheSetAssoc =
      (CVA6_CONFIG_SEL == CFG_DCACHE_DM || CVA6_CONFIG_SEL == CFG_BOTH_DM) ? 1 :
      (CVA6_CONFIG_SEL == CFG_DCACHE_ASSOC2) ? 2 :
      (CVA6_CONFIG_SEL == CFG_DCACHE_ASSOC4) ? 4 :
      CVA6ConfigDcacheSetAssoc;

  localparam CVA6ConfigDcacheFlushOnFence = 1'b1;
  localparam CVA6ConfigDcacheInvalidateOnFlush = 1'b0;

  localparam CVA6ConfigDcacheIdWidth = 3;
  localparam CVA6ConfigMemTidWidth = CVA6ConfigAxiIdWidth;

  localparam CVA6ConfigWtDcacheWbufDepth = 7;

  localparam CVA6ConfigNrScoreboardEntries = 8;

  localparam CVA6ConfigNrLoadPipeRegs = 1;
  localparam CVA6ConfigNrStorePipeRegs = 0;
  localparam CVA6ConfigNrLoadBufEntries = 8;

  localparam CVA6ConfigRASDepth = 2;
  localparam CVA6ConfigBTBEntries = 32;
  localparam CVA6ConfigBHTEntries = 128;

  localparam CVA6ConfigTvalEn = 1;

  localparam CVA6ConfigNrPMPEntries = 8;

  localparam CVA6ConfigPerfCounterEn = 1;

  localparam config_pkg::cache_type_t CVA6ConfigDcacheType = config_pkg::HPDCACHE_WB;

  localparam CVA6ConfigMmuPresent = 1;

  localparam CVA6ConfigRvfiTrace = 1;

  localparam config_pkg::cva6_user_cfg_t cva6_cfg = '{
      XLEN: unsigned'(CVA6ConfigXlen),
      VLEN: unsigned'(64),
      FpgaEn: bit'(0),  // for Xilinx and Altera
      FpgaAlteraEn: bit'(0),  // for Altera (only)
      TechnoCut: bit'(0),
      SuperscalarEn: bit'(0),
      ALUBypass: bit'(0),
      NrCommitPorts: unsigned'(2),
      AxiAddrWidth: unsigned'(CVA6ConfigAxiAddrWidth),
      AxiDataWidth: unsigned'(CVA6ConfigAxiDataWidth),
      AxiIdWidth: unsigned'(CVA6ConfigAxiIdWidth),
      AxiUserWidth: unsigned'(CVA6ConfigDataUserWidth),
      MemTidWidth: unsigned'(CVA6ConfigMemTidWidth),
      NrLoadBufEntries: unsigned'(CVA6ConfigNrLoadBufEntries),
      RVF: bit'(CVA6ConfigRVF),
      RVD: bit'(CVA6ConfigRVD),
      XF16: bit'(CVA6ConfigF16En),
      XF16ALT: bit'(CVA6ConfigF16AltEn),
      XF8: bit'(CVA6ConfigF8En),
      RVA: bit'(CVA6ConfigAExtEn),
      RVB: bit'(CVA6ConfigBExtEn),
      ZKN: bit'(1),
      RVV: bit'(CVA6ConfigVExtEn),
      RVC: bit'(CVA6ConfigCExtEn),
      RVH: bit'(CVA6ConfigHExtEn),
      RVZCB: bit'(CVA6ConfigZcbExtEn),
      RVZCMP: bit'(CVA6ConfigZcmpExtEn),
      RVZCMT: bit'(0),
      XFVec: bit'(CVA6ConfigFVecEn),
      CvxifEn: bit'(CVA6ConfigCvxifEn),
      CoproType: config_pkg::COPRO_NONE,
      RVZiCond: bit'(CVA6ConfigRVZiCond),
      RVZicntr: bit'(1),
      RVZihpm: bit'(1),
      NrScoreboardEntries: unsigned'(CVA6ConfigNrScoreboardEntries),
      PerfCounterEn: bit'(CVA6ConfigPerfCounterEn),
      MmuPresent: bit'(CVA6ConfigMmuPresent),
      RVS: bit'(1),
      RVU: bit'(1),
      SoftwareInterruptEn: bit'(1),
      HaltAddress: 64'h800,
      ExceptionAddress: 64'h808,
      RASDepth: unsigned'(CVA6ConfigRASDepth),
      BTBEntries: unsigned'(CVA6ConfigBTBEntries),
      BPType: config_pkg::BHT,
      BHTEntries: unsigned'(CVA6ConfigBHTEntries),
      BHTHist: unsigned'(3),
      DmBaseAddress: 64'h0,
      TvalEn: bit'(CVA6ConfigTvalEn),
      DirectVecOnly: bit'(0),
      NrPMPEntries: unsigned'(CVA6ConfigNrPMPEntries),
      PMPCfgRstVal: {64{64'h0}},
      PMPAddrRstVal: {64{64'h0}},
      PMPEntryReadOnly: 64'd0,
      PMPNapotEn: bit'(1),
      NOCType: config_pkg::NOC_TYPE_AXI4_ATOP,
      NrNonIdempotentRules: unsigned'(2),
      NonIdempotentAddrBase: 1024'({64'b0, 64'b0}),
      NonIdempotentLength: 1024'({64'b0, 64'b0}),
      NrExecuteRegionRules: unsigned'(3),
      ExecuteRegionAddrBase: 1024'({64'h8000_0000, 64'h1_0000, 64'h0}),
      ExecuteRegionLength: 1024'({64'h40000000, 64'h10000, 64'h1000}),
      NrCachedRegionRules: unsigned'(1),
      CachedRegionAddrBase: 1024'({64'h8000_0000}),
      CachedRegionLength: 1024'({64'h40000000}),
      MaxOutstandingStores: unsigned'(7),
      DebugEn: bit'(1),
      AxiBurstWriteEn: bit'(0),
      IcacheByteSize: unsigned'(SwIcacheByteSize),
      IcacheSetAssoc: unsigned'(SwIcacheSetAssoc),
      IcacheLineWidth: unsigned'(CVA6ConfigIcacheLineWidth),
      DCacheType: CVA6ConfigDcacheType,
      DcacheByteSize: unsigned'(SwDcacheByteSize),
      DcacheSetAssoc: unsigned'(SwDcacheSetAssoc),
      DcacheLineWidth: unsigned'(CVA6ConfigDcacheLineWidth),
      DcacheFlushOnFence: bit'(CVA6ConfigDcacheFlushOnFence),
      DcacheInvalidateOnFlush: bit'(CVA6ConfigDcacheInvalidateOnFlush),
      DataUserEn: unsigned'(CVA6ConfigDataUserEn),
      WtDcacheWbufDepth: int'(CVA6ConfigWtDcacheWbufDepth),
      FetchUserWidth: unsigned'(CVA6ConfigFetchUserWidth),
      FetchUserEn: unsigned'(CVA6ConfigFetchUserEn),
      InstrTlbEntries: int'(16),
      DataTlbEntries: int'(16),
      UseSharedTlb: bit'(0),
      SharedTlbDepth: int'(64),
      NrLoadPipeRegs: int'(CVA6ConfigNrLoadPipeRegs),
      NrStorePipeRegs: int'(CVA6ConfigNrStorePipeRegs),
      DcacheIdWidth: int'(CVA6ConfigDcacheIdWidth)
  };

endpackage

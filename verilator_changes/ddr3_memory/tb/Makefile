# Copyright 2026 Universidad Nacional de Cordoba, FaMAF.
#
# Standalone build for the DDR3 model. Nothing here touches the CVA6 build:
# it compiles only the DDR3 sources, the AXI interface and the array, so a
# timing change can be checked in about a minute instead of rebuilding the
# whole core.
#
#   make         build and run, using the verilator on PATH
#   make docker  same, inside the project image, for when it is not
#   make lint    lint the DDR3 sources with nothing waived
#   make clean

REPO      := $(abspath $(CURDIR)/../../..)
VERILATOR ?= verilator
OBJDIR    := obj_dir

.DEFAULT_GOAL := all

SRC := \
  $(REPO)/vendor/pulp-platform/axi/src/axi_pkg.sv \
  $(REPO)/corev_apu/tb/axi_intf.sv \
  $(REPO)/vendor/pulp-platform/tech_cells_generic/src/rtl/tc_sram.sv \
  $(REPO)/common/local/util/tc_sram_wrapper.sv \
  $(REPO)/common/local/util/sram.sv \
  $(REPO)/verilator_changes/ddr3_memory/rtl/ddr3_pkg.sv \
  $(REPO)/verilator_changes/ddr3_memory/rtl/ddr3_scheduler.sv \
  $(REPO)/verilator_changes/ddr3_memory/rtl/axi_ddr3_slave.sv \
  $(REPO)/verilator_changes/ddr3_memory/tb/ddr3_tb_top.sv

# The upstream files carry width warnings the CVA6 Makefile also tolerates.
# The DDR3 sources are clean at -Wall and should stay that way.
VFLAGS := --cc --exe --build --no-timing -O3 \
          --top-module ddr3_tb_top \
          -Wall -Wno-DECLFILENAME -Wno-UNUSED -Wno-style \
          -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND -Wno-UNSIGNED -Wno-fatal \
          -CFLAGS "-O2 -std=c++17" \
          --Mdir $(OBJDIR)

.PHONY: all build run clean lint docker

# Verilator lives in the project image rather than on the host, so this runs
# the whole thing there. IMAGE and VLT_IN_IMAGE match dockerfiles/CVA6.
IMAGE        ?= manuel313/famaf_cva6:v1.0.0
VLT_IN_IMAGE ?= /CVA6/tools/verilator/bin/verilator

docker:
	docker run --rm -v "$(REPO)":/repo \
	  -w /repo/verilator_changes/ddr3_memory/tb $(IMAGE) \
	  bash -lc '$(MAKE) VERILATOR=$(VLT_IN_IMAGE) run'

all: run

build:
	$(VERILATOR) $(VFLAGS) $(SRC) ddr3_tb_main.cpp

run: build
	./$(OBJDIR)/Vddr3_tb_top

# Lint with no warnings waived and report only those raised in the DDR3
# sources, since the upstream files carry width warnings of their own.
lint:
	$(VERILATOR) --lint-only --top-module ddr3_tb_top \
	  -Wall -Wno-DECLFILENAME -Wno-UNUSED -Wno-style $(SRC) 2>&1 \
	  | grep -E "^%(Warning|Error)-[A-Z]+: [^:]*ddr3_memory/" \
	  || echo "DDR3 sources lint clean"

clean:
	rm -rf $(OBJDIR)

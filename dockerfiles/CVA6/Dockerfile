# ==============================================================================
# CVA6 + Verilator image for the FaMAF CVA6 project
# ==============================================================================
# Builds the Verilated cv64a6_imafdc_sv39_hpdcache_wb harness from THIS working
# tree rather than from a clone, so an edited RTL file reaches the container.
#
# Build from the ROOT of this repository, not from this folder:
#
#     docker build -f dockerfiles/CVA6/Dockerfile -t manuel313/famaf_cva6:build .
#     docker build --build-arg JOBS=2 ...          # on a smaller machine
#
# The RISC-V toolchain is the expensive step: ~30 GB while building, ~14 GB in
# the image, two to four hours. GCC's bootstrap peaks near 2 GB per job, so
# keep JOBS under (RAM in GB) / 2. See the README for the rest.
# ==============================================================================
# The same base as the gem5 image, so both containers share one Ubuntu and
# one set of system libraries.
FROM ubuntu:24.04

ARG JOBS=8
ENV DEBIAN_FRONTEND=noninteractive
ENV NUM_JOBS=${JOBS}

# Toolchain build dependencies, the CVA6 flow's own, and the few conveniences
# that make the container usable by hand.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git wget curl nano less gtkwave \
    autoconf automake autotools-dev libmpc-dev libmpfr-dev libgmp-dev \
    gawk build-essential bison flex texinfo gperf libtool bc zlib1g-dev \
    help2man device-tree-compiler ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# CMake 3.27, pinned to what the CVA6 flow was run with rather than whatever
# the distribution ships.
RUN wget -q https://github.com/Kitware/CMake/releases/download/v3.27.9/cmake-3.27.9-linux-x86_64.tar.gz \
    && tar -xzf cmake-3.27.9-linux-x86_64.tar.gz -C /opt \
    && mv /opt/cmake-3.27.9-linux-x86_64 /opt/cmake-3.27.9 \
    && rm cmake-3.27.9-linux-x86_64.tar.gz \
    && for b in cmake ccmake cpack ctest; do \
    ln -sf /opt/cmake-3.27.9/bin/$b /usr/local/bin/$b; done

ENV RISCV=/CVA6/tools
ENV PATH=/CVA6/tools/bin:${PATH}

# ---- the RISC-V toolchain ---------------------------------------------------
# Only the builder is copied at this point, so editing the RTL or a benchmark
# does not rebuild GCC. This is the layer worth caching above all others.
COPY util/toolchain-builder/ /CVA6/util/toolchain-builder/
WORKDIR /CVA6/util/toolchain-builder
RUN bash get-toolchain.sh && bash build-toolchain.sh /CVA6/tools

# ---- Verilator and Spike ----------------------------------------------------
# Built from the verification harness alone, again before the RTL arrives, so
# a changed core does not rebuild the simulators.
COPY verif/ /CVA6/verif/
COPY vendor/ /CVA6/vendor/
WORKDIR /CVA6
# Noble marks the system Python as externally managed, which refuses a plain
# pip install. The flow's packages are what this Python exists for here.
RUN pip3 install --no-cache-dir --break-system-packages \
    -r verif/sim/dv/requirements.txt
# Verilator's lexer needs FlexLexer.h, which Ubuntu ships in libfl-dev and
# which --no-install-recommends leaves out. Installed here, beside its
# user, so the toolchain layer above stays cached.
RUN apt-get update && apt-get install -y --no-install-recommends libfl-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# cva6.py refuses to run unless spike's own version string carries the commit
# of the source it was built from, and no history reaches this image, so the
# vendored source gets a one-commit repo of its own before spike is built.
ENV SPIKE_SRC_DIR=/CVA6/verif/core-v-verif/vendor/riscv/riscv-isa-sim
RUN git init -q "${SPIKE_SRC_DIR}" \
    && git -C "${SPIKE_SRC_DIR}" add -A \
    && git -C "${SPIKE_SRC_DIR}" -c user.email=build@local \
    -c user.name=build commit -qm "vendored spike source"

# Both installers ignore their own failures, and Verilator's default path
# is not the one setup-env.sh puts on PATH, so both are pinned and checked.
# The last test is cva6.py's own version gate, failed here rather than at run.
ENV VERILATOR_INSTALL_DIR=/CVA6/tools/verilator
ENV SPIKE_INSTALL_DIR=/CVA6/tools/spike
RUN bash -c "source ./verif/regress/install-verilator.sh" \
    && bash -c "source ./verif/regress/install-spike.sh" \
    && test -x "${VERILATOR_INSTALL_DIR}/bin/verilator" \
    && test -x "${SPIKE_INSTALL_DIR}/bin/spike" \
    && "${VERILATOR_INSTALL_DIR}/bin/verilator" --version \
    && "${SPIKE_INSTALL_DIR}/bin/spike" -v 2>&1 \
    | grep -q "$(git -C "${SPIKE_SRC_DIR}" log -1 --pretty=tformat:%h)"

# ---- the design and this project's own files --------------------------------
# Everything else, last, so an edit here rebuilds one small layer. .dockerignore
# keeps the run artefacts, the traces and the git history out.
COPY . /CVA6/

# The gem5 side, the fork's host tools and the viewer's second copies have no
# business here, so scripts/ is rebuilt from the viewer's own and everything
# read from is deleted once it has been read.
RUN rm -rf /CVA6/dockerfiles /CVA6/scripts \
    && mv /CVA6/viewers/CVA6Flow /CVA6/CVA6Flow \
    && rm -rf /CVA6/viewers \
    && mkdir -p /CVA6/scripts /CVA6/CVA6_configs /CVA6/results \
    /CVA6/benchmarks/config /CVA6/benchmarks/viewer \
    && cp /CVA6/CVA6Flow/scripts/run_CVA6.py \
    /CVA6/CVA6Flow/scripts/run_all_CVA6_benchmarks.py \
    /CVA6/CVA6Flow/scripts/clean_CVA6_runs.py \
    /CVA6/CVA6Flow/scripts/run_CVA6Flow_sweep.py \
    /CVA6/CVA6Flow/scripts/create_all_CVA6Flow_jsons.py /CVA6/scripts/ \
    && cp /CVA6/gem5_config_CVA6/CVA6/benchmarks/*.c \
    /CVA6/gem5_config_CVA6/CVA6/benchmarks/*.S \
    /CVA6/gem5_config_CVA6/CVA6/benchmarks/.overhead_suite \
    /CVA6/benchmarks/config/ \
    && cp /CVA6/CVA6Flow/benchmarks/*.c \
    /CVA6/CVA6Flow/benchmarks/*.S \
    /CVA6/CVA6Flow/benchmarks/.overhead_suite \
    /CVA6/benchmarks/viewer/ \
    && cp /CVA6/CVA6Flow/configs/*.sv /CVA6/CVA6_configs/ \
    && rm -rf /CVA6/CVA6Flow/scripts /CVA6/CVA6Flow/configs \
    /CVA6/CVA6Flow/benchmarks /CVA6/CVA6Flow/README.md \
    /CVA6/CVA6Flow/LICENSE /CVA6/CVA6Flow/CITATION.cff \
    /CVA6/CVA6Flow/.gitignore /CVA6/CVA6Flow/.nojekyll \
    /CVA6/CVA6Flow/tests/README.md \
    /CVA6/verilator_changes/custom_size_vcds/README.md \
    /CVA6/gem5_config_CVA6 /CVA6/verilator_changes/ddr3_memory \
    && chmod +x /CVA6/scripts/*.py /CVA6/CVA6Flow/*.py

COPY viewers/CVA6Flow/scripts/serve_CVA6Flow.py /CVA6/scripts/
COPY scripts/patch_vcd_window.py  /CVA6/scripts/patch_vcd_window.py
COPY scripts/run_CVA6_config_sweep.py /CVA6/scripts/

# The cache geometry package this side sweeps, beside the viewer's. It is
# copied rather than installed: the sweep puts it over the live one.
COPY gem5_config_CVA6/CVA6/configs/cv64a6_imafdc_sv39_hpdcache_wb_config_testing_pkg.sv \
    /CVA6/CVA6_configs/

# The container's own documents, which describe what is in here rather than the
# repository the image was built from. The upstream licences stay as they are,
# since the code they cover is in here too.
COPY dockerfiles/CVA6/README.md           /CVA6/README.md
COPY dockerfiles/CVA6/LICENSE.FaMAF       /CVA6/LICENSE.FaMAF
COPY dockerfiles/CVA6/CITATION.cff        /CVA6/CITATION.cff
COPY dockerfiles/CVA6/gitignore.container /CVA6/.gitignore

RUN chmod +x /CVA6/scripts/*.py

ENV DV_SIMULATORS=veri-testharness

# The viewer is served rather than opened in the container.
EXPOSE 8000

WORKDIR /CVA6
CMD ["/bin/bash"]

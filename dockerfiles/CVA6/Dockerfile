# ==============================================================================
# CVA6 + Verilator image for the FaMAF CVA6 project
# ==============================================================================
# Builds the Verilated cv64a6_imafdc_sv39_hpdcache_wb harness from THIS working
# tree rather than from a clone, so an edited RTL file reaches the container.
#
# Build from the ROOT of this repository, not from this folder:
#
#     docker build -f dockerfiles/CVA6/Dockerfile -t famaf_cva6_project/cva6:build .
#     docker build --build-arg JOBS=2 ...          # on a smaller machine
#
# The RISC-V toolchain is the expensive step: ~30 GB while building, ~14 GB in
# the image, two to four hours. GCC's bootstrap peaks near 2 GB per job, so
# keep JOBS under (RAM in GB) / 2. See the README for the rest.
# ==============================================================================
FROM ubuntu:22.04

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

# CMake 3.27, newer than jammy ships and what the CVA6 flow expects.
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
RUN pip3 install --no-cache-dir -r verif/sim/dv/requirements.txt
RUN bash -c "source ./verif/regress/install-verilator.sh" \
    && bash -c "source ./verif/regress/install-spike.sh"

# ---- the design and this project's own files --------------------------------
# Everything else, last, so an edit here rebuilds one small layer. .dockerignore
# keeps the run artefacts, the traces and the git history out.
COPY . /CVA6/

# The gem5 side and the fork's host tools have no business here, and the
# viewer's scripts/, configs/ and benchmarks/ would be second copies of the
# root's, so scripts/ is rebuilt and the copies go once they have been read.
RUN rm -rf /CVA6/gem5_config_CVA6/gem5 /CVA6/dockerfiles /CVA6/scripts \
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
    /CVA6/CVA6Flow/benchmarks \
    && chmod +x /CVA6/scripts/*.py /CVA6/CVA6Flow/*.py

COPY scripts/serve_viewers.py /CVA6/scripts/serve_viewers.py

ENV DV_SIMULATORS=veri-testharness

# The viewer is served rather than opened in the container.
EXPOSE 8000

WORKDIR /CVA6
CMD ["/bin/bash"]

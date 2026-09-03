# ==============================================================================
# CVA6 + Verilator image for the FaMAF CVA6 project
# ==============================================================================
# Builds the Verilated cv64a6_imafdc_sv39_hpdcache_wb harness from THIS working
# tree rather than from a clone, so an edited RTL file reaches the container.
#
# Build from the ROOT of this repository, not from this folder:
#
#     docker build -f dockerfiles/CVA6/Dockerfile -t famaf/cva6 .
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

ENV RISCV=/cva6/tools
ENV PATH=/cva6/tools/bin:${PATH}

# ---- the RISC-V toolchain ---------------------------------------------------
# Only the builder is copied at this point, so editing the RTL or a benchmark
# does not rebuild GCC. This is the layer worth caching above all others.
COPY util/toolchain-builder/ /cva6/util/toolchain-builder/
WORKDIR /cva6/util/toolchain-builder
RUN bash get-toolchain.sh && bash build-toolchain.sh /cva6/tools

# ---- Verilator and Spike ----------------------------------------------------
# Built from the verification harness alone, again before the RTL arrives, so
# a changed core does not rebuild the simulators.
COPY verif/ /cva6/verif/
COPY vendor/ /cva6/vendor/
WORKDIR /cva6
RUN pip3 install --no-cache-dir -r verif/sim/dv/requirements.txt
RUN bash -c "source ./verif/regress/install-verilator.sh" \
    && bash -c "source ./verif/regress/install-spike.sh"

# ---- the design and this project's own files --------------------------------
# Everything else, last, so an edit here rebuilds one small layer. .dockerignore
# keeps the run artefacts, the traces and the git history out.
COPY . /cva6/

# The gem5 side of the project has no business in this image: it would carry
# the gem5 configurations, the patch, the gem5 benchmarks and the MinorFlow
# viewer along for no reason and make /cva6 read as something it is not.
RUN rm -rf /cva6/gem5_config_CVA6/gem5 \
           /cva6/benchmarks/gem5 \
           /cva6/viewers/MinorFlow \
           /cva6/dockerfiles \
    && rm -f /cva6/clean_CVA6_repo.py /cva6/ignore_big_json.py \
             /cva6/get_cva6_files.py

# The drivers run from /cva6, which is what the README documents and what the
# hardcoded root expects, so they sit there rather than two folders down.
RUN cp /cva6/benchmarks/CVA6/run_CVA6.py \
       /cva6/benchmarks/CVA6/run_all_CVA6_benchmarks.py \
       /cva6/benchmarks/CVA6/clean_CVA6_runs.py /cva6/ \
    && mkdir -p /cva6/benchmarks_cva6 \
    && cp /cva6/benchmarks/CVA6/*.c /cva6/benchmarks/CVA6/*.S /cva6/benchmarks_cva6/ \
    && rm -rf /cva6/benchmarks \
    && mv /cva6/benchmarks_cva6 /cva6/benchmarks \
    && chmod +x /cva6/*.py /cva6/viewers/CVA6Flow/*.py

COPY dockerfiles/serve_viewers.py /cva6/serve_viewers.py

ENV DV_SIMULATORS=veri-testharness

# The viewer is served rather than opened in the container.
EXPOSE 8000

WORKDIR /cva6
CMD ["/bin/bash"]

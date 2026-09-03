# ==============================================================================
# gem5 image for the FaMAF CVA6 project
# ==============================================================================
# Builds gem5 v25.0.0.1 twice from one source tree: build/RISCV from the
# pristine sources, then build/RISCV_PATCH after applying MinorCPU_CVA6.patch.
# That order matters, since the driver tells the builds apart by a SimObject
# only the patch adds.
#
# Build from the ROOT of this repository, not from this folder:
#
#     docker build -f dockerfiles/gem5/Dockerfile -t famaf/gem5 .
#     docker build --build-arg JOBS=2 ...          # on a smaller machine
#
# Two gem5 builds are the whole cost: ~25 GB while building, ~12 GB in the
# image, one to three hours. Linking peaks near 4 GB per job, so keep JOBS
# under (RAM in GB) / 4. See the README for the rest.
# ==============================================================================
FROM ubuntu:22.04

ARG JOBS=4
ARG GEM5_TAG=v25.0.0.1
ENV DEBIAN_FRONTEND=noninteractive

# gem5's own build dependencies, then the bare-metal RISC-V toolchain the
# benchmark driver calls. riscv64-unknown-elf-gcc is the one it wants.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential scons python3-dev python3-venv python3-pip git \
        zlib1g zlib1g-dev libprotobuf-dev protobuf-compiler libprotoc-dev \
        libgoogle-perftools-dev libboost-all-dev libhdf5-serial-dev \
        python3-pydot python3-tk m4 libcapstone-dev libpng-dev libelf-dev \
        pkg-config wget cmake doxygen clang-format nano less \
        gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# The benchmarks are built for the extension set the CVA6 target implements.
RUN echo 'int main(void){return 0;}' > /tmp/probe.c && \
    riscv64-unknown-elf-gcc -march=rv64gc_zba_zbb_zbs_zbc_zbkb_zbkx_zkne_zknd_zknh \
        -mabi=lp64d -nostdlib -nostartfiles -c /tmp/probe.c -o /tmp/probe.o && \
    rm -f /tmp/probe.c /tmp/probe.o && \
    echo "[ok] toolchain accepts the benchmark -march string"

# ---- gem5, pristine ---------------------------------------------------------
RUN git clone --depth 1 --branch ${GEM5_TAG} https://github.com/gem5/gem5.git /gem5
WORKDIR /gem5

# build/RISCV must come from the unpatched tree, see the note at the top.
RUN scons defconfig build/RISCV build_opts/RISCV \
    && scons build/RISCV/gem5.opt -j${JOBS}

# ---- the patch, then the second build --------------------------------------
COPY gem5_config_CVA6/gem5/MinorCPU_CVA6.patch /gem5/MinorCPU_CVA6.patch
RUN git apply --check MinorCPU_CVA6.patch \
    && git apply MinorCPU_CVA6.patch \
    && scons defconfig build/RISCV_PATCH build_opts/RISCV \
    && scons build/RISCV_PATCH/gem5.opt -j${JOBS}

# ---- what this project adds -------------------------------------------------
# Copied last, so editing a configuration or a benchmark rebuilds one small
# layer rather than gem5.
COPY benchmarks/gem5/run_gem5.py                /gem5/
COPY benchmarks/gem5/run_all_gem5_benchmarks.py /gem5/
COPY benchmarks/gem5/clean_gem5_runs.py         /gem5/
COPY gem5_config_CVA6/gem5/*.py                 /gem5/
COPY viewers/MinorFlow/                         /gem5/viewers/MinorFlow/
COPY dockerfiles/serve_viewers.py               /gem5/serve_viewers.py

# The tests themselves, in the folder run_all_gem5_benchmarks.py looks in by
# default. Only the programs: the drivers above are the ones that run them.
COPY benchmarks/gem5/*.c benchmarks/gem5/*.S /gem5/benchmarks/

RUN chmod +x /gem5/*.py /gem5/viewers/MinorFlow/*.py

# The viewers are served rather than opened in the container
EXPOSE 8000

WORKDIR /gem5
CMD ["/bin/bash"]

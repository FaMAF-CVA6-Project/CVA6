# ==============================================================================
# gem5 image for the FaMAF CVA6 project
# ==============================================================================
# Builds gem5 v25.0.0.1 three times from one source tree: build/RISCV from the
# pristine sources, then build/RISCV_PATCH after applying MinorCPU_CVA6.patch,
# then build/RISCV_EXP from the same patched sources for working on the patch.
# That order matters, since the driver tells the builds apart by a SimObject
# only the patch adds.
#
# Build from the ROOT of this repository, not from this folder:
#
#     docker build -f dockerfiles/gem5/Dockerfile -t famaf_cva6_project/gem5:build .
#     docker build --build-arg JOBS=2 ...          # on a smaller machine
#
# Three gem5 builds are the whole cost, about 4.9 GB of build tree each, so
# roughly 37 GB while building, 17 GB in the image and two to five hours.
# Linking peaks near 4 GB per job, so keep JOBS under (RAM in GB) / 4. See
# the README for the rest.
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
COPY gem5_config_CVA6/gem5/configs/MinorCPU_CVA6.patch /gem5/MinorCPU_CVA6.patch
RUN git apply --check MinorCPU_CVA6.patch \
    && git apply MinorCPU_CVA6.patch \
    && sha1sum MinorCPU_CVA6.patch > /gem5/.built_patch_sha1 \
    && scons defconfig build/RISCV_PATCH build_opts/RISCV \
    && scons build/RISCV_PATCH/gem5.opt -j${JOBS}

# ---- the third build, for working on the patch ------------------------------
# The same sources as build/RISCV_PATCH, kept apart so an edited patch can be
# rebuilt without disturbing the build every TEST is measured against. Built
# now so its objects are warm, which makes a later edit minutes not hours.
RUN scons defconfig build/RISCV_EXP build_opts/RISCV \
    && scons build/RISCV_EXP/gem5.opt -j${JOBS}

# ---- what this project adds -------------------------------------------------
# Copied last, so editing a configuration or a benchmark rebuilds one small
# layer rather than gem5. They keep the place they have in the repository and
# still run with the root as the working directory, where build/ is.
COPY viewers/MinorFlow/scripts/run_gem5.py                /gem5/scripts/
COPY viewers/MinorFlow/scripts/run_all_gem5_benchmarks.py /gem5/scripts/
COPY viewers/MinorFlow/scripts/clean_gem5_runs.py         /gem5/scripts/
COPY viewers/MinorFlow/scripts/run_MinorFlow_sweep.py     /gem5/scripts/
COPY scripts/run_config_search_sweep.py                   /gem5/scripts/
COPY scripts/check_patch_parity.py                        /gem5/scripts/
COPY scripts/patch_gem5.py                                /gem5/scripts/
COPY scripts/serve_viewers.py                             /gem5/scripts/
COPY viewers/MinorFlow/scripts/create_all_MinorFlow_jsons.py /gem5/scripts/
COPY viewers/MinorFlow/                                   /gem5/MinorFlow/

# The viewer arrives whole, so its scripts/ is a second copy of every driver
# already in /gem5/scripts. One copy is the point of putting them there.
RUN rm -rf /gem5/MinorFlow/scripts

# Every configuration under gem5_configs/, one folder per origin, which is where
# the drivers look for one given by name alone.
COPY gem5_config_CVA6/gem5/configs/*.py                /gem5/gem5_configs/config/
COPY gem5_config_CVA6/gem5/configs/MinorCPU_CVA6.patch /gem5/gem5_configs/config/
COPY viewers/MinorFlow/configs/*.py                    /gem5/gem5_configs/viewer/
COPY viewers/MinorFlow/docs/CARLA2026/gem5_config_Reference_Core.py \
    /gem5/gem5_configs/CARLA2026/

# The tests themselves, one folder per suite, which is what the overhead
# tables are indexed by. Only the programs: the drivers above run them.
COPY gem5_config_CVA6/gem5/benchmarks/*.c \
    gem5_config_CVA6/gem5/benchmarks/*.S /gem5/benchmarks/config/
COPY gem5_config_CVA6/gem5/benchmarks/.overhead_suite /gem5/benchmarks/config/
COPY viewers/MinorFlow/benchmarks/*.c \
    viewers/MinorFlow/benchmarks/*.S /gem5/benchmarks/viewer/
COPY viewers/MinorFlow/benchmarks/.overhead_suite /gem5/benchmarks/viewer/

RUN chmod +x /gem5/scripts/*.py /gem5/MinorFlow/*.py

# The viewers are served rather than opened in the container
EXPOSE 8000

WORKDIR /gem5
CMD ["/bin/bash"]

# ==============================================================================
# gem5 image for the FaMAF CVA6 project
# ==============================================================================
# Builds gem5 v25.0.0.1 three times from one source tree: build/RISCV from the
# pristine sources, then build/RISCV_PATCH after applying MinorCPU_CVA6.patch,
# then build/RISCV_EXP from the same patched sources for working on the patch.
# That order matters, since the driver tells the builds apart by a SimObject
# only the patch adds. Like the CVA6 image, it carries no git history.
#
# Build from the ROOT of this repository, not from this folder:
#
#     docker build -f dockerfiles/gem5/Dockerfile -t manuel313/famaf_gem5:build .
#     docker build --build-arg JOBS=2 ...          # on a smaller machine
#
# Three gem5 builds are the whole cost, about 4.9 GB of build tree each, so
# roughly 37 GB while building, 17 GB in the image and two to five hours.
# Linking peaks near 4 GB per job, so keep JOBS under (RAM in GB) / 4. See
# the README for the rest.
# ==============================================================================
# Noble, not jammy: the benchmark driver compiles with the bitmanip and
# crypto extensions, which jammy's bare-metal gcc 10 rejects. This ships 13.
FROM ubuntu:24.04

ARG JOBS=4
ARG GEM5_TAG=v25.0.0.1

# What this image is, for anyone reading it rather than the repository. The
# build date is an argument, since a layer's own timestamp says when that
# layer was made rather than when the image was assembled.
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="FaMAF CVA6 Project, the gem5 container"
LABEL org.opencontainers.image.description="gem5 built three times, stock, \
patched with MinorCPU_CVA6.patch and a third for working on the patch, with \
the matched configurations, the calibration harnesses and benchmarks, the \
run drivers and sweeps, and the MinorFlow viewer with a sample of every one \
of its programs"
LABEL org.opencontainers.image.source="https://github.com/FaMAF-CVA6-Project/CVA6"
LABEL org.opencontainers.image.licenses="MIT AND BSD-3-Clause"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.version="${GEM5_TAG}"
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
# The clone is for its sources only, so its history goes in the same layer
# and never reaches the image. The pristine src/ stays behind as a 4 MB
# archive, which scripts/patch_gem5.py create diffs the tree against.
RUN git clone --depth 1 --branch ${GEM5_TAG} https://github.com/gem5/gem5.git /gem5 \
    && XZ_OPT=-T0 tar -C /gem5 -cJf /gem5/.pristine_src.tar.xz src \
    && rm -rf /gem5/.git
WORKDIR /gem5

# build/RISCV must come from the unpatched tree, see the note at the top.
RUN scons defconfig build/RISCV build_opts/RISCV \
    && scons build/RISCV/gem5.opt -j${JOBS}

# ---- the patch, then the second build --------------------------------------
# git apply needs no repository, and unlike patch it refuses a patch that
# does not apply exactly.
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
# Copied last, so editing a configuration or a benchmark rebuilds small layers
# rather than gem5. The tools all land in scripts/ and run with the root as the
# working directory, where build/ is.
COPY viewers/MinorFlow/scripts/run_gem5.py                   /gem5/scripts/
COPY viewers/MinorFlow/scripts/run_all_gem5_benchmarks.py    /gem5/scripts/
COPY viewers/MinorFlow/scripts/clean_gem5_runs.py            /gem5/scripts/
COPY viewers/MinorFlow/scripts/measure_gem5_overhead.py      /gem5/scripts/
COPY viewers/MinorFlow/scripts/run_MinorFlow_sweep.py        /gem5/scripts/
COPY scripts/run_gem5_config_sweep.py                        /gem5/scripts/
COPY scripts/check_patch_parity.py                           /gem5/scripts/
COPY scripts/patch_gem5.py                                   /gem5/scripts/
COPY viewers/MinorFlow/scripts/serve_MinorFlow.py            /gem5/scripts/
COPY viewers/MinorFlow/scripts/create_all_MinorFlow_jsons.py /gem5/scripts/
COPY viewers/MinorFlow/scripts/make_MinorFlow_sample.py      /gem5/scripts/
COPY viewers/MinorFlow/                                      /gem5/MinorFlow/

# The viewer arrives whole. Its scripts/, configs/ and benchmarks/ would be
# second copies of what /gem5 holds, and its README, licence, citation, git
# and Pages files and docs/CARLA2026 are its repository's.
RUN rm -rf /gem5/MinorFlow/scripts /gem5/MinorFlow/configs \
    /gem5/MinorFlow/benchmarks /gem5/MinorFlow/docs/CARLA2026 \
    /gem5/MinorFlow/README.md /gem5/MinorFlow/LICENSE \
    /gem5/MinorFlow/CITATION.cff /gem5/MinorFlow/.gitignore \
    /gem5/MinorFlow/.nojekyll

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

# results/ is made now, so a fresh container already has the folder the docs
# and the copy commands name. The applied copy of the patch goes, since it is
# read from gem5_configs/, and so does every __pycache__ scons left behind.
RUN mkdir -p /gem5/results \
    && rm -f /gem5/MinorCPU_CVA6.patch \
    && find /gem5 -name __pycache__ -type d -prune -exec rm -rf {} + \
    && mv /gem5/README.md /gem5/README.gem5.md \
    && chmod +x /gem5/scripts/*.py /gem5/MinorFlow/*.py

# ---- the viewer's samples ---------------------------------------------------
# A full sample of every viewer program, so Load sample has something to show
# in a fresh container. Each trace and JSON is deleted in this layer.

# The .sample.json beside each sample goes as well, since the page reads the
# .js form, so the image keeps the samples and the manifest that lists them.
RUN set -eu; cd /gem5; \
    for src in benchmarks/viewer/*.S benchmarks/viewer/*.c; do \
        name=$(basename "$src"); name=${name%.*}; \
        case $name in test_template) continue ;; esac; \
        echo "[sample] $name"; \
        python3 scripts/run_gem5.py \
            gem5_configs/viewer/gem5_config_MinorFlow.py "$src" \
            --variant stock --gem5-out-dir results/run \
            --results-dir results/run > /dev/null; \
        python3 MinorFlow/MinorFlow_tracer.py \
            "results/run/${name}_trace.txt" -o "/tmp/${name}.json" \
            --quiet --strict; \
        python3 scripts/make_MinorFlow_sample.py "/tmp/${name}.json" \
            -n 0 > /dev/null; \
        rm -rf /tmp/${name}.json results/run \
            "MinorFlow/tests/${name}.sample.json"; \
    done; \
    rm -rf /gem5/results/*; \
    ls -la /gem5/MinorFlow/tests

# What is left of gem5's own repository. No history reaches this image, so the
# files that only serve a git workflow, and the editor and CI folders, have
# nothing to act on here. The bytecode is from the step above.
RUN rm -rf /gem5/.github /gem5/.devcontainer /gem5/.vscode \
    /gem5/.pre-commit-config.yaml /gem5/.mailmap \
    /gem5/.git-blame-ignore-revs \
    && find /gem5 -name __pycache__ -type d -prune -exec rm -rf {} + \
    && rm -rf /gem5/results/*

# The container's own documents. gem5's README is kept as README.gem5.md, and
# its LICENSE and COPYING stay where they are, since gem5 is in here.
COPY dockerfiles/gem5/README.md     /gem5/README.md
COPY dockerfiles/gem5/LICENSE.FaMAF /gem5/LICENSE.FaMAF
COPY dockerfiles/gem5/CITATION.cff  /gem5/CITATION.cff

# There is no repository here, but gem5's .gitignore stays, with this
# project's own files added, so one made later shows changed gem5 sources only.
COPY dockerfiles/gem5/gitignore.extra /gem5/.gitignore.extra
RUN cat /gem5/.gitignore.extra >> /gem5/.gitignore \
    && rm /gem5/.gitignore.extra

# The viewer is served rather than opened in the container.
EXPOSE 8000

WORKDIR /gem5
CMD ["/bin/bash"]

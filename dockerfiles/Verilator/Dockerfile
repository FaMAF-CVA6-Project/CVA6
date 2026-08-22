FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install the required packages
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    gtkwave \
    nano \
    git \
    wget

# Set NUM_JOBS to the number of cores for parallel make
ENV NUM_JOBS=8

# Clone the repository, pinned to v5.3.0-89-g272e6e51
RUN git clone https://github.com/ManuelN313/cva6.git /cva6 \
    && git -C /cva6 checkout 272e6e513fb5fed4033872150f51864e58f66bda

WORKDIR /cva6

# Install the GCC toolchain
WORKDIR /cva6/tools

WORKDIR /cva6/util/toolchain-builder

RUN apt-get install -y autoconf automake autotools-dev curl git libmpc-dev libmpfr-dev libgmp-dev gawk build-essential bison flex texinfo gperf libtool bc zlib1g-dev

RUN bash get-toolchain.sh

RUN bash build-toolchain.sh /cva6/tools

# Install CMake
WORKDIR /cva6

RUN wget https://github.com/Kitware/CMake/releases/download/v3.27.9/cmake-3.27.9-linux-x86_64.tar.gz

RUN tar -xvzf cmake-3.27.9-linux-x86_64.tar.gz

RUN mv cmake-3.27.9-linux-x86_64 /opt/cmake-3.27.9

RUN ln -sf /opt/cmake-3.27.9/bin/cmake /usr/local/bin/cmake

RUN ln -sf /opt/cmake-3.27.9/bin/ccmake /usr/local/bin/ccmake

RUN ln -sf /opt/cmake-3.27.9/bin/cpack /usr/local/bin/cpack

RUN ln -sf /opt/cmake-3.27.9/bin/ctest /usr/local/bin/ctest

# Set the RISCV environment variable
ENV RISCV=/cva6/tools

# Install help2man and device-tree-compiler
RUN apt-get install -y help2man device-tree-compiler

# Install the riscv-dv requirements
RUN pip3 install --no-cache-dir -r verif/sim/dv/requirements.txt

# Install Verilator and Spike
ENV DV_SIMULATORS=veri-testharness,spike
RUN bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh

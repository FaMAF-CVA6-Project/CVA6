FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install necessary dependencies
RUN apt-get update && apt-get install -y build-essential scons python3-dev git pre-commit zlib1g zlib1g-dev \
    libprotobuf-dev protobuf-compiler libprotoc-dev libgoogle-perftools-dev \
    libboost-all-dev  libhdf5-serial-dev python3-pydot python3-venv python3-tk mypy \
    m4 libcapstone-dev libpng-dev libelf-dev pkg-config wget cmake doxygen clang-format gcc-riscv64-linux-gnu \
    g++-riscv64-linux-gnu binutils-riscv64-linux-gnu && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone the gem5 repository
RUN git clone https://github.com/gem5/gem5.git

# Set the working directory
WORKDIR /gem5

# Compile gem5 (once the container is created)
# scons build/RISCV/gem5.opt -j$(nproc)
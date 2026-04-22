#!/bin/bash

# exit script if any command fails
set -eo pipefail

error() {
    echo -e "\n\nError: $1\n\n" >&2
    exit "${2:--1}"
}

# check if thehuzz setup file is sourced
if [[ -z "${THEHUZZ_ROOT}" ]]; then
    error "thehuzz_setup.sh file is not sourced, source it: 'source <thehuzz_setup.sh file path>/thehuzz_setup.sh'"
fi

# base install dir
BENCH_DIR="$THEHUZZ_ROOT/benchmarks"
CHIPYARD_DIR="$BENCH_DIR/chipyard_1130"
RISCV_INSTALL="$CHIPYARD_DIR/riscv-tools-install"

mkdir -p "$BENCH_DIR"
cd "$BENCH_DIR"


# Sourcing the tools script
source $THEHUZZ_ROOT/tools/chipyard_1130_tools_setup.sh



###############################################
# Clone Chipyard 1.13.0
###############################################
if [[ ! -d "$CHIPYARD_DIR" ]]; then
    echo "Cloning Chipyard 1.13.0..."
    git clone https://github.com/ucb-bar/chipyard.git chipyard_1130
    cd chipyard_1130
    git checkout 1.13.0
else
    echo "Chipyard already cloned at $CHIPYARD_DIR"
    cd chipyard_1130
fi

###############################################
# RISCV tools install dir
###############################################
mkdir -p "$RISCV_INSTALL"
export RISCV="$RISCV_INSTALL"
echo "RISCV install dir: $RISCV"


# ----------------------------------------------------
# Generate Chipyard env.sh for later "source" by thehuzz_setup.sh
# ----------------------------------------------------
ENV_SH="$CHIPYARD_DIR/env.sh"

cat > "$ENV_SH" <<EOF
# >>> cy-dir-helper initialize >>>
CY_DIR=$CHIPYARD_DIR
# <<< cy-dir-helper initialize <<<

# >>> init-submodules initialize >>>
__DIR=$CHIPYARD_DIR
PATH=\$__DIR/software/firemarshal:\$PATH
# <<< init-submodules initialize <<<

export CHIPYARD_TOOLCHAIN_SOURCED=1
export RISCV=$RISCV_INSTALL
export PATH=\${RISCV}/bin:\${PATH}
export LD_LIBRARY_PATH=\${RISCV}/lib\${LD_LIBRARY_PATH:+":\${LD_LIBRARY_PATH}"}
EOF

echo "Wrote $ENV_SH"

###############################################
# Enable GCC 13 toolchain (RedHat devtoolset)
###############################################
if [[ -f /opt/rh/gcc-toolset-13/enable ]]; then
    source /opt/rh/gcc-toolset-13/enable
else
    echo "Warning: gcc-toolset-13 not found at /opt/rh/gcc-toolset-13/enable"
fi

###############################################
# Build RISC-V GNU Toolchain (robust version)
###############################################
cd "$BENCH_DIR"
if [[ ! -d riscv_13 ]]; then
    echo "Cloning riscv-gnu-toolchain into $BENCH_DIR..."

    # Use local disk for TMPDIR (avoid NFS packfile issues)
    export TMPDIR="/tmp/$USER/git_tmp"
    mkdir -p "$TMPDIR"

    # Make submodule fetches single-threaded (more reliable on NFS/HPC)
    git config --global submodule.fetchJobs 1

    # Reduce git pack/unpack memory/FD pressure a bit
    git config --global pack.window 1
    git config --global pack.windowMemory 10m
    git config --global core.deltaBaseCacheLimit 1m

    # Raise open-files limit if low (best effort)
    if [[ "$(ulimit -n)" -lt 4096 ]]; then ulimit -n 4096 || true; fi

    # Clone toolchain
    git clone https://github.com/riscv-collab/riscv-gnu-toolchain.git riscv_13
    cd riscv_13

    mkdir -p build
    cd build
    echo "Configuring riscv-gnu-toolchain..."
    ../configure --prefix="$RISCV_INSTALL" --with-cmodel=medany --with-arch=rv64gc

    echo "Building riscv-gnu-toolchain (this will take a long time)..."
    make -j24 || echo "Warning: parallel make failed, retrying serial..."
    unset LD_LIBRARY_PATH
    make -j24 || make  
    make -j24 linux || make linux
else
    echo "riscv-gnu-toolchain already present at $BENCH_DIR/riscv_13"
fi




echo "===================================================="
echo "Chipyard 1.13.0 and RISC-V tools installed under:"
echo "  $CHIPYARD_DIR"
echo "RISC-V toolchain repo cloned at:"
echo "  $BENCH_DIR/riscv_13"
echo "Toolchain installed to:"
echo "  $RISCV_INSTALL"
echo "===================================================="
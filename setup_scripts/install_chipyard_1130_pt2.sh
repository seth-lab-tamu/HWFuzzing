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

###############################################
# Check prerequisites from part 1
###############################################

# Chipyard repo
if [[ ! -d "$CHIPYARD_DIR" ]]; then
    error "Chipyard not found at $CHIPYARD_DIR. Run the first script first."
fi

# RISCV install dir
if [[ ! -d "$RISCV_INSTALL" ]]; then
    error "RISCV install directory not found at $RISCV_INSTALL. Run the first script first."
fi

# RISC-V toolchain repo
if [[ ! -d "$BENCH_DIR/riscv_13" ]]; then
    error "RISC-V toolchain repo not found at $BENCH_DIR/riscv_13. Run the first script first."
fi

# Check binaries exist
if [[ ! -x "$RISCV_INSTALL/bin/riscv64-unknown-elf-gcc" ]]; then
    error "Baremetal RISC-V GCC not found in $RISCV_INSTALL/bin. Run the first script first."
fi

if [[ ! -x "$RISCV_INSTALL/bin/riscv64-unknown-linux-gnu-gcc" ]]; then
    error "Linux RISC-V GCC not found in $RISCV_INSTALL/bin. Run the first script first."
fi

echo "All prerequisite checks passed "
echo "Ready to continue with Part 2..."


# Sourcing the tools script
source $THEHUZZ_ROOT/tools/chipyard_1130_tools_setup.sh

#######################################################
### Patching The build script for verilator disable ###
#######################################################

cd "$THEHUZZ_ROOT/benchmarks/chipyard_1130/scripts"

# Only insert if not already present
if ! grep -q "^-DVERILATOR_DISABLE=ON" build-circt-from-source.sh; then
    sed -i '98a\    -DVERILATOR_DISABLE=ON \\' build-circt-from-source.sh
    echo "Patched build-circt-from-source.sh with -DVERILATOR_DISABLE=ON"
else
    echo "Patch already applied, skipping"
fi



#######################################################
### Patching The build script to disable the conda flag  ###
#######################################################

cd "$THEHUZZ_ROOT/benchmarks/chipyard_1130/scripts"

# Add --no-conda at the end of line 319 if it's not already there
if ! sed -n '319p' build-setup.sh | grep -q -- "--no-conda"; then
    sed -i '319s|$| --no-conda|' build-setup.sh
    echo "Patched build-setup.sh: added --no-conda to line 319"
else
    echo "Patch already applied: --no-conda already present on line 319"
fi



#######################################################
### Patching The build script to disable riscv tests that are not needed  ###
#######################################################


cd "$THEHUZZ_ROOT/benchmarks/chipyard_1130/scripts"

# Comment out lines 88 and 89 if not already commented
for ln in 88 89; do
    if ! sed -n "${ln}p" build-toolchain-extra.sh | grep -q '^[[:space:]]*#'; then
        sed -i "${ln}s|^|#|" build-toolchain-extra.sh
        echo "Commented out line ${ln} in build-toolchain-extra.sh"
    else
        echo "Line ${ln} already commented out, skipping"
    fi
done




#######################################################
### Sourcing the correct toolchain and things ###
#######################################################

# === export toolchain environment ===
export CHIPYARD_TOOLCHAIN_SOURCED=1
export RISCV="$RISCV_INSTALL"
export PATH="${RISCV}/bin:${PATH}"
export LD_LIBRARY_PATH="${RISCV}/lib${LD_LIBRARY_PATH:+":${LD_LIBRARY_PATH}"}"

echo "Environment set for Chipyard toolchain:"
echo "  RISCV=$RISCV"
echo "  PATH updated: $(command -v riscv64-unknown-elf-gcc)"
echo "  LD_LIBRARY_PATH=$LD_LIBRARY_PATH"



#######################################################
### Now doing the actual build ###
#######################################################

# Have to add verilator to path otherwise I get errors
export PATH="$THEHUZZ_ROOT/tools/verilator/verilator/bin:$PATH"


cd "$THEHUZZ_ROOT/benchmarks/chipyard_1130"

./build-setup.sh riscv-tools --build-circt -s 1 -s 3 -s 4 -s 5 -s 6 -s 7 -s 8 -s 9 -s 10 -s 11
./build-setup.sh riscv-tools --build-circt -s 1 -s 6 -s 7 -s 8 -s 9
./build-setup.sh riscv-tools --build-circt -s 1 -s 4 -s 6 -s 7 -s 8 -s 9
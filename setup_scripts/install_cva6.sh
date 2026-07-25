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

###############################################
# Ensure Chipyard tools environment is sourced
###############################################

if [[ "${CHIPYARD_TOOLS_SOURCED}" != "1" ]]; then
    TOOLS_SETUP="$THEHUZZ_ROOT/tools/chipyard_1130_tools_setup.sh"

    if [[ -f "$TOOLS_SETUP" ]]; then
        echo "Sourcing $TOOLS_SETUP ..."
        source "$TOOLS_SETUP"
        export CHIPYARD_TOOLS_SOURCED=1
    else
        error "Chipyard tools setup file not found at $TOOLS_SETUP"
    fi
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
echo "Ready to continue with CVA6 Installation..."


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

##################################################################
############# Enabling CVA6 Print Log ############################
##################################################################

# Path to CVA6 Makefile
MAKE_FILE="$CHIPYARD_DIR/generators/cva6/src/main/resources/cva6/vsrc/Makefile"
# Path to replacement file from fuzzer setup
NEW_MAKE_FILE="$THEHUZZ_ROOT/setup_scripts/cva6_setup_files/Makefile"

if [[ ! -f "$MAKE_FILE" ]]; then
    error "CVA6 Makefile not found at $MAKE_FILE"
fi

echo "Updating trace parameters in $MAKE_FILE ..."

# Always overwrite with the packaged version
cp "$NEW_MAKE_FILE" "$MAKE_FILE"
echo "Makefile replaced successfully."


#########################################################################
###################### Copying coverage file and editing make options #####################
##########################################################################

# Path to Chipyard sims/vcs
SIMS_VCS_DIR="$CHIPYARD_DIR/sims/vcs"

# Path to replacement sims directory packaged with TheHuzz
NEW_SIMS_DIR="$THEHUZZ_ROOT/setup_scripts/cva6_setup_files/sims"

if [[ ! -d "$NEW_SIMS_DIR" ]]; then
    error "Replacement sims directory not found at $NEW_SIMS_DIR"
fi

echo "Replacing contents of $SIMS_VCS_DIR with custom sims files ..."

# Ensure sims/vcs exists
mkdir -p "$SIMS_VCS_DIR"

# Remove specific known files instead of using wildcard
rm -f "$SIMS_VCS_DIR/Makefile"
rm -f "$SIMS_VCS_DIR/vcs.mk"

# Copy in new files
cp -r "$NEW_SIMS_DIR"/* "$SIMS_VCS_DIR"

echo "sims/vcs directory replaced successfully."

###############################################
# Build CVA6 if not already built
###############################################

SIMS_VCS_DIR="$CHIPYARD_DIR/sims/vcs"
SIMV_BINARY="$SIMS_VCS_DIR/simv-chipyard.harness-CVA6Config"
GEN_SRC_DIR="$SIMS_VCS_DIR/generated-src"

echo "Checking if CVA6Config simulation is already built ..."

if [[ -x "$SIMV_BINARY" && -d "$GEN_SRC_DIR" ]]; then
    echo "Simulation already built: $SIMV_BINARY and $GEN_SRC_DIR exist."
else
    echo "Building CVA6Config simulation ..."
    cd "$SIMS_VCS_DIR"
    make clean
    make CONFIG=CVA6Config CHIPYARD_ROOT=$CHIPYARD_DIR
    echo "Build completed."
fi

###############################################
###### Copy dramsim2_ini into CVA6 ##########
###############################################

SRC_DRAMSIM_DIR="$CHIPYARD_DIR/generators/testchipip/src/main/resources/dramsim2_ini"
DEST_DIR="$THEHUZZ_ROOT/benchmarks/cva6"

if [[ ! -d "$SRC_DRAMSIM_DIR" ]]; then
    error "dramsim2_ini directory not found at $SRC_DRAMSIM_DIR"
fi

echo "Copying dramsim2_ini into $DEST_DIR ..."

# Ensure destination exists
mkdir -p "$DEST_DIR"

# Copy directory recursively
cp -r "$SRC_DRAMSIM_DIR" "$DEST_DIR/"

echo "dramsim2_ini copied successfully."

##############################################
######### Copying SimV to simulation #########
##############################################

mkdir -p $THEHUZZ_ROOT/sim/sim_chipyard_1130/
cp -r $SIMS_VCS_DIR $THEHUZZ_ROOT/sim/sim_chipyard_1130/vcs_0

echo "SimV binary and generated-src copied to $THEHUZZ_ROOT/sim/sim_chipyard_1130/vcs_0"

echo -e "\n\n CVA6 installation completed successfully."
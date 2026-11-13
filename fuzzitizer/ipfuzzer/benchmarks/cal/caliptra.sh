#!/bin/bash

# Define environment variables
export CALIPTRA_WORKSPACE="${IPFUZZ_ROOT}/benchmarks/cal/"
export CALIPTRA_ROOT="${CALIPTRA_WORKSPACE}/"
export TESTNAME="iccm_lock"

# Create a run folder for build outputs
RUN_FOLDER="${CALIPTRA_WORKSPACE}/run_folder"
mkdir -p "$RUN_FOLDER"

export CALIPTRA_SOC_SOURCED=1






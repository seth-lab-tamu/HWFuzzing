#!/bin/bash

sim_perif(){
    local curr_dir=$PWD
    local sim_status
    cd "$1" || return $?
    cp "$3" input.csv || {
        sim_status=$?
        cd "$curr_dir" || return $?
        return "$sim_status"
    }

    CALIPTRA_ROOT="${IPFUZZ_ROOT}/benchmarks/cal" \
        make vcs TOP_LEVEL_MODULE="${8}_tb" V="$8" RANDOM_SEED_SIM="$7" 1> "$6" 2>&1
    sim_status=$?
    stty echo 2>/dev/null || true
    cd "$curr_dir" || return $?
    return "$sim_status"
}

sim_perif "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8"

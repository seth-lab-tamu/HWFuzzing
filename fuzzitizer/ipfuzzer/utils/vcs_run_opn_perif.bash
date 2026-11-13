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
    "./$8/rel-0.1/simv" -V +vcs+lic+wait +permissive -cm "line+cond+fsm+tgl+branch+assert" \
       +ntb_random_seed="$7" +verbose +vcs+finish+"$5" +permissive-off \
       1> "$6" 2>&1
    sim_status=$?
    stty echo 2>/dev/null || true
    cd "$curr_dir" || return $?
    return "$sim_status"
}

sim_perif "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8"

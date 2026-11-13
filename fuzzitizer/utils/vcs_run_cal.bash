#!/usr/bin/env bash
set -euo pipefail

sim_dir=$1
input_file=$3
finish_time=$5

cd -- "$sim_dir"
cp -- "$input_file" program.hex
./simv.caliptra_top_tb \
    "+vcs+finish+$finish_time" \
    -l exec.log \
    -cm line+cond+fsm+tgl+branch \
    > sim.log

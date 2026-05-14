#!/bin/bash

curr_dir=$PWD
cd $1/
./simv-chipyard.harness-CVA6Config \
        +permissive -cm "line+cond+fsm+tgl+branch" \
        +dramsim +dramsim_ini_dir=$2 +max-cycles=10000000  +ntb_random_seed=$7 +loadmem=$3 +verbose +vcs+finish+$5 +permissive-off $3 \
        1> cva6_sim_terminal.log 2>&1

# fix the stty issue in SLURM batch environment
if [ -t 0 ]; then
stty echo
fi

cd $curr_dir

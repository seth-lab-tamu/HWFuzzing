#!/bin/bash

curr_dir=$PWD
cd $1/
cp $3 mem.image
opn/rel-0.1/simv -cm line+cond+tgl+fsm+branch+assert +vcs+lic+wait +wait_cycle_to_kill=10 +dowarningfinish +doerrorfinish +spc_pipe=0 +vcs+dumpvarsoff +ntb_random_seed=$7 +max_cycle=$5 +tg_seed=0 +fuzzitizer_debug_on_marker +good_trap0=0000000080000506 +bad_trap0=0000000080000508 +asm_diag_name=user_program.c +dv_root=piton > sim.log
stty echo
cd $curr_dir

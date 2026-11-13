#!/bin/bash

set -euo pipefail

error() {
    echo -e "\n\nError: $1\n\n" >&2
    exit "${2:--1}"
}

if [[ -z "${FUZZITIZER_ROOT:-}" ]]; then
    error "fuzzitizer_setup.sh is not sourced; run: source <fuzzitizer path>/fuzzitizer_setup.sh"
fi

if [[ ! -f "$FUZZITIZER_ROOT/fuzzitizer_setup.sh" ]]; then
    error "FUZZITIZER_ROOT does not point to a FUZZItizer repository: $FUZZITIZER_ROOT"
fi

export IPFUZZ_ROOT="$FUZZITIZER_ROOT/ipfuzzer"
sanitizer_filelist="$FUZZITIZER_ROOT/ipfuzzer/ipfuzzer_output/Flist.opn.fuzz"
[[ -f "$sanitizer_filelist" ]] || error "OpenPiton SoC sanitizer filelist not found at $sanitizer_filelist"

if ! command -v python >/dev/null 2>&1; then
    error "OpenPiton preprocessing requires Python 2.7, but no python executable was found"
fi

python_major="$(python -c 'import sys; print(sys.version_info[0])')"
if [[ "$python_major" != "2" ]]; then
    error "OpenPiton preprocessing requires Python 2.7; found $(python --version 2>&1)"
fi


opn_root="$FUZZITIZER_ROOT/benchmarks/opn"
opn_build_dir="$opn_root/build/vcs_opn"
sim_install_dir="$FUZZITIZER_ROOT/sim/opn"

if [[ ! -d "$opn_root" ]]; then
    error "OpenPiton source not found at $opn_root"
fi

cd "$opn_root"
set +u
source piton/ariane_setup.sh
set -u
cd "$opn_root/build"
sims -sys=opn -model_dir="$opn_build_dir" -x_tiles=2 -y_tiles=1 -vcs_build -ariane -vcs_use_cm -vcs_cm_args=line+cond+tgl+fsm+branch+assert
cd "$opn_build_dir"
touch diag.ev

rm -rf -- "$sim_install_dir"
mkdir -p -- "$sim_install_dir"

cp -r -- "$opn_build_dir" "$sim_install_dir/vcs_0"

printf '\nOpenPiton SoC installation completed successfully.\n'

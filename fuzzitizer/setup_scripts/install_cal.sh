#!/usr/bin/env bash
set -euo pipefail

error() {
    printf '\nError: %s\n\n' "$1" >&2
    exit "${2:-1}"
}

if [[ -z "${FUZZITIZER_ROOT:-}" ]]; then
    error "fuzzitizer_setup.sh is not sourced"
fi
if [[ ! -f "$FUZZITIZER_ROOT/fuzzitizer_setup.sh" ]]; then
    error "FUZZITIZER_ROOT does not point to a FUZZItizer repository: $FUZZITIZER_ROOT"
fi

export IPFUZZ_ROOT="$FUZZITIZER_ROOT/ipfuzzer"
caliptra_root="$FUZZITIZER_ROOT/benchmarks/cal"
run_folder="$caliptra_root/run_folder"
sanitizer_filelist="$FUZZITIZER_ROOT/ipfuzzer/ipfuzzer_output/Flist.cal.fuzz"
compiler="riscv64-unknown-elf-gcc"

[[ -d "$caliptra_root/src" ]] || error "Caliptra source repository not found at $caliptra_root"
[[ -f "$sanitizer_filelist" ]] || error "Caliptra SoC sanitizer filelist not found at $sanitizer_filelist"
command -v make >/dev/null 2>&1 || error "make was not found on PATH"
command -v vlogan >/dev/null 2>&1 || error "Synopsys vlogan was not found on PATH"
command -v vcs >/dev/null 2>&1 || error "Synopsys VCS was not found on PATH"
command -v "$compiler" >/dev/null 2>&1 || error "$compiler was not found on PATH"

compiler_version="$($compiler -dumpfullversion)"
[[ "$compiler_version" == 12.2* ]] || error "$compiler version 12.2.x is required; found $compiler_version"
multilibs="$($compiler -print-multi-lib)"
grep -q '^rv32im/ilp32;' <<<"$multilibs" || error "$compiler is missing rv32im/ilp32 multilib support"
grep -q '^rv32imc/ilp32;' <<<"$multilibs" || error "$compiler is missing rv32imc/ilp32 multilib support"

export CALIPTRA_ROOT="$caliptra_root"
mkdir -p "$run_folder"
make -C "$run_folder" -f "$caliptra_root/tools/scripts/Makefile" TESTNAME=fuzzer SANITIZER_FILELIST="$sanitizer_filelist" vcs

[[ -x "$run_folder/simv.caliptra_top_tb" ]] || error "Caliptra VCS executable was not produced"
[[ -d "$run_folder/simv.caliptra_top_tb.vdb" ]] || error "Caliptra VCS coverage database was not produced"
[[ -f "$run_folder/crt0.o" ]] || error "Caliptra crt0.o was not produced"

sim_install_dir="$FUZZITIZER_ROOT/sim/cal/vcs_0"
software_crt0="$FUZZITIZER_ROOT/software/riscv/cal/crt0.o"
sim_parent="$(dirname "$sim_install_dir")"
mkdir -p "$sim_parent" "$(dirname "$software_crt0")"
staging_dir="$(mktemp -d "$sim_parent/.install.XXXXXX")"
trap 'rm -rf -- "$staging_dir"' EXIT

mkdir "$staging_dir/vcs_0"
cp -a -- "$run_folder/." "$staging_dir/vcs_0/"
cp -- "$run_folder/crt0.o" "$staging_dir/crt0.o"

previous_sim="$sim_parent/.vcs_0.previous.$$"
if [[ -e "$sim_install_dir" ]]; then
    mv -- "$sim_install_dir" "$previous_sim"
fi
if ! mv -- "$staging_dir/vcs_0" "$sim_install_dir"; then
    [[ ! -e "$previous_sim" ]] || mv -- "$previous_sim" "$sim_install_dir"
    error "could not install the Caliptra simulator"
fi
rm -rf -- "$previous_sim"
mv -- "$staging_dir/crt0.o" "$software_crt0"

printf '\nCaliptra SoC installation completed successfully.\n'

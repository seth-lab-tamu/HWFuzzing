#!/bin/bash

set -eo pipefail

error() {
    echo -e "\n\nError: $1\n\n" >&2
    exit "${2:--1}"
}

install_soc_perif() {
    local peripheral="$1"
    local soc="$2"
    local soc_probe_file="$3"
    local soc_root="$4"
    local vcs_copy_dir
    local cov_dir

    if [[ -z "${IPFUZZ_ROOT:-}" ]]; then
        error "IPFUZZ_ROOT is not set; source the parent FUZZItizer environment"
    fi

    if [[ ! -f "${soc_probe_file}" ]]; then
        error "${soc} RTL source tree is incomplete; expected ${soc_probe_file}"
    fi

    if [[ "${soc}" == "opn" ]]; then
        rm -rf -- "${soc_root}/build/vcs_${peripheral}"
    elif [[ "${soc}" == "cal" ]]; then
        make -C "${soc_root}/tools/scripts" -f Makefile clean
    else
        error "unsupported SoC family: ${soc}"
    fi

    cd "${soc_root}"

    printf 'l=[]\n' > "${IPFUZZ_ROOT}/utils/${peripheral}_inst_list.py"
    mkdir -p "${IPFUZZ_ROOT}/benchmarks/${peripheral}/tb"
    mkdir -p "${IPFUZZ_ROOT}/benchmarks/${peripheral}/sim"
    printf 'jg*\n' > "${IPFUZZ_ROOT}/benchmarks/${peripheral}/sim/.gitignore"

    cd "${IPFUZZ_ROOT}/fuzz"
    python3 createPerifTb.py -co "${peripheral}"
    python3 -c "import createPerifSanitizersJg as s; s.main(empty_only=True)" -co "${peripheral}"

    cd "${soc_root}"
    if [[ "${soc}" == "opn" ]]; then
        source "${soc_root}/piton/ariane_setup.sh"
        cd "${soc_root}/build"
        sims -sys="${peripheral}" -model_dir="${PITON_ROOT}/build/vcs_${peripheral}" -x_tiles=2 -y_tiles=1 -vcs_build -ariane -vcs_use_cm -vcs_cm_args=line+cond+tgl+fsm+branch+assert -vcs_build_args="-debug_access+r -kdb -cm_fsmopt allowTmp+allowZeroChecks+includeCalcFsms+report2StateFsms+reportvalues+reportWait+reportXassign" | tee comp.log
        vcs_copy_dir="build/vcs_${peripheral}"
    else
        source "${soc_root}/caliptra.sh"
        cd "${soc_root}/tools/scripts"
        make vcs-build TOP_LEVEL_MODULE="${peripheral}_tb" V="${peripheral}"
        rm -rf -- "${soc_root}/tools/scripts/work.lib++"
        vcs_copy_dir="tools/scripts"
    fi

    rm -rf -- "${IPFUZZ_ROOT}/sim/${peripheral}"
    mkdir -p "${IPFUZZ_ROOT}/sim/${peripheral}"
    cp -r -- "${soc_root}/${vcs_copy_dir}" "${IPFUZZ_ROOT}/sim/${peripheral}/vcs_0"

    : > "${IPFUZZ_ROOT}/setup_scripts/input.csv"
    "${IPFUZZ_ROOT}/utils/vcs_run_${soc}_perif.bash" \
        "${IPFUZZ_ROOT}/sim/${peripheral}/vcs_0" t \
        "${IPFUZZ_ROOT}/setup_scripts/input.csv" t 1000 testRun.log 100 "${peripheral}"

    rm -rf -- "${IPFUZZ_ROOT}/fuzz/test"
    cd "${IPFUZZ_ROOT}/fuzz"
    if [[ "${soc}" == "opn" ]]; then
        cov_dir="${peripheral}/rel-0.1/simv.vdb/snps/coverage/db/testdata/cm_data"
    else
        cov_dir="simv.${peripheral}.vdb/snps/coverage/db/testdata/test"
    fi
    cp -r -- "../sim/${peripheral}/vcs_0/${cov_dir}" "${IPFUZZ_ROOT}/fuzz/test"
    python3 -c "import parse_cov as p; p.get_inst_list('test/'); exit()" -co "${peripheral}"
    printf '    ]\n' >> list.py
    cp -- list.py "${IPFUZZ_ROOT}/utils/${peripheral}_inst_list.py"
    rm -f -- list.py

    rm -rf -- "${IPFUZZ_ROOT}/sim/${peripheral}_san"
    if ((1)); then
        cd "${IPFUZZ_ROOT}/fuzz"
        python3 createPerifSanitizersJg.py -co "${peripheral}"

        mkdir -p "${IPFUZZ_ROOT}/sim/${peripheral}_san"

        if [[ "${soc}" == "opn" ]]; then
            rm -rf -- "${soc_root}/build/vcs_${peripheral}"
            cd "${soc_root}/build"
            sims -sys="${peripheral}" -model_dir="${PITON_ROOT}/build/vcs_${peripheral}" -x_tiles=2 -y_tiles=1 -vcs_build -ariane -vcs_use_cm -vcs_cm_args=line+cond+tgl+fsm+branch+assert -vcs_build_args="-debug_access+r -kdb -cm_fsmopt allowTmp+allowZeroChecks+includeCalcFsms+report2StateFsms+reportvalues+reportWait+reportXassign" | tee comp.log
        else
            make -C "${soc_root}/tools/scripts" -f Makefile clean
            cd "${soc_root}/tools/scripts"
            make vcs-build TOP_LEVEL_MODULE="${peripheral}_tb" V="${peripheral}"
            rm -rf -- "${soc_root}/tools/scripts/work.lib++"
        fi

        cp -r -- "${soc_root}/${vcs_copy_dir}" "${IPFUZZ_ROOT}/sim/${peripheral}_san/vcs_0"
    fi

    echo -e "\n\n ${peripheral} installation completed successfully."
}

opn_perifs=("opn_aes0" "opn_aes1" "opn_aes2" "opn_acct" "opn_dbg" "opn_dma" "opn_hmac" "opn_reglk" "opn_rng" "opn_rsa" "opn_rst" "opn_sha256")
cal_perifs=("cal_csrng" "cal_doe" "cal_dv" "cal_ecc" "cal_entropy_src" "cal_hmac" "cal_kv" "cal_pv" "cal_spi_host" "cal_sha256" "cal_sha512" "cal_uart")
all_perifs=("${opn_perifs[@]}" "${cal_perifs[@]}")

declare -A soc_file
declare -A soc_dir
soc_file["opn"]="${IPFUZZ_ROOT}/benchmarks/opn/piton/design/chip/tile/ariane/src/aes0/aes0_wrapper.sv"
soc_file["cal"]="${IPFUZZ_ROOT}/benchmarks/cal/src/sha512/rtl/sha512_core.v"
soc_dir["opn"]="${IPFUZZ_ROOT}/benchmarks/opn"
soc_dir["cal"]="${IPFUZZ_ROOT}/benchmarks/cal"

if (($# == 0)); then
    error "no peripherals requested" 2
fi

valid_perifs=()
if (($# == 1)) && [[ "$1" == "all" ]]; then
    valid_perifs=("${all_perifs[@]}")
else
    for arg in "$@"; do
        if [[ "${arg}" == "all" ]]; then
            error "all cannot be combined with individual peripherals" 2
        elif [[ " ${all_perifs[*]} " =~ " ${arg} " ]]; then
            valid_perifs+=("${arg}")
        else
            echo "WARNING: skipping unsupported peripheral: ${arg}" >&2
        fi
    done
fi

if ((${#valid_perifs[@]} == 0)); then
    error "none of the requested peripherals are supported" 2
fi

python3 "${IPFUZZ_ROOT}/utils/export_soc_input_manifest.py"

for peripheral in "${valid_perifs[@]}"; do
    echo "Installing ${peripheral} peripheral"
    soc="${peripheral:0:3}"
    install_soc_perif \
        "${peripheral}" \
        "${soc}" \
        "${soc_file[$soc]}" \
        "${soc_dir[$soc]}"
    echo "Installing ${peripheral} peripheral done"
done

"""Caliptra whole-SoC benchmark configuration."""

import os as host_os
from pathlib import Path
from string import Template

from peripheral_inputs import load_peripheral_specs


pt = {}
pt["sim_dir_t"] = Template(
    f"{host_os.path.join(host_os.environ['FUZZITIZER_ROOT'], 'sim/cal')}/vcs_${{tno}}"
)
pt["core_dram_path"] = ""

core_name = "cal"
ready = True
isa = "riscv"
os = "cal"
instruction_xlen = 32
allow_privilege_switch = False
emit_initial_mmio_store = False

mmio_word_bits = 32
mmio_address_bits = 32
mmio_alignment = 4
mmio_settings = {
    "word_bits": 32,
    "alignment": 4,
    "c_scalar_type": "uint32_t",
    "load_mnemonic": "lw",
    "store_mnemonic": "sw",
}

pt["fuzzer_input_format"] = "cal"
pt["sim_out_path_t"] = Template(f"{pt['sim_dir_t'].template}/sim.log")
pt["trace_out_path_t"] = Template(f"{pt['sim_dir_t'].template}/exec.log")
pt["bug_out_path_t"] = Template(f"{pt['sim_dir_t'].template}/bug.log")
pt["cov_out_path_t"] = Template(
    f"{pt['sim_dir_t'].template}/simv.caliptra_top_tb.vdb"
)
pt["vdb_test_dir"] = "snps/coverage/db/testdata/test/"
pt["vdb_ext_test_dir"] = "snps/coverage/db/testdata/test_ext/"
top_instance = "caliptra_top_tb"
max_sim_cycles = 340
time_fr_1_cycle = 10_000
tot_sim_time = 1_000_000_000
max_syscall_prob = 100
syscall_ids = []

peripheral_base_addresses = {
    "cal_csrng": 0x20002000,
    "cal_doe": 0x10000000,
    "cal_dv": 0x1001C000,
    "cal_ecc": 0x10008000,
    "cal_entropy_src": 0x20003000,
    "cal_hmac": 0x10010000,
    "cal_kv": 0x10018000,
    "cal_pv": 0x1001A000,
    "cal_spi_host": 0x20000000,
    "cal_sha256": 0x10028000,
    "cal_sha512": 0x10020000,
    "cal_uart": 0x20001000,
}


def add_external_trigger(spec):
    spec["external_trigger_mmio"] = {
        # The official Caliptra simulation testbench interprets this firmware
        # write as a request to assert the SoC scan-mode input after 100 cycles.
        "address": 0x300300CC,
        "data": 0xEF,
        "wait_nops": 160,
    }
    return spec


def get_peripheral_specs(handoff_root=None):
    ipfuzz_root = Path(host_os.environ["FUZZITIZER_ROOT"]) / "ipfuzzer"
    if handoff_root is None:
        handoff_root = ipfuzz_root / "ipfuzzer_output"
    specs = load_peripheral_specs(
        Path(handoff_root) / "soc_input_manifest.json",
        "cal",
        peripheral_base_addresses,
        ipfuzz_root,
    )
    return tuple(add_external_trigger(spec) for spec in specs)


peripheral_specs = ()
perif_addresses = list(peripheral_base_addresses.values())

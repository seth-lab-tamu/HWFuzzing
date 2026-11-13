import os as host_os
from pathlib import Path
from string import Template

from peripheral_inputs import load_peripheral_specs


#############
# VARIABLES #
#############
pt = {}

pt["sim_dir_t"] = Template(f"{host_os.path.join(host_os.environ['FUZZITIZER_ROOT'], 'sim/opn')}/vcs_${{tno}}")
pt["core_dram_path"] = ""

core_name       = "opn"
ready           = True
isa = "riscv"
os = "opn"
instruction_xlen = 64
allow_privilege_switch = True
emit_initial_mmio_store = True
mmio_word_bits = 64
mmio_address_bits = 64
mmio_alignment = 8
mmio_settings = {
    "word_bits": 64,
    "alignment": 8,
    "c_scalar_type": "uint64_t",
    "load_mnemonic": "ld",
    "store_mnemonic": "sd",
}
peripheral_base_addresses = {
    "opn_aes0": 0xFFF5200000,
    "opn_aes1": 0xFFF5201000,
    "opn_sha256": 0xFFF5202000,
    "opn_hmac": 0xFFF5203000,
    "opn_acct": 0xFFF5205000,
    "opn_reglk": 0xFFF5206000,
    "opn_dma": 0xFFF5207000,
    "opn_rng": 0xFFF5208000,
    "opn_aes2": 0xFFF5209000,
    "opn_rst": 0xFFF520A000,
    "opn_rsa": 0xFFF5211000,
    "opn_dbg": 0xFFF1000000,
}
def get_peripheral_specs(handoff_root=None):
    ipfuzz_root = Path(host_os.environ["FUZZITIZER_ROOT"]) / "ipfuzzer"
    if handoff_root is None:
        handoff_root = ipfuzz_root / "ipfuzzer_output"
    return load_peripheral_specs(
        Path(handoff_root) / "soc_input_manifest.json",
        "opn",
        peripheral_base_addresses,
        ipfuzz_root,
    )


peripheral_specs = ()



pt["fuzzer_input_format"]  = 'opn'
pt["sim_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/sim.log")
pt["trace_out_path_t"] = Template(f"{pt['sim_dir_t'].template}/trace_hart_0.log")
pt["bug_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/bug.log") 
pt["cov_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/opn/rel-0.1/simv.vdb")

pt["vdb_test_dir"] = "snps/coverage/db/testdata/cm_data/"
pt["vdb_ext_test_dir"] = "snps/coverage/db/testdata/cm_data_ext/"

top_instance = "cmp_top.system"
max_sim_cycles = 340
time_fr_1_cycle = 10_000
tot_sim_time = 400000
max_syscall_prob = 100

syscall_ids = []

perif_addresses = list(peripheral_base_addresses.values())

"""
This is the config script for cva6 related settings
"""
import os
from string import Template


#############
# VARIABLES #
#############

#paths (update these when you are setting up fuzzer or soc in a new place)
pt = {} # dictionary to store all paths

pt["sim_dir_t"] = Template(f"{os.path.join(os.environ['THEHUZZ_ROOT'], 'sim/sim_chipyard_1130/')}/vcs_${{tno}}")  # dir where simulation is run
pt["core_dram_path"] = os.path.join(os.environ['THEHUZZ_ROOT'], 'benchmarks/cva6_1130/dramsim2_ini') # copied from chipyard/generators/testchipip/src/main/resources
# assert the core dram is present
# assert os.path.exists(pt["core_dram_path"]), f"Core dram path not found: {pt['core_dram_path']}"

pt["dtb_file_path"] = os.path.join(os.environ['THEHUZZ_ROOT'], "benchmarks/cva6_1130/cva6.dtb")
pt["elf_entry_addr"] = "0x80000000"
pt["csr_regs"] = [] # havent configured trace log for now
pt["spike_max_inst"] = 350 # max instructions for spike to dump csr info

# other variables
core_name       = "cva6"
ready           = True # tells the fuzzer if this core is ready to be fuzzed
core_full_name  = "CVA6"
isa = "riscv_1130"
os = "bm"

################################
# EDIT WITH CAUTION BELOW THIS #
################################
#inferred paths (update these if the soc or fuzzer git repo structure is changed)

# general
pt["input_format"]     = 'riscv'
pt["sim_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/sim.log") # vcs output file path
pt["trace_out_path_t"] = Template(f"{pt['sim_dir_t'].template}/trace_hart_0.log") # rtl trace output file path
pt["bug_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/bug.log") 
pt["cov_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/simv-chipyard.harness-{core_full_name}Config.vdb") # rtl coverage o/p file path

pt["vdb_test_dir"] = "snps/coverage/db/testdata/test/"
pt["vdb_ext_test_dir"] = "snps/coverage/db/testdata/test_ext/"

top_instance = "TestDriver.testHarness.chiptop0.system.tile_prci_domain.element_reset_domain_cva6_tile.core"

#max_sim_cycles = 340  # this is enough to run about 500 instructions 
#time_fr_1_cycle = 10_000  # 10,000 ps = 10 ns = 100Mh
time_per_inst = 20_000 #ps
#max_sim_instr = 10_000 # max inst for cascade sim
max_sim_instr = 500
tot_sim_time = time_per_inst * max_sim_instr

# list the riscv instruction extensions for the core
inst_isa = { "rv32i": 1, "rv64i": 1
            ,"rv32m": 1, "rv64m": 1
            ,"rv32a": 1, "rv64a": 1
        }

#cov_sizes = {'line': 6590, 'branch': 11382, 'cond': 12361, 'fsm': 287, 'tgl': 251266}
cov_sizes = {'line': 6576, 'branch': 11388, 'cond': 45394, 'fsm': 281, 'tgl': 350222}
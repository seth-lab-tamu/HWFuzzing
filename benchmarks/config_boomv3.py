"""
This is the config script for boom related settings
"""
import os
from string import Template


#############
# VARIABLES #
#############

#paths (update these when you are setting up fuzzer or soc in a new place)
pt = {} # dictionary to store all paths

pt["sim_dir_t"] = Template(f"{os.path.join(os.environ['THEHUZZ_ROOT'], 'sim/sim_chipyard_1130/')}/vcs_${{tno}}") # dir where simulation is run
pt["core_dram_path"] = os.path.join(os.environ['THEHUZZ_ROOT'], 'benchmarks/boomv3_1130/dramsim2_ini') # copied from chipyard/generators/testchipip/src/main/resources
# assert the core dram is present
# assert os.path.exists(pt["core_dram_path"]), f"Core dram path not found: {pt['core_dram_path']}"

# used for spike emulation
pt["dtb_file_path"] = os.path.join(os.environ['THEHUZZ_ROOT'], "benchmarks/boomv3_1130/boomv3.dtb")
pt["elf_entry_addr"] = "0x80000000"
pt["csr_regs"] = ['fflags', 'frm', 'fcsr', 'sstatus', 'sie'\
                , 'stvec','scounteren', 'senvcfg', 'sscratch'\
                , 'sepc', 'scause', 'stval', 'sip', 'satp'\
                , 'mstatus', 'misa', 'medeleg', 'mideleg'\
                , 'mie', 'mtvec', 'mcounteren', 'mscratch', 'mepc'\
                , 'mcause', 'mtval', 'mip', 'mtval2', 'menvcfg'\
                , 'mnscratch', 'mnepc', 'mncause', 'mnstatus'\
                , 'minstret', 'pmpcfg0', 'pmpcfg2', 'pmpaddr0'\
                , 'pmpaddr1', 'pmpaddr2', 'pmpaddr3', 'pmpaddr4'\
                , 'pmpaddr5', 'pmpaddr6', 'pmpaddr7', 'pmpaddr8'\
                , 'pmpaddr9', 'pmpaddr10', 'pmpaddr11',            'pmpaddr12'\
                , 'pmpaddr13', 'pmpaddr14', 'pmpaddr15']
pt["spike_max_inst"] = 350 # max instructions for spike to dump csr info

# other variables
core_name       = "boomv3"
ready           = True # tells the fuzzer if this core is ready to be fuzzed
core_full_name  = "SmallBoomV3"
isa = "riscv_1130"
os = "bm"

################################
# EDIT WITH CAUTION BELOW THIS #
################################
#inferred paths (update these if the soc or fuzzer git repo structure is changed)

# general
pt["input_format"]     = 'riscv'
pt["sim_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/sim.log") # vcs output file path
pt["trace_out_path_t"] = Template(f"{pt['sim_dir_t'].template}/rtl_trace_out.log")
pt["bug_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/bug.log") 
pt["cov_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/simv-chipyard.harness-{core_full_name}Config.vdb") # rtl coverage o/p file path

pt["vdb_test_dir"] = "snps/coverage/db/testdata/test/"
pt["vdb_ext_test_dir"] = "snps/coverage/db/testdata/test_ext/"

top_instance = "TestDriver.testHarness.chiptop0.system.tile_prci_domain.element_reset_domain_boom_tile"

#max_sim_cycles = 340 # this is enough to run about 500 instructions
#time_fr_1_cycle = 10_000  # 10,000 ps = 10 ns = 100Mhz
#max_sim_instr = 350 # max instructions for spike to dump csr information
time_per_inst = 20_000 #ps
# todo add a condition to specify inputs from thehuzz or cascade
#max_sim_instr = 10_000 # max inst for cascade sim
max_sim_instr = 500
tot_sim_time = time_per_inst * max_sim_instr

# list the riscv instruction extensions for the core
inst_isa = { "rv32i": 1, "rv64i": 1
            ,"rv32m": 1, "rv64m": 1
            ,"rv32a": 1, "rv64a": 1
        }

#cov_sizes = {'line': 13384, 'branch': 15780, 'cond': 12140, 'fsm': 434, 'tgl': 642406}
cov_sizes = {'line': 13383, 'branch': 16009, 'cond': 59546, 'fsm': 421, 'tgl': 642394}
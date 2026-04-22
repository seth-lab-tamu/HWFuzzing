"""
This is the config script for spike emulator related settings
"""
import os
from string import Template


#############
# VARIABLES #
#############

#paths (update these when you are setting up fuzzer or soc in a new place)
pt = {} # dictionary to store all paths

pt["sim_dir_t"] = Template(f"{os.path.join(os.environ['THEHUZZ_ROOT'], 'sim/spike/')}") # dir where simulation is run

# other variables
emu_name       = "spike"
ready           = True # tells the fuzzer if this emu is ready to be fuzzed
emu_full_name  = "spike"
isa = "riscv"
os = "bm"


################################
# EDIT WITH CAUTION BELOW THIS #
################################
#inferred paths (update these if the soc or fuzzer git repo structure is changed)

# general
pt["input_format"]     = 'mem'
pt["sim_out_path_t"]   = Template(f"{pt['sim_dir_t'].template}/sim_${{tno}}.log") # spike emulation output file path
pt["trace_out_path_t"] = None # rtl trace output file path (none means we can use custom path for trace)

tot_sim_time = 2 # real time in seconds

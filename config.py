"""
- This is the main config file for the TheHuzz project
- Use the configManager library to parse this config file
- This script requires the environment variable THEHUZZ_ROOT to be set because it uses os.environ["THEHUZZ_ROOT"]
    - This variable is set by the thehuzz_setup.sh script
- Note: 
    - All the variables in argVars will be availabe to be edited as arguments
      from the terminal
      - Ex: max_fuzz_time can be edited as: 
        - python3  <script>.py --max_fuzz_time 500 (or) python3  <script>.py -mt 500 
      - Run python3 <script>.py --help for list of available variables
    - Dont use one variable to create another variable
        - Use functions to do this. For example, see vdb_cov_files'
        - All functions will be replaced with absolute values uisng data from input
          arguments IN THE ORDER THEY ARE DEFINED
            - so, avoid using value of one func in another
    - New variables with names as keys of argVars dict will be created and added
      to config by the configManager
      - Ex: 'core_name' will be a variable of config and can be accessed as 'config.core_name'
    - For arrays use this format: python3 <script>.py --list 1 1 0 

- TODOs: 
    - add debug run mode,  nop run mode, and random run mode
"""


###########
# imports #
###########
import os
from datetime import datetime
from string import Template
import config_rc as RC, config_cva6 as CVA6, config_boomv3 as BOOMV3, config_boomv4 as BOOMV4 
import config_spike as SPIKE, config_spike_csr as SPIKE_CSR
import rc_inst_list, cva6_inst_list, boomv3_inst_list, boomv4_inst_list
from riscv_isa import inst_isa

import warnings
# Suppress SyntaxWarning
warnings.filterwarnings("ignore", category=SyntaxWarning)

#################
# ARG VARIABLES #
#################
"""
- Structure of argVars values: 
    - 's': short name, 'v': default value, 'c': valid choices, 'h': help text
- All variables in the argVars are user options
- Change the 'v' value of any variable as needed
    - You can also change these variables from the terminal to avoid changing the script itself
        - Run 'python3 <file_name>.py --help' for more details
"""

argVars = {}
argVars['core_name']        = {'s' : 'co' , 'v' : 'rc', 'c' : ['rc', 'cva6', 'boomv3', 'boomv4'], 'h' : "select core(benchmark) to fuzz"}
argVars['run_id']           = {'s' : 'id' , 'v' : f"{datetime.now().strftime('%y_%m_%d_%H_%M_%S')}",  'c' : None, 'h' : "select run name to store results (uses current time by default)"}
argVars['run_mode']         = {'s' : 'rm' , 'v' : 'thehuzz','c' : ['thehuzz', 'random', 'noptest', 'psofuzz', 'mabfuzz', 'refuzztest'], 'h' : "select which fuzzers to run"}
argVars['output_root_dir']  = {'s' : 'ord', 'v' : '',       'c' : None,     'h' : "absolute parent directory for outputs and outputs_all (default: THEHUZZ_ROOT)"}
argVars['run_task']         = {'s' : 'rt' , 'v' : 'fuzz',   'c' : ['fuzz', 'check_mismatches', 'update_excel', 'plot_graph'], 'h' : "runs normally if fuzz is selected. rest of the options are subtasks that run corresponding task and quit"}
argVars['max_fuzz_time']    = {'s' : 'mt' , 'v' : 259_200,  'c' : None,     'h' : "select max time to run (in seconds)"}
argVars['max_fuzz_progs']   = {'s' : 'mp' , 'v' : 50_000,   'c' : None,     'h' : "select max no. of testcases to run"}
argVars['random_seed']      = {'s' : 'rs' , 'v' : 0,        'c' : None,     'h' : "provide a integer as random seed to use. give 0 to generate seed randomly"}
argVars['target_cov']       = {'s' : 'tc' , 'v' : 100,      'c' : None,     'h' : "select coverage target (in percentage)"}
argVars['sim_batch_size']   = {'s' : 'sj' , 'v' : 10,       'c' : None,     'h' : "select number of testcases to simulate at once (recommended between 10 to 100)"}
argVars['seed_gen_interval']= {'s' : 'sge', 'v' : 2000,     'c' : None,     'h' : "new seeds will be introduced after these many mutations to ensure fuzzer explores entire design"}
argVars['no_threads']       = {'s' : 'j'  , 'v' : 10,       'c' : None,     'h' : "select max no of threads to use (should not be greater than sim_batch_size)"}
argVars['num_times_to_mut'] = {'s' : 'mm' , 'v' : 10,       'c' : None,     'h' : "select max no of times testcases are mutated during fuzzing)"}
argVars['store_elf_file']   = {'s' : 'sfe', 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to store the generated elf files"}
argVars['store_trace_file'] = {'s' : 'sft', 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to store the generated trace files"}
argVars['store_cov_file']   = {'s' : 'sfc', 'v' : 0,        'c' : [0,1],    'h' : "set to 1 to store the coverage files (not needed to run TheHuzz, setting this reduces fuzzer speed)"}
argVars['collect_interesting_tests'] = {'s' : 'cit', 'v' : 0, 'c' : [0,1],  'h' : "set to 1 to store tests that increase the feedback coverage metrics"}
argVars['collect_cov_samples'] = {'s' : 'ccs', 'v' : 0,      'c' : [0,1],    'h' : "set to 1 to store merged coverage samples at target coverage intervals"}
argVars['cov_sample_interval'] = {'s' : 'csi', 'v' : 2.5,    'c' : None,     'h' : "coverage percentage interval for storing coverage samples"}

argVars['start_type_cov']   = {'s' : 'stc', 'v' : 'new',                     'c' : ['new', 'continue'], 'h' : "select continue if fuzzer should continue using existing coverage, make sure to set the file path with -icf arg"}
argVars['input_cov_file']   = {'s' : 'icf', 'v' : '',                        'c' : None,                'h' : "set the full path for the json coverage dictionary file that fuzzer should continue using"}
argVars['cov_types']        = {'s' : 'ct' , 'v' : ['line', 'branch', 'cond', 'fsm', 'tgl'], 'c' : None, 'h' : "select which coverage metrics to collect and use for results (available types: 'line', 'branch', 'cond', 'fsm', 'tgl')"}
argVars['feedback_cov_types']={'s' : 'fct', 'v' : ['line', 'branch', 'cond', 'fsm', 'tgl'], 'c' : None, 'h' : "select which coverage metrics to use as feedback  (available types: 'line', 'branch', 'cond', 'fsm', 'tgl')"}
argVars['cov_enable']       = {'s' : 'ce' , 'v' : 1,        'c' : [1],      'h' : "set to 1 to collect coverage (this has to be enabled if fuzzer should use coverage feedback)"}

argVars['detecting_bugs']   = {'s' : 'db' , 'v' : 0,        'c' : [0, 1],   'h' : "sets bug hunting on/off"}
argVars['detecting_bugs_mode']={'s':'dbm' , 'v' : 'fileno','c' : ['fileno','debug'],'h' : "fileno is default, debug is if you want to check specific file"}
argVars['detecting_bugs_file_nos']={'s':'dbn', 'v' : [0],   'c' : None,     'h' : "set of files to run mismatch detection on"}
argVars['debug_print']      = {'s' : 'dp' , 'v' : 0,        'c' : [0,1],    'h' : "set to 1 to enable debug print messages in the log file"}
argVars['force_delete']     = {'s' : 'fd' , 'v' : 0,        'c' : [0,1],    'h' : 'set to 1 to skip confirmation when deleting files & dirs (use with caution)'}

# profiling related
argVars['prof_gen_progs']   = {'s' : 'pg' , 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to generate program files"}
argVars['prof_mut_progs']   = {'s' : 'pm' , 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to mutate program files"}
argVars['prof_run_progs']   = {'s' : 'pr' , 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to simulate program files"}
argVars['prof_merge_cov']   = {'s' : 'pmc', 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to merge cov and collect cov increments"}
argVars['prof_run_optimizer']={'s' : 'pro', 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to run the optimizer"}
argVars['prof_check_prog_files'] = {'s' : 'pc', 'v' : 1,    'c' : [0,1],    'h' : "set to 1 to check if all prog files are generated correctly"} 

# graph related
argVars['cov_type_to_plot'] = {'s' : 'ctp', 'v' : 'total',  'c' : ['line', 'branch', 'cond', 'fsm', 'tgl', 'total'], 'h' : "select cov types to plot"}
argVars['runs_to_plot']     = {'s' : 'rtp', 'v' : ["thehuzz", "random"],'c' : None, 'h' : "select run types to plot"}
argVars['graph_time_prog']  = {'s' : 'gtp', 'v' : 'prog',   'c' : ['time', 'prog'], 'h' : "select time or programs for x-axis"}
argVars['no_col_per_exp']   = {'s' : 'cpe', 'v' : 7,        'c' : None,     'h' : "specify the no. of columns of data per experiment in excel sheet"}
argVars['graph_skip_rows']  = {'s' : 'gsr', 'v' : 1,        'c' : None,     'h' : "select no. of rows to skip in excel sheet"}
argVars['graph_prog_step']  = {'s' : 'gps', 'v' : 100,      'c' : None,     'h' : "set resolution of points to plot"}
argVars['graph_prog_tick']  = {'s' : 'gpt', 'v' : 1000,     'c' : None,     'h' : "set resolution of ticks on x-axis"}
argVars['graph_time_step']  = {'s' : 'gts', 'v' : 60,       'c' : None,     'h' : "set resolution of points to plot (in sec)"}
argVars['graph_time_tick']  = {'s' : 'gtt', 'v' : 60*60,    'c' : None,     'h' : "set resolution of ticks on x-axis (in sec)"}
argVars['graph_in_percent'] = {'s' : 'gip', 'v' :  1,       'c' : [0,1],    'h' : "set to 1 to plot coverage percentage on y-axis, else it plots no. of cov points"}
argVars['graph_4x_plot']    = {'s' : 'g4p', 'v' :  0,       'c' : [0,1],    'h' : "set to 1 to plot broken axis graph"}
argVars['graph_max_progs_to_plot']  = {'s' : 'gmp', 'v' : 10**10,'c': None, 'h' : "set max no. of testcases to plot"}
argVars['graph_max_time_to_plot']   = {'s' : 'gmt', 'v' : 10**10,'c': None, 'h' : "set max time to plot (in sec)"}
argVars['use_cust_cov_files_dir']   = {'s' : 'gcd', 'v' : "",    'c': None, 'h' : "provide a custom dir for cov files (if empty string, default path will be used)"} 
argVars['use_cust_graph_excel_file']= {'s' : 'gef', 'v' : "",    'c': None, 'h' : "provide a custom excel file path (if empty string, default path will be used)"} 
argVars['use_cust_graph_plot_file'] = {'s' : 'gpf', 'v' : "",    'c': None, 'h' : "provide a custom graph output file (if empty string, default path will be used)"}
argVars['use_cust_ref_cov_dict_file']={'s' : 'gcf', 'v' : "",    'c': None, 'h' : "provide a custom path for the reference coverage dict file (if empty string, default path will be used)"}
argVars['excel_file_path']          = {'s' : 'efp', 'v' : '',    'c' : None,'h' : "full path to the excel file where the cov data should be stored"}

# bug detection related
argVars['ign_mm_after_first']= {'s': 'bif', 'v' : 1,        'c' : [0,1],    'h' : "set to ignore any mismatches after the first mismatch in trace output of each program input"}
argVars['ign_itr_mm']        = {'s': 'bim', 'v' : ["1"],       'c' : None,     'h' : "provide a array of mismatch ids to ignore. Ex: -bim 1 5 9"}

# multi arm bandit related
argVars['mab_algo']         = {'s' : 'maba' , 'v' : 'Greedy','c' : ['Greedy', 'UCB', 'EpsilonGreedy', 'EXP3'], 'h' : "select which MAB algo to use (only relevant for mabfuzz run_mode)"}
argVars['mab_num_seed_arms'] = {'s' : 'mabns' , 'v' : 10,'c' : None, 'h' : "select how many arms seed mab should have (only relevant for mabfuzz run_mode)"}
argVars['mab_n_picks_reset'] = {'s' : 'mabnpr' , 'v' : 3,'c' : None, 'h' : "select reset after how many iterations with 0 cov incr (only relevant for mabfuzz run_mode)"}

# contextual bandit testing related
argVars['refuzz_train_source'] = {'s' : 'rts' , 'v' : 'thehuzzcascade', 'c' : ['thehuzz', 'thehuzzcascade'], 'h' : "select which ReFuzz trained DB source to use"}
argVars['training_processors'] = {'s' : 'tp' , 'v' : ['cva6', 'rc', 'boomv3', 'boomv4'], 'c' : ['cva6', 'rc', 'boomv3', 'boomv4'], 'h' : "select ReFuzz training benchmarks used to derive the trained DB model name"}
argVars['refuzz_train_method'] = {'s' : 'rtm' , 'v' : 'refuzz_train', 'c' : ['refuzz_train'], 'h' : "select ReFuzz training method"}
argVars['refuzz_epoch_num'] = {'s' : 'ren' , 'v' : 10000, 'c' : None, 'h' : "select ReFuzz training epochs"}
argVars['cb_vul'] = {'s' : 'cbv' , 'v' : 0, 'c' : [0, 1], 'h' : "sets vul_train on/off (only relevant for refuzztest run_mode)"}


################################
# EDIT WITH CAUTION BELOW THIS #
################################
"""
- All variables below are developer options, edit with caution
- Check the pt function for the directory structure of the project
"""

# coverage files
def vdb_cov_files(): return [f"{cov_type}.verilog.data.xml" for cov_type in cov_types]

# core specific variables #
def CORE(): 
    if core_name == 'rc': 
        CORE_local = RC
    elif core_name == 'cva6': 
        CORE_local = CVA6
    elif core_name == 'boomv3':
        CORE_local = BOOMV3
    elif core_name == 'boomv4':
        CORE_local = BOOMV4
    else: 
        assert False, f"unknown core:{core_name} encountered"
    assert core_name == CORE_local.core_name, f"incorrect core config file imported, {core_name}, {CORE_local.core_name}"
    assert CORE_local.ready, f"core is not ready to run yet {CORE_local.ready}"

    return CORE_local

# core instance list for coverage
def core_instance_list(): 
    if core_name == 'rc': 
        core_instance_list_local = rc_inst_list.l
    elif core_name == 'cva6': 
        core_instance_list_local = cva6_inst_list.l
    elif core_name == 'boomv3':
        core_instance_list_local = boomv3_inst_list.l
    elif core_name == 'boomv4':
        core_instance_list_local = boomv4_inst_list.l
    else: 
        assert False, f"unknown core:{core_name} encountered"

    return core_instance_list_local

# emu specific variables
def EMU(): 
    # select the emulator to use depending on the ISA
    isa = CORE.isa
    os = CORE.os

    if isa == 'riscv' and os == 'bm': 
        EMU_local = SPIKE
    elif isa == 'riscv_1130' and os == 'bm':
        EMU_local = SPIKE_CSR
    elif isa == 'riscv' and os == 'opn': 
        EMU_local = SPIKE # TODO: fix this for openpiton OS
    elif isa == 'rsd' and os == 'bm':
        EMU_local = SPIKE # TODO: fix this for rsd
    elif isa == 'xiangshan':
        EMU_local = SPIKE # xiangshan has an embedded grm
    else: 
        assert False, f"unknown isa/os:{isa}/{os} encountered for core:{core_name}"
    assert EMU_local.ready, f"emulator is not ready to run yet {EMU_local.ready}"

    return EMU_local


# riscv isa configuration
def inst_list_all_w_ext(): 

    inst_list_all_w_ext = {}
    for ext,ext_data in inst_isa.items():
        if CORE.inst_isa[ext] == 0:  #skip this extension
            continue
        ext_dict = ext_data
        for inst, inst_data in ext_dict.items():
            #inst_list_all[inst] = inst_data
            inst_list_all_w_ext[(inst, ext)] = inst_data

    return inst_list_all_w_ext


#inferred paths (update these if the soc or fuzzer git repo structure is changed)
def pt():

    pt = {} # dictionary to store all paths

    emu_name_local = EMU.emu_name

    # name of the run/database
    pt['run_name'] = f"{core_name}_{run_mode}_{run_id}" 

    # git repo path
    pt["root_dir"] = os.environ["THEHUZZ_ROOT"]

    # root
    pt["benchmarks_dir"]=os.path.join(pt["root_dir"] , "benchmarks/"        )
    pt["docs_dir"]     = os.path.join(pt["root_dir"] , "docs/"              )
    pt["utils_dir"]    = os.path.join(pt["root_dir"] , "utils/"             )
    pt["thehuzz_dir"]  = os.path.join(pt["root_dir"] , "thehuzz/"           )
    pt["sw_dir"]       = os.path.join(pt["root_dir"] , "software/"          )
    pt["input_seeds_dir"] = os.path.join(pt["root_dir"], "input_seeds/"     ) 
    pt["setup_scripts_dir"] = os.path.join(pt["root_dir"], "setup_scripts/" ) 

    output_root_dir_local = pt["root_dir"] if output_root_dir == "" else os.path.expanduser(output_root_dir)
    assert os.path.isabs(output_root_dir_local), f"output_root_dir must be an absolute path: {output_root_dir}"
    os.makedirs(output_root_dir_local, exist_ok=True)
    pt["output_root_dir"] = output_root_dir_local
    pt["outputs_dir"]  = os.path.join(output_root_dir_local , "outputs/"           )
    pt["outputs_all_dir"]  = os.path.join(output_root_dir_local , "outputs_all/"   )

    # utils dir
    pt["opt_sol_file"] = os.path.join(pt["utils_dir"], f"cplex_cov_sol_{core_name}.json")
    pt["sim_bash_file"] = os.path.join(pt["utils_dir"], f"vcs_run_{core_name}.bash")
    pt["emu_bash_file"] = os.path.join(pt["utils_dir"], f"emu_run_{emu_name_local}.bash")
   
    # sw_dir
    pt["sw_run_dir"] = os.path.join(pt["sw_dir"], CORE.isa, CORE.os)
    # outputs and outputs all dirs
    pt["outputs_run_dir"]    = os.path.join(pt["outputs_dir"], pt['run_name']) # dir where non-reproducable or small data about run is stored
    pt["outputs_all_run_dir"]= os.path.join(pt["outputs_all_dir"], pt['run_name']) # dir where all reproducable and big log files will be stored
    pt["trash_run_dir"]      = os.path.join(pt["outputs_all_dir"], f"trash_{pt['run_name']}/") # dir where all useless files are moved (bcz moving is faster than deleting)


    if use_cust_cov_files_dir == "": 
        pt['graph_cov_files_dir'] = os.path.join(pt['outputs_dir'], 'cov_files')
    else: 
        pt['graph_cov_files_dir'] = use_cust_graph_excel_file

    if use_cust_graph_excel_file == "": 
        pt['graph_excel_file'] = os.path.join(pt['outputs_dir'], 'exp_data.xlsx')
    else: 
        pt['graph_excel_file'] = use_cust_graph_excel_file

    if use_cust_graph_plot_file == "": 
        pt['graph_plot_file'] = os.path.join(pt['outputs_dir'], 'exp_plot.pdf')
    else: 
        pt['graph_plot_file'] = use_cust_graph_plot_file

    if use_cust_ref_cov_dict_file == "": 
        pt['graph_ref_cov_dict_file'] = os.path.join(pt['outputs_dir'], f'{core_name}_ref_cov_dict.json')
    else: 
        pt['graph_ref_cov_dict_file'] = use_cust_ref_cov_dict_file


    # outputs/<run_name> dir and outputs_all/<run_name> dir
    pt["gen_progs_dir"]      = os.path.join(pt["outputs_run_dir"], "gen_progs") # dir name where i/p progs r generated
    pt["sim_store_dir"]      = os.path.join(pt["outputs_all_run_dir"], "sim_out") # dir name where sim logs are stored
    pt["all_progs_dir"]      = os.path.join(pt["outputs_run_dir"], "all_progs") # dir where fuzzer will store all testcases
    pt["merged_covs_dir"]    = os.path.join(pt["outputs_run_dir"], "merged_covs") # dir where profiler stores merged cov
    pt["merged_cov_file"]    = os.path.join(pt["outputs_run_dir"], "merged_cov.json") # file where merged cov is stored
    pt["cov_log_file"]       = os.path.join(pt["outputs_run_dir"], "cov_log.json") # file where merged cov is stored
    pt["particle_cov_log_file"]= os.path.join(pt["outputs_run_dir"], "particle_cov_log.jsonl") # file where each particle merged cov is stored
    pt["particle_status_log_file"]= os.path.join(pt["outputs_run_dir"], "particle_status_log.jsonl") # file where each particles status is stored
    pt["inputs_log_file"]    = os.path.join(pt["outputs_run_dir"], "inputs_log.txt") # file where logs about testcases is stored
    pt["fuzz_log_file"]      = os.path.join(pt["outputs_run_dir"], "fuzz_log.txt") # file where fuzz log is stored
    pt["cov_data_dict_file"] = os.path.join(pt["outputs_run_dir"], "cov_data_dict.json") # file where merged cov is stored
    pt["mismatches_summary_file"] = os.path.join(pt["outputs_run_dir"], "mismatches_summary.json") # file where a summary of all mismatches is recorded
    pt["interesting_tests_dir"] = os.path.join(pt["outputs_run_dir"], "interesting_tests") # dir where feedback-coverage-increasing tests are stored
    pt["interesting_cov_log_file"] = os.path.join(pt["interesting_tests_dir"], "interesting_cov_log.json") # cov log for interesting tests
    pt["cov_samples_dir"] = os.path.join(pt["outputs_run_dir"], "cov_samples") # dir where target coverage samples are stored
    pt["cov_samples_log_file"] = os.path.join(pt["cov_samples_dir"], "cov_samples_log.json") # log for target coverage samples

    # outputs/<run_name>/gen_progs dir
    pt['hex_file_t']    = Template("inst_file_$fno.hex")
    pt['hex_file_re']   = "inst_file_(\d+).hex"
    pt['bin_file_t']    = Template("inst_file_$fno.bin")
    pt['bin_file_re']   = "inst_file_(\d+).bin"
    pt['mem_file_t']    = Template("inst_file_$fno.mem")  # should be same as hex file name
    pt['riscv_file_t']  = Template("inst_file_$fno.riscv")
    pt['riscv_file_re']  = "inst_file_(\d+).riscv"


    # outputs/<run_name>/sim_out dir
    pt['trace_out_t'] = Template("rtl_trace_out_$fno.log")
    pt['trace_out_re']= "rtl_trace_out_(\d+).log"
    # dump for rsd debugging purpose
    pt['instr_out_t'] = Template("rtl_instr_out_$fno.log")
    pt['instr_out_re']= "rtl_instr_out_(\d+).log"
    pt['sim_out_t'] = Template("rtl_sim_out_$fno.log")
    pt['sim_out_re']= "rtl_sim_out_(\d+).log"
    pt['bug_out_t']   = Template("rtl_bug_out_$fno.log")
    pt['cov_out_t']   = Template("rtl_cov_out_$fno.pickle")
    pt['emu_trace_out_t'] = Template("emu_trace_out_$fno.log")
    pt['comp_trace_out_t'] = Template("comp_trace_out_$fno.json")

    # outputs/<run_name>/all_progs_dir
    pt['hex_file_itr_t']  = Template("inst_file_$fno_itr_$itrno.hex")
    pt['hex_file_itr_re'] = "inst_file_(\d+)_itr_(\d+).hex"
    pt['hex_file_mut_t']  = Template("inst_file_${file_no}_itr_${file_itr}_mut_${mut}_inst_${inst_no}.hex")
    pt['hex_file_mut_re'] = "inst_file_(\d+)_itr_(\d+)_mut_(\d+)_inst_(\d+).hex"
    pt['mem_file_mut_re'] = "inst_file_(\d+)_itr_(\d+)_mut_(\d+)_inst_(\d+).mem"

    # inputs dir
    pt['seed_input_file_re'] = "[^\.](.*).hex" # shouldnt start with . bcz they are swap files

    return pt

# perform any checks here
# this function will use the updated values provided by the users
#   TODO: check if this is true for func values also 
def config_check(): 
    t = 1

# fuzzer variables and other variables
num_inst_in_prog_prof   = 20  # number of times the instrn will get mutated when profiling
num_itr_per_inst        = 8  # number of times each instrn is generated for profiling
num_inst_in_prog        = 20 # number of instructions in seed testcases
num_nops_at_start       = 15 # number of nop instructions before testing instructions in testcase
num_nops_at_end         = 15 # number of nop instructions after testing instructions in testcase
all_cov_types           = ['line', 'branch', 'cond', 'fsm', 'tgl', 'total'] # available types of coverage
val_muts                = [0,1,2,3,4,5,6,7] #value mutations, they dont change the opcode 
opc_muts                = [8,9,10,11]  #these mutations can change the opcode

###############
# depreciated #
###############
    #pt["gen_progs_run_dir_name"]= f"gen_progs_{run_name}/"  # dir name where i/p progs r generated 

    #argVars['clone_no']         = {'s' : 'cl' , 'v' : 0,        'c' : None,     'h' : "select current clone if using multiple instances of fuzzer parallely, else ignore it"}

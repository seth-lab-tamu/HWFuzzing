###########
# imports #
###########
import os
from datetime import datetime
from string import Template
import config_opn_perif as OPN_PERIF
import config_cal_perif as CAL_PERIF
import opn_aes0_inst_list, opn_acct_inst_list, opn_hmac_inst_list, opn_sha256_inst_list, opn_rng_inst_list
import opn_aes1_inst_list, opn_aes2_inst_list, opn_rsa_inst_list, opn_reglk_inst_list, opn_rst_inst_list, opn_dma_inst_list, opn_dbg_inst_list
import cal_csrng_inst_list, cal_doe_inst_list, cal_dv_inst_list, cal_ecc_inst_list, cal_entropy_src_inst_list, cal_hmac_inst_list, cal_kv_inst_list, cal_pv_inst_list, cal_spi_host_inst_list, cal_sha256_inst_list, cal_sha512_inst_list, cal_uart_inst_list

#################
# ARG VARIABLES #
#################
opn_perifs = [f"opn_{i}" for i in ["aes0", "aes1", "aes2", "acct", "dbg", "dma", "hmac", "reglk", "rng", "rsa", "rst", "sha256"]]
cal_perifs = ["cal_csrng", "cal_doe", "cal_dv", "cal_ecc", "cal_entropy_src", "cal_hmac", "cal_kv", "cal_pv", "cal_spi_host", "cal_sha256", "cal_sha512", "cal_uart"]

argVars = {}
argVars['core_name']        = {'s' : 'co' , 'v' : 'opn_aes0', 'c' : opn_perifs+cal_perifs, 'h' : "select peripheral to fuzz"}
argVars['run_id']           = {'s' : 'id' , 'v' : f"{datetime.now().strftime('%y_%m_%d_%H_%M_%S')}",  'c' : None, 'h' : "select run name to store results (uses current time by default)"}

argVars['run_mode']         = {'s' : 'rm' , 'v' : 'fuzz',   'c' : ['fuzz', 'random'], 'h' : "select coverage-guided fuzzing or random regression"}
argVars['max_fuzz_time']    = {'s' : 'mt' , 'v' : 259_200,  'c' : None,     'h' : "select max time to run (in seconds)"}
argVars['max_fuzz_progs']   = {'s' : 'mp' , 'v' : 20_000,   'c' : None,     'h' : "select max no. of testcases to run"}
argVars['random_seed']      = {'s' : 'rs' , 'v' : 0,        'c' : None,     'h' : "provide a integer as random seed to use. give 0 to generate seed randomly"}
argVars['target_cov']       = {'s' : 'tc' , 'v' : 100,      'c' : None,     'h' : "select coverage target (in percentage)"}
argVars['sim_batch_size']   = {'s' : 'sj' , 'v' : 10,       'c' : None,     'h' : "select number of testcases to simulate at once (recommended between 10 to 100)"}
argVars['seed_gen_interval']= {'s' : 'sge', 'v' : 2000,     'c' : None,     'h' : "new seeds will be introduced after these many mutations to ensure fuzzer explores entire design"}
argVars['no_threads']       = {'s' : 'j'  , 'v' : 10,       'c' : None,     'h' : "select max no of threads to use (should not be greater than sim_batch_size)"}
argVars['num_times_to_mut'] = {'s' : 'mm' , 'v' : 10,       'c' : None,     'h' : "select max no of times testcases are mutated during fuzzing)"}
argVars['mutation_prob']    = {'s' : 'mupb','v' : 20,       'c' : None,     'h' : "select prob of mutating inputs"}
argVars['replay_input_policy'] = {'s' : 'rip', 'v' : 'greedy', 'c' : ['greedy', 'interesting'], 'h' : "select which peripheral inputs to replay with sanitizers"}
argVars['soc_assertion_policy'] = {'s' : 'sap', 'v' : 'violations', 'c' : ['violations', 'all'], 'h' : "select which peripheral assertions to export for whole-SoC fuzzing"}

argVars['start_type_cov']   = {'s' : 'stc', 'v' : 'new',                     'c' : ['new', 'continue'], 'h' : "select continue if fuzzer should continue using existing coverage, make sure to set the file path with -icf arg"}
argVars['input_cov_file']   = {'s' : 'icf', 'v' : '',                        'c' : None,                'h' : "set the full path for the json coverage dictionary file that fuzzer should continue using"}
argVars['cov_types']        = {'s' : 'ct' , 'v' : ['line', 'branch', 'cond', 'fsm', 'tgl', 'assert'], 'c' : None, 'h' : "select which coverage metrics to collect and use for results (available types: 'line', 'branch', 'cond', 'fsm', 'tgl', 'assert')"}
argVars['feedback_cov_types']={'s' : 'fct', 'v' : ['line', 'branch', 'cond', 'fsm', 'tgl'], 'c' : None, 'h' : "select which coverage metrics to use as feedback (available types: 'line', 'branch', 'cond', 'fsm', 'tgl')"}
argVars['cov_enable']       = {'s' : 'ce' , 'v' : 1,        'c' : [1],      'h' : "set to 1 to collect coverage (this has to be enabled if fuzzer should use coverage feedback)"}

argVars['debug_print']      = {'s' : 'dp' , 'v' : 0,        'c' : [0,1],    'h' : "set to 1 to enable debug print messages in the log file"}
argVars['force_delete']     = {'s' : 'fd' , 'v' : 0,        'c' : [0,1],    'h' : 'set to 1 to skip confirmation when deleting files & dirs (use with caution)'}

         




"""
- All variables below are developer options
"""

def vdb_cov_files(): return [f"{cov_type}.verilog.data.xml" for cov_type in cov_types]

def CORE(): 
    if core_name in opn_perifs:
        CORE_local = OPN_PERIF
        CORE_local.refresh(core_name)
    elif core_name in cal_perifs:
        CORE_local = CAL_PERIF
        CORE_local.refresh(core_name)
    else: 
        assert False, f"unknown core:{core_name} encountered"
    assert core_name == CORE_local.core_name, f"incorrect core config file imported, {core_name}, {CORE_local.core_name}"
    assert CORE_local.ready, f"core is not ready to run yet {CORE_local.ready}"

    return CORE_local

def core_instance_list(): 
    if core_name in opn_perifs:
        core_instance_list_local = globals()[f"{core_name}_inst_list"].l
    elif core_name in cal_perifs:
        core_instance_list_local = globals()[f"{core_name}_inst_list"].l
    else: 
        assert False, f"unknown core:{core_name} encountered"

    return core_instance_list_local

def pt():

    pt = {}

    pt['run_name'] = f"{core_name}_{run_mode}_{run_id}" 

    pt["root_dir"] = os.environ["IPFUZZ_ROOT"]

    pt["benchmarks_dir"]=os.path.join(pt["root_dir"] , "benchmarks/"        )
    pt["docs_dir"]     = os.path.join(pt["root_dir"] , "docs/"              )
    pt["utils_dir"]    = os.path.join(pt["root_dir"] , "utils/"             )
    pt["fuzz_dir"]     = os.path.join(pt["root_dir"] , "fuzz/"              )
    pt["outputs_dir"]  = os.path.join(pt["root_dir"] , "outputs/"           )
    pt["outputs_all_dir"]  = os.path.join(pt["root_dir"] , "outputs_all/"   )
    pt["input_seeds_dir"] = os.path.join(pt["root_dir"], "input_seeds/"     ) 
    pt["setup_scripts_dir"] = os.path.join(pt["root_dir"], "setup_scripts/" ) 

    if core_name in opn_perifs: 
        pt["sim_bash_file"] = os.path.join(pt["utils_dir"], f"vcs_run_opn_perif.bash")
    elif core_name in cal_perifs: 
        pt["sim_bash_file"] = os.path.join(pt["utils_dir"], f"vcs_run_cal_perif.bash")
    else: 
        pt["sim_bash_file"] = os.path.join(pt["utils_dir"], f"vcs_run_{core_name}.bash")
   
    pt["outputs_run_dir"]    = os.path.join(pt["outputs_dir"], pt['run_name'])
    pt["outputs_all_run_dir"]= os.path.join(pt["outputs_all_dir"], pt['run_name'])
    pt["trash_run_dir"]      = os.path.join(pt["outputs_all_dir"], f"trash_{pt['run_name']}/")


    pt["gen_progs_dir"]      = os.path.join(pt["outputs_run_dir"], "gen_progs")
    pt["sim_store_dir"]      = os.path.join(pt["outputs_all_run_dir"], "sim_out")
    pt["cov_store_dir"]      = os.path.join(pt["outputs_all_run_dir"], "cov_out")
    pt["all_progs_dir"]      = os.path.join(pt["outputs_run_dir"], "all_progs")
    pt["merged_cov_file"]    = os.path.join(pt["outputs_run_dir"], "merged_cov.json")
    pt["cov_log_file"]       = os.path.join(pt["outputs_run_dir"], "cov_log.jsonl")
    pt["inputs_log_file"]    = os.path.join(pt["outputs_run_dir"], "inputs_log.txt")
    pt["fuzz_log_file"]      = os.path.join(pt["outputs_run_dir"], "fuzz_log.txt")
    pt["cov_data_dict_file"] = os.path.join(pt["outputs_run_dir"], "cov_data_dict.json")
    pt["selected_inputs_dir"] = os.path.join(pt["outputs_run_dir"], "selected_inputs")
    pt["sanitizer_replay_inputs_dir"] = os.path.join(
        pt["outputs_run_dir"], "sanitizer_replay_inputs")

    pt['fuzzer_input_file_t']   = Template(f"ip_file_$fno.{CORE.pt['fuzzer_input_format']}")
    pt['fuzzer_input_file_re']  = rf"ip_file_(\d+).{CORE.pt['fuzzer_input_format']}"
    pt['trace_out_t'] = Template("rtl_trace_out_$fno.log")
    pt['trace_out_re']= r"rtl_trace_out_(\d+).log"
    pt['cov_out_t']   = Template("rtl_cov_out_$fno.json")

    pt['seed_input_file_re'] = r"[^\.]" + pt['fuzzer_input_file_re']

    return pt

all_cov_types           = ['line', 'branch', 'cond', 'fsm', 'tgl', 'assert', 'total']
val_muts                = [0,1,2,3,4,5,6,7]

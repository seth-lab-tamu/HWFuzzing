
import os
import types
from datetime import datetime
from string import Template
import config_cal as CAL
import config_opn as OPN
import cal_inst_list
import opn_inst_list


argVars = {}
argVars['core_name']        = {'s' : 'co' , 'v' : 'opn',    'c' : ['opn', 'cal'],   'h' : "select core(benchmark) to fuzz"}
argVars['perif_addresses']  = {'s' : 'pa' , 'l' : 'perif-addresses', 'v' : ['default'], 'c' : None, 'h' : "override peripheral base addresses"}
argVars['ipfuzz_handoff']   = {'s' : 'ifh', 'l' : 'ipfuzz-handoff', 'v' : 'ipfuzzer_output', 'c' : None, 'h' : "select an IPFuzz handoff directory relative to ipfuzzer"}
argVars['precompiled_fuzzitizer_seeds'] = {'s' : 'pfs', 'l' : 'precompiled-fuzzitizer-seeds', 'v' : '', 'c' : None, 'h' : "reuse compiled FUZZItizer seed programs from this directory instead of regenerating them from CSV inputs"}
argVars['peripheral_replay']= {'s' : 'pre', 'l' : 'peripheral-replay', 'v' : 'compressed-mmio', 'c' : ['compressed-mmio', 'direct-mmio', 'external-trigger-mmio', 'gap-mmio'], 'h' : "select historical, direct, external-trigger, or idle-gap-preserving peripheral input replay"}
argVars['run_id']           = {'s' : 'id' , 'v' : f"{datetime.now().strftime('%y_%m_%d_%H_%M_%S')}",  'c' : None, 'h' : "select run name to store results (uses current time by default)"}

argVars['run_mode']         = {'s' : 'rm' , 'v' : 'thehuzz','c' : ['fuzzitizer', 'thehuzz', 'random'], 'h' : "select FUZZItizer, TheHuzz, or Random Regression"}
argVars['max_fuzz_time']    = {'s' : 'mt' , 'v' : 259_200,  'c' : None,     'h' : "select max time to run (in seconds)"}
argVars['max_fuzz_progs']   = {'s' : 'mp' , 'v' : 5_000,  'c' : None,     'h' : "select max no. of testcases to run"}
argVars['random_seed']      = {'s' : 'rs' , 'v' : 0,        'c' : None,     'h' : "provide a integer as random seed to use. give 0 to generate seed randomly"}
argVars['debug_program_percent'] = {'s' : 'dpp', 'l' : 'debug-program-percent', 'v' : 10, 'c' : None, 'h' : "select percentage of programs that request debug or scan mode"}
argVars['target_cov']       = {'s' : 'tc' , 'v' : 100,      'c' : None,     'h' : "select coverage target (in percentage)"}
argVars['sim_batch_size']   = {'s' : 'sj' , 'v' : 10,       'c' : None,     'h' : "select number of testcases to simulate at once (recommended between 10 to 100)"}
argVars['syscall_prob']     = {'s' : 'sp' , 'v' : 90,       'c' : None,     'h' : "select percentage of times instructions should be syscalls"}
argVars['seed_gen_interval']= {'s' : 'sge', 'v' : 2000,     'c' : None,     'h' : "new seeds will be introduced after these many mutations to ensure fuzzer explores entire design"}
argVars['no_threads']       = {'s' : 'j'  , 'v' : 10,       'c' : None,     'h' : "select max no of threads to use (should not be greater than sim_batch_size)"}
argVars['num_times_to_mut'] = {'s' : 'mm' , 'v' : 10,       'c' : None,     'h' : "select max no of times testcases are mutated during fuzzing)"}
argVars['mutation_prob']    = {'s' : 'mupb','v' : 20,       'c' : None,     'h' : "select prob of mutating inputs"}
argVars['store_elf_file']   = {'s' : 'sfe', 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to store the generated elf files"}
argVars['store_trace_file'] = {'s' : 'sft', 'v' : 0,        'c' : [0,1],    'h' : "set to 1 to store the generated trace files"}
argVars['store_cov_file']   = {'s' : 'sfc', 'v' : 0,        'c' : [0,1],    'h' : "set to 1 to store coverage files (not needed for normal fuzzing; storing them reduces fuzzer speed)"}

argVars['start_type_cov']   = {'s' : 'stc', 'v' : 'new',                     'c' : ['new', 'continue'], 'h' : "select continue if fuzzer should continue using existing coverage, make sure to set the file path with -icf arg"}
argVars['input_cov_file']   = {'s' : 'icf', 'v' : '',                        'c' : None,                'h' : "set the full path for the json coverage dictionary file that fuzzer should continue using"}
argVars['cov_types']        = {'s' : 'ct' , 'v' : ['line', 'branch', 'cond', 'fsm', 'tgl', 'assert'], 'c' : None, 'h' : "select which coverage metrics to collect and use for results (available types: 'line', 'branch', 'cond', 'fsm', 'tgl', 'assert')"}
argVars['feedback_cov_types']={'s' : 'fct', 'v' : ['line', 'branch', 'cond', 'fsm', 'tgl'], 'c' : None, 'h' : "select which coverage metrics to use as feedback  (available types: 'line', 'branch', 'cond', 'fsm', 'tgl')"}
argVars['cov_enable']       = {'s' : 'ce' , 'v' : 1,        'c' : [1],      'h' : "set to 1 to collect coverage (this has to be enabled if fuzzer should use coverage feedback)"}

argVars['debug_print']      = {'s' : 'dp' , 'v' : 0,        'c' : [0,1],    'h' : "set to 1 to enable debug print messages in the log file"}
argVars['force_delete']     = {'s' : 'fd' , 'v' : 0,        'c' : [0,1],    'h' : 'set to 1 to skip confirmation when deleting files & dirs (use with caution)'}

argVars['prof_gen_progs']   = {'s' : 'pg' , 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to generate program files"}
argVars['prof_mut_progs']   = {'s' : 'pm' , 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to mutate program files"}
argVars['prof_run_progs']   = {'s' : 'pr' , 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to simulate program files"}
argVars['prof_merge_cov']   = {'s' : 'pmc', 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to merge cov and collect cov increments"}
argVars['prof_run_optimizer']={'s' : 'pro', 'v' : 1,        'c' : [0,1],    'h' : "set to 1 to run the optimizer"}
argVars['prof_check_prog_files'] = {'s' : 'pc', 'v' : 1,    'c' : [0,1],    'h' : "set to 1 to check if all prog files are generated correctly"} 


"""
- All variables below are developer options, edit with caution
"""

def vdb_cov_files(): return [f"{cov_type}.verilog.data.xml" for cov_type in cov_types]

def ipfuzz_output_dir():
    ipfuzz_root = os.path.realpath(
        os.path.join(os.environ["FUZZITIZER_ROOT"], "ipfuzzer")
    )
    candidate = os.path.realpath(os.path.join(ipfuzz_root, ipfuzz_handoff))
    try:
        contained = os.path.commonpath((ipfuzz_root, candidate)) == ipfuzz_root
    except ValueError:
        contained = False
    if not contained:
        raise ValueError(f"IPFuzz handoff resolves outside IPFuzz: {candidate}")
    return candidate

def CORE(): 
    core_configs = {'opn': OPN, 'cal': CAL}
    CORE_local = core_configs[core_name]
    if run_mode == 'fuzzitizer':
        configured_core = types.ModuleType(CORE_local.__name__)
        configured_core.__dict__.update(CORE_local.__dict__)
        CORE_local = configured_core
        CORE_local.peripheral_specs = CORE_local.get_peripheral_specs(
            ipfuzz_output_dir
        )
        CORE_local.perif_addresses = [
            spec["base_address"] for spec in CORE_local.peripheral_specs
        ]

    parsed_perif_addresses = None
    if perif_addresses != ['default']:
        parsed_perif_addresses = []
        for address in perif_addresses:
            try:
                parsed_address = int(address, 0)
            except ValueError as error:
                raise ValueError(f"invalid peripheral address: {address}") from error
            maximum_base = (2 ** CORE_local.mmio_address_bits) - 1 - 0x1000
            if (parsed_address < 0
                    or parsed_address % CORE_local.mmio_alignment != 0
                    or parsed_address > maximum_base):
                raise ValueError(f"invalid peripheral address: {address}")
            parsed_perif_addresses.append(parsed_address)

    if parsed_perif_addresses is not None:
        configured_core = types.ModuleType(CORE_local.__name__)
        configured_core.__dict__.update(CORE_local.__dict__)
        CORE_local = configured_core
        CORE_local.perif_addresses = parsed_perif_addresses
    assert core_name == CORE_local.core_name, f"incorrect core config file imported, {core_name}, {CORE_local.core_name}"
    assert CORE_local.ready, f"core is not ready to run yet {CORE_local.ready}"

    return CORE_local

def core_instance_list(): 
    return {'opn': opn_inst_list.l, 'cal': cal_inst_list.l}[core_name]

def pt():

    pt = {}

    pt['run_name'] = f"{core_name}_{run_mode}_{run_id}" 

    pt["root_dir"] = os.environ["FUZZITIZER_ROOT"]

    pt["benchmarks_dir"]=os.path.join(pt["root_dir"] , "benchmarks/"        )
    pt["utils_dir"]    = os.path.join(pt["root_dir"] , "utils/"             )
    pt["sw_dir"]       = os.path.join(pt["root_dir"] , "software/"          )
    pt["outputs_dir"]  = os.path.join(pt["root_dir"] , "outputs/"           )
    pt["outputs_all_dir"]  = os.path.join(pt["root_dir"] , "outputs_all/"   )
    pt["input_seeds_dir"] = os.path.join(pt["root_dir"], "input_seeds/"     ) 
    pt["ipfuzz_root"] = os.path.join(pt["root_dir"], "ipfuzzer")
    pt["ipfuzz_output_dir"] = ipfuzz_output_dir

    pt["opt_sol_file"] = os.path.join(pt["utils_dir"], f"cplex_cov_sol_{CORE.isa}.json")
    pt["sim_bash_file"] = os.path.join(pt["utils_dir"], f"vcs_run_{core_name}.bash")
   
    pt["sw_run_dir"] = os.path.join(pt["sw_dir"], CORE.isa, CORE.os)

    pt["outputs_run_dir"]    = os.path.join(pt["outputs_dir"], pt['run_name'])
    pt["outputs_all_run_dir"]= os.path.join(pt["outputs_all_dir"], pt['run_name'])
    pt["trash_run_dir"]      = os.path.join(pt["outputs_all_dir"], f"trash_{pt['run_name']}/")


    pt["gen_progs_dir"]      = os.path.join(pt["outputs_run_dir"], "gen_progs")
    pt["sim_store_dir"]      = os.path.join(pt["outputs_all_run_dir"], "sim_out")
    pt["cov_store_dir"]      = os.path.join(pt["outputs_all_run_dir"], "cov_out")
    pt["all_progs_dir"]      = os.path.join(pt["outputs_run_dir"], "all_progs")
    pt["merged_covs_dir"]    = os.path.join(pt["outputs_run_dir"], "merged_covs")
    pt["merged_cov_file"]    = os.path.join(pt["outputs_run_dir"], "merged_cov.json")
    pt["cov_log_file"]       = os.path.join(pt["outputs_run_dir"], "cov_log.jsonl")
    pt["inputs_log_file"]    = os.path.join(pt["outputs_run_dir"], "inputs_log.txt")
    pt["fuzz_log_file"]      = os.path.join(pt["outputs_run_dir"], "fuzz_log.txt")
    pt["cov_data_dict_file"] = os.path.join(pt["outputs_run_dir"], "cov_data_dict.json")
    pt["triage_dir"]         = os.path.join(pt["outputs_run_dir"], "triage")

    hex = CORE.pt['fuzzer_input_format']
    pt['hex_file_t']    = Template(f"inst_file_$fno.{hex}")
    pt['hex_file_re']   = rf"inst_file_(\d+).{hex}"
    pt['riscv_file_t']  = Template(f"inst_file_$fno.riscv")

    pt['trace_out_t'] = Template("rtl_trace_out_$fno.log")
    pt['trace_out_re']= r"rtl_trace_out_(\d+).log"
    pt['sim_out_t'] = Template("rtl_sim_out_$fno.log")
    pt['sim_out_re']= r"rtl_sim_out_(\d+).log"
    pt['cov_out_t']   = Template("rtl_cov_out_$fno.json")

    pt['hex_file_itr_t']  = Template(f"inst_file_$fno_itr_$itrno.{hex}")
    pt['hex_file_itr_re'] = rf"inst_file_(\d+)_itr_(\d+).{hex}"
    pt['hex_file_mut_t']  = Template(f"inst_file_${{file_no}}_itr_${{file_itr}}_mut_${{mut}}_inst_${{inst_no}}.{hex}")
    pt['hex_file_mut_re'] = rf"inst_file_(\d+)_itr_(\d+)_mut_(\d+)_inst_(\d+).{hex}"

    pt['seed_input_file_re'] = rf"[^\.](.*).{hex}"

    return pt

def config_check(): 
    assert syscall_prob <= CORE.max_syscall_prob, f"core should not have syscalls, {core_name}, {syscall_prob}, {CORE.max_syscall_prob}"
    if not 0 <= debug_program_percent <= 100:
        raise ValueError("debug program percentage must be between 0 and 100")
    if precompiled_fuzzitizer_seeds and run_mode != 'fuzzitizer':
        raise ValueError("precompiled FUZZItizer seeds require run mode fuzzitizer")

num_inst_in_prog_prof   = 20
num_itr_per_inst        = 8
num_inst_in_prog        = 1100
per_safe_insts_in_prog  = 50
num_nops_at_start       = 15
num_nops_at_end         = 15
all_cov_types           = ['line', 'branch', 'cond', 'fsm', 'tgl', 'assert', 'total']
val_muts                = [0,1,2,3,4,5,6,7]
opc_muts                = [8,9,10,11]
per_opc_muts            = 15

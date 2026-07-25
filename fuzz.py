"""
Created by: Rahul Kande
This is the main script to run the TheHuzz fuzzer
- Notes: 

- TODOs: 
    - Add pause/resume feature
"""

import subprocess, os, sys, re, shutil
import time, random, copy, datetime, math
import json, jsonlines
from string import Template
from tqdm import tqdm
import logging as lg # critical, error, warning, info, debug
import pandas as pd

import config
from configManager import getCONFIG
import prog_gen, riscv_isa, prog_mut, prog_sim, parse_cov, feedback, detect_bugs, plot_graphs
from riscv_isa import nop_inst_bin_32
import thehuzz_utils as TU


"""
Gets the optimal instruction-mutation pairs from the optimizer solution
"""
def get_sol(sol_file):
    sol = {}

    sol_file_p = open(sol_file, 'r')
    sol_data_json = json.load(sol_file_p)

    for variable in sol_data_json["CPLEXSolution"]["variables"]:
        if variable["value"] == '1.0':
            name_data = re.match('bool_([^"]*)_([0-9])', variable["name"])
            sol_opcode = name_data.group(1)
            sol_mut = int(name_data.group(2))
            if sol_opcode in sol: # opcode already there, append the mut type
                sol[sol_opcode].append(sol_mut)
            else:  # new opcode, create a new list with mut type
                sol[sol_opcode] = [sol_mut]

    return sol


"""
- Gets the optimizer solution with the optimal instruction-mutation pairs,
  and the opcodes to use for seed generation. 
- If we are running random regression, opcode list is all instructions and 
  first_opcode_list is empty (bcz we dont use first opcode list in case of random)
"""
def get_thehuzz_parameters(core, sol_file, run_mode, inst_list_all_w_ext):

    # if random, return all instructions
    if run_mode == 'random': 
        opcode_list = list(inst_list_all_w_ext.keys())

        return {}, [], opcode_list

    # get the solution from the optimizer
    if core in ['cva6']: # update the old format to the new one
        old_optimizer_sol = get_sol(sol_file)
        optimizer_sol = {}
        for opc,mut_list in old_optimizer_sol.items():
            for opc_ext in inst_list_all_w_ext:
                if opc == opc_ext[0]:
                    optimizer_sol[opc_ext[0] + "_" + opc_ext[1]] = mut_list

    else:
        optimizer_sol = get_sol(sol_file)

    # get the opcode lists
    opcode_list_temp = [sol for sol in optimizer_sol]
    opcode_list = [tuple(opc.split('_')) for opc in opcode_list_temp]
    first_opcode_list = []
    new_opcode_list = []
    for opcode in opcode_list:
        if not opcode in inst_list_all_w_ext.keys():
            continue
        if inst_list_all_w_ext[opcode][6] == '0':
            first_opcode_list.append(opcode)

        new_opcode_list.append(opcode)

    #print(optimizer_sol, len(optimizer_sol), '\n')
    #print(first_opcode_list, '\n')
    #print(opcode_list, '\n')

    return optimizer_sol, first_opcode_list, new_opcode_list


"""
Loads the core-specific NOP baseline coverage and derives coverage sizes.
"""
def load_noptest_cov(CONFIG_PT, core, cov_types):
    nop_cov_file = os.path.join(CONFIG_PT["root_dir"], "noptest", f"{core}_nop_cov.json")
    noptest_cmd = f"python3 fuzz.py -rm noptest -co {core} -sj 1 -j 1 -mp 1 -fd 1"
    assert os.path.exists(nop_cov_file), \
        f"Missing NOP coverage baseline '{nop_cov_file}'. Run '{noptest_cmd}' first."

    try:
        with open(nop_cov_file, 'r') as fp:
            nop_cov_dict = json.load(fp)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid NOP coverage baseline '{nop_cov_file}': {e}. Run '{noptest_cmd}' again.") from e

    assert isinstance(nop_cov_dict, dict), \
        f"NOP coverage baseline '{nop_cov_file}' must contain a JSON object. Run '{noptest_cmd}' again."

    for cov_type in cov_types:
        assert cov_type in nop_cov_dict, \
            f"NOP coverage baseline '{nop_cov_file}' is missing '{cov_type}'. Run '{noptest_cmd}' again."
        cov_str = nop_cov_dict[cov_type]
        assert isinstance(cov_str, str) and len(cov_str) > 0 and set(cov_str).issubset({'0', '1'}), \
            f"NOP coverage baseline '{nop_cov_file}' has invalid '{cov_type}' data. Run '{noptest_cmd}' again."

    nop_cov_dict = {cov_type: nop_cov_dict[cov_type] for cov_type in cov_types}
    cov_sizes = {cov_type: len(cov_str) for cov_type, cov_str in nop_cov_dict.items()}
    return nop_cov_dict, cov_sizes


"""
Simulates all the testcases in the testcases_to_sim array and returns a dictionary 
of coverage data for each simulation
"""
def sim_testcases(testcases_to_sim, testcase_ids, CONFIG_CORE_PT, CONFIG_EMU_PT, CONFIG_PT\
               , detecting_bugs, no_threads, core, *sim_xargs, return_cov=True):

    assert len(sim_xargs) == 8, f"incorrect simulation arguments: {sim_xargs}"

    store_trace_file, store_cov_file, tot_sim_time, cov_enable, cov_types, \
        vdb_cov_files, instance_list, emu_tot_sim_time = sim_xargs

    sim_files_to_save = {} # files to save
    # store trace file only if we cannot use custom path and user asks for it
    store_trace_file = (CONFIG_CORE_PT['trace_out_path_t'] != None) and store_trace_file
    store_emu_trace_file = (CONFIG_EMU_PT['trace_out_path_t'] != None) and detecting_bugs

    data_types = [('cov', store_cov_file), ('trace', store_trace_file)] 
    
    for data, store_en in data_types: 
        sim_files_to_save[data] = { 'en': store_en\
                , 'from': CONFIG_CORE_PT[f'{data}_out_path_t']\
                , 'to': Template(f"{CONFIG_PT['sim_store_dir']}/{CONFIG_PT[f'{data}_out_t'].template}") }

    # also add emu trace
    sim_files_to_save['emu_trace']=  {'en': store_emu_trace_file\
                , 'from': CONFIG_EMU_PT[f'trace_out_path_t']\
                , 'to': Template(f"{CONFIG_PT['sim_store_dir']}/{CONFIG_PT[f'emu_trace_out_t'].template}") }

    cov_data = prog_sim.sim_progs(testcases_to_sim, no_threads, testcase_ids \
            , core, tot_sim_time, cov_enable, cov_types, vdb_cov_files\
            , instance_list, CONFIG_PT["sim_bash_file"], CONFIG_CORE_PT, time.time()\
            , sim_files_to_save, detecting_bugs, CONFIG_PT["emu_bash_file"]\
            , CONFIG_EMU_PT, emu_tot_sim_time, return_cov)

    return cov_data


"""
This function mutates the testcases to generate new testcases
"""
def run_muts(testcases_to_mut, prog_mut_xargs, cb_vul_test=False):

    #mutate each of the program selected by the feedback engine
    mutation_prob = 100 #float(20) + float(80/num_progs_to_gen)
    progs_to_sim = []
    num_testcases_generated = 0
    core = prog_mut_xargs[-2]

    for testcase in testcases_to_mut:
        num_testcases_generated += len(testcase['new_hex_files'])
        for hex_file_out in testcase['new_hex_files']:
            prog_mut.mutate_prog(testcase['hex_file'], hex_file_out, mutation_prob\
                        , *prog_mut_xargs, 'optimizer')

            riscv_file_out = hex_file_out.replace('hex','riscv')
            TU.hex_to_riscv(hex_file_out, riscv_file_out)

    return num_testcases_generated


"""
"""
def get_merge_mode(run_mode): 
    if run_mode in ['thehuzz']: merge_mode = 'incremental'
    elif run_mode in ['random', 'noptest']: merge_mode = 'direct'
    elif run_mode in ['mabfuzz', 'refuzztest']: merge_mode = 'mab'
    else: assert 0, f"unknown run mode {run_mode}"
    return merge_mode


def _get_dict_entry(data_dict, key):
    if key in data_dict:
        return data_dict[key]
    str_key = str(key)
    if str_key in data_dict:
        return data_dict[str_key]
    return None


def _copy_or_create_test_artifacts(testcase, test_dir):
    os.makedirs(test_dir, exist_ok=True)

    src_hex_file = testcase['hex_file']
    src_riscv_file = testcase['riscv_file']
    dst_hex_file = os.path.join(test_dir, os.path.basename(src_hex_file))
    dst_riscv_file = os.path.join(test_dir, os.path.basename(src_riscv_file))

    if os.path.exists(src_hex_file):
        shutil.copyfile(src_hex_file, dst_hex_file)
    elif os.path.exists(src_riscv_file):
        TU.riscv_to_hex(src_riscv_file, dst_hex_file)
    else:
        assert False, f"missing interesting testcase hex/riscv files: {src_hex_file}, {src_riscv_file}"

    if os.path.exists(src_riscv_file):
        shutil.copyfile(src_riscv_file, dst_riscv_file)
    elif os.path.exists(src_hex_file):
        TU.hex_to_riscv(src_hex_file, dst_riscv_file)
    else:
        assert False, f"missing interesting testcase hex/riscv files: {src_hex_file}, {src_riscv_file}"


def store_interesting_tests(CONFIG_PT, testcases_to_sim, cov_data_dict, cov_increment_dict,
                            feedback_cov_types, collect_interesting_tests):
    if not collect_interesting_tests:
        return

    os.makedirs(CONFIG_PT['interesting_tests_dir'], exist_ok=True)

    interesting_cov_data = []
    for testcase in testcases_to_sim:
        testcase_id = testcase['id']
        cov_increment_data = _get_dict_entry(cov_increment_dict, testcase_id)
        if cov_increment_data is None:
            continue

        feedback_cov_incr = sum(cov_increment_data['incr'].get(cov_type, 0)
                                for cov_type in feedback_cov_types)
        if feedback_cov_incr <= 0:
            continue

        test_dir = os.path.join(CONFIG_PT['interesting_tests_dir'], f"test_{testcase_id}")
        _copy_or_create_test_artifacts(testcase, test_dir)

        test_cov_data = _get_dict_entry(cov_data_dict, testcase_id)
        assert test_cov_data is not None, f"missing coverage data for interesting testcase {testcase_id}"
        cov_out_file = os.path.join(test_dir, f"cov_out_{testcase_id}.json")
        with open(cov_out_file, 'w') as fp:
            json.dump(test_cov_data, fp, indent=2)

        interesting_cov_data.append(cov_increment_data)

    if interesting_cov_data:
        with jsonlines.open(CONFIG_PT['interesting_cov_log_file'], 'a') as fp:
            for cov_data in interesting_cov_data:
                fp.write(cov_data)


def _format_cov_sample_threshold(threshold):
    threshold = round(threshold, 5)
    if threshold == int(threshold):
        return f"{threshold:.1f}"
    return f"{threshold}".rstrip('0').rstrip('.')


def init_cov_sample_state(feedback_cov_types, cov_sample_interval, collect_cov_samples):
    if not collect_cov_samples:
        return None

    assert len(feedback_cov_types) == 1, \
        f"coverage sampling requires exactly one feedback coverage metric, got {feedback_cov_types}"
    cov_sample_interval = float(cov_sample_interval)
    assert cov_sample_interval > 0, f"cov_sample_interval must be > 0, got {cov_sample_interval}"

    return {
        'target_cov_metric': feedback_cov_types[0],
        'interval': cov_sample_interval,
        'next_threshold': None,
        'first_sample_done': False,
    }


def sample_target_cov(CONFIG_PT, merged_cov_dict, cov_sample_state, fuzz_time, testcase_id=None):
    if cov_sample_state is None:
        return

    target_cov_metric = cov_sample_state['target_cov_metric']
    assert target_cov_metric in merged_cov_dict, \
        f"target coverage metric {target_cov_metric} not found in merged coverage"

    target_cov_str = merged_cov_dict[target_cov_metric]
    total_points = len(target_cov_str)
    assert total_points > 0, f"target coverage metric {target_cov_metric} has no coverage points"

    covered_points = target_cov_str.count('1')
    actual_percent = round((covered_points / total_points) * 100, 5)
    sample_records = []

    if not cov_sample_state['first_sample_done']:
        cov_sample_state['next_threshold'] = round(
            math.floor(actual_percent / cov_sample_state['interval']) * cov_sample_state['interval'],
            5
        )
        cov_sample_state['first_sample_done'] = True

    while cov_sample_state['next_threshold'] > 0 \
       and cov_sample_state['next_threshold'] <= 100 \
       and actual_percent >= cov_sample_state['next_threshold']:
        threshold = round(cov_sample_state['next_threshold'], 5)
        threshold_str = _format_cov_sample_threshold(threshold)

        os.makedirs(CONFIG_PT['cov_samples_dir'], exist_ok=True)
        sample_file = os.path.join(CONFIG_PT['cov_samples_dir'], f"{threshold_str}_cov.json")
        with open(sample_file, 'w') as fp:
            json.dump(merged_cov_dict, fp, indent=2)

        sample_records.append({
            'metric': target_cov_metric,
            'threshold': threshold,
            'actual_percent': actual_percent,
            'time': fuzz_time.get_time(False),
            'id': testcase_id,
            'covered': covered_points,
            'total': total_points,
            'file': os.path.relpath(sample_file, CONFIG_PT['outputs_run_dir']),
        })
        cov_sample_state['next_threshold'] = round(
            cov_sample_state['next_threshold'] + cov_sample_state['interval'], 5
        )

    if sample_records:
        with jsonlines.open(CONFIG_PT['cov_samples_log_file'], 'a') as fp:
            for sample_record in sample_records:
                fp.write(sample_record)


"""
Main function that runs the fuzzer
- Fuzzer stops when timelimit, testcase limit, or coverage % limit is reached
"""
def run_thehuzz(fuzz_time, CONFIG_PT, CONFIG_CORE_PT, CONFIG_EMU_PT, run_mode\
              , start_type_cov, input_cov_file\
              , core, emu, max_fuzz_time, max_fuzz_progs, target_cov, sim_batch_size\
              , seed_gen_interval\
              , detecting_bugs, no_threads, store_elf_file\
              , num_times_to_mut, val_muts, opc_muts\
              , feedback_cov_types, prog_gen_xargs, prog_mut_xargs, prog_sim_xargs\
              , bug_detection_xargs, collect_interesting_tests, collect_cov_samples\
              , cov_sample_interval, debug_print): 

    #######################################
    ########### set variables  ############
    #######################################
    input_database = TU.DATABASE(core, CONFIG_PT['all_progs_dir']\
                               , CONFIG_PT['hex_file_t'], CONFIG_PT['bin_file_t']\
                               , CONFIG_PT['riscv_file_t'], run_mode) # database of input testcases
    tot_cov_points = None # total coverage points
    cov_per_ach    = 0 # percentage of coverage achieved so far 
    merged_cov_dict = None # merged coverage of all simulations
    inputs_log_file = CONFIG_PT['inputs_log_file']
    num_mutations_after_seed_gen = 0 # number of testcases generated since the
                                    # last time new seeds were added to database
    save_filetypes = ['riscv','hex'] if store_elf_file else ['hex']
    noptest_dir = os.path.join(CONFIG_PT['root_dir'], "noptest")
    noptest_cov_log_file = os.path.join(noptest_dir, f"{core}_cov_log.jsonl")
    noptest_cov_file = os.path.join(noptest_dir, f"{core}_nop_cov.json")
    cov_sample_state = init_cov_sample_state(feedback_cov_types, cov_sample_interval, collect_cov_samples)

    #######################################
    ######### get user input progs ########
    #######################################

    if run_mode == "noptest":
        noptest_hex_file = os.path.join(noptest_dir, "inst_nop_file_0.hex")
        noptest_riscv_file = os.path.join(noptest_dir, "inst_nop_file_0.riscv")
        assert os.path.exists(noptest_hex_file), f"missing noptest hex file: {noptest_hex_file}"
        assert os.path.exists(noptest_riscv_file), f"missing noptest riscv file: {noptest_riscv_file}"

        os.makedirs(CONFIG_PT['input_seeds_dir'], exist_ok=True)
        staged_hex_file = os.path.join(CONFIG_PT['input_seeds_dir'], "inst_nop_file_0.hex")
        staged_riscv_file = os.path.join(CONFIG_PT['input_seeds_dir'], "inst_nop_file_0.riscv")
        shutil.copyfile(noptest_hex_file, staged_hex_file)
        shutil.copyfile(noptest_riscv_file, staged_riscv_file)

        save_filetypes = ['riscv', 'hex']
        sim_batch_size = 1
        max_fuzz_progs = 1
        target_cov = max(target_cov, 100)


    TU.TIMELOG(fuzz_time, f" -- Loading input seeds (.hex format)", False, True) 
    if CONFIG_CORE_PT["input_format"] == 'riscv': # used for chipyard 1130
        CONFIG_PT['seed_input_file_re'] =  CONFIG_PT['seed_input_file_re'].replace("hex", "riscv")
    
    if run_mode == "noptest":
        input_test_files = [staged_riscv_file if CONFIG_CORE_PT["input_format"] == 'riscv' else staged_hex_file]
    else:
        input_test_files = TU.get_files_in_dir(CONFIG_PT['input_seeds_dir'], CONFIG_PT['seed_input_file_re'])
    input_database.add_testcases(input_test_files, save_filetypes)
    TU.log(inputs_log_file, f"Loaded {len(input_test_files)} input seeds | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
    TU.TIMELOG(fuzz_time, f" -- Loading input seeds", True, True)

    #######################################
    ############# load coverage ###########
    #######################################
    if start_type_cov == 'continue': 
        TU.TIMELOG(fuzz_time, f" -- Loading input coverage data from {input_cov_file} file", False, True)
        with open(input_cov_file, 'r') as fp: merged_cov_dict = json.load(fp)

        # update the log files
        cov_data_tot = parse_cov.full_cov_to_cov_num(merged_cov_dict)
        cov_data = { 'id': '', 'time': fuzz_time.get_time(False), 'incr': cov_data_tot, 'tot': cov_data_tot }
        with jsonlines.open(CONFIG.pt['cov_log_file'], 'a') as fp: fp.write(cov_data)
        TU.TIMELOG(fuzz_time, f" -- Loading input coverage data", True, True)

    #######################################
    ######### main loop of fuzzer #########
    #######################################
    while (fuzz_time.time_diff() < max_fuzz_time \
       and input_database.num_testcases_simulated() < max_fuzz_progs \
       and cov_per_ach < target_cov): # stopping condition of thehuzz 

        #######################################
        ############ seed generator ###########
        #######################################
        # find if there are enough testcases in database
        num_progs = sim_batch_size - input_database.num_new_testcases()
        if run_mode in ['thehuzz']: # inject seeds after regular intervals
            if num_mutations_after_seed_gen > seed_gen_interval: 
                num_progs = sim_batch_size
        
        if run_mode == "noptest":
            num_progs = 0
        
        # generate inputs if database doesnt have enough testcases
        if num_progs > 0:
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases")
            del_repo = 1 
            generated_test_files = prog_gen.gen_multi_prog(del_repo, run_mode, core\
                , no_threads, CONFIG_PT['gen_progs_dir'], CONFIG_PT['sw_run_dir']\
                , num_progs, prog_gen_xargs, CONFIG_PT['trash_run_dir'], debug_print)

            input_database.add_testcases(generated_test_files, save_filetypes)

            num_mutations_after_seed_gen = 0 # reset this as seeds are generated

            TU.log(inputs_log_file, f"Generated {num_progs} testcases | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases", True)

        
        #######################################
        ############ prog simulator ###########
        #######################################
        TU.TIMELOG(fuzz_time, f" -- Running simulations")
        testcases_to_sim = input_database.get_testcases_to_sim(sim_batch_size)
        files_to_sim = [i['riscv_file'] for i in testcases_to_sim]
        save_ids = [i['id'] for i in testcases_to_sim]
        cov_data_dict = sim_testcases(files_to_sim, save_ids\
               , CONFIG_CORE_PT, CONFIG_EMU_PT, CONFIG_PT\
               , detecting_bugs, no_threads, core, *prog_sim_xargs)
        TU.TIMELOG(fuzz_time, f" -- Running simulations", True)
        
        #######################################
        ########## feedback analysis ##########
        #######################################
        TU.TIMELOG(fuzz_time, f" -- Analyzing coverage data")
        # merge coverage 
        merge_mode = get_merge_mode(run_mode)
        pre_merge_cov_dict = dict(merged_cov_dict) if merged_cov_dict is not None else None
        merge_time = fuzz_time.get_time(False)
        merged_cov_dict, cov_increment_dict \
                    = parse_cov.merge_cov_dicts(cov_data_dict, 'dict', merge_mode\
                                    , merged_cov_dict, merge_time)

        # update the cov log file
        with jsonlines.open(CONFIG_PT['cov_log_file'], 'a') as fp: 
            for cov_data in cov_increment_dict.values(): fp.write(cov_data)
        interesting_cov_increment_dict = cov_increment_dict
        if collect_interesting_tests and merge_mode == 'direct':
            _, interesting_cov_increment_dict = parse_cov.merge_cov_dicts(
                cov_data_dict, 'dict', 'incremental', pre_merge_cov_dict, merge_time
            )
        store_interesting_tests(CONFIG_PT, testcases_to_sim, cov_data_dict, interesting_cov_increment_dict,
                                feedback_cov_types, collect_interesting_tests)
        sample_target_cov(CONFIG_PT, merged_cov_dict, cov_sample_state, fuzz_time, save_ids[-1])

        # coverage feedback
        if run_mode in ['thehuzz']: 
            testcases_to_mut, interesting_testcases, just_generated_testcases = \
                feedback.feedback_based_selection(input_database.num_new_testcases()\
                        , testcases_to_sim, cov_increment_dict, num_times_to_mut\
                        , feedback_cov_types)
            TU.log(inputs_log_file, f"Testcases to mutate: Interesting:{interesting_testcases} | Just generated: {just_generated_testcases}\n", fuzz_time)
        TU.TIMELOG(fuzz_time, f" -- Analyzing coverage data", True)

        print("\n\t\tMUTATION START\n")
        #######################################
        ############ prog mutation ############
        #######################################
        if run_mode in ['thehuzz']: 
            TU.TIMELOG(fuzz_time, f" -- Mutating testcases")
            testcases_to_mut = input_database.allocate_testcases_to_mut(testcases_to_mut)
            num_testcases_generated = run_muts(testcases_to_mut, prog_mut_xargs)
            num_mutations_after_seed_gen += num_testcases_generated
            TU.log(inputs_log_file, f"Mutation done | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
            TU.TIMELOG(fuzz_time, f" -- Mutating testcases", True)
        print("\n\t\tMUTATION END\n")

        #######################################
        ########## coverage achieved ##########
        #######################################
        if not tot_cov_points: 
            tot_cov_points = sum([len(cov_str) for cov_str in merged_cov_dict.values()]) 
        cov_points_ach = sum((parse_cov.full_cov_to_cov_num(merged_cov_dict)).values())
        cov_per_ach = round( (cov_points_ach / tot_cov_points)*100, 2 )
        TU.TIMELOG(fuzz_time, f" -- {input_database.num_testcases_simulated()} testcases, {cov_per_ach}% coverage achieved", False, True)

        if run_mode == "noptest":
            break

    #######################################
    ############ log statistics ###########
    #######################################
    if merged_cov_dict: 
        tot_cov = {key: len(cov_str) for key, cov_str in merged_cov_dict.items()}
        tot_cov['total'] = sum(tot_cov.values())
        ach_cov = parse_cov.full_cov_to_cov_num(merged_cov_dict, True)
        cov_per = round( (ach_cov['total'] / tot_cov['total'])*100, 2 )
    else:  # need to run atleast one simulation to get these stats
        tot_cov = {}
        ach_cov = {}
        cov_per = 0
    stats_string  = f"\n{'-'*60}\n"
    stats_string += f"  Benchmark              : {core}\n"
    stats_string += f"  Run time               : {fuzz_time.get_time(False)} sec\n"
    stats_string += f"  No. of testcases       : {input_database.num_testcases_simulated()}\n"
    stats_string += f"  No. of coverage points : {tot_cov}\n"
    stats_string += f"  No. of points covered  : {ach_cov}\n"
    stats_string += f"  % coverage achieved    : {cov_per}%\n"
    stats_string += f"{'-'*60}\n"
    TU.TIMELOG(fuzz_time, stats_string, False, True)
    # save fuzzer real end time
    TU.TIMELOG(prog_time, f" EndTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", False, True)


    # save final coverage
    if merged_cov_dict: 
        with open(CONFIG_PT['merged_cov_file'], 'w') as fp: json.dump(merged_cov_dict, fp, indent=2)
        if run_mode == "noptest":
            with open(noptest_cov_file, 'w') as fp: json.dump(merged_cov_dict, fp, indent=2)
            shutil.copyfile(CONFIG_PT['cov_log_file'], noptest_cov_log_file)

    #######################################
    ############ bug detection ############
    #######################################
    if detecting_bugs: 
        TU.TIMELOG(fuzz_time, f" Comparing traces to detect mismatches", False, True)
        detect_bugs.detect_mismatches(*bug_detection_xargs)
        TU.TIMELOG(fuzz_time, f" Comparing traces to detect mismatches", True, True)


"""
Deletes any previous log files and starts TheHuzz
"""
def main(prog_time): 

    bug_detection_xargs = [CONFIG.detecting_bugs_mode, CONFIG.detecting_bugs_file_nos\
                     , CONFIG.core_name, CONFIG.EMU.emu_name\
                     , CONFIG.ign_mm_after_first, CONFIG.ign_itr_mm\
                     , CONFIG.pt['mismatches_summary_file'] \
                     , CONFIG.no_threads\
                     , CONFIG.pt['sim_store_dir']\
                     , CONFIG.pt['sim_store_dir'],   CONFIG.pt['sim_store_dir']\
                     , CONFIG.pt['trace_out_re'],    CONFIG.pt['trace_out_t']\
                     , CONFIG.pt['emu_trace_out_t'], CONFIG.pt['comp_trace_out_t']]

    sheet_name = f'{CONFIG.run_mode}_{CONFIG.core_name}'
    cov_files = pd.DataFrame({CONFIG.pt['run_name']: [CONFIG.pt['cov_log_file'],sheet_name]}\
                            , index=['filename', 'sheet_name'])
    update_excel_xargs = [cov_files, CONFIG.all_cov_types, CONFIG.excel_file_path]


    excel_xargs = [CONFIG.core_name, CONFIG.excel_file_path, CONFIG.runs_to_plot\
                 , CONFIG.no_col_per_exp, CONFIG.graph_max_progs_to_plot, CONFIG.graph_max_time_to_plot]
    x_ranges = [0, 1201, 1000, 5000, 30001, 10000, 10000]  # no progs
                        # start of range1, stop of range1, step range1, start
                        # range2, stop range2, step range2, first tick for 2
    y_ranges = [0, 62, 20, 62, 71, 5, 65] # this y value is in percentage
                        # start of range1, stop of range1, step range1, start
                        # range2, stop range2, step range2, first tick for 2
    x_ranges = [0, 7*60*60, 5*60*60, 9*60*60, 72*60*60, 10*60*60, 10*60*60]  # time in sec
    y_ranges = [0, 62, 20, 62, 71, 5, 65] # this y value is in percentage
    y_label = "% H/W points covered"
    x_label = "# Programs (xK)" if CONFIG.graph_time_prog == 'prog' else "Time (hrs)"
    plot_xargs = dict(legend=True, x_ranges=x_ranges\
                    , y_ranges=y_ranges, x_label=x_label\
                    , y_label=y_label, plot_file_name=CONFIG.pt['graph_plot_file']\
                    , g_fsize=50, g_fsize_labels=60, width_ratio=[1,2], height_ratio=[2,1]\
                    , wspace=0.05, hspace=0.05, slash_width=0.02\
                    , have_grid=True, legend_ncol=1)
    plot_graph_xargs = [excel_xargs, CONFIG.cov_type_to_plot, CONFIG.all_cov_types\
                      , CONFIG.graph_prog_step, CONFIG.graph_time_step\
                      , CONFIG.pt['graph_ref_cov_dict_file']\
                      , CONFIG.graph_time_prog, CONFIG.graph_in_percent\
                      , CONFIG.graph_prog_tick, CONFIG.graph_time_tick, plot_xargs]

    #######################################
    # Sub-features of TheHuzz like doing only bug detection, generating plots, etc
    #######################################
    if CONFIG.run_task == 'check_mismatches': # not running fuzzer, only doing mismatch comparison
        TU.TIMELOG(prog_time, f" Comparing traces to detect mismatches", False, True, False)
        detect_bugs.detect_mismatches(*bug_detection_xargs)
        TU.TIMELOG(prog_time, f" Comparing traces to detect mismatches", True, True, False)
        return

    elif CONFIG.run_task == 'update_excel': # update the excel file with cov data
        TU.TIMELOG(prog_time, f" Updating the excel data file", False, True, False)
        plot_graphs.update_excel_file(*update_excel_xargs)
        TU.TIMELOG(prog_time, f" Updating the excel data file", True, True, False)
        return

    elif CONFIG.run_task == 'plot_graph': # generate the cov plot
        TU.TIMELOG(prog_time, f" Generating the results plot", False, True, False)
        plot_graphs.gen_prog_vs_cov_plot(*plot_graph_xargs)
        TU.TIMELOG(prog_time, f" Generating the results plot", True, True, False)
        return

    #######################################
    # Prepare the environment and run the fuzzer
    #######################################
    print(f"[-------] Deleting previous log files")
    TU.delete_dir(CONFIG.pt['outputs_run_dir'], CONFIG.force_delete) 
    TU.delete_dir(CONFIG.pt['outputs_all_run_dir'], CONFIG.force_delete) 
    TU.delete_dir(CONFIG.pt['trash_run_dir'], CONFIG.force_delete) 
    subprocess.call([ 'mkdir', CONFIG.pt['all_progs_dir'] ])
    subprocess.call([ 'mkdir', CONFIG.pt['sim_store_dir'] ])
    print(f"[-------] Deleting previous log files done")

    
    print(f"[-------] Setup simulation repositories")
    sim_dirs = [CONFIG.CORE.pt['sim_dir_t'].substitute(tno=i) for i in range(CONFIG.no_threads)]
    assert os.path.isdir(CONFIG.CORE.pt['sim_dir_t'].substitute(tno=0))\
                        , f"no simulation repos found: {CONFIG.CORE.pt['sim_dir_t'].template}"
    repos_to_create = [repo for repo in sim_dirs if not os.path.isdir(repo)]
    for repo in tqdm(repos_to_create, desc="[-------] creating simulation repositories"): 
        subprocess.call([ 'cp', '-r', CONFIG.CORE.pt['sim_dir_t'].substitute(tno=0), repo ])
    print(f"[-------] Setup simulation repositories done")

    prog_time.reset_start_time() # count time only after deleting previous logs

    # set the log file
    debug_level = lg.DEBUG if CONFIG.debug_print else lg.INFO 
    lg.basicConfig(filename=CONFIG.pt['fuzz_log_file'], filemode='w', level=debug_level)

    # save fuzzer real start time
    TU.TIMELOG(prog_time, f" StartTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", False, False, True)

    # set and record the seed for this run
    seed = CONFIG.random_seed
    seed = random.randrange(sys.maxsize) if seed == 0 else seed
    random.seed(seed)
    TU.TIMELOG(prog_time, f" RandomSeed: {seed}", False, False, True)

    # save input args to log file
    arg_dict = {arg: CONFIG.__dict__[arg] for arg in CONFIG.argVars.keys()}
    TU.TIMELOG(prog_time, json.dumps(arg_dict, indent=2), False, False, True)

    TU.TIMELOG(prog_time, f" Getting the parameters for the fuzzer", False, True)
    optimizer_sol, first_opcode_list, opcode_list = get_thehuzz_parameters(CONFIG.core_name\
                , CONFIG.pt['opt_sol_file'], CONFIG.run_mode, CONFIG.inst_list_all_w_ext)
    TU.TIMELOG(prog_time, f" Getting the parameters for the fuzzer", True, True)

    if CONFIG.run_mode == 'thehuzz': 
        TU.TIMELOG(prog_time, f" Running TheHuzz on given benchmark, {CONFIG.core_name}", False, True)
    elif CONFIG.run_mode == 'random': 
        TU.TIMELOG(prog_time, f" Running TheHuzz as random regression on given benchmark, {CONFIG.core_name}", False, True)
    elif CONFIG.run_mode == 'noptest':
        TU.TIMELOG(prog_time, f" Running NOP coverage baseline on given benchmark, {CONFIG.core_name}", False, True)
    elif CONFIG.run_mode == 'refuzztest': 
        TU.TIMELOG(prog_time, f" Running ReFuzz Testing on given benchmark, {CONFIG.core_name}", False, True)
    else: 
        assert 0, f"running thehuzz in incorrect mode, {CONFIG.run_mode}. If you are trying to do profiling, run the profiler script"
  
    prog_gen_xargs = [CONFIG.num_inst_in_prog,  opcode_list, CONFIG.inst_list_all_w_ext\
                    , CONFIG.num_nops_at_start, CONFIG.num_nops_at_end\
                    , first_opcode_list, CONFIG.core_name]

    prog_mut_xargs = [optimizer_sol, nop_inst_bin_32, CONFIG.inst_list_all_w_ext\
                    , CONFIG.val_muts, CONFIG.opc_muts, CONFIG.num_nops_at_start\
                    , CONFIG.num_nops_at_end, CONFIG.core_name, CONFIG.CORE.os]

    prog_sim_xargs = [CONFIG.store_trace_file,    CONFIG.store_cov_file\
                    , CONFIG.CORE.tot_sim_time,   CONFIG.cov_enable\
                    , CONFIG.cov_types,           CONFIG.vdb_cov_files\
                    , CONFIG.core_instance_list,  CONFIG.EMU.tot_sim_time]

    if CONFIG.run_mode in ['thehuzz', 'random', 'noptest']:
        run_thehuzz(prog_time, CONFIG.pt, CONFIG.CORE.pt, CONFIG.EMU.pt, CONFIG.run_mode\
                  , CONFIG.start_type_cov, CONFIG.input_cov_file\
                  , CONFIG.core_name,           CONFIG.EMU.emu_name,    CONFIG.max_fuzz_time\
                  , CONFIG.max_fuzz_progs,      CONFIG.target_cov,      CONFIG.sim_batch_size\
                  , CONFIG.seed_gen_interval\
                  , CONFIG.detecting_bugs,      CONFIG.no_threads,      CONFIG.store_elf_file\
                  , CONFIG.num_times_to_mut,    CONFIG.val_muts,        CONFIG.opc_muts\
                  , CONFIG.feedback_cov_types\
                  , prog_gen_xargs,             prog_mut_xargs,         prog_sim_xargs\
                  , bug_detection_xargs, CONFIG.collect_interesting_tests\
                  , CONFIG.collect_cov_samples, CONFIG.cov_sample_interval, CONFIG.debug_print)
    elif CONFIG.run_mode in ['refuzztest']:
        from refuzz.refuzztest import run_refuzz
        nop_cov_dict, nop_cov_sizes = load_noptest_cov(CONFIG.pt, CONFIG.core_name, CONFIG.cov_types)
        TU.TIMELOG(prog_time, f" Loaded NOP coverage baseline sizes: {nop_cov_sizes}", False, True)
        run_refuzz(prog_time, CONFIG.pt, CONFIG.CORE.pt, CONFIG.EMU.pt, CONFIG.run_mode\
                  , CONFIG.core_name,           CONFIG.EMU.emu_name,    CONFIG.max_fuzz_time\
                  , CONFIG.max_fuzz_progs,      CONFIG.target_cov,      CONFIG.sim_batch_size\
                  , CONFIG.seed_gen_interval\
                  , CONFIG.detecting_bugs,      CONFIG.no_threads,      CONFIG.store_elf_file\
                  , CONFIG.num_times_to_mut,    CONFIG.val_muts,        CONFIG.opc_muts\
                  , CONFIG.feedback_cov_types\
                  , CONFIG.mab_algo, CONFIG.mab_num_seed_arms, CONFIG.mab_n_picks_reset \
                  , CONFIG.refuzz_train_source, CONFIG.training_processors, CONFIG.cb_vul, CONFIG.all_cov_types \
                  , prog_gen_xargs,             prog_mut_xargs,         prog_sim_xargs\
                  , bug_detection_xargs, nop_cov_dict, CONFIG.collect_interesting_tests\
                  , CONFIG.collect_cov_samples, CONFIG.cov_sample_interval, CONFIG.debug_print)


    TU.TIMELOG(prog_time, f" Running {CONFIG.run_mode} on given benchmark, {CONFIG.core_name} done", False, True)


if __name__ == '__main__': 

    # custom time object
    prog_time = TU.Mytime()

    # get variables from config file or dict, and update any present in args
    CONFIG = getCONFIG(config, configType='file')
   
    # uncomment the line below to see all the config variables
    #print(CONFIG.printConfig(CONFIG)); exit()

    main(prog_time)

"""Run FUZZItizer full-SoC fuzzing campaigns."""

import subprocess, os, sys, re
import random, datetime
import json, jsonlines
from pathlib import Path
from string import Template
import logging as lg # critical, error, warning, info, debug

from path_setup import configure_project_paths

FUZZITIZER_ROOT = configure_project_paths()

import config
from configManager import getCONFIG
import prog_gen, prog_mut, prog_sim, parse_cov, feedback
import soc_violation_triage
from riscv_isa import inst_list_all_w_ext, nop_inst_bin_32
import fuzz_utils as TU
from ipfuzz_handoff import loadselectedinputs


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


def get_fuzzing_parameters(core, sol_file, run_mode, inst_list_all_w_ext):

    if core not in ('opn', 'cal'):
        raise ValueError(f"unsupported core: {core}")

    if run_mode == 'random': 
        opcode_list = list(inst_list_all_w_ext.keys())

        return {}, [], opcode_list

    optimizer_sol = get_sol(sol_file)
    allowed_optimizer_names = {"_".join(opcode) for opcode in inst_list_all_w_ext}
    optimizer_sol = {
        name: mutations
        for name, mutations in optimizer_sol.items()
        if name in allowed_optimizer_names
    }

    opcode_list_temp = [sol for sol in optimizer_sol]
    opcode_list = [tuple(opc.split('_')) for opc in opcode_list_temp]
    first_opcode_list = []
    for opcode in opcode_list:
        if inst_list_all_w_ext[opcode][6] == '0':
            first_opcode_list.append(opcode)

    return optimizer_sol, first_opcode_list, opcode_list


def sim_testcases(testcases_to_sim, testcase_ids, CONFIG_CORE_PT, CONFIG_PT\
               , no_threads, core\
               , store_trace_file, store_cov_file, tot_sim_time, cov_enable\
               , cov_types, vdb_cov_files, instance_list, return_cov=True):

    sim_files_to_save = {}
    move_trace_file = (CONFIG_CORE_PT['trace_out_path_t'] != None) and store_trace_file
    store_sim_file = True

    data_types = [('cov', False), ('trace', move_trace_file), ('sim', store_sim_file)]
    for data, store_en in data_types: 
        sim_files_to_save[data] = { 'en': store_en\
                , 'from': CONFIG_CORE_PT[f'{data}_out_path_t']\
                , 'to': Template(f"{CONFIG_PT['sim_store_dir']}/{CONFIG_PT[f'{data}_out_t'].template}") }

    cov_data = prog_sim.sim_progs(testcases_to_sim, no_threads, testcase_ids \
            , core, tot_sim_time, cov_enable, cov_types, vdb_cov_files\
            , instance_list, CONFIG_PT["sim_bash_file"], CONFIG_CORE_PT\
            , sim_files_to_save, return_cov)

    return cov_data


def run_muts(testcases_to_mut, prog_mut_xargs):

    num_testcases_generated = 0

    for testcase in testcases_to_mut:
        num_testcases_generated += len(testcase['new_hex_files'])
        for hex_file_out in testcase['new_hex_files']:
            prog_mut.mutate_prog(testcase['hex_file'], hex_file_out\
                        , *prog_mut_xargs)

    return num_testcases_generated


def runtriage(config_object):
    if config_object.run_mode != "fuzzitizer":
        return None
    return soc_violation_triage.triagerun(
        config_object.pt["ipfuzz_output_dir"],
        config_object.pt["ipfuzz_root"],
        config_object.pt["sim_store_dir"],
        config_object.core_name,
        config_object.pt["triage_dir"],
    )


def get_merge_mode(run_mode): 
    if run_mode in ['fuzzitizer', 'thehuzz']: merge_mode = 'incremental'
    elif run_mode == 'random': merge_mode = 'direct'
    else: assert 0, f"unknown run mode {run_mode}"
    return merge_mode


def loadinputseeds(
    config_paths,
    run_mode,
    core,
    peripheral_specs,
    precompiled_fuzzitizer_seeds="",
):
    if run_mode in ("thehuzz", "random"):
        return TU.get_files_in_dir(
            config_paths["input_seeds_dir"],
            config_paths["seed_input_file_re"],
        )
    if run_mode == "fuzzitizer":
        if precompiled_fuzzitizer_seeds:
            seed_dir = Path(precompiled_fuzzitizer_seeds)
            if not seed_dir.is_dir():
                raise ValueError(
                    f"precompiled FUZZItizer seed directory does not exist: {seed_dir}"
                )
            seeds = TU.get_files_in_dir(
                seed_dir,
                config_paths["seed_input_file_re"],
            )
            if not seeds:
                raise ValueError(
                    f"precompiled FUZZItizer seed directory contains no seeds: {seed_dir}"
                )
            return seeds
        return loadselectedinputs(
            Path(config_paths["ipfuzz_output_dir"]),
            Path(config_paths["ipfuzz_root"]),
            core,
            [spec["identifier"] for spec in peripheral_specs],
        )
    raise ValueError(f"unsupported run mode: {run_mode}")


def run_fuzzer(fuzz_time, CONFIG_PT, CONFIG_CORE_PT, run_mode, peripheral_replay\
              , start_type_cov, input_cov_file\
              , core, peripheral_specs, max_fuzz_time, max_fuzz_progs, target_cov, sim_batch_size\
              , seed_gen_interval\
              , no_threads, store_elf_file\
              , num_times_to_mut, val_muts, opc_muts\
              , feedback_cov_types, prog_gen_xargs, prog_mut_xargs, prog_sim_xargs\
              , store_cov_file, debug_print, precompiled_fuzzitizer_seeds=""):

    input_database = TU.DATABASE(CONFIG_PT['all_progs_dir']\
                            , CONFIG_PT['hex_file_t']) # database of input testcases
    tot_cov_points = None # total coverage points
    cov_per_ach    = 0 # percentage of coverage achieved so far 
    merged_cov_dict = None # merged coverage of all simulations
    inputs_log_file = CONFIG_PT['inputs_log_file']
    num_mutations_after_seed_gen = 0
    save_filetypes = ['riscv'] if store_elf_file else [] 

    input_test_files = loadinputseeds(
        CONFIG_PT,
        run_mode,
        core,
        peripheral_specs,
        precompiled_fuzzitizer_seeds,
    )

    if run_mode in ('thehuzz', 'random') or precompiled_fuzzitizer_seeds:
        TU.TIMELOG(fuzz_time, f" -- Loading compiled input seeds", False, True)
        input_database.add_testcases(input_test_files, save_filetypes)
        TU.TIMELOG(fuzz_time, f" -- Loading compiled input seeds", True, True)
    elif run_mode == 'fuzzitizer':
        TU.TIMELOG(fuzz_time, " -- Loading interesting peripheral inputs (.csv format)", False, True)
        del_repo = 1
        generated_test_files = prog_gen.gen_multi_prog(del_repo, 'gen1'\
            , no_threads, CONFIG_PT['gen_progs_dir'], CONFIG_PT['sw_run_dir']\
            , len(input_test_files), prog_gen_xargs, CONFIG_CORE_PT['fuzzer_input_format']\
            , CONFIG_PT['trash_run_dir'], debug_print, input_test_files)
        input_database.add_testcases(generated_test_files, save_filetypes)
        TU.TIMELOG(fuzz_time, " -- Loading interesting peripheral inputs", True, True)

    TU.log(inputs_log_file, f"Loaded {len(input_test_files)} input seeds | Total testcases = {input_database.num_testcases()}\n", fuzz_time)

    if start_type_cov == 'continue': 
        TU.TIMELOG(fuzz_time, f" -- Loading input coverage data from {input_cov_file} file", False, True)
        with open(input_cov_file, 'r') as fp: merged_cov_dict = json.load(fp)

        # update the log files
        cov_data_tot = parse_cov.full_cov_to_cov_num(merged_cov_dict)
        cov_data = { 'id': '', 'time': fuzz_time.get_time(False), 'incr': cov_data_tot, 'tot': cov_data_tot }
        with jsonlines.open(CONFIG.pt['cov_log_file'], 'a') as fp: fp.write(cov_data)
        TU.TIMELOG(fuzz_time, f" -- Loading input coverage data", True, True)

    while (fuzz_time.time_diff() < max_fuzz_time \
       and input_database.num_testcases_simulated() < max_fuzz_progs \
       and cov_per_ach < target_cov): # stopping condition of the fuzzer

        # find if there are enough testcases in database
        num_progs = sim_batch_size - input_database.num_new_testcases()
        if run_mode in ['fuzzitizer', 'thehuzz']: # inject seeds after regular intervals
            if num_mutations_after_seed_gen > seed_gen_interval: 
                num_progs = sim_batch_size
        save_filetypes = ['riscv'] if store_elf_file else [] 
        
        # generate inputs if database doesnt have enough testcases
        if num_progs > 0:
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases")
            del_repo = 1 
            generated_test_files = prog_gen.gen_multi_prog(del_repo, run_mode\
                , no_threads, CONFIG_PT['gen_progs_dir'], CONFIG_PT['sw_run_dir']\
                , num_progs, prog_gen_xargs, CONFIG_CORE_PT['fuzzer_input_format']\
                , CONFIG_PT['trash_run_dir'], debug_print)

            input_database.add_testcases(generated_test_files, save_filetypes)

            num_mutations_after_seed_gen = 0 # reset this as seeds are generated

            TU.log(inputs_log_file, f"Generated {num_progs} testcases | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases", True)

        TU.TIMELOG(fuzz_time, f" -- Running simulations")
        testcases_to_sim = input_database.get_testcases_to_sim(sim_batch_size)
        files_to_sim = [i['hex_file'] for i in testcases_to_sim]
        save_ids = [i['id'] for i in testcases_to_sim]
        cov_data_dict = sim_testcases(files_to_sim, save_ids\
               , CONFIG_CORE_PT, CONFIG_PT\
               , no_threads, core, *prog_sim_xargs)
        TU.TIMELOG(fuzz_time, f" -- Running simulations", True)

        TU.TIMELOG(fuzz_time, f" -- Analyzing coverage data")
        # merge coverage 
        merge_mode = get_merge_mode(run_mode)
        merged_cov_dict, cov_increment_dict \
                    = parse_cov.merge_cov_dicts(cov_data_dict, 'dict', merge_mode\
                                    , merged_cov_dict, fuzz_time.get_time(False))

        # update the cov log file
        with jsonlines.open(CONFIG.pt['cov_log_file'], 'a') as fp: 
            for cov_data in cov_increment_dict.values(): fp.write(cov_data)

        # coverage feedback
        if run_mode in ['fuzzitizer', 'thehuzz']:
            testcases_to_mut, interesting_testcases, just_generated_testcases = \
                feedback.feedback_based_selection(input_database.num_new_testcases()\
                        , testcases_to_sim, cov_increment_dict, num_times_to_mut\
                        , feedback_cov_types)
            TU.log(inputs_log_file, f"Testcases to mutate: Interesting:{interesting_testcases} | Just generated: {just_generated_testcases}\n", fuzz_time)
        TU.TIMELOG(fuzz_time, f" -- Analyzing coverage data", True)

        if run_mode in ['fuzzitizer', 'thehuzz']:
            TU.TIMELOG(fuzz_time, f" -- Mutating testcases")
            testcases_to_mut = input_database.allocate_testcases_to_mut(testcases_to_mut)
            num_testcases_generated = run_muts(testcases_to_mut, prog_mut_xargs)
            num_mutations_after_seed_gen += num_testcases_generated
            TU.log(inputs_log_file, f"Mutation done | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
            TU.TIMELOG(fuzz_time, f" -- Mutating testcases", True)

        if not tot_cov_points: 
            tot_cov_points = sum([len(cov_str) for cov_str in merged_cov_dict.values()]) 
        cov_points_ach = sum((parse_cov.full_cov_to_cov_num(merged_cov_dict)).values())
        cov_per_ach = round( (cov_points_ach / tot_cov_points)*100, 2 )
        TU.TIMELOG(fuzz_time, f" -- {input_database.num_testcases_simulated()} testcases, {cov_per_ach}% coverage achieved", False, True)


        if store_cov_file: 
          latest_sim_test = str(max([int(i['id']) for i in cov_increment_dict.values()]))
          store_file = os.path.join(CONFIG_PT['cov_store_dir'], CONFIG_PT['cov_out_t'].substitute(fno=latest_sim_test))
          with open(store_file, 'w') as fp: json.dump(merged_cov_dict, fp, indent=2)


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
    TU.TIMELOG(prog_time, f" EndTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", False, True)

    if merged_cov_dict: 
        with open(CONFIG_PT['merged_cov_file'], 'w') as fp: json.dump(merged_cov_dict, fp, indent=2)

"""
Deletes any previous log files and starts the requested fuzzing campaign
"""
def main(prog_time): 
    print(f"[-------] Deleting previous log files")
    TU.delete_dir(CONFIG.pt['outputs_run_dir'], CONFIG.force_delete) 
    TU.delete_dir(CONFIG.pt['outputs_all_run_dir'], CONFIG.force_delete) 
    TU.delete_dir(CONFIG.pt['trash_run_dir'], CONFIG.force_delete) 
    subprocess.call([ 'mkdir', CONFIG.pt['all_progs_dir'] ])
    subprocess.call([ 'mkdir', CONFIG.pt['sim_store_dir'] ])
    subprocess.call([ 'mkdir', CONFIG.pt['cov_store_dir'] ])
    print(f"[-------] Deleting previous log files done")

    
    print(f"[-------] Setup simulation repositories")
    TU.setup_simulation_repos(CONFIG.CORE.pt['sim_dir_t'], CONFIG.no_threads)
    print(f"[-------] Setup simulation repositories done")

    prog_time.reset_start_time() # count time only after deleting previous logs

    debug_level = lg.DEBUG if CONFIG.debug_print else lg.INFO 
    lg.basicConfig(filename=CONFIG.pt['fuzz_log_file'], filemode='w', level=debug_level)

    TU.TIMELOG(prog_time, f" StartTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", False, False, True)

    seed = CONFIG.random_seed
    seed = random.randrange(sys.maxsize) if seed == 0 else seed
    random.seed(seed)
    TU.TIMELOG(prog_time, f" RandomSeed: {seed}", False, False, True)

    arg_dict = {arg: CONFIG.__dict__[arg] for arg in CONFIG.argVars.keys()}
    TU.TIMELOG(prog_time, json.dumps(arg_dict, indent=2), False, False, True)

    TU.TIMELOG(prog_time, f" Getting the parameters for the fuzzer", False, True)
    target_inst_list = prog_gen.instructions_for_xlen(
        inst_list_all_w_ext, CONFIG.CORE.instruction_xlen
    )
    optimizer_sol, first_opcode_list, opcode_list = get_fuzzing_parameters(CONFIG.core_name\
                , CONFIG.pt['opt_sol_file'], CONFIG.run_mode, target_inst_list)
    TU.TIMELOG(prog_time, f" Getting the parameters for the fuzzer", True, True)

    if CONFIG.run_mode == 'fuzzitizer':
        TU.TIMELOG(prog_time, f" Running FUZZItizer on benchmark, {CONFIG.core_name}", False, True)
    elif CONFIG.run_mode == 'thehuzz':
        TU.TIMELOG(prog_time, f" Running coverage-guided fuzzing on benchmark, {CONFIG.core_name}", False, True)
    elif CONFIG.run_mode == 'random': 
        TU.TIMELOG(prog_time, f" Running Random Regression on benchmark, {CONFIG.core_name}", False, True)
    else: 
        assert 0, f"unsupported fuzzing run mode, {CONFIG.run_mode}. If you are trying to do profiling, run the profiler script"
  
    prog_gen_xargs = [CONFIG.num_inst_in_prog,  opcode_list, target_inst_list\
                    , CONFIG.num_nops_at_start, CONFIG.num_nops_at_end\
                    , first_opcode_list, CONFIG.syscall_prob\
                    , CONFIG.CORE.max_syscall_prob, CONFIG.CORE.os\
                    , CONFIG.CORE.syscall_ids, CONFIG.CORE.perif_addresses\
                    , CONFIG.per_safe_insts_in_prog, CONFIG.CORE.peripheral_specs\
                    , CONFIG.CORE.mmio_settings, CONFIG.CORE.allow_privilege_switch\
                    , CONFIG.CORE.emit_initial_mmio_store, CONFIG.peripheral_replay\
                    , CONFIG.debug_program_percent]

    prog_mut_xargs = [CONFIG.mutation_prob, optimizer_sol, nop_inst_bin_32, target_inst_list\
                    , CONFIG.val_muts, CONFIG.opc_muts, CONFIG.num_nops_at_start\
                    , CONFIG.num_nops_at_end, CONFIG.per_opc_muts]

    prog_sim_xargs = [CONFIG.store_trace_file,    CONFIG.store_cov_file\
                    , CONFIG.CORE.tot_sim_time,   CONFIG.cov_enable\
                    , CONFIG.cov_types,           CONFIG.vdb_cov_files\
                    , CONFIG.core_instance_list]

    run_fuzzer(prog_time, CONFIG.pt, CONFIG.CORE.pt, CONFIG.run_mode\
              , CONFIG.peripheral_replay\
              , CONFIG.start_type_cov, CONFIG.input_cov_file\
              , CONFIG.core_name,           CONFIG.CORE.peripheral_specs\
              , CONFIG.max_fuzz_time\
              , CONFIG.max_fuzz_progs,      CONFIG.target_cov,      CONFIG.sim_batch_size\
              , CONFIG.seed_gen_interval\
              , CONFIG.no_threads,          CONFIG.store_elf_file\
              , CONFIG.num_times_to_mut,    CONFIG.val_muts,        CONFIG.opc_muts\
              , CONFIG.feedback_cov_types\
              , prog_gen_xargs,             prog_mut_xargs,         prog_sim_xargs\
              , CONFIG.store_cov_file\
              , CONFIG.debug_print\
              , CONFIG.precompiled_fuzzitizer_seeds)

    runtriage(CONFIG)

    TU.TIMELOG(prog_time, f" Fuzzing benchmark, {CONFIG.core_name} done", False, True)




if __name__ == '__main__': 

    prog_time = TU.Mytime()

    CONFIG = getCONFIG(config, configType='file')
   
    main(prog_time)


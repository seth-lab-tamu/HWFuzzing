"""
Created by: Rahul Kande
This is the main script to run the TheHuzz fuzzer
- Notes: 

- TODOs: 
    - Add pause/resume feature
"""

import subprocess, os, sys, re
import time, random, copy, datetime
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
Simulates all the testcases in the testcases_to_sim array and returns a dictionary 
of coverage data for each simulation
"""
def sim_testcases(testcases_to_sim, testcase_ids, CONFIG_CORE_PT, CONFIG_EMU_PT, CONFIG_PT\
               , detecting_bugs, no_threads, core\
               , store_trace_file, store_cov_file, tot_sim_time, cov_enable\
               , cov_types, vdb_cov_files, instance_list, emu_tot_sim_time, return_cov=True):

    if core == 'xiangshan':
        return_cov = False

    sim_files_to_save = {} # files to save
    # store trace file only if we cannot use custom path and user asks for it
    store_trace_file = (CONFIG_CORE_PT['trace_out_path_t'] != None) and store_trace_file
    store_emu_trace_file = (CONFIG_EMU_PT['trace_out_path_t'] != None) and detecting_bugs

    if core == 'rsd':
        data_types = [('cov', store_cov_file), ('trace', store_trace_file), ('instr', store_trace_file), ('sim', store_trace_file)]
    else:
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
def run_muts(testcases_to_mut, prog_mut_xargs):

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
    elif run_mode == 'random': merge_mode = 'direct'
    else: assert 0, f"unknown run mode {run_mode}"
    return merge_mode


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
              , bug_detection_xargs, debug_print): 

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

    #######################################
    ######### get user input progs ########
    #######################################
    TU.TIMELOG(fuzz_time, f" -- Loading input seeds (.hex format)", False, True) 
    if CONFIG_CORE_PT["input_format"] == 'riscv': # used for chipyard 1130
        CONFIG_PT['seed_input_file_re'] =  CONFIG_PT['seed_input_file_re'].replace("hex", "riscv")
    
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
        save_filetypes = ['riscv'] if store_elf_file else [] 
        
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
        merged_cov_dict, cov_increment_dict \
                    = parse_cov.merge_cov_dicts(cov_data_dict, 'dict', merge_mode\
                                    , merged_cov_dict, fuzz_time.get_time(False))
        

        # update the cov log file
        with jsonlines.open(CONFIG.pt['cov_log_file'], 'a') as fp: 
            for cov_data in cov_increment_dict.values(): fp.write(cov_data)

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

    if CONFIG.run_mode in ['thehuzz', 'random']:
        run_thehuzz(prog_time, CONFIG.pt, CONFIG.CORE.pt, CONFIG.EMU.pt, CONFIG.run_mode\
                  , CONFIG.start_type_cov, CONFIG.input_cov_file\
                  , CONFIG.core_name,           CONFIG.EMU.emu_name,    CONFIG.max_fuzz_time\
                  , CONFIG.max_fuzz_progs,      CONFIG.target_cov,      CONFIG.sim_batch_size\
                  , CONFIG.seed_gen_interval\
                  , CONFIG.detecting_bugs,      CONFIG.no_threads,      CONFIG.store_elf_file\
                  , CONFIG.num_times_to_mut,    CONFIG.val_muts,        CONFIG.opc_muts\
                  , CONFIG.feedback_cov_types\
                  , prog_gen_xargs,             prog_mut_xargs,         prog_sim_xargs\
                  , bug_detection_xargs, CONFIG.debug_print)

    TU.TIMELOG(prog_time, f" Running {CONFIG.run_mode} on given benchmark, {CONFIG.core_name} done", False, True)


if __name__ == '__main__': 

    # custom time object
    prog_time = TU.Mytime()

    # get variables from config file or dict, and update any present in args
    CONFIG = getCONFIG(config, configType='file')
   
    # uncomment the line below to see all the config variables
    #print(CONFIG.printConfig(CONFIG)); exit()

    main(prog_time)
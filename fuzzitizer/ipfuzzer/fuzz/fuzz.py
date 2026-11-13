
import subprocess, os, sys
import time, random, copy, datetime
import json, jsonlines
from pathlib import Path
from string import Template
from tqdm import tqdm
import logging as lg

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _directory in (
        _REPO_ROOT, _REPO_ROOT / "fuzz", _REPO_ROOT / "utils",
        _REPO_ROOT / "benchmarks"):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

import config
from configManager import getCONFIG
import prog_gen, prog_mut, prog_sim, parse_cov, feedback
import fuzz_utils as TU
import input_selection
from violation_triage import triage_run
from soc_handoff import select_soc_sanitizers, publish_peripheral_run


def sim_testcases(testcases_to_sim, testcase_ids, CONFIG_CORE_PT, CONFIG_PT\
               , no_threads, core\
               , store_trace_file, tot_sim_time, cov_enable\
               , cov_types, vdb_cov_files, instance_list, return_cov=True):

    sim_files_to_save = {}
    move_trace_file = (CONFIG_CORE_PT['trace_out_path_t'] != None) and store_trace_file

    sim_files_to_save['cov'] = { 'en': False\
        , 'from': CONFIG_CORE_PT[f'cov_out_path_t']\
        , 'to': Template(f"{CONFIG_PT['sim_store_dir']}/{CONFIG_PT[f'cov_out_t'].template}") }

    sim_files_to_save['trace'] = { 'en': move_trace_file\
        , 'from': CONFIG_CORE_PT[f'trace_out_path_t']\
        , 'to': Template(f"{CONFIG_PT['sim_store_dir']}/{CONFIG_PT[f'trace_out_t'].template}") \
                    if store_trace_file else Template('/dev/null') }

    cov_data = prog_sim.sim_progs(testcases_to_sim, no_threads, testcase_ids \
            , core, tot_sim_time, cov_enable, cov_types, vdb_cov_files\
            , instance_list, CONFIG_PT["sim_bash_file"], CONFIG_CORE_PT, time.time()\
            , sim_files_to_save, return_cov)

    if store_trace_file:
        for testcase_id in testcase_ids:
            trace_path = sim_files_to_save['trace']['to'].substitute(
                fno=str(testcase_id))
            if not os.path.isfile(trace_path):
                raise FileNotFoundError(
                    f"sanitizer replay did not produce expected trace: {trace_path}")

    return cov_data


def run_muts(testcases_to_mut, val_muts, input_format_info, mutation_prob=5):

    progs_to_sim = []
    num_testcases_generated = 0

    for testcase in testcases_to_mut:
        num_testcases_generated += len(testcase['new_ip_files'])
        for ip_file_out in testcase['new_ip_files']:
            prog_mut.mutate_inputs(testcase['ip_file'], ip_file_out, mutation_prob\
                        , val_muts, input_format_info)

    return num_testcases_generated


def run_fuzzer(fuzz_time, CONFIG_PT, CONFIG_CORE_PT, run_mode\
              , start_type_cov, input_cov_file\
              , core, max_fuzz_time, max_fuzz_progs, target_cov, sim_batch_size\
              , seed_gen_interval\
              , no_threads, num_times_to_mut, val_muts\
              , feedback_cov_types, prog_sim_xargs\
              , input_format_info, num_clocks_in_input\
              , mutation_prob):

    input_database = TU.DATABASE(CONFIG_PT['all_progs_dir']\
                            , CONFIG_PT['fuzzer_input_file_t'])
    tot_cov_points = None
    cov_per_ach    = 0
    merged_cov_dict = None
    inputs_log_file = CONFIG_PT['inputs_log_file']
    num_mutations_after_seed_gen = 0
    all_interesting_testcases = []

    TU.TIMELOG(fuzz_time, f" -- Loading input seeds (.{CONFIG_CORE_PT['fuzzer_input_format']} format)", False, True)
    input_test_files = TU.get_files_in_dir(CONFIG_PT['input_seeds_dir'], CONFIG_PT['seed_input_file_re'])
    input_database.add_testcases(input_test_files)
    TU.log(inputs_log_file, f"Loaded {len(input_test_files)} input seeds | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
    TU.TIMELOG(fuzz_time, f" -- Loading input seeds", True, True)

    if start_type_cov == 'continue': 
        TU.TIMELOG(fuzz_time, f" -- Loading input coverage data from {input_cov_file} file", False, True)
        with open(input_cov_file, 'r') as fp: merged_cov_dict = json.load(fp)

        cov_data_tot = parse_cov.full_cov_to_cov_num(merged_cov_dict)
        cov_data = { 'id': '', 'time': fuzz_time.get_time(False), 'incr': cov_data_tot, 'tot': cov_data_tot }
        with jsonlines.open(CONFIG.pt['cov_log_file'], 'a') as fp: fp.write(cov_data)
        TU.TIMELOG(fuzz_time, f" -- Loading input coverage data", True, True)

    while (fuzz_time.time_diff() < max_fuzz_time \
       and input_database.num_testcases_simulated() < max_fuzz_progs \
       and cov_per_ach < target_cov):

        num_progs = sim_batch_size - input_database.num_new_testcases()
        if run_mode == 'fuzz':
            if num_mutations_after_seed_gen > seed_gen_interval: 
                num_progs = sim_batch_size
        if num_progs > 0:
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases")
            del_repo = 1 
            generated_test_files = prog_gen.gen_multi_prog(del_repo, run_mode\
                , CONFIG_PT['gen_progs_dir'], num_progs, CONFIG_PT['fuzzer_input_file_t']\
                , input_format_info, num_clocks_in_input\
                , mutation_prob, CONFIG_PT['trash_run_dir'])

            input_database.add_testcases(generated_test_files)

            num_mutations_after_seed_gen = 0

            TU.log(inputs_log_file, f"Generated {num_progs} testcases | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases", True)

        TU.TIMELOG(fuzz_time, f" -- Running simulations")
        testcases_to_sim = input_database.get_testcases_to_sim(sim_batch_size)
        files_to_sim = [i['ip_file'] for i in testcases_to_sim]
        save_ids = [i['id'] for i in testcases_to_sim]
        cov_data_dict = sim_testcases(files_to_sim, save_ids\
               , CONFIG_CORE_PT, CONFIG_PT\
               , no_threads, core, *prog_sim_xargs)
        TU.TIMELOG(fuzz_time, f" -- Running simulations", True)

        TU.TIMELOG(fuzz_time, f" -- Analyzing coverage data")
        merged_cov_dict, cov_increment_dict \
                    = parse_cov.merge_cov_dicts(cov_data_dict, 'dict'\
                                    , merged_cov_dict, fuzz_time.get_time(False))

        with jsonlines.open(CONFIG.pt['cov_log_file'], 'a') as fp: 
            for cov_data in cov_increment_dict.values(): fp.write(cov_data)

        for testcase_id, cov_data in cov_increment_dict.items(): 
            testcase_cov_increase = sum(cov_data['incr'].values())
            if testcase_cov_increase > 0:
                testcase_path = input_database.get_testcase_path(testcase_id)
                all_interesting_testcases.append([testcase_cov_increase, testcase_path])
                store_file = os.path.join(CONFIG_PT['cov_store_dir'], CONFIG_PT['cov_out_t'].substitute(fno=testcase_id))
                with open(store_file, 'w') as fp: json.dump(cov_data_dict[testcase_id], fp, indent=2)
                

        if run_mode == 'fuzz':
            testcases_to_mut, interesting_testcases, just_generated_testcases = \
                feedback.feedback_based_selection(input_database.num_new_testcases()\
                        , testcases_to_sim, cov_increment_dict, num_times_to_mut\
                        , feedback_cov_types)
            TU.log(inputs_log_file, f"Testcases to mutate: Interesting:{interesting_testcases} | Just generated: {just_generated_testcases}\n", fuzz_time)
        TU.TIMELOG(fuzz_time, f" -- Analyzing coverage data", True)

        if run_mode == 'fuzz':
            TU.TIMELOG(fuzz_time, f" -- Mutating testcases")
            testcases_to_mut = input_database.allocate_testcases_to_mut(testcases_to_mut)
            num_testcases_generated = run_muts(testcases_to_mut, val_muts\
                                        , input_format_info, mutation_prob)
            num_mutations_after_seed_gen += num_testcases_generated
            TU.log(inputs_log_file, f"Mutation done | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
            TU.TIMELOG(fuzz_time, f" -- Mutating testcases", True)

        if not tot_cov_points: 
            tot_cov_points = sum([len(cov_str) for cov_str in merged_cov_dict.values()]) 
        cov_points_ach = sum((parse_cov.full_cov_to_cov_num(merged_cov_dict)).values())
        cov_per_ach = round( (cov_points_ach / tot_cov_points)*100, 2 )
        TU.TIMELOG(fuzz_time, f" -- {input_database.num_testcases_simulated()} testcases, {cov_per_ach}% coverage achieved", False, True)


    if merged_cov_dict: 
        tot_cov = {key: len(cov_str) for key, cov_str in merged_cov_dict.items()}
        tot_cov['total'] = sum(tot_cov.values())
        ach_cov = parse_cov.full_cov_to_cov_num(merged_cov_dict, True)
        cov_per = round( (ach_cov['total'] / tot_cov['total'])*100, 2 )
    else:
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

    return all_interesting_testcases


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
    sim_dirs = [CONFIG.CORE.pt['sim_dir_t'].substitute(tno=i) for i in range(CONFIG.no_threads)]
    assert os.path.isdir(CONFIG.CORE.pt['sim_dir_t'].substitute(tno=0))\
                        , f"no simulation repos found: {CONFIG.CORE.pt['sim_dir_t'].template}"
    repos_to_create = [repo for repo in sim_dirs if not os.path.isdir(repo)]
    for repo in tqdm(repos_to_create, desc="[-------] creating simulation repositories"): 
        subprocess.call([ 'cp', '-r', CONFIG.CORE.pt['sim_dir_t'].substitute(tno=0), repo ])
    print(f"[-------] Setup simulation repositories done")

    prog_time.reset_start_time()

    debug_level = lg.DEBUG if CONFIG.debug_print else lg.INFO 
    lg.basicConfig(filename=CONFIG.pt['fuzz_log_file'], filemode='w', level=debug_level)

    TU.TIMELOG(prog_time, f" StartTime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", False, False, True)

    seed = CONFIG.random_seed
    seed = random.randrange(sys.maxsize) if seed == 0 else seed
    random.seed(seed)
    TU.TIMELOG(prog_time, f" RandomSeed: {seed}", False, False, True)

    arg_dict = {arg: CONFIG.__dict__[arg] for arg in CONFIG.argVars.keys()}
    TU.TIMELOG(prog_time, json.dumps(arg_dict, indent=2), False, False, True)

    if CONFIG.run_mode == 'fuzz':
        TU.TIMELOG(prog_time, f" Running fuzzer on given benchmark, {CONFIG.core_name}", False, True)
    elif CONFIG.run_mode == 'random': 
        TU.TIMELOG(prog_time, f" Running random regression on given benchmark, {CONFIG.core_name}", False, True)
    else: 
        assert 0, f"running fuzzer in incorrect mode, {CONFIG.run_mode}"
    prog_sim_xargs = [False,                      CONFIG.CORE.tot_sim_time\
                    , CONFIG.cov_enable\
                    , CONFIG.cov_types,           CONFIG.vdb_cov_files\
                    , CONFIG.core_instance_list]

    interesting_testcases = run_fuzzer(prog_time, CONFIG.pt, CONFIG.CORE.pt, CONFIG.run_mode\
              , CONFIG.start_type_cov, CONFIG.input_cov_file\
              , CONFIG.core_name,           CONFIG.max_fuzz_time\
              , CONFIG.max_fuzz_progs,      CONFIG.target_cov,      CONFIG.sim_batch_size\
              , CONFIG.seed_gen_interval\
              , CONFIG.no_threads,          CONFIG.num_times_to_mut\
              , CONFIG.val_muts\
              , CONFIG.feedback_cov_types,  prog_sim_xargs\
              , CONFIG.CORE.input_format_info, CONFIG.CORE.num_clocks_in_input\
              , CONFIG.mutation_prob)

    input_selection.prepare_input_corpora(
        CONFIG.replay_input_policy,
        CONFIG.core_name,
        CONFIG.pt['cov_store_dir'],
        CONFIG.pt['all_progs_dir'],
        CONFIG.pt['selected_inputs_dir'],
        CONFIG.pt['sanitizer_replay_inputs_dir'],
        [testcase[1] for testcase in interesting_testcases],
    )
    replay_inputs = input_selection.load_selected_inputs(
        CONFIG.pt['sanitizer_replay_inputs_dir'])
    TU.TIMELOG(prog_time,
        f" Replaying {len(replay_inputs)} inputs with sanitizers",
        False, True)

    CONFIG.CORE.pt['sim_dir_t'] = Template(os.path.join(
        os.environ['IPFUZZ_ROOT'], f"sim/{CONFIG.core_name}_san/vcs_${{tno}}"))
    sim_dirs = [CONFIG.CORE.pt['sim_dir_t'].substitute(tno=i) for i in range(CONFIG.no_threads)]
    assert os.path.isdir(CONFIG.CORE.pt['sim_dir_t'].substitute(tno=0))\
                        , f"no sanitized simulation repos found: {CONFIG.CORE.pt['sim_dir_t'].template}"
    for repo in [repo for repo in sim_dirs if not os.path.isdir(repo)]:
        subprocess.call([ 'cp', '-r', CONFIG.CORE.pt['sim_dir_t'].substitute(tno=0), repo ])

    if replay_inputs:
        sim_testcases(
            [str(input_path) for _, input_path in replay_inputs],
            [input_id for input_id, _ in replay_inputs],
            CONFIG.CORE.pt, CONFIG.pt,
            CONFIG.no_threads, CONFIG.core_name,
            True, CONFIG.CORE.tot_sim_time,
            CONFIG.cov_enable, CONFIG.cov_types, CONFIG.vdb_cov_files,
            CONFIG.core_instance_list,
            return_cov=False,
        )
    TU.TIMELOG(prog_time,
        f" Replaying {len(replay_inputs)} inputs with sanitizers",
        True, True)

    triage_result = triage_run(
        Path(CONFIG.pt['sim_store_dir']),
        Path(CONFIG.CORE.pt['sanitizers_sva_file_path']),
        Path(CONFIG.CORE.pt['perif_jg_tcl_log_file']),
        Path(CONFIG.pt['outputs_run_dir']) / 'triage',
    )
    soc_sanitizer_path = (
        Path(CONFIG.pt['outputs_run_dir'])
        / 'soc_sanitizers'
        / f"sanitizers_{CONFIG.core_name}.sva"
    )
    select_soc_sanitizers(
        Path(CONFIG.CORE.pt['soc_sanitizers_sva_file_path']),
        soc_sanitizer_path,
        CONFIG.soc_assertion_policy,
        triage_result.selected_assertions,
        triage_result.retained_covers,
    )
    publish_peripheral_run(
        Path(os.environ['IPFUZZ_ROOT']),
        CONFIG.core_name,
        Path(CONFIG.pt['outputs_run_dir']),
        soc_sanitizer_path,
    )

    TU.TIMELOG(prog_time, f" Running fuzzer on given benchmark, {CONFIG.core_name} done", False, True)




if __name__ == '__main__': 

    prog_time = TU.Mytime()

    CONFIG = getCONFIG(config, configType='file')
   

    main(prog_time)



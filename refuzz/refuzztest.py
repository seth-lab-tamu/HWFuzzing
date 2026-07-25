"""Run ReFuzz testing with trained contextual-bandit seeds.

Author: Chen Chen
The code is cleaned up by Codex
"""

import os
import json
import shutil

import jsonlines
import numpy as np

import thehuzz.prog_gen as prog_gen
import thehuzz.parse_cov as parse_cov
import thehuzz.feedback as feedback
import thehuzz.thehuzz_utils as TU
import thehuzz.detect_bugs as detect_bugs
import fuzz
import mabfuzz.MABAlgos as MAB_algos

coverage_file_initialized = False

def init_cb_cov_list(fuzz_time, cb_init_flags, current_context, \
                     cb_remaining_seeds, cb_train_files, mab_algo, \
                     mab_n_picks_reset, merged_cov_dict, input_database, \
                     inputs_log_file, prog_mut_xargs, cb_vul_test, \
                     num_mutations_after_seed_gen, cb_train_results, \
                     save_filetypes, sim_batch_size):
    """
    Reinitialize MAB object and database with the remaining seeds for a given context, and mutate each seed to create up to sim_batch_size-1 mutants per seed initially.
    """

    cb_init_flags[current_context] = True
    TU.TIMELOG(fuzz_time, f" -- Reinitialize the refuzz with remaining {current_context} contextual training results", False, True)

    cb_test_num_seed_arms = len(cb_remaining_seeds[current_context])
    cb_test_seed_dir = cb_train_files[current_context]["seeds_dir"]
    cb_test_seed = MAB_algos.create_mab_object(mab_algo, [cb_test_num_seed_arms, mab_n_picks_reset])

    remaining = cb_remaining_seeds[current_context]
    for i in range(len(cb_test_seed.values)):
        seed_id = remaining[i]
        cb_test_seed.values[i] = cb_train_results[current_context]["policy_scores"][seed_id]

    for i in range(cb_test_seed.n_arms):
        cb_test_seed.arm_merged_cov_dict[i] = merged_cov_dict

    input_database.seed_mab_new_testcases = [[] for _ in range(cb_test_num_seed_arms)]

    TU.TIMELOG(fuzz_time, f" -- Loading input seeds (.hex format) from context training", False, True)
    # Remap per-context seed IDs to the contiguous arm space expected by the MAB.
    cb_test_seed.local_to_orig = list(cb_remaining_seeds[current_context])
    input_test_files = []
    cb_seed_arm_ids = []
    for local_arm_id, seed_id in enumerate(cb_remaining_seeds[current_context]):
        seed_file_name = cb_train_results[current_context]['seeds'][seed_id]
        input_test_files.append(os.path.join(cb_test_seed_dir, seed_file_name))
        cb_seed_arm_ids.append(local_arm_id)

    newly_added_testcases = input_database.add_testcases(
        input_test_files, save_filetypes, cb_vul_test, seed_arm_ids=cb_seed_arm_ids, init_train=True
    )

    TU.log(inputs_log_file, f"Loaded {len(input_test_files)} input seeds | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
    TU.TIMELOG(fuzz_time, f" -- Loading input seeds", True, True)

    for testcase in newly_added_testcases:
        cb_test_seed.arm_seed[testcase['seed_arm_id']] = testcase  # arms need to remember seed testcase
        testcase.update({'mut_times': sim_batch_size - 1})

    testcases_to_mut = input_database.allocate_testcases_to_mut(newly_added_testcases, cb_vul_test)
    num_testcases_generated = fuzz.run_muts(testcases_to_mut, prog_mut_xargs, cb_vul_test)
    num_mutations_after_seed_gen += num_testcases_generated
    TU.TIMELOG(fuzz_time, f" -- Mutate initial CB seeds from {current_context} context training", True, True)

    return cb_test_seed, num_mutations_after_seed_gen, cb_test_num_seed_arms


def _ensure_coverage_log_initialized(coverage_type_names):
    """
    Make sure coverage_progress.txt exists and has a header.
    Only called when we actually log the first time.
    """
    global coverage_file_initialized
    header_line = f"iteration total {' '.join(coverage_type_names)}\n"

    if os.path.exists('coverage_progress.txt'):
        with open('coverage_progress.txt', 'r') as f:
            existing_lines = f.readlines()
        if len(existing_lines) <= 1:
            with open('coverage_progress.txt', 'w') as f:
                f.write(header_line)
    else:
        with open('coverage_progress.txt', 'w') as f:
            f.write(header_line)

    coverage_file_initialized = True

def _log_coverage_progress(current_iteration, merged_cov_dict):
    """
    Append a single line of coverage progress to coverage_progress.txt.
    """
    global coverage_file_initialized

    coverage_type_names = list(merged_cov_dict.keys())

    if not coverage_file_initialized:
        _ensure_coverage_log_initialized(coverage_type_names)

    total_points_per_type = {key: len(cov_str) for key, cov_str in merged_cov_dict.items()}
    total_points_per_type['total'] = sum(total_points_per_type.values())

    coverage_counts = parse_cov.full_cov_to_cov_num(merged_cov_dict, include_tot=True)

    coverage_percentages = {}
    for cov_type, count in coverage_counts.items():
        denom = total_points_per_type.get(cov_type, 0)
        coverage_percentages[cov_type] = round((count / denom) * 100, 2) if denom > 0 else 0.0

    total_percentage = coverage_percentages.get('total', 0.0)
    individual_percentages = [coverage_percentages[cov_type] for cov_type in coverage_type_names]

    with open('coverage_progress.txt', 'a') as coverage_log_file:
        coverage_log_file.write(
            f"{current_iteration} {total_percentage} {' '.join(str(val) for val in individual_percentages)}\n"
        )


def run_refuzz(fuzz_time, CONFIG_PT, CONFIG_CORE_PT, CONFIG_EMU_PT,
               run_mode, core, emu, max_fuzz_time, max_fuzz_progs,
               target_cov, sim_batch_size, seed_gen_interval,
               detecting_bugs, no_threads, store_elf_file,
               num_times_to_mut, val_muts, opc_muts,
               feedback_cov_types, mab_algo, mab_num_seed_arms,
               mab_n_picks_reset, refuzz_train_source, training_processors, cb_vul, all_cov_types,
               prog_gen_xargs, prog_mut_xargs, prog_sim_xargs,
               bug_detection_xargs, nop_cov_dict, collect_interesting_tests,
               collect_cov_samples, cov_sample_interval, debug_print):
    """
    Main function that runs the fuzzer:
    - Fuzzer stops when timelimit, testcase limit, or coverage % limit is reached
    """
    assert run_mode == 'refuzztest', "this script is only for refuzz testing"
    assert len(feedback_cov_types) == 1, "the script is implemented for only one coverage metric, but can easily be extended if needed"
    tar_cov_metric = feedback_cov_types[0]
    cov_sizes = {cov_type: len(cov_str) for cov_type, cov_str in nop_cov_dict.items()}

    if tar_cov_metric == 'cond':
        context_thresholds = [45, 50, 55, 60, 65]
    elif tar_cov_metric == 'branch':
        context_thresholds = [55, 60, 65, 70]
    else:
        assert False, f"unrecognized target coverage metric {tar_cov_metric}"

    last_ctx = context_thresholds[-1]

    assert refuzz_train_source in ['thehuzz', 'thehuzzcascade'], \
        f"unrecognized ReFuzz train source {refuzz_train_source}"
    train_model_name = "_".join(training_processors) + "_train"
    trained_model = (
        f"{os.environ['THEHUZZ_ROOT']}/refuzz/refuzz_train/trained_db/"
        f"{refuzz_train_source}/{tar_cov_metric}/{train_model_name}"
    )
    assert os.path.isdir(trained_model), f"Error: ReFuzz trained model directory '{trained_model}' does not exist."

    cb_vul_train_files = f"{trained_model}/vul_train"

    cb_train_files = {
        t: {
            "train": f"{trained_model}/{t}.json",
            "seeds_dir": f"{trained_model}/{t}",
        }
        for t in context_thresholds
    }

    cb_train_results = {}
    for train_cov in cb_train_files:
        train_result_file = cb_train_files[train_cov]["train"]
        assert os.path.exists(train_result_file), f"Error: CB Training file '{train_result_file}' does not exist."
        with open(train_result_file, 'r') as f:
            cb_train_results[train_cov] = json.load(f)

    cb_test_num_seed_arms = no_threads  # in case all train results are empty
    input_database = TU.DATABASE(core, CONFIG_PT['all_progs_dir'],
                                 CONFIG_PT['hex_file_t'], CONFIG_PT['riscv_file_t'], run_mode,
                                 cb_test_num_seed_arms,
        )

    tot_cov_points = None
    tot_cov_points_feedback = None
    cov_per_ach = 0
    cb_tar_cov_per_ach = 0
    cb_vul_test = bool(cb_vul)  # mirror cb_vul; run vulnerability tests first only if enabled
    merged_cov_dict = dict(nop_cov_dict)
    inputs_log_file = CONFIG_PT['inputs_log_file']
    num_mutations_after_seed_gen = 0
    save_filetypes = ['riscv', 'hex'] if store_elf_file else ['hex']
    iteration_num = 0
    cov_sample_state = fuzz.init_cov_sample_state(feedback_cov_types, cov_sample_interval, collect_cov_samples)

    TU.TIMELOG(fuzz_time, f" -- Loading input seeds (.riscv format)", False, True)

    if cb_vul_test:
        TU.TIMELOG(fuzz_time, f" -- Loading input seeds from {cb_vul_train_files}", False, True)
        for filename in os.listdir(cb_vul_train_files):
            if filename.endswith(('.riscv', '.hex')):
                shutil.copy(
                    os.path.join(cb_vul_train_files, filename),
                    os.path.join(CONFIG_PT['input_seeds_dir'], filename),
                )
    else:
        TU.TIMELOG(fuzz_time, f" -- Skipping input seeds from {cb_vul_train_files}", False, True)

    if CONFIG_CORE_PT["input_format"] == 'riscv':  # used for chipyard 1130
        CONFIG_PT['seed_input_file_re'] = CONFIG_PT['seed_input_file_re'].replace("hex", "riscv")

    input_test_files = TU.get_files_in_dir(CONFIG_PT['input_seeds_dir'], CONFIG_PT['seed_input_file_re'])
    newly_added_testcases = input_database.add_testcases(input_test_files, save_filetypes, cb_vul_test)

    TU.log(inputs_log_file, f"Loaded {len(input_test_files)} input seeds | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
    TU.TIMELOG(fuzz_time, f" -- Loading input seeds", True, True)

    max_fuzz_vul_progs = len(input_test_files) * 10 if cb_vul_test else 0  # mutate 10 for each file when enabled

    TU.TIMELOG(fuzz_time, f" -- Analyzing CB Vulnerability List", False, True)

    while input_database.num_testcases_simulated() < max_fuzz_vul_progs:
        num_progs = sim_batch_size - input_database.num_new_testcases(cb_vul_test=cb_vul_test)
        if num_mutations_after_seed_gen > seed_gen_interval:
            num_progs = sim_batch_size

        if num_progs > 0:
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases")
            del_repo = 1
            generated_test_files = prog_gen.gen_multi_prog(del_repo, run_mode, core\
                , no_threads, CONFIG_PT['gen_progs_dir'], CONFIG_PT['sw_run_dir']\
                , num_progs, prog_gen_xargs, CONFIG_PT['trash_run_dir'], debug_print
            )

            newly_added_testcases = input_database.add_testcases(generated_test_files, save_filetypes, cb_vul_test)
            num_mutations_after_seed_gen = 0  # reset as seeds are generated

            TU.log(
                inputs_log_file,
                f"Generated {num_progs} testcases | Total testcases = {input_database.num_testcases()}\n",
                fuzz_time,
            )
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases", True)

        chosen_seed_arm = -1
        testcases_to_sim = input_database.get_testcases_to_sim(sim_batch_size, chosen_seed_arm, cb_vul_test)
        files_to_sim = [i['riscv_file'] for i in testcases_to_sim]
        save_ids = [i['id'] for i in testcases_to_sim]

        cov_data_dict = fuzz.sim_testcases(files_to_sim, save_ids\
            , CONFIG_CORE_PT, CONFIG_EMU_PT, CONFIG_PT\
            , detecting_bugs, no_threads, core, *prog_sim_xargs
        )
        TU.TIMELOG(fuzz_time, f" -- Running simulations", True)

        TU.TIMELOG(fuzz_time, f" -- Analyzing coverage data")

        merge_mode = fuzz.get_merge_mode('thehuzz')

        (
            merged_cov_dict,
            cov_increment_dict,
            _,
            _,
            arm_merged_cov_dict,
            arm_cov_increment_dict,
        ) = parse_cov.merge_cov_dicts(
            cov_data_dict,
            'dict',
            merge_mode,
            merged_cov_dict,
            fuzz_time.get_time(False),
        )

        with jsonlines.open(CONFIG_PT['cov_log_file'], 'a') as fp:
            for cov_data in cov_increment_dict.values():
                fp.write(cov_data)
        fuzz.store_interesting_tests(
            CONFIG_PT,
            testcases_to_sim,
            cov_data_dict,
            cov_increment_dict,
            feedback_cov_types,
            collect_interesting_tests,
        )
        fuzz.sample_target_cov(CONFIG_PT, merged_cov_dict, cov_sample_state, fuzz_time, save_ids[-1])

        testcases_to_mut, interesting_testcases, just_generated_testcases = feedback.feedback_based_selection(
            input_database.num_new_testcases(cb_vul_test=cb_vul_test),
            testcases_to_sim,
            cov_increment_dict,
            num_times_to_mut,
            feedback_cov_types,
        )

        if not tot_cov_points:
            tot_cov_points = sum([len(cov_str) for cov_str in merged_cov_dict.values()])
        full_cov_num = parse_cov.full_cov_to_cov_num(merged_cov_dict)
        cov_points_ach = sum(full_cov_num.values())
        cov_per_ach = round((cov_points_ach / tot_cov_points) * 100, 2)
        cb_tar_cov_per_ach = sum([full_cov_num[cov_type] for cov_type in feedback_cov_types])
        cb_tar_cov_per_ach = round((cb_tar_cov_per_ach / cov_sizes[tar_cov_metric]) * 100, 2)

        TU.log(
            inputs_log_file,
            f"Testcases to mutate: Interesting:{interesting_testcases} | Just generated: {just_generated_testcases}\n",
            fuzz_time,
        )

        testcases_to_mut = input_database.allocate_testcases_to_mut(testcases_to_mut, cb_vul_test)
        num_testcases_generated = fuzz.run_muts(testcases_to_mut, prog_mut_xargs, cb_vul_test)
        num_mutations_after_seed_gen += num_testcases_generated

        TU.TIMELOG(
            fuzz_time,
            f" -- {input_database.num_testcases_simulated()} testcases, {cov_per_ach}% coverage achieved, {cb_tar_cov_per_ach}% target coverage achieved",
            False,
            True,
        )

        iteration_num += 1

    TU.TIMELOG(fuzz_time, f" -- Analyzing Vulnerability List", True, True)

    TU.TIMELOG(fuzz_time, f" -- Analyzing CB Coverage List", False, True)

    if not tot_cov_points:
        tot_cov_points = sum([len(cov_str) for cov_str in merged_cov_dict.values()])
    full_cov_num = parse_cov.full_cov_to_cov_num(merged_cov_dict)
    cov_points_ach = sum(full_cov_num.values())
    cov_per_ach = round((cov_points_ach / tot_cov_points) * 100, 2)
    cb_tar_cov_per_ach = sum([full_cov_num[cov_type] for cov_type in feedback_cov_types])
    cb_tar_cov_per_ach = round((cb_tar_cov_per_ach / cov_sizes[tar_cov_metric]) * 100, 2)

    cb_vul_test = False

    cb_init_flags = {t: False for t in context_thresholds}
    num_seed_drop = 0
    current_context = 0
    cb_seed_empty = {t: False for t in context_thresholds}

    cb_remaining_seeds = {t: [] for t in context_thresholds}
    exe_remaining_seeds = False
    # Preserve original context/seed IDs when several contexts share a new local arm space.
    combined_arm_map = None

    assert cb_seed_empty[last_ctx] is False, f"the last coverage list should not be empty at this moment"

    while (
        fuzz_time.time_diff() < max_fuzz_time
        and input_database.num_testcases_simulated() < max_fuzz_progs
        and cov_per_ach < target_cov
    ):
        if cb_seed_empty[last_ctx] is False and exe_remaining_seeds is False:
            for i, ctx in enumerate(context_thresholds):

                lower = float("-inf") if i == 0 else context_thresholds[i - 1]
                upper = ctx  # context is the bucket's UPPER bound

                if cb_init_flags[ctx] is True:
                    continue

                cond = False
                if (i == 0):
                    # First coverage list: (-inf, upper)
                    cond = (cb_tar_cov_per_ach < upper)
                elif i < len(context_thresholds) - 1:
                    # Middle coverage lists: [lower, upper)
                    # If the lower bucket is empty, advance to the nearest non-empty bucket.
                    cond = ((cb_tar_cov_per_ach >= lower and cb_tar_cov_per_ach < upper) or
                            (cb_tar_cov_per_ach < lower
                             and cb_seed_empty.get(lower, False) is True
                             and cb_seed_empty.get(upper, False) is False))
                else:
                    # Last bucket: [lower, +inf)
                    cond = ((cb_tar_cov_per_ach >= lower) or
                           (cb_tar_cov_per_ach < lower and cb_seed_empty.get(lower, False) is True))

                if cond:
                    cb_init_flags[ctx] = True
                    current_context = ctx
                    num_seed_drop = 0
                    TU.TIMELOG(fuzz_time, f" -- Reinitialize the refuzz with {ctx} contextual training results", False, True)

                    cb_remaining_seeds[ctx].extend(list(range(len(cb_train_results[ctx]["seeds"]))))

                    cb_test_seed, num_mutations_after_seed_gen, cb_test_num_seed_arms = init_cb_cov_list(
                        fuzz_time,
                        cb_init_flags,
                        current_context,
                        cb_remaining_seeds,
                        cb_train_files,
                        mab_algo,
                        mab_n_picks_reset,
                        merged_cov_dict,
                        input_database,
                        inputs_log_file,
                        prog_mut_xargs,
                        cb_vul_test,
                        num_mutations_after_seed_gen,
                        cb_train_results,
                        save_filetypes,
                        sim_batch_size,
                    )
                    break
        elif cb_seed_empty[last_ctx] is True and exe_remaining_seeds is True:
            if any(cb_init_flags[ctx] is False for ctx in context_thresholds[:-1]):
                for ctx in context_thresholds[:-1]:
                    cb_init_flags[ctx] = True
                current_context = context_thresholds[0]
                num_seed_drop = 0

                combined_arm_map = []
                policy_scs = []
                for cov_context in cb_remaining_seeds:
                    for seed_id in cb_remaining_seeds[cov_context]:
                        combined_arm_map.append((cov_context, seed_id))
                        policy_scs.append(cb_train_results[cov_context]["policy_scores"][seed_id])

                cb_test_num_seed_arms = len(combined_arm_map)

                cb_test_seed = MAB_algos.create_mab_object(mab_algo, [cb_test_num_seed_arms, mab_n_picks_reset])
                for i in range(len(cb_test_seed.values)):
                    cb_test_seed.values[i] = policy_scs[i]

                for i in range(cb_test_seed.n_arms):
                    cb_test_seed.arm_merged_cov_dict[i] = merged_cov_dict

                input_database.seed_mab_new_testcases = [[] for _ in range(cb_test_num_seed_arms)]

                TU.TIMELOG(fuzz_time, f" -- Loading input seeds (.hex format) from context training", False, True)
                input_test_files = []
                cb_seed_arm_ids = []
                for local_arm_id, (cov_context, seed_id) in enumerate(combined_arm_map):
                    cb_test_seed_dir = cb_train_files[cov_context]["seeds_dir"]
                    seed_file_name = cb_train_results[cov_context]['seeds'][seed_id]
                    input_test_files.append(os.path.join(cb_test_seed_dir, seed_file_name))
                    cb_seed_arm_ids.append(local_arm_id)

                newly_added_testcases = input_database.add_testcases(
                    input_test_files, save_filetypes, cb_vul_test, seed_arm_ids=cb_seed_arm_ids, init_train=True
                )

                TU.log(
                    inputs_log_file,
                    f"Loaded {len(input_test_files)} input seeds | Total testcases = {input_database.num_testcases()}\n",
                    fuzz_time,
                )
                TU.TIMELOG(fuzz_time, f" -- Loading input seeds", True, True)

                for testcase in newly_added_testcases:
                    cb_test_seed.arm_seed[testcase['seed_arm_id']] = testcase
                    testcase.update({'mut_times': sim_batch_size - 1})

                testcases_to_mut = input_database.allocate_testcases_to_mut(newly_added_testcases, cb_vul_test)
                num_testcases_generated = fuzz.run_muts(testcases_to_mut, prog_mut_xargs, cb_vul_test)
                num_mutations_after_seed_gen += num_testcases_generated
                TU.TIMELOG(fuzz_time, f" -- Mutate initial CB seeds from {current_context} context training", True, True)

        seed_arm_ids = np.where(np.array([len(i) for i in input_database.seed_mab_new_testcases]) == 0)[0]
        num_progs = len(seed_arm_ids)

        if num_progs > 0:
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases")
            del_repo = 1
            generated_test_files = prog_gen.gen_multi_prog(
                del_repo,
                run_mode,
                core,
                no_threads,
                CONFIG_PT['gen_progs_dir'],
                CONFIG_PT['sw_run_dir'],
                num_progs,
                prog_gen_xargs,
                CONFIG_PT['trash_run_dir'],
                debug_print,
            )
            newly_added_testcases = input_database.add_testcases(
                generated_test_files, save_filetypes, cb_vul_test, seed_arm_ids=seed_arm_ids
            )

            num_mutations_after_seed_gen = 0  # reset as seeds are generated

            TU.log(
                inputs_log_file,
                f"Generated {num_progs} testcases, {seed_arm_ids} | Total testcases = {input_database.num_testcases()}\n",
                fuzz_time,
            )
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases", True)

            for testcase in newly_added_testcases:
                cb_test_seed.arm_seed[testcase['seed_arm_id']] = testcase
                testcase.update({'mut_times': sim_batch_size - 1})

            testcases_to_mut = input_database.allocate_testcases_to_mut(newly_added_testcases, cb_vul_test)
            num_testcases_generated = fuzz.run_muts(testcases_to_mut, prog_mut_xargs, cb_vul_test)
            num_mutations_after_seed_gen += num_testcases_generated

        TU.TIMELOG(fuzz_time, f" -- Running simulations")
        chosen_seed_arm = int(cb_test_seed.select_arm())

        testcases_to_sim = input_database.get_testcases_to_sim(sim_batch_size, chosen_seed_arm, cb_vul_test)
        files_to_sim = [i[f"{CONFIG_CORE_PT['input_format']}_file"] for i in testcases_to_sim]
        save_ids = [i['id'] for i in testcases_to_sim]

        cov_data_dict = fuzz.sim_testcases(
            files_to_sim,
            save_ids,
            CONFIG_CORE_PT,
            CONFIG_EMU_PT,
            CONFIG_PT,
            detecting_bugs,
            no_threads,
            core,
            *prog_sim_xargs,
        )
        TU.TIMELOG(fuzz_time, f" -- Running simulations", True)

        TU.TIMELOG(fuzz_time, f" -- Analyzing coverage data")
        merge_mode = fuzz.get_merge_mode(run_mode)

        (
            merged_cov_dict,
            cov_increment_dict,
            _,
            _,
            arm_merged_cov_dict,
            arm_cov_increment_dict,
        ) = parse_cov.merge_cov_dicts(
            cov_data_dict,
            'dict',
            merge_mode,
            merged_cov_dict,
            fuzz_time.get_time(False),
            cb_test_seed.arm_merged_cov_dict[chosen_seed_arm],
        )

        with jsonlines.open(CONFIG_PT['cov_log_file'], 'a') as fp:
            for cov_data in cov_increment_dict.values():
                fp.write(cov_data)
        if run_mode in ['refuzztest']:
            with jsonlines.open(CONFIG_PT['particle_cov_log_file'], 'a') as fp:
                fp.write({'itr_no': iteration_num, 'arm_id': int(chosen_seed_arm), 'num_tests': len(testcases_to_sim)})
                for cov_data in arm_cov_increment_dict.values():
                    fp.write(cov_data)
            fuzz.store_interesting_tests(
                CONFIG_PT,
                testcases_to_sim,
                cov_data_dict,
                arm_cov_increment_dict,
                feedback_cov_types,
                collect_interesting_tests,
            )
            fuzz.sample_target_cov(CONFIG_PT, merged_cov_dict, cov_sample_state, fuzz_time, save_ids[-1])

        testcases_to_mut, interesting_testcases, just_generated_testcases = feedback.feedback_based_selection(
            input_database.num_new_testcases(chosen_seed_arm, cb_vul_test=cb_vul_test),
            testcases_to_sim,
            arm_cov_increment_dict,
            num_times_to_mut,
            feedback_cov_types,
        )

        tot_cov_incr_dict = list(cov_increment_dict.values())[-1]
        tot_cov_incr = sum([tot_cov_incr_dict['incr'][cov_type] for cov_type in feedback_cov_types])
        arm_cov_incr_dict = {cov_type: sum(i['incr'][cov_type] for i in arm_cov_increment_dict.values()) for cov_type in merged_cov_dict.keys()}
        arm_cov_incr = sum([arm_cov_incr_dict[cov_type] for cov_type in feedback_cov_types])
        if not tot_cov_points_feedback:
            tot_cov_points_feedback = sum([len(merged_cov_dict[i]) for i in feedback_cov_types])

        TU.log(
            inputs_log_file,
            f"Testcases to mutate: Interesting:{interesting_testcases} | Just generated: {just_generated_testcases}\n",
            fuzz_time,
        )

        cb_test_seed.update_arm(chosen_seed_arm, tot_cov_incr, arm_merged_cov_dict, arm_cov_incr, tot_cov_points_feedback)
        with jsonlines.open(CONFIG_PT['particle_status_log_file'], 'a') as fp:
            fp.write({
                'itr_no': iteration_num,
                'arm': chosen_seed_arm,
                'interesting_to_mutate': interesting_testcases,
                'just_gen_mutate': just_generated_testcases,
            })
            fp.write({'itr_no': iteration_num, 'arm': chosen_seed_arm, 'counts': list(cb_test_seed.counts), 'values': list(cb_test_seed.values)})

        TU.TIMELOG(fuzz_time, f" -- Analyzing coverage data", True)

        TU.TIMELOG(fuzz_time, f" -- Mutating testcases")
        testcases_to_mut = input_database.allocate_testcases_to_mut(testcases_to_mut, cb_vul_test)
        num_testcases_generated = fuzz.run_muts(testcases_to_mut, prog_mut_xargs)
        num_mutations_after_seed_gen += num_testcases_generated
        TU.log(inputs_log_file, f"Mutation done | Total testcases = {input_database.num_testcases()}\n", fuzz_time)
        TU.TIMELOG(fuzz_time, f" -- Mutating testcases", True)

        if not tot_cov_points:
            tot_cov_points = sum([len(cov_str) for cov_str in merged_cov_dict.values()])
        full_cov_num = parse_cov.full_cov_to_cov_num(merged_cov_dict)
        cov_points_ach = sum(full_cov_num.values())
        cov_per_ach = round((cov_points_ach / tot_cov_points) * 100, 2)
        cb_tar_cov_per_ach = sum([full_cov_num[cov_type] for cov_type in feedback_cov_types])
        cb_tar_cov_per_ach = round((cb_tar_cov_per_ach / cov_sizes[tar_cov_metric]) * 100, 2)

        TU.TIMELOG(
            fuzz_time,
            f" -- {input_database.num_testcases_simulated()} testcases, {cov_per_ach}% total coverage achieved, {cb_tar_cov_per_ach}% target coverage achieved",
            False,
            True,
        )

        reset_arms = cb_test_seed.check_reset(
            chosen_seed_arm, input_database.num_new_testcases(chosen_seed_arm, cb_vul_test=cb_vul_test) > 0
        )

        for arm_info in reset_arms:
            input_database.seed_mab_new_testcases[arm_info[0]] = []
        if reset_arms:
            with jsonlines.open(CONFIG_PT['particle_status_log_file'], 'a') as fp:
                fp.write({'itr_no': iteration_num, 'arm': chosen_seed_arm, 'reset_arms': reset_arms})

            num_seed_drop += len(reset_arms)
            # Map local arm indices back to original seeds and drop them from cb_remaining_seeds:
            # - When executing remaining seeds across contexts, use combined_arm_map (local -> (context, seed_id))
            # - When handling a single context, use cb_test_seed.local_to_orig (local -> original seed_id)
            for reset_arm in reset_arms:
                reset_arm_id = reset_arm[0]
                if exe_remaining_seeds and combined_arm_map:
                    cov_context, seed_id = combined_arm_map[reset_arm_id]
                    if seed_id in cb_remaining_seeds[cov_context]:
                        cb_remaining_seeds[cov_context].remove(seed_id)
                elif hasattr(cb_test_seed, 'local_to_orig') and 0 <= reset_arm_id < len(cb_test_seed.local_to_orig):
                    orig_seed_id = cb_test_seed.local_to_orig[reset_arm_id]
                    if orig_seed_id in cb_remaining_seeds[current_context]:
                        cb_remaining_seeds[current_context].remove(orig_seed_id)
                elif reset_arm_id in cb_remaining_seeds[current_context]:
                    cb_remaining_seeds[current_context].remove(reset_arm_id)

        if num_seed_drop >= cb_test_num_seed_arms:
            cb_seed_empty[current_context] = True
            TU.TIMELOG(fuzz_time, f" -- seeds of list {current_context} becomes empty", True)

        if cb_seed_empty[last_ctx] is True and exe_remaining_seeds is False:
            for ctx in context_thresholds[:-1]:
                if cb_seed_empty[ctx] is False:
                    cb_init_flags[ctx] = False
            exe_remaining_seeds = True

        _log_coverage_progress(input_database.num_testcases_simulated(), merged_cov_dict)

        iteration_num += 1

    if merged_cov_dict:
        tot_cov = {key: len(cov_str) for key, cov_str in merged_cov_dict.items()}
        tot_cov['total'] = sum(tot_cov.values())
        ach_cov = parse_cov.full_cov_to_cov_num(merged_cov_dict, True)
        cov_per = round((ach_cov['total'] / tot_cov['total']) * 100, 2)
    else:
        tot_cov = {}
        ach_cov = {}
        cov_per = 0

    stats_string = f"\n{'-' * 60}\n"
    stats_string += f"  Benchmark              : {core}\n"
    stats_string += f"  Run time               : {fuzz_time.get_time(False)} sec\n"
    stats_string += f"  No. of testcases       : {input_database.num_testcases_simulated()}\n"
    stats_string += f"  No. of coverage points : {tot_cov}\n"
    stats_string += f"  No. of points covered  : {ach_cov}\n"
    stats_string += f"  % coverage achieved    : {cov_per}%\n"
    stats_string += f"{'-' * 60}\n"
    TU.TIMELOG(fuzz_time, stats_string, False, True)

    if merged_cov_dict:
        with open(CONFIG_PT['merged_cov_file'], 'w') as fp:
            json.dump(merged_cov_dict, fp, indent=2)

    if detecting_bugs:
        TU.TIMELOG(fuzz_time, f" Comparing traces to detect mismatches", False, True)
        detect_bugs.detect_mismatches(*bug_detection_xargs)
        TU.TIMELOG(fuzz_time, f" Comparing traces to detect mismatches", True, True)

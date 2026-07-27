"""Coverage-guided processor fuzzing with multi-armed bandit seed selection.

Each arm owns a generated seed and its descendants. During every iteration,
the configured bandit policy selects an arm, MABFuzz simulates that arm's
queued testcases, rewards coverage growth, and mutates useful testcases to
replenish the arm.
"""

import datetime
import json

import jsonlines
import numpy as np

import detect_bugs
import feedback
import fuzz
import mabfuzz.MABAlgos as MAB_algos
import parse_cov
import prog_gen
import thehuzz_utils as TU


def run_mabfuzz(
    fuzz_time,
    CONFIG_PT,
    CONFIG_CORE_PT,
    CONFIG_EMU_PT,
    run_mode,
    core,
    emu,
    max_fuzz_time,
    max_fuzz_progs,
    target_cov,
    sim_batch_size,
    seed_gen_interval,
    detecting_bugs,
    no_threads,
    store_elf_file,
    num_times_to_mut,
    val_muts,
    opc_muts,
    feedback_cov_types,
    mab_algo,
    mab_num_seed_arms,
    mab_n_picks_reset,
    all_cov_types,
    prog_gen_xargs,
    prog_mut_xargs,
    prog_sim_xargs,
    bug_detection_xargs,
    nop_cov_dict,
    collect_interesting_tests,
    collect_cov_samples,
    cov_sample_interval,
    debug_print,
):
    """Run a MABFuzz campaign until a configured stopping condition is met.

    The positional interface is shared with ``fuzz.py``. Some configuration
    values are consumed by the argument bundles assembled there rather than
    directly in this function.
    """
    assert run_mode == "mabfuzz", "this script is only for mabfuzz"

    input_database = TU.DATABASE(
        core,
        CONFIG_PT["all_progs_dir"],
        CONFIG_PT["hex_file_t"],
        CONFIG_PT["riscv_file_t"],
        run_mode,
        mab_num_seed_arms,
    )
    tot_cov_points = None
    tot_cov_points_feedback = None
    cov_per_ach = 0
    merged_cov_dict = dict(nop_cov_dict)
    inputs_log_file = CONFIG_PT["inputs_log_file"]
    save_filetypes = ["riscv", "hex"] if store_elf_file else ["hex"]

    iteration_num = 0
    cov_sample_state = fuzz.init_cov_sample_state(
        feedback_cov_types,
        cov_sample_interval,
        collect_cov_samples,
    )
    seed_mab = MAB_algos.create_mab_object(
        mab_algo,
        [mab_num_seed_arms, mab_n_picks_reset],
    )

    while (
        fuzz_time.time_diff() < max_fuzz_time
        and input_database.num_testcases_simulated() < max_fuzz_progs
        and cov_per_ach < target_cov
    ):
        # Generate one initial seed for every arm whose queue is empty.
        seed_arm_ids = np.where(
            np.array(
                [
                    len(testcases)
                    for testcases in input_database.seed_mab_new_testcases
                ]
            )
            == 0
        )[0]
        num_progs = len(seed_arm_ids)

        if num_progs > 0:
            TU.TIMELOG(fuzz_time, f" -- Generating {num_progs} testcases")
            generated_test_files = prog_gen.gen_multi_prog(
                1,
                run_mode,
                core,
                no_threads,
                CONFIG_PT["gen_progs_dir"],
                CONFIG_PT["sw_run_dir"],
                num_progs,
                prog_gen_xargs,
                CONFIG_PT["trash_run_dir"],
                debug_print,
            )
            newly_added_testcases = input_database.add_testcases(
                generated_test_files,
                save_filetypes,
                cb_vul_test=False,
                seed_arm_ids=seed_arm_ids,
            )

            TU.log(
                inputs_log_file,
                (
                    f"Generated {num_progs} testcases | "
                    f"Total testcases = {input_database.num_testcases()}\n"
                ),
                fuzz_time,
            )
            TU.TIMELOG(
                fuzz_time,
                f" -- Generating {num_progs} testcases",
                True,
            )

            # Populate each new arm with enough mutations for simulation.
            for testcase in newly_added_testcases:
                seed_mab.arm_seed[testcase["seed_arm_id"]] = testcase
                testcase.update({"mut_times": sim_batch_size - 1})
            testcases_to_mut = input_database.allocate_testcases_to_mut([])
            fuzz.run_muts(testcases_to_mut, prog_mut_xargs, run_mode)

        # Select one seed arm and simulate its queued testcases.
        TU.TIMELOG(fuzz_time, " -- Running simulations")
        chosen_seed_arm = int(seed_mab.select_arm())
        testcases_to_sim = input_database.get_testcases_to_sim(
            sim_batch_size,
            chosen_seed_arm,
        )
        files_to_sim = [
            testcase["riscv_file"] for testcase in testcases_to_sim
        ]
        save_ids = [testcase["id"] for testcase in testcases_to_sim]
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
        TU.TIMELOG(fuzz_time, " -- Running simulations", True)

        # Merge coverage and calculate global and arm-local increments.
        TU.TIMELOG(fuzz_time, " -- Analyzing coverage data")
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
            "dict",
            merge_mode,
            merged_cov_dict,
            fuzz_time.get_time(False),
            seed_mab.arm_merged_cov_dict[chosen_seed_arm],
        )

        with jsonlines.open(CONFIG_PT["cov_log_file"], "a") as fp:
            for cov_data in cov_increment_dict.values():
                fp.write(cov_data)

        with jsonlines.open(CONFIG_PT["particle_cov_log_file"], "a") as fp:
            fp.write(
                {
                    "itr_no": iteration_num,
                    "arm_id": int(chosen_seed_arm),
                    "num_tests": len(testcases_to_sim),
                }
            )
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
        fuzz.sample_target_cov(
            CONFIG_PT,
            merged_cov_dict,
            cov_sample_state,
            fuzz_time,
            save_ids[-1],
        )

        (
            testcases_to_mut,
            interesting_testcases,
            just_generated_testcases,
        ) = feedback.feedback_based_selection(
            input_database.num_new_testcases(
                seed_arm_id=chosen_seed_arm
            ),
            testcases_to_sim,
            arm_cov_increment_dict,
            num_times_to_mut,
            feedback_cov_types,
        )

        tot_cov_incr_dict = list(cov_increment_dict.values())[-1]
        tot_cov_incr = sum(
            tot_cov_incr_dict["incr"][cov_type]
            for cov_type in feedback_cov_types
        )
        arm_cov_incr_dict = {
            cov_type: sum(
                cov_data["incr"][cov_type]
                for cov_data in arm_cov_increment_dict.values()
            )
            for cov_type in merged_cov_dict
        }
        arm_cov_incr = sum(
            arm_cov_incr_dict[cov_type]
            for cov_type in feedback_cov_types
        )
        if not tot_cov_points_feedback:
            tot_cov_points_feedback = sum(
                len(merged_cov_dict[cov_type])
                for cov_type in feedback_cov_types
            )
        seed_mab.update_arm(
            chosen_seed_arm,
            tot_cov_incr,
            arm_merged_cov_dict,
            arm_cov_incr,
            tot_cov_points_feedback,
        )

        with jsonlines.open(CONFIG_PT["particle_status_log_file"], "a") as fp:
            fp.write(
                {
                    "itr_no": iteration_num,
                    "arm": chosen_seed_arm,
                    "interesting_to_mutate": interesting_testcases,
                    "just_gen_mutate": just_generated_testcases,
                }
            )
            fp.write(
                {
                    "itr_no": iteration_num,
                    "arm": chosen_seed_arm,
                    "counts": list(seed_mab.counts),
                    "values": list(seed_mab.values),
                }
            )
        TU.TIMELOG(fuzz_time, " -- Analyzing coverage data", True)

        # Mutate selected testcases to replenish the chosen arm.
        print("\n\t\tMUTATION START\n")
        TU.TIMELOG(fuzz_time, " -- Mutating testcases")
        testcases_to_mut = input_database.allocate_testcases_to_mut(
            testcases_to_mut
        )
        fuzz.run_muts(testcases_to_mut, prog_mut_xargs, run_mode)
        TU.log(
            inputs_log_file,
            (
                "Mutation done | "
                f"Total testcases = {input_database.num_testcases()}\n"
            ),
            fuzz_time,
        )
        TU.TIMELOG(fuzz_time, " -- Mutating testcases", True)
        print("\n\t\tMUTATION END\n")

        if not tot_cov_points:
            tot_cov_points = sum(
                len(cov_str) for cov_str in merged_cov_dict.values()
            )
        cov_points_ach = sum(
            parse_cov.full_cov_to_cov_num(merged_cov_dict).values()
        )
        cov_per_ach = round((cov_points_ach / tot_cov_points) * 100, 2)
        TU.TIMELOG(
            fuzz_time,
            (
                f" -- {input_database.num_testcases_simulated()} testcases, "
                f"{cov_per_ach}% coverage achieved"
            ),
            False,
            True,
        )

        reset_arms = seed_mab.check_reset(
            chosen_seed_arm,
            input_database.num_new_testcases(chosen_seed_arm) > 0,
        )
        for arm_info in reset_arms:
            input_database.seed_mab_new_testcases[arm_info[0]] = []
        if reset_arms:
            with jsonlines.open(
                CONFIG_PT["particle_status_log_file"],
                "a",
            ) as fp:
                fp.write(
                    {
                        "itr_no": iteration_num,
                        "arm": chosen_seed_arm,
                        "reset_arms": reset_arms,
                    }
                )

        iteration_num += 1

    # Report and persist final campaign statistics.
    if merged_cov_dict:
        tot_cov = {
            key: len(cov_str)
            for key, cov_str in merged_cov_dict.items()
        }
        tot_cov["total"] = sum(tot_cov.values())
        ach_cov = parse_cov.full_cov_to_cov_num(merged_cov_dict, True)
        cov_per = round((ach_cov["total"] / tot_cov["total"]) * 100, 2)
    else:
        tot_cov = {}
        ach_cov = {}
        cov_per = 0

    stats_string = f"\n{'-' * 60}\n"
    stats_string += f"  Benchmark              : {core}\n"
    stats_string += f"  Run time               : {fuzz_time.get_time(False)} sec\n"
    stats_string += (
        "  No. of testcases       : "
        f"{input_database.num_testcases_simulated()}\n"
    )
    stats_string += f"  No. of coverage points : {tot_cov}\n"
    stats_string += f"  No. of points covered  : {ach_cov}\n"
    stats_string += f"  % coverage achieved    : {cov_per}%\n"
    stats_string += f"{'-' * 60}\n"
    TU.TIMELOG(fuzz_time, stats_string, False, True)
    TU.TIMELOG(
        fuzz_time,
        (
            " EndTime: "
            f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        False,
        True,
    )

    if merged_cov_dict:
        with open(CONFIG_PT["merged_cov_file"], "w") as fp:
            json.dump(merged_cov_dict, fp, indent=2)

    if detecting_bugs:
        TU.TIMELOG(
            fuzz_time,
            " Comparing traces to detect mismatches",
            False,
            True,
        )
        detect_bugs.detect_mismatches(*bug_detection_xargs)
        TU.TIMELOG(
            fuzz_time,
            " Comparing traces to detect mismatches",
            True,
            True,
        )

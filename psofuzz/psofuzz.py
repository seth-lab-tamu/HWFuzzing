# This code was cleaned up by Codex.
"""Coverage-guided processor fuzzing with particle swarm optimization."""

import datetime
import json

import jsonlines
import numpy as np

import detect_bugs
import fuzz
import parse_cov
import prog_gen
import thehuzz_utils as TU
from psofuzz import PSO


def _validate_particle_batch(testcases, particle_count):
    particle_ids = [testcase["particle_id"] for testcase in testcases]
    expected = set(range(particle_count))
    actual = set(particle_ids)
    if len(testcases) != particle_count or actual != expected:
        raise ValueError(
            "PSOFuzz requires exactly one testcase per particle; "
            f"expected {sorted(expected)}, got {particle_ids}"
        )


def _particle_increment_dict(
    cov_data_dict,
    testcases_to_sim,
    previous_particle_cov,
    merge_time,
):
    increments = {}
    for testcase in testcases_to_sim:
        testcase_id = testcase["id"]
        particle_id = testcase["particle_id"]
        _, testcase_increment = parse_cov.merge_cov_dicts_incremental(
            {testcase_id: cov_data_dict[testcase_id]},
            "dict",
            previous_particle_cov[particle_id],
            merge_time,
        )
        increments.update(testcase_increment)
    return increments


def run_psofuzz(
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
    detecting_bugs,
    no_threads,
    store_elf_file,
    val_muts,
    opc_muts,
    feedback_cov_types,
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
    """Run a PSOFuzz campaign until one configured stopping limit is reached."""
    if run_mode != "psofuzz":
        raise ValueError("run_psofuzz can only be used with psofuzz run mode")

    input_database = TU.DATABASE(
        core,
        CONFIG_PT["all_progs_dir"],
        CONFIG_PT["hex_file_t"],
        CONFIG_PT["bin_file_t"],
        CONFIG_PT["riscv_file_t"],
        run_mode,
    )
    inputs_log_file = CONFIG_PT["inputs_log_file"]
    save_filetypes = ["riscv", "hex"] if store_elf_file else ["hex"]
    mutation_count = len(val_muts) + len(opc_muts)

    (
        particle_count,
        positions,
        velocities,
        local_best,
        local_best_cov,
        particle_merged_cov,
        particle_total_cov,
        global_best,
        global_best_cov,
        saturate_counts,
        seed_iterations,
        particle_seed_ids,
    ) = PSO.init_pso_variables(
        sim_batch_size,
        mutation_count,
        run_mode,
        initial_cov=nop_cov_dict,
    )

    merged_cov_dict = dict(nop_cov_dict)
    total_cov_points = sum(len(cov) for cov in merged_cov_dict.values())
    achieved_cov = parse_cov.full_cov_to_cov_num(merged_cov_dict)
    coverage_percent = round(
        (sum(achieved_cov.values()) / total_cov_points) * 100, 2
    )
    iteration_num = 0
    cov_sample_state = fuzz.init_cov_sample_state(
        feedback_cov_types,
        cov_sample_interval,
        collect_cov_samples,
    )

    while (
        fuzz_time.time_diff() < max_fuzz_time
        and input_database.num_testcases_simulated() < max_fuzz_progs
        and coverage_percent < target_cov
    ):
        reset_particle_ids = [
            particle_id
            for particle_id, seed_id in enumerate(particle_seed_ids)
            if seed_id == -1
        ]
        queued_particle_ids = {
            testcase["particle_id"] for testcase in input_database.new_testcases
        }
        duplicate_particles = queued_particle_ids & set(reset_particle_ids)
        if duplicate_particles:
            raise ValueError(
                "replacement requested for particles that already have queued "
                f"testcases: {sorted(duplicate_particles)}"
            )

        if reset_particle_ids:
            num_progs = len(reset_particle_ids)
            TU.TIMELOG(
                fuzz_time, f" -- Generating {num_progs} particle seeds"
            )
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
            if len(generated_test_files) != num_progs:
                raise ValueError(
                    "program generator returned "
                    f"{len(generated_test_files)} seeds for {num_progs} particles"
                )
            input_database.add_testcases(
                generated_test_files,
                save_filetypes,
                particle_ids=reset_particle_ids,
            )
            TU.log(
                inputs_log_file,
                (
                    f"Generated {num_progs} particle seeds | "
                    f"Total testcases = {input_database.num_testcases()}\n"
                ),
                fuzz_time,
            )
            TU.TIMELOG(
                fuzz_time,
                f" -- Generating {num_progs} particle seeds",
                True,
            )

        if input_database.num_new_testcases() != particle_count:
            raise ValueError(
                "PSOFuzz must have exactly one queued testcase per particle; "
                f"found {input_database.num_new_testcases()}, "
                f"expected {particle_count}"
            )

        TU.TIMELOG(fuzz_time, " -- Running simulations")
        testcases_to_sim = input_database.get_testcases_to_sim(particle_count)
        _validate_particle_batch(testcases_to_sim, particle_count)
        for testcase in testcases_to_sim:
            particle_seed_ids[testcase["particle_id"]] = testcase["id"]

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

        TU.TIMELOG(fuzz_time, " -- Analyzing coverage data")
        merge_time = fuzz_time.get_time(False)
        previous_particle_cov = [
            dict(coverage) for coverage in particle_merged_cov
        ]
        particle_increment_dict = _particle_increment_dict(
            cov_data_dict,
            testcases_to_sim,
            previous_particle_cov,
            merge_time,
        )
        (
            merged_cov_dict,
            cov_increment_dict,
            particle_merged_cov,
            particle_total_cov,
        ) = parse_cov.merge_cov_dicts(
            cov_data_dict,
            "dict",
            merge_mode=fuzz.get_merge_mode(run_mode),
            initial_cov=merged_cov_dict,
            time=merge_time,
            particle_seed_ids=particle_seed_ids,
            particle_initial_cov=previous_particle_cov,
        )

        with jsonlines.open(CONFIG_PT["cov_log_file"], "a") as fp:
            for cov_data in cov_increment_dict.values():
                fp.write(cov_data)

        with jsonlines.open(
            CONFIG_PT["particle_cov_log_file"], "a"
        ) as fp:
            for particle_id, coverage in enumerate(particle_total_cov):
                fp.write(
                    {
                        "itr_no": iteration_num,
                        "p_id": particle_id,
                        "seed_id": particle_seed_ids[particle_id],
                        "tot": coverage,
                    }
                )

        fuzz.store_interesting_tests(
            CONFIG_PT,
            testcases_to_sim,
            cov_data_dict,
            particle_increment_dict,
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
            local_best,
            local_best_cov,
            global_best,
            global_best_cov,
            saturate_counts,
            particle_seed_ids,
            testcases_to_mut,
            particle_mutations,
        ) = PSO.update_l_gbest(
            particle_total_cov,
            feedback_cov_types,
            local_best,
            local_best_cov,
            global_best,
            global_best_cov,
            saturate_counts,
            positions,
            particle_seed_ids,
            testcases_to_sim,
        )
        reset_particle_ids = {
            particle_id
            for particle_id, seed_id in enumerate(particle_seed_ids)
            if seed_id == -1
        }
        (
            positions,
            velocities,
            seed_iterations,
            saturate_counts,
        ) = PSO.update_P_V(
            local_best,
            global_best,
            positions,
            velocities,
            seed_iterations,
            particle_seed_ids,
            saturate_counts,
            mutation_count,
        )
        baseline_counts = parse_cov.full_cov_to_cov_num(
            nop_cov_dict, True
        )
        for particle_id in reset_particle_ids:
            particle_merged_cov[particle_id] = dict(nop_cov_dict)
            particle_total_cov[particle_id] = dict(baseline_counts)
            local_best[particle_id] = np.copy(positions[particle_id])
            local_best_cov[particle_id] = dict(baseline_counts)

        with jsonlines.open(
            CONFIG_PT["particle_status_log_file"], "a"
        ) as fp:
            for particle_id in range(particle_count):
                fp.write(
                    {
                        "itr_no": iteration_num,
                        "p_id": particle_id,
                        "lbest": np.round(
                            local_best[particle_id], 4
                        ).tolist(),
                        "lbest_cov": local_best_cov[particle_id],
                        "saturate_ct": saturate_counts[particle_id],
                        "particle_seed_id": particle_seed_ids[particle_id],
                        "reset": particle_id in reset_particle_ids,
                        "times_to_mut": particle_mutations[particle_id],
                        "P": np.round(
                            positions[particle_id], 4
                        ).tolist(),
                        "V": np.round(
                            velocities[particle_id], 4
                        ).tolist(),
                        "seeds_itr": seed_iterations[particle_id],
                    }
                )
            fp.write(
                {
                    "itr_no": iteration_num,
                    "gbest": np.round(global_best, 4).tolist(),
                    "gbest_cov": global_best_cov,
                }
            )
        TU.TIMELOG(fuzz_time, " -- Analyzing coverage data", True)

        TU.TIMELOG(fuzz_time, " -- Mutating testcases")
        testcases_to_mut = input_database.allocate_testcases_to_mut(
            testcases_to_mut
        )
        generated_count = fuzz.run_muts(
            testcases_to_mut,
            prog_mut_xargs,
            run_mode,
            mutation_weights=positions,
        )
        TU.log(
            inputs_log_file,
            (
                f"Mutation generated {generated_count} testcases | "
                f"Total testcases = {input_database.num_testcases()}\n"
            ),
            fuzz_time,
        )
        TU.TIMELOG(fuzz_time, " -- Mutating testcases", True)

        achieved_cov = parse_cov.full_cov_to_cov_num(merged_cov_dict)
        coverage_percent = round(
            (sum(achieved_cov.values()) / total_cov_points) * 100, 2
        )
        TU.TIMELOG(
            fuzz_time,
            (
                f" -- {input_database.num_testcases_simulated()} testcases, "
                f"{coverage_percent}% coverage achieved"
            ),
            False,
            True,
        )
        iteration_num += 1

    total_cov = {
        cov_type: len(cov_string)
        for cov_type, cov_string in merged_cov_dict.items()
    }
    total_cov["total"] = sum(total_cov.values())
    achieved_cov = parse_cov.full_cov_to_cov_num(merged_cov_dict, True)
    coverage_percent = round(
        (achieved_cov["total"] / total_cov["total"]) * 100, 2
    )
    stats_string = f"\n{'-' * 60}\n"
    stats_string += f"  Benchmark              : {core}\n"
    stats_string += f"  Run time               : {fuzz_time.get_time(False)} sec\n"
    stats_string += (
        "  No. of testcases       : "
        f"{input_database.num_testcases_simulated()}\n"
    )
    stats_string += f"  No. of coverage points : {total_cov}\n"
    stats_string += f"  No. of points covered  : {achieved_cov}\n"
    stats_string += f"  % coverage achieved    : {coverage_percent}%\n"
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

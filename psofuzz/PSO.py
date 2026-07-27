# This code was cleaned up by Codex.
"""Particle-swarm state used by the PSOFuzz mutation scheduler."""

import numpy as np
from sklearn.preprocessing import normalize


RESET_PARAMETER = 3
# Keep the original public name for compatibility with older scripts.
reset_parameter = RESET_PARAMETER


def _coverage_counts(initial_cov):
    if not initial_cov:
        return {}
    counts = {cov_type: cov_string.count("1") for cov_type, cov_string in initial_cov.items()}
    counts["total"] = sum(counts.values())
    return counts


def _normalize_positions(positions):
    """L1-normalize positions and recover rows with no usable weight."""
    positions = np.asarray(positions, dtype=float)
    positions[positions < 0] = 0
    zero_rows = np.isclose(np.sum(positions, axis=1), 0)
    if np.any(zero_rows):
        positions[zero_rows] = np.random.randint(
            1, 100, size=(int(np.sum(zero_rows)), positions.shape[1])
        )
    return normalize(positions, axis=1, norm="l1")


def _normalize_velocities(velocities):
    return normalize(np.asarray(velocities, dtype=float), axis=1, norm="l1")


def init_pso_variables(
    sim_batch_size, tot_num_muts, run_mode, initial_cov=None
):
    """Initialize one PSO particle for every simulation slot."""
    if run_mode != "psofuzz":
        return (
            None,
            [],
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    if sim_batch_size <= 0:
        raise ValueError("PSOFuzz requires sim_batch_size to be greater than zero")
    if tot_num_muts <= 0:
        raise ValueError("PSOFuzz requires at least one mutation operator")

    num_particle = sim_batch_size
    (
        positions,
        velocities,
        local_best,
        local_best_cov,
        particle_merged_cov,
        total_particle_merged_cov,
        global_best,
        global_best_cov,
    ) = init_pos_v(num_particle, tot_num_muts, initial_cov)

    return (
        num_particle,
        positions,
        velocities,
        local_best,
        local_best_cov,
        particle_merged_cov,
        total_particle_merged_cov,
        global_best,
        global_best_cov,
        [0 for _ in range(num_particle)],
        [True for _ in range(num_particle)],
        [-1 for _ in range(num_particle)],
    )


def init_pos_v(num_particle, num_mut_algo, initial_cov=None):
    """Initialize particle positions, velocity, and baseline coverage state."""
    positions = _normalize_positions(
        np.random.randint(100, size=(num_particle, num_mut_algo))
    )
    velocities = _normalize_velocities(
        np.random.randint(
            low=-100, high=100, size=(num_particle, num_mut_algo)
        )
    )

    baseline_counts = _coverage_counts(initial_cov)
    local_best = np.copy(positions)
    local_best_cov = [dict(baseline_counts) for _ in range(num_particle)]
    particle_merged_cov = [
        dict(initial_cov) if initial_cov is not None else None
        for _ in range(num_particle)
    ]
    total_particle_merged_cov = [
        dict(baseline_counts) for _ in range(num_particle)
    ]
    global_best = np.copy(positions[0])
    global_best_cov = dict(baseline_counts)

    return (
        positions,
        velocities,
        local_best,
        local_best_cov,
        particle_merged_cov,
        total_particle_merged_cov,
        global_best,
        global_best_cov,
    )


def update_l_gbest(
    particle_total_cov,
    target_covs,
    local_best,
    local_best_cov,
    global_best,
    global_best_cov,
    saturate_counts,
    positions,
    particle_seed_ids,
    testcases_to_sim,
):
    """Update local/global bests and mark saturated particles for replacement."""
    particle_count = len(positions)
    if len(particle_total_cov) != particle_count:
        raise ValueError(
            "PSOFuzz coverage count does not match the particle count"
        )

    testcase_by_particle = {}
    for testcase in testcases_to_sim:
        particle_id = testcase["particle_id"]
        if particle_id not in range(particle_count):
            raise ValueError(f"invalid PSOFuzz particle id {particle_id}")
        if particle_id in testcase_by_particle:
            raise ValueError(
                f"particle {particle_id} received more than one testcase"
            )
        if particle_seed_ids[particle_id] != testcase["id"]:
            raise ValueError(
                f"particle {particle_id} expected testcase "
                f"{particle_seed_ids[particle_id]}, got {testcase['id']}"
            )
        testcase_by_particle[particle_id] = testcase

    missing_particles = set(range(particle_count)) - set(testcase_by_particle)
    if missing_particles:
        raise ValueError(
            f"particles without a testcase: {sorted(missing_particles)}"
        )

    particle_mutations = [-1 for _ in range(particle_count)]
    for particle_id, coverage in enumerate(particle_total_cov):
        missing_cov = [
            cov_type
            for cov_type in target_covs
            if cov_type not in coverage
        ]
        if missing_cov:
            raise ValueError(
                f"particle {particle_id} is missing coverage types {missing_cov}"
            )

        current_score = sum(coverage[cov_type] for cov_type in target_covs)
        best_score = sum(
            local_best_cov[particle_id].get(cov_type, 0)
            for cov_type in target_covs
        )
        if current_score > best_score:
            local_best[particle_id] = np.copy(positions[particle_id])
            local_best_cov[particle_id] = dict(coverage)
            saturate_counts[particle_id] = 0
        else:
            saturate_counts[particle_id] += 1

        testcase = testcase_by_particle[particle_id]
        if saturate_counts[particle_id] > RESET_PARAMETER:
            particle_seed_ids[particle_id] = -1
            testcase["mut_times"] = 0
            particle_mutations[particle_id] = 0
        else:
            testcase["mut_times"] = 1
            particle_mutations[particle_id] = 1

    global_score = sum(
        global_best_cov.get(cov_type, 0) for cov_type in target_covs
    )
    for particle_id in range(particle_count):
        local_score = sum(
            local_best_cov[particle_id].get(cov_type, 0)
            for cov_type in target_covs
        )
        if local_score > global_score:
            global_best = np.copy(local_best[particle_id])
            global_best_cov = dict(local_best_cov[particle_id])
            global_score = local_score

    return (
        local_best,
        local_best_cov,
        global_best,
        global_best_cov,
        saturate_counts,
        particle_seed_ids,
        testcases_to_sim,
        particle_mutations,
    )


def update_P_V(
    local_best,
    global_best,
    positions,
    velocities,
    seed_iterations,
    particle_seed_ids,
    saturate_counts,
    num_mut_algo,
):
    """Advance the swarm and reinitialize particles whose seeds saturated."""
    inertia = 0.5
    local_weight = 0.5
    global_weight = 0.5

    for particle_id in range(len(positions)):
        if particle_seed_ids[particle_id] == -1:
            saturate_counts[particle_id] = 0
            seed_iterations[particle_id] = True
            positions[particle_id] = np.random.randint(
                1, 100, size=num_mut_algo
            )
            velocities[particle_id] = np.random.randint(
                low=-100, high=100, size=num_mut_algo
            )
        elif not seed_iterations[particle_id]:
            velocities[particle_id] = (
                inertia * velocities[particle_id]
                + local_weight
                * (local_best[particle_id] - positions[particle_id])
                + global_weight * (global_best - positions[particle_id])
            )
            positions[particle_id] += velocities[particle_id]
            positions[particle_id][positions[particle_id] < 0] = 0
        else:
            seed_iterations[particle_id] = False

    positions = _normalize_positions(positions)
    velocities = _normalize_velocities(velocities)
    return positions, velocities, seed_iterations, saturate_counts

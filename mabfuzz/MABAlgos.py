#!/usr/bin/env python3
"""Multi-armed bandit policies used by MABFuzz and ReFuzz.
Created on Tue Aug 15 19:55:58 2023

@author: gohil.vasudev
The code is cleaned up by Codex
"""

import numpy as np


class MABalgos:
    """Shared reward tracking and arm-reset behavior for MAB policies."""

    def __init__(self, n_arms, n_picks_reset):
        self.n_arms = n_arms
        self.values = np.zeros(n_arms)
        self.counts = np.zeros(n_arms)
        self.n_picks_reset = n_picks_reset
        self.arm_merged_cov_dict = [None for _ in range(n_arms)]
        self.arm_arm_cov_incr_hist = [[] for _ in range(n_arms)]
        self.arm_seed = [None for _ in range(n_arms)]

    def select_arm(self):
        """Select an arm according to the policy."""
        raise NotImplementedError

    def update(self, arm, reward):
        """Update policy state after observing an arm reward."""
        raise NotImplementedError

    @staticmethod
    def compute_reward(tot_incr_cov, arm_incr_cov):
        """Combine global and arm-local coverage increments into one reward."""
        return (tot_incr_cov * 0.75) + (arm_incr_cov * 0.25)

    def update_arm(
        self,
        arm,
        tot_incr_cov,
        arm_merged_cov_dict,
        arm_incr_cov,
        tot_cov_points,
    ):
        """Record coverage feedback and update the selected arm."""
        self.tot_cov_points = tot_cov_points
        self.arm_merged_cov_dict[arm] = arm_merged_cov_dict
        self.arm_arm_cov_incr_hist[arm].append(arm_incr_cov)
        self.arm_arm_cov_incr_hist[arm] = self.arm_arm_cov_incr_hist[arm][
            -self.n_picks_reset:
        ]

        reward = self.compute_reward(tot_incr_cov, arm_incr_cov)
        self.update(arm, reward)

    def check_reset(self, arm, arm_has_batch_testcases):
        """Reset a stalled or depleted arm and return its reset records."""
        reset_arms = []

        # RC1: the arm produced no local coverage in its recent selections.
        arm_history = self.arm_arm_cov_incr_hist[arm]
        if (
            len(arm_history) == self.n_picks_reset
            and sum(arm_history) == 0
        ):
            reset_arms.append(
                [arm, "RC1", len(arm_history), sum(arm_history)]
            )

        # RC2: the selected arm has no remaining testcases for a full batch.
        if not arm_has_batch_testcases:
            reset_arms.append([arm, "RC2", arm_has_batch_testcases])

        # Preserve one reset call per reset record, including simultaneous RC1/RC2.
        for arm_info in reset_arms:
            self.reset_arm(arm_info[0])

        return reset_arms

    def reset_arm(self, arm):
        """Clear learned and coverage state for one arm."""
        self.values[arm] = 0
        self.counts[arm] = 0
        self.arm_merged_cov_dict[arm] = None
        self.arm_arm_cov_incr_hist[arm] = []


class Greedy(MABalgos):
    """Always choose the arm with the highest mean observed reward."""

    def select_arm(self):
        return np.argmax(self.values)

    def update(self, arm, reward):
        self.counts[arm] += 1
        self.values[arm] += (reward - self.values[arm]) / self.counts[arm]


class EpsilonGreedy(MABalgos):
    """Choose a random arm with probability 0.2, otherwise act greedily."""

    def __init__(self, *xargs):
        super().__init__(*xargs)
        self.epsilon = 0.2

    def select_arm(self):
        if np.random.rand() < self.epsilon:
            return np.random.choice(self.n_arms)
        return np.argmax(self.values)

    def update(self, arm, reward):
        self.counts[arm] += 1
        self.values[arm] += (reward - self.values[arm]) / self.counts[arm]


class UCB(MABalgos):
    """Select arms using an upper-confidence-bound exploration bonus."""

    def __init__(self, *xargs):
        super().__init__(*xargs)
        self.time = 0

    def select_arm(self):
        self.time += 1
        ucb_values = self.values + np.sqrt(
            (2 * np.log(self.time)) / (self.counts + 1e-6)
        )
        return np.argmax(ucb_values)

    def update(self, arm, reward):
        self.counts[arm] += 1
        self.values[arm] += (reward - self.values[arm]) / self.counts[arm]


class EXP3(MABalgos):
    """Select arms using the EXP3 adversarial-bandit policy."""

    def __init__(self, *xargs):
        super().__init__(*xargs)
        self.gamma = 0.1
        self.weights = np.ones(self.n_arms)

    def select_arm(self):
        normalized_weights = self.weights / np.sum(self.weights)
        normalized_weights[np.isnan(normalized_weights)] = 0.0
        self.probabilities = (
            (1 - self.gamma) * normalized_weights
        ) + (self.gamma / self.n_arms)
        arm = np.random.choice(self.n_arms, p=self.probabilities)
        self.counts[arm] += 1
        return arm

    def update(self, arm, reward):
        normalized_reward = reward / self.tot_cov_points
        estimated_reward = normalized_reward / self.probabilities[arm]
        weight_update = np.exp(
            (self.gamma / self.n_arms) * estimated_reward
        )
        self.weights[arm] *= weight_update
        self.values = self.weights

    def reset_arm(self, arm):
        super().reset_arm(arm)
        self.weights[arm] = (
            (np.sum(self.weights) - self.weights[arm]) / (self.n_arms - 1)
        )


_SUPPORTED_ALGORITHMS = {
    "Greedy": Greedy,
    "UCB": UCB,
    "EpsilonGreedy": EpsilonGreedy,
    "EXP3": EXP3,
}


def create_mab_object(mab_algo, xargs):
    """Create one of the MAB policies supported by the command-line interface."""
    try:
        algorithm_class = _SUPPORTED_ALGORITHMS[mab_algo]
    except KeyError as exc:
        supported = ", ".join(_SUPPORTED_ALGORITHMS)
        raise ValueError(
            f"Unsupported MAB algorithm {mab_algo!r}; choose one of: {supported}"
        ) from exc
    return algorithm_class(*xargs)

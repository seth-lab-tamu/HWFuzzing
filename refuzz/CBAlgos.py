#!/usr/bin/env python3
"""Implement the contextual-bandit algorithm used by ReFuzz training.

Author: Chen Chen
The code is cleaned up by Codex
"""
from abc import ABC, abstractmethod
import numpy as np
import random, json
from mabwiser.mab import MAB, LearningPolicy, NeighborhoodPolicy


class CBalgoBase(ABC):
    def __init__(self, context, num_picks, num_seeds):
        self.context_train = context
        self.num_picks = num_picks
        self.num_seeds = num_seeds
        self.seeds = []
        self.context = [[context]]
        self.policy = None
        self.ave_rewards = {}

    def init_arms(self, seeds=[]):
        assert len(self.seeds) == 0
        for seed in seeds:
            self.seeds.append(seed)
            self.ave_rewards[seed] = {
                "ave": 0,
                "each_t": [],
                "removed": False,
                "select_count": 0
            }

        self.policy = MAB(self.seeds, LearningPolicy.EpsilonGreedy(epsilon=0.2), \
                          neighborhood_policy=NeighborhoodPolicy.Radius(radius=5))

    def select_arm(self):
        seed = self.policy.predict(self.context)
        assert seed in self.ave_rewards
        return seed

    def update_policy(self, seed, reward):
        self.policy.partial_fit(decisions=[seed], rewards=[reward], contexts=self.context)
        self.ave_rewards[seed]["each_t"].append(reward)
        self.ave_rewards[seed]["ave"] = np.mean(self.ave_rewards[seed]["each_t"])
        self.ave_rewards[seed]["select_count"] += 1

    @abstractmethod
    def dump_training_results(self):
        pass


class CBalgo_Adaptive(CBalgoBase):
    def __init__(self, context, reset_window, adaptive_threshold,
                 adaptive_pick_threshold, num_picks, num_seeds):
        super().__init__(context, num_picks, num_seeds)
        self.reset_window = reset_window
        self.adaptive_threshold = adaptive_threshold
        self.adaptive_pick_threshold = adaptive_pick_threshold
        self.seed_candidates = []
        self.candidates_policy_scores = []
        self.candidates_ave_rewards = []
        self.candidates_select_counts = []

    def check_reset(self, seed, seed_list):
        predict_exps = self.policy.predict_expectations(self.context)
        seed_policy_score = predict_exps[seed]
        is_reset = False
        if len(self.ave_rewards[seed]["each_t"]) >= self.reset_window:
            if self.ave_rewards[seed]["ave"] <= 0 or (
                self.ave_rewards[seed]["ave"] > 0 and seed_policy_score > self.adaptive_threshold
                or len(self.ave_rewards[seed]["each_t"]) > self.adaptive_pick_threshold):
                is_reset = True
                if (self.ave_rewards[seed]["ave"] > 0 and seed_policy_score > self.adaptive_threshold):
                    self.seed_candidates.append(seed)
                    self.candidates_policy_scores.append(seed_policy_score)
                    self.candidates_ave_rewards.append(self.ave_rewards[seed]["ave"])
                    self.candidates_select_counts.append(self.ave_rewards[seed]["select_count"])
                seed_list = self.drop_add_new_seed(seed, seed_list)

        return is_reset, seed_list

    def drop_add_new_seed(self, tar_seed, seed_list):
        self.policy.remove_arm(tar_seed)
        self.seeds.remove(tar_seed)
        self.ave_rewards[tar_seed]["removed"] = True

        new_seed = seed_list[random.randint(0, len(seed_list)-1)]
        self.seeds.append(new_seed)
        self.ave_rewards[new_seed] = {
            "ave": 0,
            "each_t": [],
            "removed": False,
            "select_count": 0
        }
        self.policy.add_arm(arm=new_seed)
        seed_list.remove(new_seed)

        return seed_list

    def dump_training_results(self, log_file):
        temp_data = []
        for i, seed in enumerate(self.seed_candidates):
            temp_data.append({
                "seed": seed,
                "policy_score": self.candidates_policy_scores[i],
                "ave_reward": self.candidates_ave_rewards[i],
                "select_count": self.candidates_select_counts[i]
            })

        temp_data = sorted(temp_data, key=lambda x: x["policy_score"], reverse=True)

        if len(temp_data) > self.num_seeds:
            temp_data = temp_data[:self.num_seeds]

        train_dict = {
            "context": self.context_train,
            "seeds": [x["seed"] for x in temp_data],
            "policy_scores": [x["policy_score"] for x in temp_data],
            "ave_rewards": [x["ave_reward"] for x in temp_data],
            "select_counts": [x["select_count"] for x in temp_data]
        }
        with open(log_file, "w") as f:
            json.dump(train_dict, f, indent=2)

        dumped_seeds = [x["seed"] for x in temp_data]
        return dumped_seeds

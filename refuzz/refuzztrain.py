"""Train ReFuzz contextual-bandit models and prepare coverage data.

Author: Chen Chen
The code is cleaned up by Codex
"""
import os
import sys
import faulthandler
import re
import json
import argparse
import shutil
import random
import copy
import math
import subprocess
import multiprocessing as mp
from typing import Dict, List, Tuple, Optional, Any, Callable
from tqdm import tqdm
from os.path import join, abspath
from string import Template

faulthandler.enable()

REFUZZ_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(REFUZZ_DIR)
for _path in (REPO_ROOT, join(REPO_ROOT, "thehuzz"), join(REPO_ROOT, "utils"), join(REPO_ROOT, "benchmarks"), REFUZZ_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)
os.environ.setdefault("THEHUZZ_ROOT", REPO_ROOT)

import thehuzz.thehuzz_utils as thehuzz_utils
import thehuzz.parse_cov as parse_cov
import jsonlines
import config as project_config
import rc_inst_list
import cva6_inst_list
import boomv3_inst_list
import boomv4_inst_list

_CBALGOS = None


def get_cbalgos_module():
    """
    Import CBAlgos only for CB training paths. It pulls in optional native/ML
    dependencies, so keeping it lazy lets other CLI methods fail cleanly.
    """
    global _CBALGOS
    if _CBALGOS is None:
        import CBAlgos as cbalgos
        _CBALGOS = cbalgos
    return _CBALGOS

RISCV_SEED_PATTERN = r"^(?P<fuzzer>[^_]+)_(?P<core>cva6|rc|boomv3|boomv4)_(?P<file_id>\d+)\.riscv$"
ROUND_RISCV_SEED_PATTERN = r"^(?P<fuzzer>[^_]+)_(?P<core>cva6|rc|boomv3|boomv4)_r(?P<round>\d+)_(?P<file_id>\d+)\.riscv$"


def require_env(var_name: str) -> str:
    """
    Return environment var or raise a descriptive exception.
    """
    val = os.getenv(var_name)
    if not val:
        raise EnvironmentError(f"Required environment variable '{var_name}' is not set")
    return val


def assert_file_exists(path: str, msg: Optional[str] = None) -> None:
    """
    Raise FileNotFoundError if file doesn't exist.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(msg or f"File not found: {path}")


def assert_dir_exists(path: str, msg: Optional[str] = None) -> None:
    """
    Raise FileNotFoundError if directory doesn't exist.
    """
    if not os.path.isdir(path):
        raise FileNotFoundError(msg or f"Directory not found: {path}")


def ensure_dir_exists(path: str) -> None:
    """
    Ensure directory exists for writing outputs.
    """
    os.makedirs(path, exist_ok=True)


def validate_cleanup_target(path: str) -> str:
    """
    Return a normalized cleanup target after enforcing TRAIN_ROOT boundaries.

    Cleanup targets may be files or directories, but must be descendants of
    TRAIN_ROOT. Symlinked targets are rejected so cleanup never follows a
    destination outside the generated training tree.
    """
    train_root_abs = abspath(TRAIN_ROOT)
    target_abs = abspath(path)
    train_root_real = os.path.realpath(train_root_abs)
    target_real = os.path.realpath(target_abs)

    if target_abs == train_root_abs:
        raise ValueError(f"Refusing to remove TRAIN_ROOT itself: {target_abs}")
    try:
        within_train_root = os.path.commonpath([train_root_real, target_real]) == train_root_real
    except ValueError:
        within_train_root = False
    if not within_train_root:
        raise ValueError(
            f"Refusing to remove destination outside TRAIN_ROOT '{train_root_abs}': {target_abs}"
        )
    if os.path.lexists(target_abs) and os.path.islink(target_abs):
        raise ValueError(f"Refusing to remove symlinked destination: {target_abs}")
    return target_abs


def confirm_and_remove_destinations(paths: List[str]) -> List[str]:
    """
    Confirm every existing destination before removing any of them.

    Only an exact trimmed ``y`` confirms a target. Any other response,
    including EOF, aborts without deleting any destination.
    """
    normalized_targets: List[str] = []
    seen = set()
    for path in paths:
        target = validate_cleanup_target(path)
        if target in seen or not os.path.lexists(target):
            continue
        seen.add(target)
        normalized_targets.append(target)

    for target in normalized_targets:
        try:
            response = input(
                f"Remove existing destination '{target}'? Enter y to confirm: "
            )
        except EOFError as exc:
            raise RuntimeError(
                "Cleanup cancelled because confirmation input reached EOF; "
                "no destinations were removed."
            ) from exc
        if response.strip() != "y":
            raise RuntimeError(
                f"Cleanup cancelled for '{target}'; no destinations were removed."
            )

    # Revalidate all targets after confirmation and before the first removal
    # to reduce the chance of a path or symlink swap during prompting.
    for target in normalized_targets:
        validate_cleanup_target(target)

    for target in normalized_targets:
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        print(f"Removed existing destination: {target}")
    return normalized_targets


def safe_json_load(path: str) -> dict:
    """
    Load JSON with clear error on failure.
    """
    assert_file_exists(path)
    try:
        with open(path, "r") as fp:
            return json.load(fp)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in {path}: {e}") from e


def parse_seed_filename(filename: str) -> Dict[str, Optional[str]]:
    """
    Validate and parse legacy and round-aware minimized seed filenames.
    """
    base = os.path.basename(filename)
    for pattern in (ROUND_RISCV_SEED_PATTERN, RISCV_SEED_PATTERN):
        m = re.match(pattern, base)
        if m:
            return {
                "fuzzer": m.group("fuzzer"),
                "core": m.group("core"),
                "round": m.groupdict().get("round"),
                "file_id": m.group("file_id"),
                "stem": os.path.splitext(base)[0],
            }
    raise ValueError(
        "Filename does not match expected seed patterns "
        f"'{RISCV_SEED_PATTERN}' or '{ROUND_RISCV_SEED_PATTERN}': {filename}"
    )


def parse_riscv_filename(filename: str) -> Tuple[str, str, str]:
    """
    Validate and parse a riscv filename into fuzzer, source core, and test id.
    """
    seed_info = parse_seed_filename(filename)
    return seed_info["fuzzer"], seed_info["core"], seed_info["file_id"]


def seed_coverage_key(filename: str) -> str:
    """
    Return the stable coverage dump key for a minimized seed filename.
    """
    return parse_seed_filename(filename)["stem"]


def filter_training_seed_corpus(corpus_list: List[str], training_processors: List[str],
                                min_seed_count: int, context: str, log: bool = True) -> List[str]:
    """
    Keep only corpus seeds generated from processors used for training.
    """
    allowed_processors = set(training_processors)
    kept: List[str] = []
    filtered = 0

    for seed in sorted(corpus_list):
        if not seed.endswith(".riscv"):
            continue
        try:
            seed_info = parse_seed_filename(seed)
        except ValueError as e:
            raise ValueError(f"Invalid ReFuzz corpus seed filename for {context}: {seed}") from e

        if seed_info["core"] in allowed_processors:
            kept.append(seed)
        else:
            filtered += 1

    if log:
        print(
            f"[train] {context}: kept {len(kept)} seed(s), filtered {filtered} seed(s) "
            f"for training processors {sorted(allowed_processors)}"
        )

    if len(kept) < min_seed_count:
        raise ValueError(
            f"Not enough ReFuzz training seeds for {context}: kept {len(kept)} seed(s) "
            f"for processors {sorted(allowed_processors)}, need at least {min_seed_count}"
        )

    return kept


def get_core_info(cpu: str) -> Tuple[str, List[str]]:
    """
    Map cpu short name to full name and instance list.
    """
    if cpu == "rc":
        return "Rocket", rc_inst_list.l
    if cpu == "cva6":
        return "CVA6", cva6_inst_list.l
    if cpu == "boomv3":
        return "SmallBoomV3", boomv3_inst_list.l
    if cpu == "boomv4":
        return "SmallBoomV4", boomv4_inst_list.l
    raise ValueError(f"Unsupported CPU: {cpu}")


class CoverageOptimizationResult:
    """
    Simple container for solver results.
    """
    def __init__(self, status_str: str, chosen_ids: List[str], obj_value: Optional[float]) -> None:
        self.status_str = status_str
        self.chosen_ids = chosen_ids
        self.obj_value = obj_value


_ORTOOLS_CP_MODEL = None


def get_ortools_cp_model():
    """
    Import and cache OR-Tools before tqdm creates its monitor thread.

    Importing cp_model after a tqdm progress bar has started can segfault in
    the rlfuzz Python 3.12 environment, so seed_mini calls this before loading
    coverage data with tqdm.
    """
    global _ORTOOLS_CP_MODEL
    if _ORTOOLS_CP_MODEL is None:
        try:
            from ortools.sat.python import cp_model
        except ImportError as e:
            raise RuntimeError("OR-Tools is required for seed minimization. Install with: pip install ortools") from e
        _ORTOOLS_CP_MODEL = cp_model
    return _ORTOOLS_CP_MODEL


def build_opt_model_ortools(all_cov_data: Dict[str, Dict[str, str]]):
    """
    Convert the coverage selection problem into a CP-SAT ILP.

    all_cov_data:
        dict[str -> cov_dict]
        where each cov_dict is: {cov_type: "01010101..."} (string of '0'/'1' per coverage point)

    Returns:
        (model, x_vars, cover_constraints_info)
    """
    cp_model = get_ortools_cp_model()

    cov_ids = list(all_cov_data.keys())

    all_merged_cov_dict = parse_cov.merge_cov_dicts_direct([all_cov_data, None, 'dict'])[0]
    always_cov_dict = parse_cov.check_always_covered([all_cov_data, None, 'dict'])[0]

    model = cp_model.CpModel()

    x_vars = {cid: model.NewBoolVar(f"bool_{cid}") for cid in cov_ids}

    cover_constraints_info = []

    for cov_type, cov_str_any in all_merged_cov_dict.items():
        cov_str_all = always_cov_dict[cov_type]
        assert len(cov_str_any) == len(cov_str_all)
        for idx, (any_bit, all_bit) in enumerate(zip(cov_str_any, cov_str_all)):
            if any_bit == '0' or all_bit == '1':
                continue

            covering_list = []
            for cid in cov_ids:
                bit_val = int(all_cov_data[cid][cov_type][idx])
                if bit_val == 1:
                    covering_list.append(x_vars[cid])

            if not covering_list:
                continue

            model.Add(sum(covering_list) >= 1)
            cover_constraints_info.append((cov_type, idx, [v.Name() for v in covering_list]))

    model.Minimize(sum(x_vars[cid] for cid in cov_ids))

    return model, x_vars, cover_constraints_info


def solve_opt_model_ortools(model: Any, x_vars: Dict[str, Any], log_output: bool = True):
    """
    Solve CP-SAT model and extract chosen cov_dicts.
    """
    cp_model = get_ortools_cp_model()
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen_ids = [cid for cid, var in x_vars.items() if solver.Value(var) >= 1]
        status_str = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
        obj_value = solver.ObjectiveValue()
        if log_output:
            print(f"[minimizer] Solver status: {status_str}")
            print(f"[minimizer] Obj (number of cov_dicts used): {obj_value}")
            if chosen_ids:
                print("[minimizer] Selected coverage dict IDs:")
                for cid in sorted(chosen_ids, key=lambda x: int(x)):
                    print(f"    Use {cid}")
        return CoverageOptimizationResult(status_str, chosen_ids, obj_value)

    return CoverageOptimizationResult("INFEASIBLE_OR_UNKNOWN", [], None)


def generate_optimized_solution(cov_dict_filelist: List[str], cov_dict_ids: List[str], fuzzer: str, cpu: str, minimized_sol_path: str):
    """
    1. Load all coverage dicts from JSON.
    2. Solve coverage minimization.
    4. Dump result to JSON in INTEREST_TESTS_ROOT/<fuzzer>_interesting_tests/<tar_cov_metric>/<cpu>/
       using CPLEX-like structure so get_sol() can parse it.
    """
    # Import OR-Tools before tqdm starts; importing it after tqdm creates its
    # monitor thread has segfaulted in the rlfuzz environment.
    get_ortools_cp_model()

    all_cov_data = {}
    for (cov_dict_file, cov_dict_id) in tqdm(list(zip(cov_dict_filelist, cov_dict_ids)), desc="[minimizer] loading cov data"):
        all_cov_data[cov_dict_id] = safe_json_load(cov_dict_file)

    model, x_vars, _ = build_opt_model_ortools(all_cov_data)

    result = solve_opt_model_ortools(model, x_vars, log_output=True)

    sol_json = {"CPLEXSolution": {"variables": []}}
    for cid in x_vars.keys():
        val = 1 if cid in result.chosen_ids else 0
        sol_json["CPLEXSolution"]["variables"].append({
            "name": f"bool_{cid}",
            "value": f"{float(val):.1f}",
        })

    ensure_dir_exists(minimized_sol_path)
    out_name = f"{fuzzer}_{cpu}_solution.json"
    out_file = join(minimized_sol_path, out_name)
    with open(out_file, "w") as fp:
        json.dump(sol_json, fp, indent=2)
    print(f"[minimizer] Wrote solution file: {out_file}")

    return result


def get_sol(sol_file: str) -> List[int]:
    assert_file_exists(sol_file)
    sol_data_json = safe_json_load(sol_file)
    sol = []
    for variable in sol_data_json.get("CPLEXSolution", {}).get("variables", []):
        if variable.get("value") == '1.0':
            name_data = re.match(r'bool_([0-9]+)', variable.get("name", ""))
            if name_data:
                sol.append(int(name_data.group(1)))
    return sol


def _sort_numeric_strings(values: List[str]) -> List[str]:
    return sorted(values, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))


def discover_interesting_tests20k_cov(
    interesting_tests_root: str,
    fuzzer: str,
    cpu: str,
) -> Tuple[List[str], List[str], Dict[int, Dict[str, str]]]:
    """
    Discover precomputed coverage and seed files from:
      interesting_tests20K/<tar_cov_metric>/<fuzzer>/<cpu>/<round>/test_<id>/

    Solver IDs are assigned sequentially because test IDs can repeat across
    rounds.
    """
    preferred_cpu_root = join(interesting_tests_root, tar_cov_metric, fuzzer, cpu)
    legacy_cpu_root = join(interesting_tests_root, fuzzer, cpu)
    cpu_root = preferred_cpu_root if os.path.isdir(preferred_cpu_root) else legacy_cpu_root
    if not os.path.isdir(cpu_root):
        print(
            "[minimizer][WARN] interesting_tests20K cpu dir not found for "
            f"coverage='{tar_cov_metric}', fuzzer='{fuzzer}', cpu='{cpu}'. "
            f"Checked: {preferred_cpu_root} and {legacy_cpu_root}"
        )
        return [], [], {}

    cov_dict_filelist: List[str] = []
    cov_dict_ids: List[str] = []
    seed_metadata: Dict[int, Dict[str, str]] = {}

    for round_name in _sort_numeric_strings(os.listdir(cpu_root)):
        round_dir = join(cpu_root, round_name)
        if not os.path.isdir(round_dir):
            continue

        for test_dir_name in _sort_numeric_strings(os.listdir(round_dir)):
            test_match = re.match(r"test_([0-9]+)$", test_dir_name)
            if not test_match:
                continue

            test_id = test_match.group(1)
            test_dir = join(round_dir, test_dir_name)
            cov_file = join(test_dir, f"cov_out_{test_id}.json")
            seed_file = join(test_dir, f"inst_file_{test_id}.riscv")

            if not os.path.isfile(cov_file):
                print(f"[minimizer][WARN] Missing coverage json: {cov_file}")
                continue
            if not os.path.isfile(seed_file):
                print(f"[minimizer][WARN] Missing source seed: {seed_file}")
                continue

            solver_id = len(cov_dict_ids)
            cov_dict_filelist.append(cov_file)
            cov_dict_ids.append(str(solver_id))
            seed_metadata[solver_id] = {
                "round": round_name,
                "test_id": test_id,
                "seed_file": seed_file,
                "cov_file": cov_file,
            }

    return cov_dict_filelist, cov_dict_ids, seed_metadata


def seed_mini(
    interesting_tests_root: str,
    fuzzers_for_train: Optional[List[str]] = None,
    cpus_for_train: Optional[List[str]] = None,
):
    """
    1) For each fuzzer/cpu pair, load cov_out_*.json from interesting_tests20K.
    2) Run OR-Tools coverage minimization and write solution under the old
       INTEREST_TESTS_ROOT layout for compatibility.
    3) Copy selected seeds into TRAIN_ROOT/minimized_tests/<fuzzers>/<tar_cov_metric>/corpus.
    """
    fuzzers = fuzzers_for_train or FUZZERS
    cpus = cpus_for_train or CPUS_FOR_TRAIN
    dst_dir = get_corpus_dir(fuzzers)

    discovered_inputs: Dict[
        Tuple[str, str],
        Tuple[List[str], List[str], Dict[int, Dict[str, str]]],
    ] = {}
    missing_inputs: List[str] = []
    for fuzzer in fuzzers:
        for cpu in cpus:
            discovered = discover_interesting_tests20k_cov(
                interesting_tests_root, fuzzer, cpu
            )
            discovered_inputs[(fuzzer, cpu)] = discovered
            cov_dict_filelist, cov_dict_ids, _ = discovered
            if not cov_dict_filelist or not cov_dict_ids:
                missing_inputs.append(
                    f"{tar_cov_metric}/{fuzzer}/{cpu}"
                )

    if missing_inputs:
        raise FileNotFoundError(
            "Missing interesting-test coverage for requested source/processor pairs: "
            + ", ".join(missing_inputs)
        )

    # Validate the optional solver dependency before removing prior results.
    get_ortools_cp_model()

    solution_dirs = [
        join(INTEREST_TESTS_ROOT, fuzzer, tar_cov_metric, cpu)
        for fuzzer in fuzzers
        for cpu in cpus
    ]
    confirm_and_remove_destinations([dst_dir, *solution_dirs])
    ensure_dir_exists(dst_dir)

    for fuzzer in fuzzers:
        for cpu in cpus:
            cov_dict_filelist, cov_dict_ids, seed_metadata = discovered_inputs[(fuzzer, cpu)]
            minimized_sol_path = join(INTEREST_TESTS_ROOT, f"{fuzzer}", tar_cov_metric, cpu)
            ensure_dir_exists(minimized_sol_path)

            try:
                generate_optimized_solution(cov_dict_filelist, cov_dict_ids, fuzzer, cpu, minimized_sol_path)
            except RuntimeError as e:
                print(f"[minimizer][ERROR] {e}")
                print("[minimizer] Skipping this (fuzzer,cpu) pair due to OR-Tools minimizer failure.")
                continue

            sol_file = join(minimized_sol_path, f"{fuzzer}_{cpu}_solution.json")
            if not os.path.exists(sol_file):
                print(f"[minimizer][ERROR] Solution file not found: {sol_file}")
                continue

            chosen_ids = sorted(get_sol(sol_file))
            print(f"[minimizer] {fuzzer}/{cpu}: chosen {len(chosen_ids)} tests.")

            copied = 0
            for solver_id in chosen_ids:
                metadata = seed_metadata.get(solver_id)
                if metadata is None:
                    print(f"[minimizer][WARN] Missing metadata for solver id: {solver_id}")
                    continue
                src = metadata["seed_file"]
                if not os.path.exists(src):
                    print(f"[minimizer][WARN] Missing source seed: {src}")
                    continue
                dst_name = f"{fuzzer}_{cpu}_r{metadata['round']}_{metadata['test_id']}.riscv"
                dst_path = join(dst_dir, dst_name)
                shutil.copyfile(src, dst_path)
                copied += 1

            print(f"[minimizer] Copied {copied} seeds to {dst_dir} for {fuzzer}/{cpu}")


def pre_train(
    no_threads: int,
    tot_sim_time: int,
    fuzzers_for_train: Optional[List[str]] = None,
    cpus_for_train: Optional[List[str]] = None,
) -> None:
    """
    Precompute coverage of each test on all training CPUs.
    """
    fuzzers = fuzzers_for_train or FUZZERS
    cpus = cpus_for_train or CPUS_FOR_TRAIN
    SRC_CORPUS = get_corpus_dir(fuzzers)
    COV_DUMP_ROOT = get_cov_dump_dir(fuzzers)

    assert_dir_exists(SRC_CORPUS, f"SRC_CORPUS not found: {SRC_CORPUS}")
    validate_corpus_sources(SRC_CORPUS, fuzzers)
    validate_simulation_setup(cpus, no_threads)
    confirm_and_remove_destinations([COV_DUMP_ROOT])
    ensure_dir_exists(COV_DUMP_ROOT)

    for cpu in cpus:
        get_cov_pre_train(SRC_CORPUS, COV_DUMP_ROOT, cpu, no_threads, tot_sim_time)


def cal_ave_cov_incr_each_test_each_context(
    test_dir: str,
    cov_dir: str,
    cpus_for_train: List[str],
    cov_contexts: List[str],
    context_samples: int,
    cov_incr_file: str
):
    """
    Calculate average coverage increment per test per context across CPUs.
    """
    assert_dir_exists(test_dir, f"Test dir not found: {test_dir}")
    assert_dir_exists(cov_dir, f"Coverage dir not found: {cov_dir}")
    if context_samples <= 0:
        raise ValueError("context_samples must be > 0")

    cov_incr: Dict[str, dict] = {}
    for cov_context in cov_contexts:
        cov_incr[cov_context] = {}

        for testname in tqdm(os.listdir(test_dir), desc="Processing tests"):
            if not testname.endswith('.riscv'):
                continue
            parse_riscv_filename(testname)
            cov_incr[cov_context][testname] = {}

            ave_cov_incr = 0.0
            for cpu in cpus_for_train:
                if cpu not in cov_incr[cov_context][testname]:
                    cov_incr[cov_context][testname][cpu] = {"cov_per_context": [], "ave_cov_incr": 0.0}

                ave_cov_incr_per_cpu = 0.0
                cov_re_dir = f'{cov_dir}/{cpu}'
                assert_dir_exists(cov_re_dir, f"Coverage per-CPU dir not found: {cov_re_dir}")

                cov_re_file = join(cov_re_dir, f'cov_out_{seed_coverage_key(testname)}.json')
                cov_data_dict = safe_json_load(cov_re_file)

                cb_files = get_cb_train_cov_files()
                if cpu not in cb_files or cov_context not in cb_files[cpu]:
                    raise KeyError(f"Missing context '{cov_context}' for CPU '{cpu}' in training coverage files")

                for i in range(context_samples):
                    try:
                        cov_context_file = cb_files[cpu][cov_context][i]
                    except IndexError:
                        raise IndexError(f"Not enough context samples ({i}) for {cpu}/{cov_context}")
                    merged_cov_dict = safe_json_load(cov_context_file)
                    init_cov_tot = parse_cov.full_cov_to_cov_num(merged_cov_dict)

                    cov_inc_percent = cal_cov_incr(merged_cov_dict, cov_data_dict, cov_incr, init_cov_tot, cpu, cov_context, testname)
                    ave_cov_incr_per_cpu += cov_inc_percent

                ave_cov_incr_per_cpu /= context_samples
                cov_incr[cov_context][testname][cpu]["ave_cov_incr"] = ave_cov_incr_per_cpu
                ave_cov_incr += ave_cov_incr_per_cpu

            ave_cov_incr = ave_cov_incr / len(cpus_for_train)
            cov_incr[cov_context][testname]['ave_cov_incr'] = ave_cov_incr

    ensure_dir_exists(os.path.dirname(cov_incr_file) or ".")
    with open(cov_incr_file, 'w') as f:
        json.dump(cov_incr, f, indent=4)


def cal_cov_incr(merged_cov_dict: Dict[str, str], cov_data_dict: Dict[str, str],
                 cov_incr: Dict[str, Any], init_cov_tot: Dict[str, int],
                 cpu: str, cov_context: str, filename: str) -> float:
    """
    In-place merge cov_data_dict into merged_cov_dict and compute coverage increment percent.
    """
    for cov_type, cov_str in merged_cov_dict.items():
        new_merged_cov_arr = [*cov_str]
        for i, cov_point in enumerate(cov_str):
            if not int(cov_point) and cov_data_dict[cov_type][i] == '1':
                new_merged_cov_arr[i] = '1'
        merged_cov_dict[cov_type] = ''.join(new_merged_cov_arr)

    test_cov_tot = parse_cov.full_cov_to_cov_num(merged_cov_dict)
    cov_inc = test_cov_tot[tar_cov_metric] - init_cov_tot[tar_cov_metric]
    cov_inc_percent = cov_inc / get_total_cov_points(cpu, tar_cov_metric)
    cov_incr[cov_context][filename][cpu]["cov_per_context"].append(cov_inc_percent)
    return cov_inc_percent


FUZZ_ROOT = os.getenv("THEHUZZ_ROOT")
TRAIN_ROOT = join(FUZZ_ROOT, "refuzz", "refuzz_train")
INTEREST_TESTS_ROOT = join(TRAIN_ROOT, "interesting_tests")
INTEREST_TESTS20K_ROOT = os.getenv("INTEREST_TESTS20K_ROOT") or join(REPO_ROOT, "interesting_tests20K")

cov_types = ['line', 'branch', 'cond', 'fsm', 'tgl']
vdb_cov_files = [f"{cov_type}.verilog.data.xml" for cov_type in cov_types]
vdb_test_dir = "snps/coverage/db/testdata/test/"
tar_cov_metric = 'cond'
feedback_cov_types = [tar_cov_metric]

thread_number = 0  # This is for vul detection training

REFUZZ_CONTEXTS_DIR_NAME = "cov_contexts"
refuzz_train_cov_dir = os.path.join(TRAIN_ROOT, REFUZZ_CONTEXTS_DIR_NAME)

train_config_dict = {
    "cond": ["65", "60", "55", "50", "45"],
    "branch": ['70', '65', '60', '55']
}
train_cores_dict = {
    "cva6": "cva6",
    "rc": "rc",
    "boomv3": "boomv3",
    "boomv4": "boomv4",
}
train_contexts_dict = {
    "cond": [f"context{i}.json" for i in range(0, 3)],
    "branch": [f"context{i}.json" for i in range(0, 3)]
}


def get_cb_train_cov_files() -> Dict[str, Dict[str, List[str]]]:
    """
    Build training coverage file paths dynamically from current globals.
    """
    if tar_cov_metric not in train_contexts_dict or tar_cov_metric not in train_config_dict:
        raise KeyError(f"Missing training configuration for tar_cov_metric='{tar_cov_metric}'")

    return {
        core: {
            cov_config: [f"{refuzz_train_cov_dir}/{tar_cov_metric}/{core}/{cov_config}/{ctx}"
                         for ctx in train_contexts_dict[tar_cov_metric]]
            for cov_config in train_config_dict[tar_cov_metric]
        }
        for core in CPUS_FOR_TRAIN
    }


tot_cov_dict: Dict[str, Dict[str, int]] = {}


def load_tot_cov_dict() -> Dict[str, Dict[str, int]]:
    """
    Load total coverage sizes from noptest/<processor>_nop_cov.json.
    """
    global tot_cov_dict
    if tot_cov_dict:
        return tot_cov_dict

    noptest_root = join(os.getenv("THEHUZZ_ROOT", REPO_ROOT), "noptest")
    loaded: Dict[str, Dict[str, int]] = {}
    for processor in project_config.argVars["training_processors"]["c"]:
        nop_cov_file = join(noptest_root, f"{processor}_nop_cov.json")
        if not os.path.exists(nop_cov_file):
            continue
        nop_cov_dict = safe_json_load(nop_cov_file)
        loaded[processor] = {
            cov_type: len(cov_str)
            for cov_type, cov_str in nop_cov_dict.items()
            if cov_type in cov_types and isinstance(cov_str, str)
        }

    if not loaded:
        raise FileNotFoundError(f"No NOP coverage baselines found in {noptest_root}")

    tot_cov_dict = loaded
    return tot_cov_dict


def get_total_cov_points(processor: str, cov_type: str) -> int:
    totals = load_tot_cov_dict()
    if processor not in totals:
        raise KeyError(f"Missing NOP coverage baseline for processor '{processor}'. Expected noptest/{processor}_nop_cov.json")
    if cov_type not in totals[processor]:
        raise KeyError(f"Missing coverage type '{cov_type}' in NOP coverage baseline for processor '{processor}'")
    return totals[processor][cov_type]

FUZZERS: List[str] = ["thehuzz", "cascade"]
CPUS_FOR_TRAIN: List[str] = ["cva6", "rc", "boomv3", "boomv4"]


def get_corpus_dir(fuzzers_list: Optional[List[str]] = None) -> str:
    """
    TRAIN_ROOT/minimized_tests/<''.join(fuzzers)>/<tar_cov_metric>/corpus
    """
    fz = fuzzers_list or FUZZERS
    return join(TRAIN_ROOT, "minimized_tests", "".join(fz), tar_cov_metric, "corpus")


def get_cov_dump_dir(fuzzers_list: Optional[List[str]] = None) -> str:
    """
    TRAIN_ROOT/minimized_tests/<''.join(fuzzers)>/<tar_cov_metric>/cov_dump
    """
    fz = fuzzers_list or FUZZERS
    return join(TRAIN_ROOT, "minimized_tests", "".join(fz), tar_cov_metric, "cov_dump")


def refresh_train_roots() -> None:
    """
    Recompute training paths after TRAIN_ROOT changes.
    """
    global INTEREST_TESTS_ROOT, refuzz_train_cov_dir
    INTEREST_TESTS_ROOT = join(TRAIN_ROOT, "interesting_tests")
    preferred = join(TRAIN_ROOT, REFUZZ_CONTEXTS_DIR_NAME)
    refuzz_train_cov_dir = preferred


def source_to_fuzzers(refuzz_train_source: str) -> List[str]:
    if refuzz_train_source == "thehuzz":
        return ["thehuzz"]
    if refuzz_train_source == "thehuzzcascade":
        return ["thehuzz", "cascade"]
    raise ValueError(f"Unsupported ReFuzz train source: {refuzz_train_source}")


def validate_corpus_sources(corpus_dir: str, fuzzers: List[str]) -> None:
    """
    Require at least one minimized RISC-V seed for every selected fuzzer.
    """
    assert_dir_exists(corpus_dir, f"Corpus directory not found: {corpus_dir}")
    riscv_names = [
        filename
        for filename in os.listdir(corpus_dir)
        if filename.endswith(".riscv") and os.path.isfile(join(corpus_dir, filename))
    ]
    missing = [
        fuzzer
        for fuzzer in fuzzers
        if not any(filename.startswith(f"{fuzzer}_") for filename in riscv_names)
    ]
    if missing:
        raise FileNotFoundError(
            f"Corpus '{corpus_dir}' is missing seed families for: {', '.join(missing)}"
        )


def validate_cov_increment_sources(cov_incr_file: str, fuzzers: List[str]) -> None:
    """
    Require the precomputed increment JSON to contain every selected fuzzer.
    """
    cov_increments = safe_json_load(cov_incr_file)
    if not isinstance(cov_increments, dict):
        raise ValueError(f"Coverage increment file must contain a JSON object: {cov_incr_file}")

    seed_names = set()
    for context_data in cov_increments.values():
        if isinstance(context_data, dict):
            seed_names.update(str(seed_name) for seed_name in context_data)

    missing = [
        fuzzer
        for fuzzer in fuzzers
        if not any(seed_name.startswith(f"{fuzzer}_") for seed_name in seed_names)
    ]
    if missing:
        raise FileNotFoundError(
            f"Coverage increment file '{cov_incr_file}' is missing seed families for: "
            f"{', '.join(missing)}"
        )


def validate_pretrain_coverage_inputs(
    corpus_dir: str,
    cov_dump_dir: str,
    cpus: List[str],
    fuzzers: List[str],
) -> None:
    """
    Validate all pre_train_2 inputs before replacing its increment JSON.
    """
    validate_corpus_sources(corpus_dir, fuzzers)
    assert_dir_exists(cov_dump_dir, f"Coverage dump directory not found: {cov_dump_dir}")

    seed_names = sorted(
        filename
        for filename in os.listdir(corpus_dir)
        if filename.endswith(".riscv") and os.path.isfile(join(corpus_dir, filename))
    )
    missing_files: List[str] = []
    for cpu in cpus:
        cpu_cov_dir = join(cov_dump_dir, cpu)
        if not os.path.isdir(cpu_cov_dir):
            missing_files.append(cpu_cov_dir)
            continue
        for seed_name in seed_names:
            cov_file = join(cpu_cov_dir, f"cov_out_{seed_coverage_key(seed_name)}.json")
            if not os.path.isfile(cov_file):
                missing_files.append(cov_file)

    if missing_files:
        preview = "\n  - ".join(missing_files[:20])
        remainder = len(missing_files) - min(len(missing_files), 20)
        suffix = f"\n  ... and {remainder} more" if remainder else ""
        raise FileNotFoundError(
            "pre_train_2 coverage inputs are incomplete:\n  - "
            f"{preview}{suffix}"
        )


def validate_simulation_setup(cpus: List[str], no_threads: int) -> None:
    """
    Validate simulator wrappers, benchmark data, binaries, and worker dirs.
    """
    if no_threads <= 0:
        raise ValueError("Number of simulation threads must be greater than zero")

    fuzz_root = require_env("THEHUZZ_ROOT")
    missing: List[str] = []
    for cpu in cpus:
        core_full_name, _ = get_core_info(cpu)
        sim_script = join(fuzz_root, "utils", f"vcs_run_{cpu}.bash")
        dram_path = join(fuzz_root, "benchmarks", cpu, "dramsim2_ini")
        if not os.path.isfile(sim_script):
            missing.append(sim_script)
        if not os.path.exists(dram_path):
            missing.append(dram_path)

        for thread_no in range(no_threads):
            sim_dir = join(fuzz_root, "sim", "sim_chipyard_1130", f"vcs_{thread_no}")
            sim_binary = join(
                sim_dir,
                f"simv-chipyard.harness-{core_full_name}Config",
            )
            if not os.path.isdir(sim_dir):
                missing.append(sim_dir)
            elif not os.path.isfile(sim_binary):
                missing.append(sim_binary)

    if missing:
        preview = "\n  - ".join(missing[:20])
        remainder = len(missing) - min(len(missing), 20)
        suffix = f"\n  ... and {remainder} more" if remainder else ""
        raise FileNotFoundError(
            "Simulation prerequisites are incomplete:\n  - "
            f"{preview}{suffix}"
        )


def validate_training_context_inputs(
    cpus: List[str],
    cov_contexts: List[str],
    context_samples: int,
) -> None:
    """
    Validate every requested context coverage JSON before destructive cleanup.
    """
    context_files = get_cb_train_cov_files()
    missing: List[str] = []
    for cpu in cpus:
        for cov_context in cov_contexts:
            files = context_files.get(cpu, {}).get(cov_context, [])
            for sample_index in range(context_samples):
                if sample_index >= len(files) or not os.path.isfile(files[sample_index]):
                    missing.append(
                        files[sample_index]
                        if sample_index < len(files)
                        else f"{cpu}/{cov_context}/context sample {sample_index}"
                    )
    if missing:
        preview = "\n  - ".join(missing[:20])
        remainder = len(missing) - min(len(missing), 20)
        suffix = f"\n  ... and {remainder} more" if remainder else ""
        raise FileNotFoundError(
            "Training coverage contexts are incomplete:\n  - "
            f"{preview}{suffix}"
        )


def refuzz_train_cleanup_targets(train_result_dir: str) -> List[str]:
    """
    Return existing top-level ReFuzz outputs while preserving vul_train.
    """
    if not os.path.exists(train_result_dir):
        return []
    validate_cleanup_target(train_result_dir)
    if not os.path.isdir(train_result_dir):
        raise NotADirectoryError(f"Trained model destination is not a directory: {train_result_dir}")
    return [
        join(train_result_dir, entry)
        for entry in sorted(os.listdir(train_result_dir))
        if entry != "vul_train"
    ]


def validate_single_feedback_cov(feedback_covs: List[str]) -> str:
    if len(feedback_covs) != 1:
        raise ValueError(f"refuzz_train requires exactly one feedback coverage type, got: {feedback_covs}")
    cov = feedback_covs[0]
    if cov not in cov_types:
        raise ValueError(f"Unsupported feedback coverage type for refuzz_train: {cov}")
    return cov


def resolve_training_processors(training_processors: List[str]) -> List[str]:
    missing = [p for p in training_processors if p not in train_cores_dict]
    if missing:
        raise ValueError(f"Unsupported ReFuzz training processor(s): {missing}")

    cores = [train_cores_dict[p] for p in training_processors]
    totals = load_tot_cov_dict()
    unsupported = [core for core in cores if core not in totals]
    if unsupported:
        raise ValueError(f"Missing ReFuzz training coverage metadata for processor core(s): {unsupported}")
    return cores


def build_refuzz_train_paths(refuzz_train_source: str, training_processors: List[str], feedback_covs: List[str]) -> Dict[str, Any]:
    """
    Resolve and validate the paths used by the refuzz_train method.
    """
    cov_metric = validate_single_feedback_cov(feedback_covs)
    if cov_metric not in train_config_dict:
        raise ValueError(f"No ReFuzz training contexts configured for coverage type: {cov_metric}")

    train_cpus = resolve_training_processors(training_processors)
    fuzzers = source_to_fuzzers(refuzz_train_source)
    train_result_dir = build_train_result_dir(refuzz_train_source, training_processors, cov_metric)
    corpus_dir = get_corpus_dir(fuzzers)
    cov_dump_dir = get_cov_dump_dir(fuzzers)
    cov_incr_results = join(cov_dump_dir, f"cov_incr_{''.join(fuzzers)}.json")

    assert_dir_exists(corpus_dir, f"ReFuzz corpus dir not found: {corpus_dir}")
    assert_file_exists(cov_incr_results, f"File '{cov_incr_results}' does not exist. Please run pre_train_1 and pre_train_2 first.")
    validate_corpus_sources(corpus_dir, fuzzers)
    validate_cov_increment_sources(cov_incr_results, fuzzers)

    return {
        "tar_cov_metric": cov_metric,
        "tar_covs": train_config_dict[cov_metric],
        "train_cpus": train_cpus,
        "fuzzers": fuzzers,
        "train_result_dir": train_result_dir,
        "corpus_dir": corpus_dir,
        "cov_incr_results": cov_incr_results,
    }


def build_train_result_dir(refuzz_train_source: str, training_processors: List[str], cov_metric: str) -> str:
    """
    Resolve the trained DB model directory shared by refuzz_train and vul_train.
    """
    train_model_name = "_".join(training_processors) + "_train"
    return join(TRAIN_ROOT, "trained_db", refuzz_train_source, cov_metric, train_model_name)


def get_vul_train_files(src_dir: str, refuzz_train_source: str) -> List[str]:
    """
    Select top-level existing bug seeds for the requested trained DB source.
    """
    assert_dir_exists(src_dir, f"Source dir not found: {src_dir}")
    prefixes = source_to_fuzzers(refuzz_train_source)
    files_by_prefix: Dict[str, List[str]] = {prefix: [] for prefix in prefixes}
    for filename in sorted(os.listdir(src_dir)):
        if not filename.endswith(".riscv"):
            continue
        for prefix in prefixes:
            if filename.startswith(f"{prefix}_"):
                files_by_prefix[prefix].append(join(src_dir, filename))
                break

    missing = [prefix for prefix, paths in files_by_prefix.items() if not paths]
    if missing:
        expected = ", ".join(f"{prefix}_*.riscv" for prefix in missing)
        raise FileNotFoundError(
            f"Missing vulnerability training inputs matching {expected} in {src_dir}"
        )

    return [
        path
        for prefix in prefixes
        for path in files_by_prefix[prefix]
    ]


def thresholds_file_path(train_result_dir: str) -> str:
    return join(train_result_dir, "cb_adaptive_thresholds.json")


def load_cb_thresholds(train_result_dir: str) -> Dict[str, float]:
    path = thresholds_file_path(train_result_dir)
    if os.path.exists(path):
        try:
            with open(path, "r") as fp:
                data = json.load(fp)
                if isinstance(data, dict):
                    return data
        except Exception:
            # ignore malformed files and fall back to {}
            pass
    return {}


def save_cb_thresholds(train_result_dir: str, data: Dict[str, float]) -> None:
    ensure_dir_exists(train_result_dir)
    path = thresholds_file_path(train_result_dir)
    with open(path, "w") as fp:
        json.dump(data, fp, indent=2)


def sim_test_riscv(test_riscv: str, cpu: str):
    """
    Simulate a single RISC-V test on a specific CPU and return coverage dict.
    """
    fuzz_root = require_env("THEHUZZ_ROOT")
    assert_file_exists(test_riscv, f"Test file not found: {test_riscv}")

    sim_time = '20000000'
    _ = subprocess.call([
        f'{fuzz_root}/utils/vcs_run_{cpu}.bash',
        f'{fuzz_root}/sim/sim_chipyard_1130//vcs_{thread_number}',
        f'{fuzz_root}/benchmarks/{cpu}/dramsim2_ini',
        test_riscv,
        f'{fuzz_root}/sim/sim_chipyard_1130//vcs_{thread_number}/sim.log',
        sim_time,
        f'{fuzz_root}/dontcare.log',
        str(666), # random seed for simulation
    ])

    core_full_name, core_instance_list = get_core_info(cpu)

    rtl_cov_out_path = f'{fuzz_root}/sim/sim_chipyard_1130/vcs_{thread_number}/simv-chipyard.harness-{core_full_name}Config.vdb'
    cov_dict = parse_cov.vdb_to_dict(
        rtl_cov_out_path, cov_types, vdb_cov_files,
        core_instance_list, vdb_test_dir, 'detailed',
        f"simulation for {test_riscv} probably didn't run properly, {0}, {0}"
    )

    return cov_dict


def ave_cov_inc(cpus_for_train: List[str], test: str, train_log: Any) -> float:
    """
    Average coverage increment across CPUs for a single test.
    """
    ave = 0.0
    train_log.write(f'{test}\n')
    for cpu in cpus_for_train:
        train_log.write(f'{cpu}\n')
        merged_cov_dict = load_nop_cov_baseline(cpu)
        init_cov_tot = parse_cov.full_cov_to_cov_num(merged_cov_dict)

        cov_data_dict = sim_test_riscv(test, cpu)

        for cov_type, cov_str in merged_cov_dict.items():
            new_merged_cov_arr = [*cov_str]
            for i, cov_point in enumerate(cov_str):
                if not int(cov_point) and cov_data_dict[cov_type][i] == '1':
                    new_merged_cov_arr[i] = '1'
            merged_cov_dict[cov_type] = ''.join(new_merged_cov_arr)

        test_cov_tot = parse_cov.full_cov_to_cov_num(merged_cov_dict)
        cov_inc = test_cov_tot[tar_cov_metric] - init_cov_tot[tar_cov_metric]
        cov_inc_percent = cov_inc / get_total_cov_points(cpu, tar_cov_metric)

        train_log.write(f'init_cov_tot: {init_cov_tot}\n')
        train_log.write(f'test_cov_tot: {test_cov_tot}\n')
        train_log.write(f'cov_inc: {cov_inc}, cov_inc_percent: {cov_inc_percent}\n')

        ave += cov_inc_percent

    ave /= len(cpus_for_train)
    train_log.write(f'score: {ave}\n')
    return ave


def load_nop_cov_baseline(processor: str) -> Dict[str, str]:
    """
    Load the initial NOP coverage baseline for vulnerability scoring.
    """
    nop_cov_file = join(require_env("THEHUZZ_ROOT"), "noptest", f"{processor}_nop_cov.json")
    return safe_json_load(nop_cov_file)


def train_vul_tests(riscv_filelist: List[str], dst_dir: str, cpus_for_train: List[str], train_log: str):
    """
    Rank vulnerability tests by average coverage increment and copy with ranking.
    """
    if not riscv_filelist:
        raise ValueError("No vulnerability tests provided for training")

    ensure_dir_exists(dst_dir)

    with open(train_log, "w") as log_file:
        riscv_files = []
        for file_path in tqdm(riscv_filelist, desc="Processing .riscv files"):
            assert_file_exists(file_path)
            filename = os.path.basename(file_path)
            score = ave_cov_inc(cpus_for_train, file_path, log_file)
            riscv_files.append((filename, file_path, score))

        riscv_files.sort(key=lambda x: x[2], reverse=True)

        for rank, (filename, file_path, score) in enumerate(riscv_files, 1):
            dst_file_name = f"seed{rank}_{filename}"
            dst_file_path = join(dst_dir, dst_file_name)
            shutil.copy(file_path, dst_file_path)
            log_file.write(f"Copied {file_path} to {dst_file_path} with score {score:.4f}\n")

    print("All files copied and ranked by score.")


def acquire_sim_dir(locks: List[Any]) -> int:
    """
    Acquire a simulation directory to ensure two simulations do not use the same dir.
    """
    while True:
        for i, lock in enumerate(locks):
            if lock.acquire(block=False):
                return i


def init_sim_prog(locks_in: List[Any], write_log_lock_in: Any) -> None:
    """
    Initializer for multiprocessing pool.
    """
    global locks, write_log_lock
    locks = locks_in
    write_log_lock = write_log_lock_in


def sim_progs(file_dir: str, progs_to_sim: List[str], no_threads: int, prog_save_no: List[str], *args_for_simulation: Any) -> None:
    """
    Simulate all programs from progs_to_sim using multiprocessing.

    - ISAs supported: riscv
    - Provide mem filelist as progs_to_sim array
    - Ensure there are no_threads directories since that many simulations run in parallel
    """
    assert_dir_exists(file_dir, f"file_dir not found: {file_dir}")

    locks_local = [mp.Lock() for _ in range(no_threads)]
    write_log_lock_local = mp.Lock()

    chunk_size = max(1, int((len(progs_to_sim) / max(1, no_threads)) / 4))

    args = []
    for i, mem_file_in in enumerate(progs_to_sim):
        args.append([file_dir, mem_file_in, prog_save_no[i], *args_for_simulation])

    init_args = (locks_local, write_log_lock_local)
    with mp.Pool(processes=no_threads, initializer=init_sim_prog, initargs=init_args) as pool:
        if len(args) > 100:
            _ = list(tqdm(pool.imap(sim_prog, args, chunksize=chunk_size), total=len(args), desc="----Simulating files"))
        else:
            _ = list(pool.imap(sim_prog, args, chunksize=chunk_size))
    return None


def sim_prog(arg_list: List[Any]) -> Dict[str, Any]:
    """
    Worker function: run a single simulation and dump coverage JSON.
    """
    (file_dir, ip_file, file_no, core, tot_sim_time, cov_enable,
     cov_types_local, vdb_cov_files_local, core_instance_list,
     sim_bash_file, CORE_PT, start_time, sim_files_to_save,
     detecting_bugs, emu_bash_file, EMU_PT, emu_tot_sim_time,
     return_cov, record_fuzzer) = arg_list

    assert_dir_exists(file_dir, f"file_dir not found: {file_dir}")
    assert_file_exists(ip_file, f"Input program not found: {ip_file}")
    assert_file_exists(sim_bash_file, f"Simulation bash script not found: {sim_bash_file}")

    thread_no = acquire_sim_dir(locks)

    filename = os.path.basename(ip_file)

    if os.path.splitext(ip_file)[1][1:] != CORE_PT['input_format']:
        if CORE_PT['input_format'] == 'mem':
            new_ip_file = thehuzz_utils.change_extension(ip_file, CORE_PT['input_format'])
            thehuzz_utils.hex_to_mem(ip_file, new_ip_file)
            ip_file = new_ip_file
        else:
            raise ValueError(f"Missing core conversion specification for {core} core")

    _ = subprocess.call([
        sim_bash_file,
        CORE_PT['sim_dir_t'].substitute(tno=thread_no),
        CORE_PT['core_dram_path'],
        ip_file,
        CORE_PT['sim_out_path_t'].substitute(tno=thread_no),
        str(tot_sim_time),
        '/dev/null',
        str(666), # random seed for simulation
    ])

    rtl_cov_out_path = CORE_PT['cov_out_path_t'].substitute(tno=thread_no)
    cov_dict = parse_cov.vdb_to_dict(
        rtl_cov_out_path, cov_types_local, vdb_cov_files_local,
        core_instance_list, CORE_PT['vdb_test_dir'], 'detailed',
        f"simulation for {ip_file} probably dint run properly, {file_no}, {thread_no}"
    )

    cov_dump_path = join(file_dir, f'cov_out_{file_no}.json')

    if record_fuzzer:
        cov_dump_path = join(file_dir, f'cov_out_{seed_coverage_key(filename)}.json')

    with open(cov_dump_path, 'w') as json_f:
        json.dump(cov_dict, json_f, indent=4)

    locks[thread_no].release()

    if return_cov:
        return cov_dict
    else:
        return {k: '' for k in cov_dict.keys()}


def get_files_in_dir(target_dir: str, pattern: str = "", sort_file: bool = True, sort_key_pattern: Optional[Callable[[str], Any]] = None, full_path: bool = False) -> List[str]:
    """Return files matching a pattern, optionally sorted or fully qualified."""
    all_filelist = os.listdir(target_dir)

    filelist = []
    for filename in all_filelist:
        if re.match(pattern, filename):
            filelist.append(filename)

    if sort_file == True:
        if sort_key_pattern is not None:
            filelist.sort(key=sort_key_pattern)
        else:
            filelist.sort(key=lambda f: int(''.join(filter(str.isdigit, f))))

    if full_path:
        filelist_fullpath = [os.path.join(target_dir, filename) for filename in filelist]

        return filelist_fullpath

    return filelist


def seed_sort_key(path: str) -> Tuple[str, str, int, int, str]:
    seed_info = parse_seed_filename(os.path.basename(path))
    round_no = int(seed_info["round"]) if seed_info["round"] is not None else -1
    return (
        seed_info["fuzzer"],
        seed_info["core"],
        round_no,
        int(seed_info["file_id"]),
        os.path.basename(path),
    )


def get_cov_pre_train(SRC_CORPUS: str, COV_DUMP_ROOT: str, cpu: str, no_threads: int, tot_sim_time: int) -> None:
    filelist = get_files_in_dir(SRC_CORPUS, pattern='(.*).riscv$', sort_file=True,
                                sort_key_pattern=seed_sort_key, full_path=True)
    sim_files_to_save = None
    detecting_bugs = 0

    cov_dump_dir = join(COV_DUMP_ROOT, cpu)
    ensure_dir_exists(cov_dump_dir)

    core_full_name, core_instance_list = get_core_info(cpu)

    fuzz_root = require_env("THEHUZZ_ROOT")
    sim_bash_file = f'{fuzz_root}/utils/vcs_run_{cpu}.bash'

    CORE_PT = {'sim_dir_t': Template(f"{join(fuzz_root, 'sim/sim_chipyard_1130/')}/vcs_${{tno}}")}
    CORE_PT['input_format'] = 'riscv'
    CORE_PT['core_dram_path'] = join(fuzz_root, f'benchmarks/{cpu}/dramsim2_ini')
    CORE_PT['sim_out_path_t'] = Template(f"{CORE_PT['sim_dir_t'].template}/sim.log")
    CORE_PT['cov_out_path_t'] = Template(f"{CORE_PT['sim_dir_t'].template}/simv-chipyard.harness-{core_full_name}Config.vdb")
    CORE_PT['vdb_test_dir'] = "snps/coverage/db/testdata/test/"

    files_to_sim = []
    files_to_sim_ids = []
    for filename in tqdm(filelist, desc="Processing .riscv files"):
        if filename.endswith('.riscv'):
            files_to_sim.append(filename)
            files_to_sim_ids.append(seed_coverage_key(filename))

    sim_progs(
        cov_dump_dir, files_to_sim, no_threads, files_to_sim_ids,
        cpu, tot_sim_time, True, cov_types, vdb_cov_files, core_instance_list,
        sim_bash_file, CORE_PT, 0, sim_files_to_save, detecting_bugs,
        'None', {}, 0, False, True
    )


def random_pick_context(cb_train_cpus: List[str], cb_train_context: str):
    """
    Randomly pick a CPU and a context coverage file; return CPU, initial target coverage and coverage dict.
    """
    cb_files = get_cb_train_cov_files()
    cpu_dut = random.choice(cb_train_cpus)
    cb_train_context_cov_files = cb_files[cpu_dut][cb_train_context]
    cb_train_context_cov_file = random.choice(cb_train_context_cov_files)

    init_cov_dict = safe_json_load(cb_train_context_cov_file)
    cov_data_tot = parse_cov.full_cov_to_cov_num(init_cov_dict)
    cb_init_tar_cov = sum([cov_data_tot[cov_type] for cov_type in feedback_cov_types])

    return cpu_dut, cb_init_tar_cov, init_cov_dict


def cal_cov_inc(init_cov_dict: Dict[str, str], cov_data_dict: Dict[str, str], cb_init_tar_cov: int, cpu_dut: str) -> float:
    for cov_type, cov_str in init_cov_dict.items():
        new_merged_cov_arr = [*cov_str]
        for i, cov_point in enumerate(cov_str):
            if not int(cov_point):
                if cov_data_dict[cov_type][i] == '1':
                    new_merged_cov_arr[i] = '1'

        init_cov_dict[cov_type] = ''.join(new_merged_cov_arr)

    test_cov_tot = parse_cov.full_cov_to_cov_num(init_cov_dict)
    tar_cov_tot = sum([test_cov_tot[cov_type] for cov_type in feedback_cov_types])

    cov_inc = tar_cov_tot - cb_init_tar_cov
    cov_inc_percent = round((cov_inc / get_total_cov_points(cpu_dut, tar_cov_metric)) * 100, 5)

    return cov_inc_percent


def seed_reward(cb_train_cpus: List[str], cb_train_context: str, simp_seed_dir: str, cb_seed_train: Any, seed: str) -> Tuple[float, Any]:
    cpu_dut, cb_init_tar_cov, init_cov_dict = random_pick_context(cb_train_cpus, cb_train_context)

    test_riscv = join(simp_seed_dir, cb_seed_train.seed_mapping[seed])
    assert_file_exists(test_riscv, f"test file does not exist: {test_riscv}")

    cov_data_dict = sim_test_riscv(test_riscv, cpu_dut)
    _ = parse_cov.full_cov_to_cov_num(cov_data_dict)  # keep for potential debug parity
    cov_inc_percent = cal_cov_inc(init_cov_dict, cov_data_dict, cb_init_tar_cov, cpu_dut)

    return cov_inc_percent, cb_seed_train


def random_pick_context_no_sim(cb_train_cpus: List[str], cb_train_context: str) -> Tuple[str, int]:
    cb_files = get_cb_train_cov_files()
    cpu_dut = random.choice(cb_train_cpus)
    cb_train_context_cov_files = cb_files[cpu_dut][cb_train_context]
    cb_train_context_cov_file = random.choice(cb_train_context_cov_files)
    context_index = cb_train_context_cov_files.index(cb_train_context_cov_file)

    return cpu_dut, context_index


def seed_reward_no_sim(cb_train_cpus: List[str], cb_train_context: str, simp_seed_dir: str, cb_seed_train: Any, seed: str, context_cov_incr: Dict[str, Any]) -> Tuple[float, Any]:
    """Score a seed from previously collected coverage without simulating it."""
    cpu_dut, context_index = random_pick_context_no_sim(cb_train_cpus, cb_train_context)

    test_riscv = join(simp_seed_dir, seed)
    assert_file_exists(test_riscv, f"test file does not exist: {test_riscv}")

    cov_inc_percent = context_cov_incr[seed][cpu_dut]["cov_per_context"][context_index]
    cov_inc_percent = round(cov_inc_percent * 100, 5)

    return cov_inc_percent, cb_seed_train


def _measure_candidates_for_threshold(cb_train_context: str, threshold: float, cb_train_cpus: List[str], simp_seed_dir: str,
                                      cb_epoch_num: int, cb_num_seed_arms: int, cb_reset_window: int,
                                      cb_adaptive_pick_threshold: int, seed_minimization: bool,
                                      context_cov_incr: Dict[str, Any], target_high: int,
                                      corpus_list: List[str]) -> Tuple[int, bool]:
    """
    Run a deterministic (seed=42) probe training and return (candidate_count, early_terminated).
    No files are written and corpus_list is not modified.
    """
    random.seed(42)

    base_seed_list = filter_training_seed_corpus(
        corpus_list, cb_train_cpus, cb_num_seed_arms,
        f"threshold probe context {cb_train_context}", log=False
    )
    local_seed_list = base_seed_list.copy()

    CBAlgos = get_cbalgos_module()
    cb_seed_train = CBAlgos.CBalgo_Adaptive(int(cb_train_context), cb_reset_window,
                                            threshold, cb_adaptive_pick_threshold,
                                            cb_epoch_num, cb_num_seed_arms)

    rng = random.Random(42)
    chosen_seeds = rng.sample(local_seed_list, cb_num_seed_arms)
    for seed in chosen_seeds:
        local_seed_list.remove(seed)
    cb_seed_train.init_arms(chosen_seeds)

    for seed in cb_seed_train.seeds:
        if seed not in cb_seed_train.ave_rewards:
            cb_seed_train.ave_rewards[seed] = {"ave": 0, "each_t": [], "removed": False, "select_count": 0}
        if seed_minimization:
            cov_inc_percent, _ = seed_reward_no_sim(cb_train_cpus, cb_train_context, simp_seed_dir, cb_seed_train, seed, context_cov_incr)
        else:
            cov_inc_percent, _ = seed_reward(cb_train_cpus, cb_train_context, simp_seed_dir, cb_seed_train, seed)
        cb_seed_train.update_policy(seed, cov_inc_percent)
        _ = cb_seed_train.policy.predict_expectations(cb_seed_train.context)

    for _i in range(cb_epoch_num):
        selected_seed = cb_seed_train.select_arm()
        if seed_minimization:
            cov_inc_percent, _ = seed_reward_no_sim(cb_train_cpus, cb_train_context, simp_seed_dir, cb_seed_train, selected_seed, context_cov_incr)
        else:
            cov_inc_percent, _ = seed_reward(cb_train_cpus, cb_train_context, simp_seed_dir, cb_seed_train, selected_seed)

        cb_seed_train.update_policy(selected_seed, cov_inc_percent)
        _is_reset, local_seed_list = cb_seed_train.check_reset(selected_seed, local_seed_list)

        if len(local_seed_list) == 0:
            break

        # Early termination if candidates exceed 110% of cb_num_seed_arms
        if len(cb_seed_train.seed_candidates) > target_high:
            return len(cb_seed_train.seed_candidates), True

    return len(cb_seed_train.seed_candidates), False


def fine_tune_threshold(simp_seed_dir: str, cb_train_cpus: List[str],
                        train_result_dir: str, tar_covs: List[str],
                        cov_incr_results: str, cb_epoch_num: int, seed_minimization: bool = True) -> Dict[str, float]:
    """
    Tune and persist cb_adaptive_thresholds for each context.
    After tuning each context, run a full training (cb_epoch_num) for that context and
    remove any selected candidate seeds from the global corpus to prevent duplicates
    across contexts. Always re-tunes from scratch and overwrites any existing thresholds file.
    """
    cb_adaptive_pick_threshold = 10
    cb_reset_window = 3
    cb_num_seed_arms = 100
    ensure_dir_exists(train_result_dir)

    if seed_minimization:
        with open(cov_incr_results, 'r') as fp:
            cov_incr_dict = json.load(fp)

    corpus_list = filter_training_seed_corpus(
        os.listdir(simp_seed_dir), cb_train_cpus, cb_num_seed_arms,
        "threshold tuning"
    )

    thr_path = thresholds_file_path(train_result_dir)
    if os.path.exists(thr_path):
        try:
            os.remove(thr_path)
            print(f"[tuner] Removed existing thresholds file: {thr_path}")
        except OSError as e:
            print(f"[tuner][WARN] Could not remove existing thresholds file {thr_path}: {e}")
    cb_adaptive_thresholds: Dict[str, float] = {}

    for cb_train_context in tqdm(tar_covs, desc="Tuning contexts"):
        print(f"--------------Tuning Threshold for Context {cb_train_context}--------------------")
        training_status_log_file = join(train_result_dir, f'train_status_{cb_train_context}.log')
        with open(training_status_log_file, 'w') as fp:
            pass

        if seed_minimization:
            context_cov_incr = cov_incr_dict[cb_train_context]
        else:
            context_cov_incr = {}

        target_low = int(math.floor(0.9 * cb_num_seed_arms))
        target_high = int(math.ceil(1.1 * cb_num_seed_arms))

        low, high = 0.0, 100.0
        chosen = None
        last_mid = None
        max_iters = 17
        bs_iter = tqdm(range(max_iters), desc=f"Binary search {cb_train_context}", leave=False)
        for _bs in bs_iter:
            mid = (low + high) / 2.0
            last_mid = mid
            cnt, early = _measure_candidates_for_threshold(
                cb_train_context, mid, cb_train_cpus, simp_seed_dir, cb_epoch_num,
                cb_num_seed_arms, cb_reset_window, cb_adaptive_pick_threshold,
                seed_minimization, context_cov_incr, target_high, corpus_list
            )
            bs_iter.set_postfix(cnt=cnt, low=f"{low:.3f}", high=f"{high:.3f}", mid=f"{mid:.3f}")
            # Direction: too many -> increase threshold; too few -> decrease threshold
            if early or cnt > target_high:
                low = mid
            elif cnt < target_low:
                high = mid
            else:
                chosen = mid
                break
        cb_adaptive_threshold = chosen if chosen is not None else last_mid
        print(f"[tuner] Context {cb_train_context}: tuned threshold {cb_adaptive_threshold:.4f}, target window [{target_low}, {target_high}]")
        cb_adaptive_thresholds[cb_train_context] = cb_adaptive_threshold

        save_cb_thresholds(train_result_dir, cb_adaptive_thresholds)

        print(f"--------------Training (during tuning) Context {cb_train_context}--------------------")
        seed_list = copy.deepcopy(corpus_list)
        if len(seed_list) < cb_num_seed_arms:
            print(f"[tuner][WARN] Context {cb_train_context}: insufficient seeds ({len(seed_list)}), skip training/removal")
            continue

        CBAlgos = get_cbalgos_module()
        cb_seed_train = CBAlgos.CBalgo_Adaptive(
            int(cb_train_context), cb_reset_window, cb_adaptive_threshold,
            cb_adaptive_pick_threshold, cb_epoch_num, cb_num_seed_arms
        )

        # Deterministic init for reproducibility
        random.seed(42)
        chosen_seeds = random.sample(seed_list, cb_num_seed_arms)
        for seed in chosen_seeds:
            seed_list.remove(seed)
        cb_seed_train.init_arms(chosen_seeds)

        for seed in tqdm(cb_seed_train.seeds, desc="Warm up", leave=False):
            if seed not in cb_seed_train.ave_rewards:
                cb_seed_train.ave_rewards[seed] = {"ave": 0, "each_t": [], "removed": False, "select_count": 0}

            if seed_minimization:
                cov_inc_percent, _ = seed_reward_no_sim(cb_train_cpus, cb_train_context,
                                                        simp_seed_dir, cb_seed_train,
                                                        seed, context_cov_incr)
            else:
                cov_inc_percent, _ = seed_reward(cb_train_cpus, cb_train_context,
                                                 simp_seed_dir, cb_seed_train, seed)
            cb_seed_train.update_policy(seed, cov_inc_percent)
            _ = cb_seed_train.policy.predict_expectations(cb_seed_train.context)

        train_iter = tqdm(range(cb_epoch_num), desc=f"Epochs {cb_train_context}", leave=False)
        for i in train_iter:
            selected_seed = cb_seed_train.select_arm()
            if seed_minimization:
                cov_inc_percent, _ = seed_reward_no_sim(cb_train_cpus, cb_train_context,
                                                        simp_seed_dir, cb_seed_train,
                                                        selected_seed, context_cov_incr)
            else:
                cov_inc_percent, _ = seed_reward(cb_train_cpus, cb_train_context,
                                                 simp_seed_dir, cb_seed_train, selected_seed)

            cb_seed_train.update_policy(selected_seed, cov_inc_percent)
            train_iter.set_postfix(cands=len(cb_seed_train.seed_candidates), remaining=len(seed_list))
            is_reset, seed_list = cb_seed_train.check_reset(selected_seed, seed_list)
            if is_reset:
                with jsonlines.open(training_status_log_file, 'a') as fp:
                    fp.write({'itr_no': i, 'arm': selected_seed, 'is_reset': is_reset, 'add_arm': cb_seed_train.seeds[-1]})

            if len(seed_list) == 0:
                with jsonlines.open(training_status_log_file, 'a') as fp:
                    fp.write({'itr_no': i, 'status': 'No extra seeds', 'seed_len': len(seed_list)})
                break

            if len(cb_seed_train.seed_candidates) > target_high:
                with jsonlines.open(training_status_log_file, 'a') as fp:
                    fp.write({'itr_no': i, 'status': 'Early stop: > target_high', 'seed_candidates': len(cb_seed_train.seed_candidates)})
                break

        print("--------------------------Dumping Results (during tuning)------------------------")
        log_file = os.path.join(train_result_dir, f'{cb_train_context}.json')
        print("log_file: ", log_file)
        cb_seed_train.dump_training_results(log_file)

        # Remove selected seeds from global corpus to avoid duplicates next contexts
        removed_cnt = 0
        for seed in list(cb_seed_train.seed_candidates):
            if seed in corpus_list:
                corpus_list.remove(seed)
                removed_cnt += 1
        print(f"[tuner] Context {cb_train_context}: removed {removed_cnt} seed(s) from corpus after full training")

    return cb_adaptive_thresholds


def train_model(simp_seed_dir: str, cb_train_cpus: List[str],
                train_result_dir: str, tar_covs: List[str],
                cov_incr_results: str, cb_epoch_num: int, seed_minimization: bool = True) -> None:
    """
    Train CB model using pre-tuned thresholds for each context.
    """
    cb_adaptive_pick_threshold = 10
    cb_reset_window = 3
    cb_num_seed_arms = 100
    ensure_dir_exists(train_result_dir)

    if seed_minimization:
        with open(cov_incr_results, 'r') as fp:
            cov_incr_dict = json.load(fp)

    corpus_list = filter_training_seed_corpus(
        os.listdir(simp_seed_dir), cb_train_cpus, cb_num_seed_arms,
        "model training"
    )

    cb_adaptive_thresholds = load_cb_thresholds(train_result_dir)
    if not cb_adaptive_thresholds:
        raise FileNotFoundError(f"No thresholds found at {thresholds_file_path(train_result_dir)}. Run --method fine_tune_threshold first.")

    for cb_train_context in tqdm(tar_covs, desc="Training contexts"):
        print(f"--------------Training Context {cb_train_context}--------------------")
        training_status_log_file = join(train_result_dir, f'train_status_{cb_train_context}.log')
        with open(training_status_log_file, 'w') as fp:
            pass
        train_result_seed_dir = join(train_result_dir, f'{cb_train_context}')

        if seed_minimization:
            context_cov_incr = cov_incr_dict[cb_train_context]
        else:
            context_cov_incr = {}

        target_low = int(math.floor(0.9 * cb_num_seed_arms))
        target_high = int(math.ceil(1.1 * cb_num_seed_arms))

        if cb_train_context in cb_adaptive_thresholds:
            cb_adaptive_threshold = cb_adaptive_thresholds[cb_train_context]
            print(f"[train] Context {cb_train_context}: using threshold {cb_adaptive_threshold:.4f}")
        else:
            cb_adaptive_threshold = 5.0
            print(f"[train][WARN] Context {cb_train_context}: threshold missing; using default {cb_adaptive_threshold:.4f}")

        seed_list = copy.deepcopy(corpus_list)

        CBAlgos = get_cbalgos_module()
        cb_seed_train = CBAlgos.CBalgo_Adaptive(int(cb_train_context), cb_reset_window,
                                                cb_adaptive_threshold, cb_adaptive_pick_threshold,
                                                cb_epoch_num, cb_num_seed_arms)

        print("----------------Warm Up--------------------")
        random.seed(42)
        chosen_seeds = random.sample(seed_list, cb_num_seed_arms)
        for seed in chosen_seeds:
            seed_list.remove(seed)
        cb_seed_train.init_arms(chosen_seeds)

        for seed in tqdm(cb_seed_train.seeds, desc="Warm up"):
            if seed not in cb_seed_train.ave_rewards:
                cb_seed_train.ave_rewards[seed] = {"ave": 0, "each_t": [], "removed": False, "select_count": 0}

            if seed_minimization:
                cov_inc_percent, cb_seed_train = seed_reward_no_sim(cb_train_cpus, cb_train_context,
                                                                    simp_seed_dir, cb_seed_train,
                                                                    seed, context_cov_incr)
            else:
                cov_inc_percent, cb_seed_train = seed_reward(cb_train_cpus, cb_train_context, simp_seed_dir,
                                                             cb_seed_train, seed)
            cb_seed_train.update_policy(seed, cov_inc_percent)
            _ = cb_seed_train.policy.predict_expectations(cb_seed_train.context)

        print("----------------Start Training--------------------")
        train_iter = tqdm(range(cb_epoch_num), desc=f"Epochs {cb_train_context}", leave=False)
        for i in train_iter:
            selected_seed = cb_seed_train.select_arm()
            if seed_minimization:
                cov_inc_percent, cb_seed_train = seed_reward_no_sim(cb_train_cpus, cb_train_context,
                                                                    simp_seed_dir, cb_seed_train,
                                                                    selected_seed, context_cov_incr)
            else:
                cov_inc_percent, cb_seed_train = seed_reward(cb_train_cpus, cb_train_context, simp_seed_dir,
                                                             cb_seed_train, selected_seed)

            cb_seed_train.update_policy(selected_seed, cov_inc_percent)
            train_iter.set_postfix(cands=len(cb_seed_train.seed_candidates), remaining=len(seed_list))
            is_reset, seed_list = cb_seed_train.check_reset(selected_seed, seed_list)
            if is_reset:
                with jsonlines.open(training_status_log_file, 'a') as fp:
                    fp.write({'itr_no': i, 'arm': selected_seed, 'is_reset': is_reset, 'add_arm': cb_seed_train.seeds[-1]})

            if len(seed_list) == 0:
                with jsonlines.open(training_status_log_file, 'a') as fp:
                    fp.write({'itr_no': i, 'status': 'No extra seeds', 'seed_len': len(seed_list)})
                break

            if len(cb_seed_train.seed_candidates) > target_high:
                with jsonlines.open(training_status_log_file, 'a') as fp:
                    fp.write({'itr_no': i, 'status': 'Early stop: > target_high', 'seed_candidates': len(cb_seed_train.seed_candidates)})
                break

        print("--------------------------Dumping Results------------------------")
        log_file = os.path.join(train_result_dir, f'{cb_train_context}.json')
        print("log_file: ", log_file)
        cb_seed_train.dump_training_results(log_file)

        thehuzz_utils.delete_dir(train_result_seed_dir, True)
        ensure_dir_exists(train_result_seed_dir)
        for seed in cb_seed_train.seed_candidates:
            corpus_list.remove(seed)
            from_file = os.path.join(simp_seed_dir, seed)
            to_file = os.path.join(train_result_seed_dir, seed)
            subprocess.call(['cp', from_file, to_file])


def refuzz_train_cov_tests(simp_seed_dir: str, cb_train_cpus: List[str],
                             train_result_dir: str, tar_covs: List[str],
                             cov_incr_results: str, cb_epoch_num: int, seed_minimization: bool = True) -> None:
    """
    Backward-compatible wrapper: first tune thresholds, then train model.
    """
    _ = fine_tune_threshold(simp_seed_dir, cb_train_cpus, train_result_dir, tar_covs, cov_incr_results, cb_epoch_num, seed_minimization=seed_minimization)
    train_model(simp_seed_dir, cb_train_cpus, train_result_dir, tar_covs, cov_incr_results, cb_epoch_num, seed_minimization=seed_minimization)


def report_duplicate_filenames_across_contexts(train_result_dir: str, report_path: Optional[str] = None) -> int:
    """
    Report duplicate filenames (filename-only match) across all immediate subdirectories (contexts)
    under train_result_dir. Does not delete or modify any files. Returns total duplicate entries reported.
    """
    assert_dir_exists(train_result_dir, f"Training result dir not found: {train_result_dir}")
    contexts = [d for d in os.listdir(train_result_dir) if os.path.isdir(join(train_result_dir, d))]
    contexts.sort()

    if report_path is None:
        report_path = join(train_result_dir, "duplicates_report.jsonl")

    dup_count = 0
    seen = {}

    with jsonlines.open(report_path, 'w') as writer:
        for ctx in contexts:
            ctx_dir = join(train_result_dir, ctx)
            try:
                entries = sorted(os.listdir(ctx_dir))
            except FileNotFoundError:
                # context dir may not exist if nothing was produced
                continue

            for fn in entries:
                full_path = join(ctx_dir, fn)
                if not os.path.isfile(full_path):
                    continue
                if fn not in seen:
                    seen[fn] = {"context": ctx, "path": full_path}
                else:
                    writer.write({
                        "filename": fn,
                        "first_context": seen[fn]["context"],
                        "first_path": seen[fn]["path"],
                        "dup_context": ctx,
                        "dup_path": full_path
                    })
                    dup_count += 1

    print(f"[dup-report] Found {dup_count} duplicate filenames across contexts. Report saved to {report_path}")
    return dup_count


def parse_args(argv: Optional[List[str]] = None):
    refuzz_source_cfg = project_config.argVars["refuzz_train_source"]
    training_processors_cfg = project_config.argVars["training_processors"]
    feedback_cov_cfg = project_config.argVars["feedback_cov_types"]
    refuzz_method_cfg = project_config.argVars["refuzz_train_method"]
    refuzz_epoch_cfg = project_config.argVars["refuzz_epoch_num"]

    parser = argparse.ArgumentParser(description="ReFuzz training utility")
    parser.add_argument("--method", required=True, choices=["vul_train", "refuzz_train", "seed_mini", "pre_train_1", "pre_train_2"], help="Training method to run")
    parser.add_argument(f"-{refuzz_method_cfg['s']}", "--refuzz_train_method", dest="method", choices=refuzz_method_cfg["c"], help=argparse.SUPPRESS)
    parser.add_argument("--train-root", dest="train_root", default=os.getenv("REFUZZ_TRAIN_ROOT") or TRAIN_ROOT, help="Training root directory")
    parser.add_argument("--interesting-tests-root", dest="interesting_tests_root", default=INTEREST_TESTS20K_ROOT, help="interesting_tests20K input root for seed_mini")
    parser.add_argument("--tar-cov", dest="tar_cov_metric", choices=cov_types, default="cond", help="Target coverage metric")
    parser.add_argument(f"-{refuzz_source_cfg['s']}", "--refuzz_train_source", default=refuzz_source_cfg["v"], choices=refuzz_source_cfg["c"], help=refuzz_source_cfg["h"])
    parser.add_argument(f"-{training_processors_cfg['s']}", "--training_processors", nargs="+", default=training_processors_cfg["v"], choices=training_processors_cfg["c"], help=training_processors_cfg["h"])
    parser.add_argument(f"-{feedback_cov_cfg['s']}", "--feedback_cov_types", nargs="+", default=feedback_cov_cfg["v"], choices=cov_types, help=feedback_cov_cfg["h"])
    parser.add_argument("--no-threads", type=int, default=10, help="Number of parallel threads (used by method: pre_train_1)")
    parser.add_argument("--tot-sim-time", type=int, default=100000000, help="Total simulation time per test (used by method: pre_train_1)")
    parser.add_argument(f"-{refuzz_epoch_cfg['s']}", "--refuzz_epoch_num", type=int, default=refuzz_epoch_cfg["v"], help=refuzz_epoch_cfg["h"])
    return parser.parse_args(argv)


def main():
    args = parse_args()
    method = args.method

    global TRAIN_ROOT, INTEREST_TESTS20K_ROOT, tar_cov_metric, feedback_cov_types
    TRAIN_ROOT = abspath(args.train_root)
    INTEREST_TESTS20K_ROOT = abspath(args.interesting_tests_root)
    if method in ["refuzz_train", "vul_train"]:
        tar_cov_metric = validate_single_feedback_cov(args.feedback_cov_types)
        feedback_cov_types = [tar_cov_metric]
    else:
        tar_cov_metric = args.tar_cov_metric
        feedback_cov_types = [tar_cov_metric]
    refresh_train_roots()
    fuzzers = source_to_fuzzers(args.refuzz_train_source)

    if method == 'vul_train':
        src_dir = join(TRAIN_ROOT, "existing_bugs")
        cb_train_cpus = resolve_training_processors(args.training_processors)
        train_result_dir = build_train_result_dir(args.refuzz_train_source, args.training_processors, tar_cov_metric)
        dst_dir = join(train_result_dir, "vul_train")
        train_log = join(dst_dir, 'train.log')
        riscv_filelist = get_vul_train_files(src_dir, args.refuzz_train_source)
        validate_simulation_setup(cb_train_cpus, 1)
        confirm_and_remove_destinations([dst_dir])
        train_vul_tests(riscv_filelist, dst_dir, cb_train_cpus, train_log)

    elif method == 'seed_mini':
        seed_mini(
            INTEREST_TESTS20K_ROOT,
            fuzzers,
            [train_cores_dict[cpu] for cpu in args.training_processors],
        )

    elif method == 'pre_train_1':
        pre_train(
            args.no_threads,
            args.tot_sim_time,
            fuzzers,
            [train_cores_dict[cpu] for cpu in args.training_processors],
        )

    elif method == 'pre_train_2':
        train_cpus = [train_cores_dict[cpu] for cpu in args.training_processors]
        cov_contexts = train_config_dict[tar_cov_metric]
        context_samples = len(train_contexts_dict[tar_cov_metric])
        test_dir = get_corpus_dir(fuzzers)
        cov_dir = get_cov_dump_dir(fuzzers)
        cov_incr_file = join(cov_dir, f"cov_incr_{''.join(fuzzers)}.json")
        validate_pretrain_coverage_inputs(test_dir, cov_dir, train_cpus, fuzzers)
        validate_training_context_inputs(train_cpus, cov_contexts, context_samples)
        confirm_and_remove_destinations([cov_incr_file])
        cal_ave_cov_incr_each_test_each_context(test_dir, cov_dir, train_cpus, cov_contexts, context_samples, cov_incr_file)

    elif method == 'refuzz_train':
        train_paths = build_refuzz_train_paths(args.refuzz_train_source, args.training_processors, args.feedback_cov_types)
        tar_covs = train_paths["tar_covs"]
        cb_train_cpus = train_paths["train_cpus"]
        dst_dir = train_paths["train_result_dir"]
        corpus_dir_path = train_paths["corpus_dir"]

        validate_training_context_inputs(
            cb_train_cpus,
            tar_covs,
            len(train_contexts_dict[tar_cov_metric]),
        )
        get_cbalgos_module()
        cleanup_targets = refuzz_train_cleanup_targets(dst_dir)
        confirm_and_remove_destinations(cleanup_targets)
        ensure_dir_exists(dst_dir)

        cov_incr_results = train_paths["cov_incr_results"]
        refuzz_train_cov_tests(corpus_dir_path, cb_train_cpus, dst_dir, tar_covs, cov_incr_results, args.refuzz_epoch_num, seed_minimization=True)
        _ = report_duplicate_filenames_across_contexts(dst_dir, join(dst_dir, "duplicates_report.jsonl"))
    else:
        raise ValueError(f"Error: method {method} does not exist")


if __name__ == '__main__':
    main()

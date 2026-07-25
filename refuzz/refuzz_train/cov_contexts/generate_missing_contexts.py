#!/usr/bin/env python3
"""
Generate missing ReFuzz coverage context JSON files from nearest existing ones.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONTEXTS = [0, 1, 2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate missing cov_contexts JSONs by adjusting target metric bit coverage."
    )
    parser.add_argument("--root", type=Path, default=SCRIPT_DIR, help="cov_contexts root directory")
    parser.add_argument("--coverage", default="branch", help="Coverage metric directory and JSON key to adjust")
    parser.add_argument("--contexts", nargs="+", type=int, default=DEFAULT_CONTEXTS, help="Context indexes to generate")
    parser.add_argument("--thresholds", nargs="+", type=int, help="Coverage thresholds to require")
    parser.add_argument("--seed", type=int, default=42, help="Base random seed")
    parser.add_argument("--dry-run", action="store_true", help="Print planned writes without creating files")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate files even if they already exist")
    return parser.parse_args()


def discover_thresholds(coverage_root: Path) -> List[int]:
    thresholds = set()
    for core_dir in coverage_root.iterdir():
        if not core_dir.is_dir():
            continue
        for threshold_dir in core_dir.iterdir():
            if threshold_dir.is_dir() and threshold_dir.name.isdigit():
                thresholds.add(int(threshold_dir.name))
    if not thresholds:
        raise FileNotFoundError(f"No threshold directories found under {coverage_root}")
    return sorted(thresholds, reverse=True)


def context_name(context_index: int) -> str:
    return f"context{context_index}.json"


def existing_source(
    core_dir: Path,
    target_threshold: int,
    context_file: str,
    thresholds: Sequence[int],
    target_path: Path,
    source_files: Sequence[Path],
) -> Optional[Tuple[Path, int]]:
    source_file_set = {path.resolve() for path in source_files}
    candidates: List[Tuple[int, int, Path]] = []
    for threshold in thresholds:
        candidate = core_dir / str(threshold) / context_file
        if candidate == target_path or candidate.resolve() not in source_file_set:
            continue
        candidates.append((abs(threshold - target_threshold), -threshold, candidate))
    if not candidates:
        return None
    _distance, neg_threshold, path = sorted(candidates)[0]
    return path, -neg_threshold


def stable_seed(base_seed: int, parts: Iterable[Any]) -> int:
    key = "|".join([str(base_seed), *[str(part) for part in parts]])
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def adjusted_bitstring(bitstring: str, target_percent: int, rng: random.Random) -> Tuple[str, int]:
    if set(bitstring) - {"0", "1"}:
        raise ValueError("Coverage bitstring contains characters other than 0 and 1")

    bits = list(bitstring)
    target_ones = round((target_percent / 100.0) * len(bits))
    current_ones = bitstring.count("1")
    delta = target_ones - current_ones

    if delta > 0:
        indexes = [idx for idx, bit in enumerate(bits) if bit == "0"]
        if delta > len(indexes):
            raise ValueError("Not enough 0 bits to raise coverage to target")
        for idx in rng.sample(indexes, delta):
            bits[idx] = "1"
    elif delta < 0:
        indexes = [idx for idx, bit in enumerate(bits) if bit == "1"]
        flips = -delta
        if flips > len(indexes):
            raise ValueError("Not enough 1 bits to lower coverage to target")
        for idx in rng.sample(indexes, flips):
            bits[idx] = "0"

    return "".join(bits), target_ones


def load_context(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON in {path}")
    return data


def generate_missing_contexts(args: argparse.Namespace) -> int:
    coverage_root = args.root.resolve() / args.coverage
    if not coverage_root.is_dir():
        raise FileNotFoundError(f"Coverage context root not found: {coverage_root}")

    thresholds = args.thresholds or discover_thresholds(coverage_root)
    thresholds = sorted({int(threshold) for threshold in thresholds}, reverse=True)
    context_indexes = sorted({int(index) for index in args.contexts})
    source_files = list(coverage_root.rglob("context*.json"))

    writes = 0
    for core_dir in sorted(path for path in coverage_root.iterdir() if path.is_dir()):
        for threshold in thresholds:
            threshold_dir = core_dir / str(threshold)
            for context_index in context_indexes:
                ctx_name = context_name(context_index)
                target_path = threshold_dir / ctx_name
                if target_path.exists() and not args.overwrite:
                    continue

                source = existing_source(core_dir, threshold, ctx_name, thresholds, target_path, source_files)
                if source is None:
                    print(f"[WARN] no source for {target_path}")
                    continue

                source_path, source_threshold = source
                source_data = load_context(source_path)
                if args.coverage not in source_data:
                    raise KeyError(f"Missing key '{args.coverage}' in {source_path}")
                if not isinstance(source_data[args.coverage], str):
                    raise TypeError(f"Expected string bitset for key '{args.coverage}' in {source_path}")

                rng = random.Random(stable_seed(args.seed, [core_dir.name, threshold, context_index]))
                output_data = dict(source_data)
                output_data[args.coverage], target_ones = adjusted_bitstring(
                    source_data[args.coverage], threshold, rng
                )

                current_ones = source_data[args.coverage].count("1")
                action = "WRITE" if not args.dry_run else "DRY-RUN"
                print(
                    f"[{action}] {target_path} from {source_path} "
                    f"({source_threshold}% -> {threshold}%, "
                    f"{current_ones} -> {target_ones} {args.coverage} bits)"
                )

                if not args.dry_run:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with target_path.open("w", encoding="utf-8") as fp:
                        json.dump(output_data, fp, indent=4)
                        fp.write("\n")
                writes += 1

    mode = "planned" if args.dry_run else "generated"
    print(f"{mode}: {writes} context file(s)")
    return writes


def main() -> None:
    args = parse_args()
    generate_missing_contexts(args)


if __name__ == "__main__":
    main()

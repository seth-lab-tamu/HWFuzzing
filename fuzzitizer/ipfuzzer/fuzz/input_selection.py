import argparse
import os
import re
import json
from pathlib import Path
import shutil
import sys

import numpy as np


_INPUT_RE = re.compile(r"^ip_file_(\d+)\.csv$")


def merge_cov_dicts(dict1, dict2):
    
    merged_cov_list = np.logical_or(dict1, dict2).astype(int)

    return merged_cov_list


def load_coverage(coverage_dir: Path) -> dict[int, np.ndarray]:
    coverage_dir = Path(coverage_dir)
    if not coverage_dir.is_dir():
        raise NotADirectoryError(f"coverage directory not found: {coverage_dir}")

    all_cov_data = {}
    vector_length = None
    for filename in os.listdir(coverage_dir):
        cov_dict_file = coverage_dir / filename
        file_details = re.match(r"^rtl_cov_out_([\d]+)\.json$", filename)
        if file_details is None:
            if filename.startswith("rtl_cov_out_"):
                raise ValueError(f"malformed coverage filename: {filename}")
            continue
        file_id = int(file_details.group(1))
        if file_id in all_cov_data:
            raise ValueError(f"duplicate coverage input ID: {file_id}")
        with cov_dict_file.open('r', encoding='utf-8') as fp:
            cov_dict = json.load(fp)
            if not isinstance(cov_dict, dict) or not all(
                isinstance(value, str) for value in cov_dict.values()
            ):
                raise ValueError(f"coverage data must be an object of binary strings: {filename}")
            cov_dict = "".join(cov_dict.values())
            if any(bit not in "01" for bit in cov_dict):
                raise ValueError(f"coverage data must contain only binary strings: {filename}")
            if vector_length is None:
                vector_length = len(cov_dict)
            elif len(cov_dict) != vector_length:
                raise ValueError(
                    f"coverage vector length mismatch in {filename}: "
                    f"expected {vector_length}, got {len(cov_dict)}"
                )
            cov_dict = np.frombuffer(cov_dict.encode('ascii'), dtype='u1') - ord('0')
            all_cov_data[file_id] = cov_dict.astype('int')
    return all_cov_data


def select_inputs(all_cov_data: dict[int, np.ndarray]) -> tuple[list[int], int]:

    input_files_tot_cov = {k: np.sum(v==1) for k, v in all_cov_data.items()}

    sorted_input_files = sorted(input_files_tot_cov, key=lambda k: input_files_tot_cov[k], reverse=True)



    min_set = []
    merged_cov = None
    merged_tot = 0
    while(sorted_input_files):
        no_to_pick = max((len(sorted_input_files)* 5) // 100, 1)
        for i in range(no_to_pick):
            add_id = sorted_input_files[i]
            if merged_cov is None: 
                new_merged_cov = all_cov_data[add_id]
            else: 
                new_merged_cov = merge_cov_dicts(merged_cov, all_cov_data[add_id])
            new_merged_tot = np.sum(new_merged_cov==1)
            if new_merged_tot > merged_tot: 
                min_set.append(add_id)
                merged_tot = new_merged_tot
                merged_cov = new_merged_cov

        sorted_input_files = sorted_input_files[no_to_pick:]
        input_files_tot_cov = {}
        for i in sorted_input_files: 
            new_merged_cov = merge_cov_dicts(merged_cov, all_cov_data[i])
            new_merged_tot = np.sum(new_merged_cov==1)

            if new_merged_tot <= merged_tot:
                continue
            else: 
                input_files_tot_cov[i] = new_merged_tot - merged_tot
        
        sorted_input_files = sorted(input_files_tot_cov, key=lambda k: input_files_tot_cov[k], reverse=True)



    return min_set, int(merged_tot)


def minimize_peripheral(
    peripheral: str,
    coverage_dir: Path,
    input_dir: Path,
    output_dir: Path,
) -> dict:
    coverage_dir = Path(coverage_dir)
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    if not coverage_dir.is_dir():
        raise NotADirectoryError(f"coverage directory not found: {coverage_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"input directory not found: {input_dir}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")

    all_cov_data = load_coverage(coverage_dir)
    selected_ids, covered_points = select_inputs(all_cov_data)
    selected_csvs = [input_dir / f"ip_file_{input_id}.csv" for input_id in selected_ids]
    for csv_file in selected_csvs:
        if not csv_file.is_file():
            raise FileNotFoundError(f"selected input CSV not found: {csv_file}")

    manifest = {
        "peripheral": peripheral,
        "input_count": len(all_cov_data),
        "selected_count": len(selected_ids),
        "covered_points": covered_points,
        "selected_ids": selected_ids,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    for csv_file in selected_csvs:
        shutil.copy2(csv_file, output_dir / csv_file.name)
    with (output_dir / "selected_inputs.json").open("w", encoding="utf-8") as manifest_file:
        json.dump(manifest, manifest_file, indent=2)
        manifest_file.write("\n")

    print(f"{peripheral}: {len(all_cov_data)} inputs -> {len(selected_ids)} selected")
    return manifest


def materialize_replay_inputs(peripheral, output_dir, input_paths):
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")

    selected = {}
    for input_path in input_paths:
        input_path = Path(input_path)
        match = _INPUT_RE.fullmatch(input_path.name)
        if match is None:
            raise ValueError(f"malformed peripheral input filename: {input_path.name}")
        if not input_path.is_file():
            raise FileNotFoundError(f"interesting input CSV not found: {input_path}")
        selected[int(match.group(1))] = input_path

    selected_ids = sorted(selected)
    manifest = {
        "peripheral": peripheral,
        "input_count": len(selected_ids),
        "selected_count": len(selected_ids),
        "covered_points": None,
        "selected_ids": selected_ids,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for input_id in selected_ids:
        shutil.copy2(selected[input_id], output_dir / f"ip_file_{input_id}.csv")
    with (output_dir / "selected_inputs.json").open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return manifest


def prepare_input_corpora(
    policy,
    peripheral,
    coverage_dir,
    input_dir,
    selected_dir,
    replay_dir,
    interesting_inputs,
):
    input_dir = Path(input_dir)
    selected_dir = Path(selected_dir)
    selected_manifest = minimize_peripheral(
        peripheral, coverage_dir, input_dir, selected_dir
    )

    if policy == "greedy":
        replay_sources = [
            selected_dir / f"ip_file_{input_id}.csv"
            for input_id in selected_manifest["selected_ids"]
        ]
    elif policy == "interesting":
        replay_sources = interesting_inputs
    else:
        raise ValueError(f"unsupported replay input policy: {policy}")

    replay_manifest = materialize_replay_inputs(
        peripheral, replay_dir, replay_sources
    )
    return selected_manifest, replay_manifest


def load_selected_inputs(output_dir):
    output_dir = Path(output_dir)
    with (output_dir / "selected_inputs.json").open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    selected = []
    for input_id in manifest["selected_ids"]:
        if not isinstance(input_id, int) or input_id < 0:
            raise ValueError(f"invalid selected input ID: {input_id!r}")
        input_path = output_dir / f"ip_file_{input_id}.csv"
        if not input_path.is_file():
            raise FileNotFoundError(f"selected input CSV not found: {input_path}")
        selected.append((input_id, input_path))
    return selected


def minimize_all_peripherals(config_file: Path, output_root: Path) -> dict[str, dict]:
    config_file = Path(config_file)
    output_root = Path(output_root)
    with config_file.open("r", encoding="utf-8") as config_stream:
        config = json.load(config_stream, object_pairs_hook=reject_duplicate_json_keys)
    if not isinstance(config, dict):
        raise ValueError("batch configuration must be a JSON object")

    resolved = []
    for peripheral, entry in config.items():
        if not isinstance(peripheral, str) or not isinstance(entry, dict):
            raise ValueError("each batch entry must map a peripheral name to an object")
        validate_peripheral_name(peripheral)
        missing = [field for field in ("coverage_dir", "input_dir") if field not in entry]
        if missing:
            raise ValueError(f"{peripheral}: missing configuration field {missing[0]}")
        coverage_dir = Path(entry["coverage_dir"])
        input_dir = Path(entry["input_dir"])
        if not coverage_dir.is_absolute():
            coverage_dir = config_file.parent / coverage_dir
        if not input_dir.is_absolute():
            input_dir = config_file.parent / input_dir
        resolved.append((peripheral, coverage_dir, input_dir))

    resolved_output_root = output_root.resolve()
    if output_root.exists() and not output_root.is_dir():
        raise NotADirectoryError(f"batch output root is not a directory: {output_root}")
    for peripheral, _, _ in resolved:
        target = output_root / peripheral
        if target.is_symlink():
            raise ValueError(f"batch output cannot be a symlink: {target}")
        if target.resolve().parent != resolved_output_root:
            raise ValueError(f"unsafe peripheral output path: {peripheral}")
        if target.exists():
            if not target.is_dir():
                raise NotADirectoryError(f"peripheral output is not a directory: {target}")
            if any(target.iterdir()):
                raise FileExistsError(f"output directory is not empty: {target}")

    manifests = {}
    for peripheral, coverage_dir, input_dir in resolved:
        manifests[peripheral] = minimize_peripheral(
            peripheral,
            coverage_dir,
            input_dir,
            output_root / peripheral,
        )
    return manifests


def reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def validate_peripheral_name(peripheral: str) -> None:
    if (
        not peripheral
        or peripheral in {".", ".."}
        or Path(peripheral).is_absolute()
        or "/" in peripheral
        or "\\" in peripheral
    ):
        raise ValueError(f"unsafe peripheral name: {peripheral!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimize peripheral fuzzing inputs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    single = subparsers.add_parser("single", help="minimize one peripheral")
    single.add_argument("--peripheral", required=True)
    single.add_argument("--coverage-dir", type=Path, required=True)
    single.add_argument("--input-dir", type=Path, required=True)
    single.add_argument("--output-dir", type=Path, required=True)

    batch = subparsers.add_parser("batch", help="minimize peripherals from a JSON config")
    batch.add_argument("--config", type=Path, required=True)
    batch.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "single":
            minimize_peripheral(
                args.peripheral,
                args.coverage_dir,
                args.input_dir,
                args.output_dir,
            )
        else:
            minimize_all_peripherals(args.config, args.output_root)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

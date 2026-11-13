"""Load the artifact handoff produced by IPFuzz."""

import json
from itertools import zip_longest
from pathlib import Path

from peripheral_inputs import containedpath


def uniquepairs(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def readjson(path):
    path = Path(path)
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    try:
        return json.loads(contents, object_pairs_hook=uniquepairs)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: cannot read valid JSON: {error}") from error


def requireobject(document, path, description):
    if not isinstance(document, dict):
        raise ValueError(f"{path}: {description} must be a JSON object")
    return document


def loadinterface(handoff_root, ipfuzz_root):
    path = containedpath(
        Path(handoff_root) / "soc_input_manifest.json",
        ipfuzz_root,
        "interface manifest",
    )
    document = requireobject(readjson(path), path, "interface manifest")
    unsupported_fields = set(document) - {"peripherals"}
    if unsupported_fields:
        raise ValueError(
            f"{path}: unsupported interface-manifest fields: "
            f"{', '.join(sorted(unsupported_fields))}"
        )
    peripherals = document.get("peripherals")
    if not isinstance(peripherals, dict):
        raise ValueError(f"{path}: peripherals must be a JSON object")
    for identifier, entry in peripherals.items():
        if not identifier:
            raise ValueError(f"{path}: peripheral identifier must not be empty")
        if not isinstance(entry, dict) or not isinstance(entry.get("soc"), str):
            raise ValueError(f"{path}: invalid interface entry for {identifier!r}")
        required_fields = {"soc", "address_width", "word_bits", "alignment"}
        unsupported_fields = set(entry) - required_fields
        if unsupported_fields:
            raise ValueError(
                f"{path}: peripheral {identifier!r} has unsupported fields: "
                f"{', '.join(sorted(unsupported_fields))}"
            )
        missing_fields = required_fields - set(entry)
        if missing_fields:
            raise ValueError(
                f"{path}: peripheral {identifier!r} is missing fields: "
                f"{', '.join(sorted(missing_fields))}"
            )
    return peripherals


def loadruns(handoff_root, ipfuzz_root, known_peripherals):
    path = containedpath(
        Path(handoff_root) / "peripheral_runs.json",
        ipfuzz_root,
        "peripheral-run index",
    )
    document = requireobject(readjson(path), path, "peripheral-run index")
    unknown = set(document) - set(known_peripherals)
    if unknown:
        raise ValueError(f"{path}: unknown peripheral identifiers: {', '.join(sorted(unknown))}")

    resolved = {}
    for identifier, run_path in document.items():
        if not identifier:
            raise ValueError(f"{path}: peripheral identifier must not be empty")
        if not isinstance(run_path, str) or not run_path:
            raise ValueError(f"{path}: path for {identifier!r} must be a nonempty string")
        run_path = Path(run_path)
        if run_path.is_absolute():
            raise ValueError(f"{path}: path for {identifier!r} must be relative")
        run_dir = containedpath(
            Path(handoff_root) / run_path,
            ipfuzz_root,
            f"run path for {identifier!r}",
        )
        if not run_dir.exists():
            raise ValueError(f"{path}: run path for {identifier!r} does not exist: {run_dir}")
        if not run_dir.is_dir():
            raise ValueError(f"{path}: run path for {identifier!r} is not a directory: {run_dir}")
        resolved[identifier] = run_dir
    return resolved


def loadselection(run_dir, peripheral, ipfuzz_root):
    selected_dir = containedpath(
        Path(run_dir) / "selected_inputs",
        ipfuzz_root,
        f"selected-input directory for {peripheral!r}",
    )
    if not selected_dir.is_dir():
        raise ValueError(f"{selected_dir}: selected-input path is not a directory")
    manifest_path = containedpath(
        selected_dir / "selected_inputs.json",
        ipfuzz_root,
        f"selected-input manifest for {peripheral!r}",
    )
    manifest = requireobject(
        readjson(manifest_path), manifest_path, "selected-input manifest"
    )
    if manifest.get("peripheral") != peripheral:
        raise ValueError(
            f"{manifest_path}: peripheral must be {peripheral!r}, "
            f"found {manifest.get('peripheral')!r}"
        )
    selected_ids = manifest.get("selected_ids")
    if not isinstance(selected_ids, list):
        raise ValueError(f"{manifest_path}: selected_ids must be a list")

    seen = set()
    for input_id in selected_ids:
        if type(input_id) is not int:
            raise ValueError(f"{manifest_path}: selected input IDs must be integers")
        if input_id < 0:
            raise ValueError(f"{manifest_path}: selected input IDs must be nonnegative")
        if input_id in seen:
            raise ValueError(f"{manifest_path}: duplicate selected input ID {input_id}")
        seen.add(input_id)

    expected = {f"ip_file_{input_id}.csv" for input_id in selected_ids}
    actual = {
        path.name
        for path in selected_dir.glob("*.csv")
        if not path.name.startswith(".")
    }
    missing = expected - actual
    if missing:
        raise ValueError(f"{selected_dir}: missing selected CSVs: {', '.join(sorted(missing))}")
    undeclared = actual - expected
    if undeclared:
        raise ValueError(
            f"{selected_dir}: undeclared selected CSVs: {', '.join(sorted(undeclared))}"
        )

    selected = []
    for input_id in selected_ids:
        csv_path = selected_dir / f"ip_file_{input_id}.csv"
        resolved_csv = containedpath(
            csv_path,
            ipfuzz_root,
            f"selected CSV for {peripheral!r}",
        )
        if not resolved_csv.is_file():
            raise ValueError(f"{csv_path}: selected CSV is not a regular file")
        selected.append({"path": csv_path, "peripheral": peripheral})
    return selected


def loadselectedinputs(
    handoff_root,
    ipfuzz_root,
    soc,
    peripheral_identifiers,
):
    handoff_root = containedpath(handoff_root, ipfuzz_root, "handoff root")
    peripherals = loadinterface(handoff_root, ipfuzz_root)
    target_peripherals = {
        identifier
        for identifier, entry in peripherals.items()
        if entry["soc"] == soc
    }
    configured = set(peripheral_identifiers)
    if target_peripherals != configured:
        missing = configured - target_peripherals
        extra = target_peripherals - configured
        raise ValueError(
            f"IPFuzz interface does not match configured {soc} peripherals; "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )

    runs = loadruns(handoff_root, ipfuzz_root, peripherals)

    selections = []
    for peripheral in sorted(configured & set(runs)):
        peripheral_inputs = loadselection(
            runs[peripheral], peripheral, ipfuzz_root
        )
        selections.append(peripheral_inputs)
    selected = [
        peripheral_input
        for round_inputs in zip_longest(*selections)
        for peripheral_input in round_inputs
        if peripheral_input is not None
    ]
    if not selected:
        raise ValueError(f"IPFuzz handoff contains no selected inputs for SoC {soc}")
    return selected

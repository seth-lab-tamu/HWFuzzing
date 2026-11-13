"""Build the peripheral fuzzer's whole-SoC sanitizer handoff."""

from dataclasses import dataclass
import fcntl
import json
from pathlib import Path
import os
import re
import tempfile


PROPERTY_RE = re.compile(r"^\s*property\s+([A-Za-z_][A-Za-z0-9_$]*)\s*;")
LABEL_RE = re.compile(
    r"^\s*(a_[^:\s]+):\s+(assert|cover)\s+property\b"
)
TYPEDEF_RE = re.compile(r"^\s*typedef\s+")
BEGIN_RE = re.compile(r"\bbegin\b")
END_RE = re.compile(r"^\s*end\b")


@dataclass(frozen=True)
class SvaUnit:
    label: str
    kind: str
    text: str


def finish_cover_statement(lines, label_index):
    line = lines[label_index]
    depth = len(BEGIN_RE.findall(line))
    if depth == 0:
        return label_index + 1
    index = label_index + 1
    while index < len(lines):
        depth += len(BEGIN_RE.findall(lines[index]))
        if END_RE.match(lines[index]):
            depth -= 1
        index += 1
        if depth == 0:
            return index
    raise ValueError("unterminated cover-property action block")


def parse_sva_segments(source_text):
    lines = source_text.splitlines(keepends=True)
    segments = []
    structural = []
    index = 0
    while index < len(lines):
        unit_start = index
        property_index = index
        if TYPEDEF_RE.match(lines[index]):
            property_index += 1
            if property_index >= len(lines) or not PROPERTY_RE.match(lines[property_index]):
                structural.append(lines[index])
                index += 1
                continue
        elif not PROPERTY_RE.match(lines[index]):
            structural.append(lines[index])
            index += 1
            continue

        endproperty_index = property_index + 1
        while (
            endproperty_index < len(lines)
            and not re.match(r"^\s*endproperty\s*;", lines[endproperty_index])
        ):
            endproperty_index += 1
        if endproperty_index >= len(lines):
            raise ValueError("unterminated property declaration")

        label_index = endproperty_index + 1
        while label_index < len(lines) and not LABEL_RE.match(lines[label_index]):
            if PROPERTY_RE.match(lines[label_index]) or re.match(
                r"^\s*(endmodule|bind\b)", lines[label_index]
            ):
                break
            label_index += 1
        if label_index >= len(lines) or not LABEL_RE.match(lines[label_index]):
            structural.append(lines[index])
            index += 1
            continue

        label_match = LABEL_RE.match(lines[label_index])
        label, kind = label_match.groups()
        if kind == "cover":
            unit_end = finish_cover_statement(lines, label_index)
        else:
            unit_end = label_index + 1

        if structural:
            segments.append("".join(structural))
            structural = []
        segments.append(SvaUnit(label, kind, "".join(lines[unit_start:unit_end])))
        index = unit_end

    if structural:
        segments.append("".join(structural))
    return segments


def validate_requested_labels(units_by_label, labels, expected_kind):
    for label in sorted(labels):
        matches = units_by_label.get(label, [])
        if not matches:
            raise ValueError(f"missing {expected_kind} label: {label}")
        if len(matches) != 1:
            raise ValueError(f"duplicate {expected_kind} label: {label}")
        if matches[0].kind != expected_kind:
            raise ValueError(
                f"label {label} is {matches[0].kind}, expected {expected_kind}"
            )


def render_selected_sva(segments, assertion_policy, selected_assertions, retained_covers):
    if assertion_policy not in {"violations", "all"}:
        raise ValueError(f"unknown SoC assertion policy: {assertion_policy}")
    units_by_label = {}
    for segment in segments:
        if isinstance(segment, SvaUnit):
            units_by_label.setdefault(segment.label, []).append(segment)

    validate_requested_labels(units_by_label, selected_assertions, "assert")
    if assertion_policy == "all":
        all_assertions = {
            segment.label
            for segment in segments
            if isinstance(segment, SvaUnit) and segment.kind == "assert"
        }
        validate_requested_labels(units_by_label, all_assertions, "assert")
    validate_requested_labels(units_by_label, retained_covers, "cover")

    selected = []
    for segment in segments:
        if isinstance(segment, str):
            selected.append(segment)
        elif segment.kind == "assert" and (
            assertion_policy == "all" or segment.label in selected_assertions
        ):
            selected.append(segment.text)
        elif segment.kind == "cover" and segment.label in retained_covers:
            selected.append(segment.text)
    return "".join(selected)


def select_soc_sanitizers(
    source_sva: Path,
    destination_sva: Path,
    assertion_policy: str,
    selected_assertions: set[str],
    retained_covers: set[str],
) -> None:
    source_sva = Path(source_sva)
    destination_sva = Path(destination_sva)
    source_text = source_sva.read_text(encoding="utf-8")
    selected_text = render_selected_sva(
        parse_sva_segments(source_text),
        assertion_policy,
        set(selected_assertions),
        set(retained_covers),
    )
    destination_sva.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination_sva.parent,
            prefix=f".{destination_sva.name}.",
            delete=False,
        ) as stream:
            stream.write(selected_text)
            temporary = Path(stream.name)
        source_mode = source_sva.stat().st_mode & 0o777
        temporary.chmod(source_mode)
        os.replace(temporary, destination_sva)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def load_run_index(index_path):
    index_path = Path(index_path)
    if not index_path.exists():
        return {}
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid peripheral run index: {index_path}") from error
    if not isinstance(data, dict) or any(
        not isinstance(name, str) or not isinstance(path, str)
        for name, path in data.items()
    ):
        raise ValueError("peripheral run index must map names to path strings")
    return data


def validate_indexed_runs(ipfuzz_root, handoff_dir, run_index):
    ipfuzz_root = Path(ipfuzz_root).resolve()
    outputs_root = (ipfuzz_root / "outputs").resolve()
    validated = {}
    for peripheral, relative_run in sorted(run_index.items()):
        if not (peripheral.startswith("opn_") or peripheral.startswith("cal_")):
            raise ValueError(f"unsupported peripheral in run index: {peripheral}")
        run_dir = (Path(handoff_dir) / relative_run).resolve()
        try:
            run_dir.relative_to(outputs_root)
        except ValueError as error:
            raise ValueError(
                f"indexed run for {peripheral} is outside outputs/: {run_dir}"
            ) from error
        if not run_dir.is_dir():
            raise FileNotFoundError(f"indexed run for {peripheral} is missing: {run_dir}")
        sanitizer = (
            run_dir
            / "soc_sanitizers"
            / f"sanitizers_{peripheral}.sva"
        )
        if not sanitizer.is_file():
            raise FileNotFoundError(
                f"indexed sanitizer for {peripheral} is missing: {sanitizer}"
            )
        validated[peripheral] = (run_dir, sanitizer)
    return validated


def render_run_index(run_index):
    ordered = {name: run_index[name] for name in sorted(run_index)}
    return json.dumps(ordered, indent=2) + "\n"


def render_filelist(ipfuzz_root, validated_runs, soc):
    lines = []
    for peripheral, (run_dir, sanitizer) in sorted(validated_runs.items()):
        if not peripheral.startswith(f"{soc}_"):
            continue
        relative = sanitizer.resolve().relative_to(Path(ipfuzz_root).resolve())
        lines.append(f"$IPFUZZ_ROOT/{relative.as_posix()}")
    return "\n".join(lines) + ("\n" if lines else "")


def create_temporary_public_file(destination, content):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        delete=False,
    ) as stream:
        stream.write(content)
        temporary = Path(stream.name)
    if destination.exists():
        temporary.chmod(destination.stat().st_mode & 0o777)
    return temporary


def replace_public_files(contents):
    originals = {}
    temporary_files = {}
    for destination, content in contents.items():
        destination = Path(destination)
        originals[destination] = (
            destination.read_bytes() if destination.exists() else None
        )
        temporary_files[destination] = create_temporary_public_file(
            destination, content
        )
    replaced = []
    try:
        for destination in contents:
            os.replace(temporary_files[destination], destination)
            replaced.append(destination)
    except Exception:
        for destination in replaced:
            original = originals[destination]
            if original is None:
                destination.unlink(missing_ok=True)
            else:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=destination.parent,
                    prefix=f".{destination.name}.restore.",
                    delete=False,
                ) as stream:
                    stream.write(original)
                    restore_path = Path(stream.name)
                os.replace(restore_path, destination)
        raise
    finally:
        for temporary in temporary_files.values():
            temporary.unlink(missing_ok=True)


def publish_peripheral_run(
    ipfuzz_root: Path,
    peripheral: str,
    run_dir: Path,
    sanitizer_file: Path,
) -> None:
    ipfuzz_root = Path(ipfuzz_root).resolve()
    run_dir = Path(run_dir).resolve()
    sanitizer_file = Path(sanitizer_file).resolve()
    if not (peripheral.startswith("opn_") or peripheral.startswith("cal_")):
        raise ValueError(f"unsupported peripheral: {peripheral}")
    outputs_root = (ipfuzz_root / "outputs").resolve()
    try:
        run_dir.relative_to(outputs_root)
    except ValueError as error:
        raise ValueError(f"run directory is outside outputs/: {run_dir}") from error
    expected_sanitizer = (
        run_dir / "soc_sanitizers" / f"sanitizers_{peripheral}.sva"
    ).resolve()
    if sanitizer_file != expected_sanitizer:
        raise ValueError(
            f"unexpected sanitizer path for {peripheral}: {sanitizer_file}"
        )
    if not sanitizer_file.is_file():
        raise FileNotFoundError(sanitizer_file)

    handoff_dir = ipfuzz_root / "ipfuzzer_output"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    lock_path = handoff_dir / ".publish.lock"
    index_path = handoff_dir / "peripheral_runs.json"
    with lock_path.open("a+") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        run_index = load_run_index(index_path)
        run_index[peripheral] = Path(
            os.path.relpath(run_dir, handoff_dir)
        ).as_posix()
        validated_runs = validate_indexed_runs(
            ipfuzz_root, handoff_dir, run_index
        )
        contents = {
            handoff_dir / "Flist.opn.fuzz": render_filelist(
                ipfuzz_root, validated_runs, "opn"
            ),
            handoff_dir / "Flist.cal.fuzz": render_filelist(
                ipfuzz_root, validated_runs, "cal"
            ),
            index_path: render_run_index(run_index),
        }
        replace_public_files(contents)

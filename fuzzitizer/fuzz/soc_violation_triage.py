"""Combine IPFuzz and whole-SoC sanitizer violations."""

import csv
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from ipfuzz_handoff import loadinterface, loadruns
from peripheral_inputs import containedpath


SOC_LOG_RE = re.compile(r"rtl_sim_out_(\d+)\.log$")
SOC_ASSERTION_RE = re.compile(
    r"(?:^|\.)(a_[A-Za-z0-9_$]+):\s+started at\s+\S+\s+failed at\s+\S+"
)
SANITIZER_SOURCE_RE = re.compile(
    r"sanitizers_((?:cal|opn)_[A-Za-z0-9_]+)\.sva"
)
ASSERTION_TYPE_RE = re.compile(r"^a_([A-Za-z0-9_$]+)_\d+$")
COVER_RECORD_RE = re.compile(
    r"COVER,\s*Sanitizer:(reachDefFsmState|reachDefFsmTran),\s*"
    r"id=([^,]+),\s*time=\s*(%\d*d|\d+),\s*"
    r"state_reg=([^,]+),\s*([^\"\n]+)"
)

RESET_TYPES = {"InRstDom"}
FSM_TYPES = {
    "defUndefFsmTran", "fromUndefFsmTran", "illFsmTran",
    "reachDefFsmTran",
}
ZERO_TYPES = {"clrOnDbg", "OneTimeZero"}

FIELDNAMES = [
    "perif", "detected", "violation_kind", "assertion",
    "sanitizer_family", "sanitizer_type", "ip_cover_status",
    "soc_cover_status", "ip_input_ids", "soc_program_ids",
    "ip_violation_count", "soc_violation_count", "total_occurrences",
]


def sanitizerfamily(sanitizer_type):
    if sanitizer_type in RESET_TYPES:
        return "reset"
    if sanitizer_type in FSM_TYPES:
        return "fsm"
    if sanitizer_type in ZERO_TYPES:
        return "zero"
    return "unknown"


def sanitizertype(assertion):
    match = ASSERTION_TYPE_RE.fullmatch(assertion)
    return match.group(1) if match else "unknown"


def newrecord(perif, assertion):
    sanitizer_type = sanitizertype(assertion)
    return {
        "perif": perif,
        "assertion": assertion,
        "violation_kind": "assertion",
        "sanitizer_family": sanitizerfamily(sanitizer_type),
        "sanitizer_type": sanitizer_type,
        "ip_cover_status": "",
        "soc_cover_status": "",
        "ip_input_ids": set(),
        "soc_program_ids": set(),
        "ip_violation_count": 0,
        "soc_violation_count": 0,
    }


def parseverilogint(value):
    text = value.strip().replace("_", "").lower()
    literal = re.fullmatch(r"(?:\d+)?'s?([bodh])([0-9a-f]+)", text)
    if literal:
        radix, digits = literal.groups()
        return int(digits, {"b": 2, "o": 8, "d": 10, "h": 16}[radix])
    if text.startswith("0x"):
        return int(text, 16)
    return int(text, 10)


def parsecoverrecord(line, require_runtime_time):
    match = COVER_RECORD_RE.search(line)
    if match is None:
        return None
    sanitizer_type, cover_id, time_text, state_register, payload = (
        match.groups()
    )
    if require_runtime_time and time_text.startswith("%"):
        return None
    fields = {}
    for item in payload.split(","):
        name, separator, value = item.strip().partition("=")
        if separator:
            fields[name] = value.strip()
    assertion = f"a_{cover_id.strip()}"
    state_register = state_register.strip()
    if sanitizer_type == "reachDefFsmState":
        if "state" not in fields:
            return None
        return (
            sanitizer_type, assertion, state_register,
            parseverilogint(fields["state"]), None, None,
        )
    if "from" not in fields or "to" not in fields:
        return None
    return (
        sanitizer_type, assertion, state_register, None,
        parseverilogint(fields["from"]), parseverilogint(fields["to"]),
    )


def loadcovercontext(records, runs, ipfuzz_root):
    cover_peripherals = {
        record["perif"]
        for record in records.values()
        if record["violation_kind"] == "unobserved_fsm_cover"
    }
    identity_peripheral = {}
    transition_points = {}
    state_points = {}
    for peripheral in sorted(cover_peripherals):
        path = containedpath(
            runs[peripheral] / "soc_sanitizers"
            / f"sanitizers_{peripheral}.sva",
            ipfuzz_root,
            f"SoC sanitizer inventory for {peripheral}",
        )
        try:
            stream = path.open(errors="replace")
        except OSError as error:
            raise ValueError(f"cannot read {path}: {error}") from error
        with stream:
            for line in stream:
                point = parsecoverrecord(line, require_runtime_time=False)
                if point is None:
                    continue
                previous = identity_peripheral.get(point)
                if previous is not None and previous != peripheral:
                    raise ValueError(
                        f"ambiguous FSM cover identity in {previous} and "
                        f"{peripheral}: {point}"
                    )
                identity_peripheral[point] = peripheral
                if point[0] == "reachDefFsmTran":
                    transition_points[(peripheral, point[1])] = point
                else:
                    state_points[(peripheral, point[2], point[3])] = point

    for identity, record in records.items():
        if record["violation_kind"] != "unobserved_fsm_cover":
            continue
        transition = transition_points.get(identity)
        if transition is None:
            raise ValueError(
                f"missing SoC FSM transition inventory for "
                f"{record['perif']}:{record['assertion']}"
            )
        source = state_points.get(
            (record["perif"], transition[2], transition[4])
        )
        if source is None:
            raise ValueError(
                f"missing SoC FSM source-state cover for "
                f"{record['perif']}:{record['assertion']}"
            )
        record["transition_cover"] = transition
        record["source_cover"] = source
    return identity_peripheral


def setmetadata(record, row, path):
    metadata = {
        "violation_kind": row["violation_kind"],
        "sanitizer_family": row["sanitizer_family"],
        "sanitizer_type": row["sanitizer_type"],
    }
    if record["ip_violation_count"]:
        for name, value in metadata.items():
            if record[name] != value:
                raise ValueError(
                    f"{path}: conflicting {name} for "
                    f"{record['perif']}:{record['assertion']}"
                )
    else:
        record.update(metadata)


def readipviolations(handoff_root, ipfuzz_root, soc):
    peripherals = loadinterface(handoff_root, ipfuzz_root)
    runs = loadruns(handoff_root, ipfuzz_root, peripherals)
    target_peripherals = {
        peripheral
        for peripheral in runs
        if peripherals[peripheral]["soc"] == soc
    }
    records = {}
    for peripheral in sorted(target_peripherals):
        path = containedpath(
            runs[peripheral] / "triage/violations.csv",
            ipfuzz_root,
            f"violation report for {peripheral}",
        )
        try:
            stream = path.open(newline="", encoding="utf-8")
        except OSError as error:
            raise ValueError(f"cannot read {path}: {error}") from error
        with stream:
            reader = csv.DictReader(stream)
            required = {
                "violation_kind", "input_id", "assertion",
                "sanitizer_family", "sanitizer_type",
            }
            if reader.fieldnames is None or not required.issubset(
                reader.fieldnames
            ):
                raise ValueError(f"{path}: missing required violation columns")
            for row in reader:
                assertion = row["assertion"].strip()
                if not assertion:
                    raise ValueError(f"{path}: violation has no assertion")
                identity = (peripheral, assertion)
                record = records.setdefault(
                    identity, newrecord(peripheral, assertion)
                )
                setmetadata(record, row, path)
                if record["violation_kind"] == "unobserved_fsm_cover":
                    cover_status = (row.get("cover_status") or "").strip()
                    if cover_status not in ("candidate_bug", "not_exercised"):
                        raise ValueError(
                            f"{path}: invalid cover status {cover_status!r} "
                            f"for {peripheral}:{assertion}"
                        )
                    if (record["ip_cover_status"] and
                            record["ip_cover_status"] != cover_status):
                        raise ValueError(
                            f"{path}: conflicting cover status for "
                            f"{peripheral}:{assertion}"
                        )
                    record["ip_cover_status"] = cover_status
                input_id = row["input_id"].strip()
                if input_id:
                    try:
                        input_id = int(input_id)
                    except ValueError as error:
                        raise ValueError(
                            f"{path}: invalid input ID {input_id!r}"
                        ) from error
                    if input_id < 0:
                        raise ValueError(
                            f"{path}: invalid input ID {input_id}"
                        )
                    record["ip_input_ids"].add(input_id)
                record["ip_violation_count"] += 1
    cover_context = loadcovercontext(records, runs, ipfuzz_root)
    return records, target_peripherals, cover_context


def readsocviolations(log_dir, target_peripherals, records, cover_context):
    log_dir = Path(log_dir)
    observed_covers = set()
    for path in sorted(log_dir.glob("rtl_sim_out_*.log")):
        match = SOC_LOG_RE.fullmatch(path.name)
        if match is None:
            continue
        program_id = int(match.group(1))
        seen_assertions = set()
        with path.open(errors="replace") as stream:
            for line in stream:
                cover = parsecoverrecord(line, require_runtime_time=True)
                if cover in cover_context:
                    observed_covers.add(cover)
                assertion_match = SOC_ASSERTION_RE.search(line)
                source_match = SANITIZER_SOURCE_RE.search(line)
                if assertion_match is None or source_match is None:
                    continue
                peripheral = source_match.group(1)
                if peripheral not in target_peripherals:
                    continue
                assertion = assertion_match.group(1)
                identity = (peripheral, assertion)
                if identity in seen_assertions:
                    continue
                seen_assertions.add(identity)
                record = records.setdefault(
                    identity, newrecord(peripheral, assertion)
                )
                record["soc_program_ids"].add(program_id)
                record["soc_violation_count"] += 1
    for record in records.values():
        if record["violation_kind"] != "unobserved_fsm_cover":
            continue
        if record["transition_cover"] in observed_covers:
            record["soc_cover_status"] = "observed"
        elif record["source_cover"] in observed_covers:
            record["soc_cover_status"] = "candidate_bug"
            record["soc_violation_count"] = 1
        else:
            record["soc_cover_status"] = "not_exercised"
            record["soc_violation_count"] = 1
    return records


def detection(record):
    if record["ip_violation_count"] and record["soc_violation_count"]:
        return "both"
    if record["ip_violation_count"]:
        return "IP"
    return "SoC"


def buildrows(records):
    rows = []
    for identity in sorted(records):
        record = records[identity]
        ip_count = record["ip_violation_count"]
        soc_count = record["soc_violation_count"]
        rows.append({
            "perif": record["perif"],
            "detected": detection(record),
            "violation_kind": record["violation_kind"],
            "assertion": record["assertion"],
            "sanitizer_family": record["sanitizer_family"],
            "sanitizer_type": record["sanitizer_type"],
            "ip_cover_status": record["ip_cover_status"],
            "soc_cover_status": record["soc_cover_status"],
            "ip_input_ids": json.dumps(sorted(record["ip_input_ids"])),
            "soc_program_ids": json.dumps(sorted(record["soc_program_ids"])),
            "ip_violation_count": ip_count,
            "soc_violation_count": soc_count,
            "total_occurrences": ip_count + soc_count,
        })
    return rows


def detectioncounts(rows):
    counts = {}
    for detected in ("IP", "SoC", "both"):
        selected = [row for row in rows if row["detected"] == detected]
        counts[detected] = {
            "no of unique violations": len(selected),
            "total no of violations": sum(
                row["total_occurrences"] for row in selected
            ),
        }
    return counts


def buildsummary(rows):
    family_names = {
        "reset": "rst", "fsm": "fsm", "zero": "zero",
        "unknown": "unknown",
    }
    grouped = {name: {} for name in family_names.values()}
    rule_rows = {}
    for row in rows:
        family = family_names.get(row["sanitizer_family"], "unknown")
        key = (family, row["sanitizer_type"])
        rule_rows.setdefault(key, []).append(row)
    for family, sanitizer_type in sorted(rule_rows):
        selected = rule_rows[(family, sanitizer_type)]
        grouped[family][sanitizer_type] = {
            "no of unique violations": len(selected),
            "total no of violations": sum(
                row["total_occurrences"] for row in selected
            ),
        }

    peripherals = {}
    for peripheral in sorted({row["perif"] for row in rows}):
        selected = [row for row in rows if row["perif"] == peripheral]
        peripherals[peripheral] = {
            "violations total": sum(
                row["total_occurrences"] for row in selected
            ),
            "unique sanitizers violated total": len(selected),
            "detected": detectioncounts(selected),
        }

    return {
        "violations total": sum(row["total_occurrences"] for row in rows),
        "unique sanitizers violated total": len(rows),
        "violations": grouped,
        "peripherals": peripherals,
    }


def writereports(output_dir, rows, summary):
    output_dir = Path(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    backup = output_dir.parent / f".{output_dir.name}.backup-{uuid.uuid4().hex}"
    backup_active = False
    try:
        with (staging / "violations.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        (staging / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        if output_dir.exists():
            os.replace(output_dir, backup)
            backup_active = True
        os.replace(staging, output_dir)
        if backup.exists():
            shutil.rmtree(backup)
            backup_active = False
    except Exception:
        if backup_active and backup.exists():
            if output_dir.exists():
                shutil.rmtree(output_dir)
            os.replace(backup, output_dir)
            backup_active = False
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists() and not backup_active:
            shutil.rmtree(backup)


def triagerun(handoff_root, ipfuzz_root, soc_log_dir, soc, output_dir):
    records, target_peripherals, cover_context = readipviolations(
        handoff_root, ipfuzz_root, soc
    )
    readsocviolations(
        soc_log_dir, target_peripherals, records, cover_context
    )
    rows = buildrows(records)
    writereports(output_dir, rows, buildsummary(rows))
    output_dir = Path(output_dir)
    return {
        "violations": output_dir / "violations.csv",
        "summary_json": output_dir / "summary.json",
    }

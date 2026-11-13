"""Triage sanitizer violations produced by peripheral replay simulations."""

from dataclasses import dataclass, field
from collections import Counter
import csv
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid


ASSERTION_CONTEXT_RE = re.compile(r"\b(a_[^:\s]+):\s+started at\b")
VIOLATION_RE = re.compile(
    r"^ERROR, Sanitizer:([^,]+),\s*time=\s*(\d+),\s*(.*)$"
)
TRACE_NAME_RE = re.compile(r"rtl_trace_out_(\d+)\.log$")
COVER_RECORD_RE = re.compile(
    r"COVER,\s*Sanitizer:(reachDefFsmState|reachDefFsmTran),\s*"
    r"id=([^,]+),\s*time=\s*(%\d*d|\d+),\s*"
    r"state_reg=([^,]+),\s*([^\"\n]+)"
)

RESET_TYPES = {"InRstDom"}
FSM_TYPES = {"defUndefFsmTran", "fromUndefFsmTran", "illFsmTran"}
ZERO_TYPES = {"clrOnDbg", "OneTimeZero"}
KNOWN_TYPES = RESET_TYPES | FSM_TYPES | ZERO_TYPES


@dataclass(frozen=True)
class ViolationEvent:
    input_id: int
    trace_path: Path
    assertion: str
    sanitizer_family: str
    sanitizer_type: str
    time: int
    fields: tuple[tuple[str, str], ...]
    target_width: int | None = None


@dataclass(frozen=True)
class Rule2Transition:
    assertion: str
    state_register: str
    from_state: str
    to_state: str
    status: str
    source_reached: bool
    hit_count: int


@dataclass(frozen=True)
class FsmCoverPoint:
    sanitizer_type: str
    assertion: str
    state_register: str
    state_value: int | None = None
    from_value: int | None = None
    to_value: int | None = None
    state_text: str | None = None
    from_text: str | None = None
    to_text: str | None = None

    @property
    def identity(self):
        return (
            self.sanitizer_type,
            self.assertion,
            self.state_register,
            self.state_value,
            self.from_value,
            self.to_value,
        )


@dataclass
class TriageCounts:
    unlabeled: int = 0
    unknown_sanitizer: int = 0
    repeated_after_first_failure: int = 0
    zero_register_width_lt_8: int = 0


@dataclass(frozen=True)
class TriageResult:
    violations: tuple[ViolationEvent, ...]
    counts: TriageCounts
    rule2_transitions: tuple[Rule2Transition, ...] = ()
    selected_assertions: frozenset[str] = frozenset()
    retained_covers: frozenset[str] = frozenset()
    report_paths: dict[str, Path] = field(default_factory=dict)


def sanitizer_family(sanitizer_type):
    if sanitizer_type in RESET_TYPES:
        return "reset"
    if sanitizer_type in FSM_TYPES:
        return "fsm"
    if sanitizer_type in ZERO_TYPES:
        return "zero"
    return None


def strip_tcl_braces(value):
    while value.startswith("{") and value.endswith("}"):
        value = value[1:-1]
    return value


def parse_register_widths(jg_log):
    path = Path(jg_log)
    registers = None
    widths = None
    with path.open(errors="replace") as stream:
        for line in stream:
            if line.startswith("REGS:"):
                registers = [
                    strip_tcl_braces(value)
                    for value in line.removeprefix("REGS:").split()
                ]
            elif line.startswith("REGWIDTHS:"):
                try:
                    widths = [
                        int(value)
                        for value in line.removeprefix("REGWIDTHS:").split()
                    ]
                except ValueError as error:
                    raise ValueError("JG REGWIDTHS contains a non-integer width") from error
    if registers is None or widths is None:
        raise ValueError("JG log is missing REGS or REGWIDTHS metadata")
    if len(registers) != len(widths):
        raise ValueError(
            f"JG register/width count mismatch: {len(registers)} registers, "
            f"{len(widths)} widths"
        )
    return dict(zip(registers, widths))


def split_top_level_fields(payload):
    fields = []
    start = 0
    delimiters = []
    closing_delimiters = {"}": "{", "]": "[", ")": "("}
    in_string = False
    escaped = False
    for index, character in enumerate(payload):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "{[(":
            delimiters.append(character)
        elif character in closing_delimiters:
            if not delimiters or delimiters.pop() != closing_delimiters[character]:
                return ()
        elif character == "," and not delimiters:
            fields.append(payload[start:index])
            start = index + 1
    if delimiters or in_string:
        return ()
    fields.append(payload[start:])
    return tuple(fields)


def parse_fields(payload):
    fields = []
    for item in split_top_level_fields(payload):
        name, separator, value = item.strip().rpartition("=")
        if not separator or not name:
            return ()
        fields.append((name.strip(), value.strip()))
    return tuple(fields)


def resolve_register_width(signal, register_widths):
    if signal in register_widths:
        return register_widths[signal]
    prefix, separator, relative_signal = signal.partition(".")
    if separator:
        return register_widths.get(relative_signal)
    return None


def zeroization_target(sanitizer_type, fields):
    if not fields:
        return None
    if sanitizer_type == "OneTimeZero":
        return fields[-1][0]
    return fields[0][0]


def parse_trace(trace_path, input_id, register_widths, counts):
    events = []
    pending_assertion = None
    seen_assertions = set()
    with Path(trace_path).open(errors="replace") as stream:
        for line in stream:
            assertion_match = ASSERTION_CONTEXT_RE.search(line)
            if assertion_match:
                pending_assertion = assertion_match.group(1)
                continue
            violation_match = VIOLATION_RE.match(line.rstrip("\n"))
            if not violation_match:
                continue
            sanitizer_type, time_text, payload = violation_match.groups()
            assertion = pending_assertion
            pending_assertion = None
            if assertion is None:
                counts.unlabeled += 1
                continue
            family = sanitizer_family(sanitizer_type)
            if family is None:
                counts.unknown_sanitizer += 1
                continue
            if assertion in seen_assertions:
                counts.repeated_after_first_failure += 1
                continue
            seen_assertions.add(assertion)
            fields = parse_fields(payload)
            if not fields:
                counts.unlabeled += 1
                continue
            target_width = None
            if family == "zero":
                target = zeroization_target(sanitizer_type, fields)
                target_width = resolve_register_width(target, register_widths)
                if target_width is not None and target_width < 8:
                    counts.zero_register_width_lt_8 += 1
                    continue
            events.append(
                ViolationEvent(
                    input_id=input_id,
                    trace_path=Path(trace_path),
                    assertion=assertion,
                    sanitizer_family=family,
                    sanitizer_type=sanitizer_type,
                    time=int(time_text),
                    fields=fields,
                    target_width=target_width,
                )
            )
    return events


def parse_verilog_integer(value):
    text = value.strip().replace("_", "").lower()
    literal = re.fullmatch(r"(?:\d+)?'s?([bodh])([0-9a-f]+)", text)
    if literal:
        radix, digits = literal.groups()
        return int(digits, {"b": 2, "o": 8, "d": 10, "h": 16}[radix])
    if text.startswith("0x"):
        return int(text, 16)
    return int(text, 10)


def parse_cover_record(line, require_runtime_time):
    match = COVER_RECORD_RE.search(line)
    if match is None:
        return None
    sanitizer_type, cover_id, time_text, state_register, payload = match.groups()
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
        return FsmCoverPoint(
            sanitizer_type=sanitizer_type,
            assertion=assertion,
            state_register=state_register,
            state_value=parse_verilog_integer(fields["state"]),
            state_text=fields["state"],
        )
    if "from" not in fields or "to" not in fields:
        return None
    return FsmCoverPoint(
        sanitizer_type=sanitizer_type,
        assertion=assertion,
        state_register=state_register,
        from_value=parse_verilog_integer(fields["from"]),
        to_value=parse_verilog_integer(fields["to"]),
        from_text=fields["from"],
        to_text=fields["to"],
    )


def load_cover_inventory(peripheral_sva):
    inventory = []
    with Path(peripheral_sva).open(errors="replace") as stream:
        for line in stream:
            point = parse_cover_record(line, require_runtime_time=False)
            if point is not None:
                inventory.append(point)
    return inventory


def classify_rule2_transitions(peripheral_sva, trace_paths):
    inventory = load_cover_inventory(peripheral_sva)
    hit_counts = Counter()
    reached_states = set()
    for trace_path in trace_paths:
        with Path(trace_path).open(errors="replace") as stream:
            for line in stream:
                hit = parse_cover_record(line, require_runtime_time=True)
                if hit is None:
                    continue
                hit_counts[hit.identity] += 1
                if hit.sanitizer_type == "reachDefFsmState":
                    reached_states.add((hit.state_register, hit.state_value))
                else:
                    reached_states.add((hit.state_register, hit.from_value))
                    reached_states.add((hit.state_register, hit.to_value))

    state_covers = {
        (point.state_register, point.state_value): point.assertion
        for point in inventory
        if point.sanitizer_type == "reachDefFsmState"
    }
    results = []
    retained_covers = set()
    for point in inventory:
        if point.sanitizer_type != "reachDefFsmTran":
            continue
        if point.from_value == point.to_value:
            continue
        hit_count = hit_counts[point.identity]
        source_reached = (point.state_register, point.from_value) in reached_states
        if hit_count:
            status = "observed"
        elif source_reached:
            status = "candidate_bug"
        else:
            status = "not_exercised"
        results.append(
            Rule2Transition(
                assertion=point.assertion,
                state_register=point.state_register,
                from_state=point.from_text,
                to_state=point.to_text,
                status=status,
                source_reached=source_reached,
                hit_count=hit_count,
            )
        )
        if status != "observed":
            retained_covers.add(point.assertion)
            state_key = (point.state_register, point.from_value)
            if state_key not in state_covers:
                raise ValueError(
                    f"Rule 2 transition {point.assertion} has no source-state cover"
                )
            retained_covers.add(state_covers[state_key])
    results.sort(
        key=lambda result: (
            result.state_register,
            parse_verilog_integer(result.from_state),
            parse_verilog_integer(result.to_state),
            result.assertion,
        )
    )
    return tuple(results), frozenset(retained_covers)


def build_violation_rows(violations, rule2_transitions):
    rows = [
        {
            "violation_kind": "assertion",
            "input_id": event.input_id,
            "trace_file": str(event.trace_path),
            "assertion": event.assertion,
            "sanitizer_family": event.sanitizer_family,
            "sanitizer_type": event.sanitizer_type,
            "time": event.time,
            "fields": json.dumps(event.fields),
            "target_width": "" if event.target_width is None else event.target_width,
            "state_register": "",
            "from_state": "",
            "to_state": "",
            "source_reached": "",
            "cover_status": "",
        }
        for event in violations
    ]
    rows.extend(
        {
            "violation_kind": "unobserved_fsm_cover",
            "input_id": "",
            "trace_file": "",
            "assertion": transition.assertion,
            "sanitizer_family": "fsm",
            "sanitizer_type": "reachDefFsmTran",
            "time": "",
            "fields": "",
            "target_width": "",
            "state_register": transition.state_register,
            "from_state": transition.from_state,
            "to_state": transition.to_state,
            "source_reached": str(transition.source_reached).lower(),
            "cover_status": transition.status,
        }
        for transition in rule2_transitions
        if transition.status != "observed"
    )
    return rows


def build_summary_data(rows):
    family_names = {"reset": "rst", "fsm": "fsm", "zero": "zero"}
    grouped = {"rst": {}, "fsm": {}, "zero": {}}
    all_assertions = set()

    rule_counts = {}
    for row in rows:
        family = family_names[row["sanitizer_family"]]
        rule = row["sanitizer_type"]
        key = (family, rule)
        count = rule_counts.setdefault(key, {"assertions": set(), "total": 0})
        count["assertions"].add(row["assertion"])
        count["total"] += 1
        all_assertions.add(row["assertion"])

    for family in ("rst", "fsm", "zero"):
        for rule in sorted(
            rule for rule_family, rule in rule_counts if rule_family == family
        ):
            count = rule_counts[(family, rule)]
            grouped[family][rule] = {
                "no of unique violations": len(count["assertions"]),
                "total no of violations": count["total"],
            }

    return {
        "violations total": len(rows),
        "unique sanitizers violated total": len(all_assertions),
        "violations": grouped,
    }


def write_csv(path, fieldnames, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report_directory(output_dir, violations, counts, rule2_transitions):
    output_dir = Path(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    backup = output_dir.parent / f".{output_dir.name}.backup-{uuid.uuid4().hex}"
    backup_active = False
    try:
        violation_rows = build_violation_rows(violations, rule2_transitions)
        summary_data = build_summary_data(violation_rows)
        write_csv(
            staging / "violations.csv",
            [
                "violation_kind", "input_id", "trace_file", "assertion",
                "sanitizer_family", "sanitizer_type", "time", "fields",
                "target_width", "state_register", "from_state", "to_state",
                "source_reached", "cover_status",
            ],
            violation_rows,
        )
        (staging / "summary.json").write_text(
            json.dumps(summary_data, indent=2) + "\n",
            encoding="utf-8",
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
    return {
        "violations": output_dir / "violations.csv",
        "summary_json": output_dir / "summary.json",
    }


def triage_run(trace_dir: Path, peripheral_sva: Path, jg_log: Path, output_dir: Path):
    trace_dir = Path(trace_dir)
    peripheral_sva = Path(peripheral_sva)
    output_dir = Path(output_dir)
    if not peripheral_sva.is_file():
        raise FileNotFoundError(peripheral_sva)
    register_widths = parse_register_widths(jg_log)
    counts = TriageCounts()
    violations = []
    trace_paths = sorted(trace_dir.glob("rtl_trace_out_*.log"))
    for trace_path in trace_paths:
        match = TRACE_NAME_RE.fullmatch(trace_path.name)
        if match is None:
            continue
        violations.extend(
            parse_trace(trace_path, int(match.group(1)), register_widths, counts)
        )
    violations.sort(
        key=lambda event: (
            event.input_id,
            event.time,
            event.assertion,
            event.fields,
        )
    )
    selected_assertions = frozenset(event.assertion for event in violations)
    rule2_transitions, retained_covers = classify_rule2_transitions(
        peripheral_sva, trace_paths
    )
    report_paths = write_report_directory(
        output_dir, violations, counts, rule2_transitions
    )
    return TriageResult(
        violations=tuple(violations),
        counts=counts,
        rule2_transitions=rule2_transitions,
        selected_assertions=selected_assertions,
        retained_covers=retained_covers,
        report_paths=report_paths,
    )

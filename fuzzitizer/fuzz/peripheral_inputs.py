
import csv, json
from pathlib import Path


def manifest_error(manifest_path, message):
    raise ValueError(f"{manifest_path}: {message}")


def containedpath(path, root, description):
    resolved = Path(path).resolve()
    root = Path(root).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{description} resolves outside IPFuzz: {resolved}") from error
    return resolved


def positive_integer(entry, field, identifier, manifest_path):
    value = entry.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        manifest_error(
            manifest_path,
            f"peripheral {identifier!r} field {field!r} must be a positive integer",
        )
    return value


def load_peripheral_specs(manifest_path, soc, base_addresses, ipfuzz_root=None):
    if ipfuzz_root is None:
        manifest_path = Path(manifest_path)
    else:
        manifest_path = containedpath(
            manifest_path,
            ipfuzz_root,
            "interface manifest",
        )
    try:
        document = json.loads(manifest_path.read_text())
    except FileNotFoundError as error:
        raise FileNotFoundError(f"peripheral manifest not found: {manifest_path}") from error
    except (OSError, json.JSONDecodeError) as error:
        manifest_error(manifest_path, f"cannot read valid JSON: {error}")

    if not isinstance(document, dict):
        manifest_error(manifest_path, "top-level document must be an object")
    unsupported_top_fields = set(document) - {"peripherals"}
    if unsupported_top_fields:
        manifest_error(
            manifest_path,
            "unsupported top-level fields: "
            f"{', '.join(sorted(unsupported_top_fields))}",
        )
    peripherals = document.get("peripherals")
    if not isinstance(peripherals, dict):
        manifest_error(manifest_path, "field 'peripherals' must be an object")

    validated = {}
    for identifier, entry in peripherals.items():
        if not isinstance(identifier, str) or not identifier:
            manifest_error(manifest_path, "peripheral identifiers must be non-empty strings")
        if not isinstance(entry, dict):
            manifest_error(manifest_path, f"peripheral {identifier!r} must be an object")

        entry_soc = entry.get("soc")
        if not isinstance(entry_soc, str) or not entry_soc:
            manifest_error(
                manifest_path, f"peripheral {identifier!r} field 'soc' must be a string"
            )
        if entry_soc != soc:
            continue
        supported_fields = {"soc", "address_width", "word_bits", "alignment"}
        unsupported_fields = set(entry) - supported_fields
        if unsupported_fields:
            manifest_error(
                manifest_path,
                f"peripheral {identifier!r} has unsupported fields: "
                f"{', '.join(sorted(unsupported_fields))}",
            )

        address_width = positive_integer(
            entry, "address_width", identifier, manifest_path
        )
        word_bits = positive_integer(entry, "word_bits", identifier, manifest_path)
        alignment = positive_integer(entry, "alignment", identifier, manifest_path)
        if word_bits % 8:
            manifest_error(
                manifest_path,
                f"peripheral {identifier!r} word_bits must represent whole bytes "
                "(a multiple of 8)",
            )
        if alignment & (alignment - 1):
            manifest_error(
                manifest_path,
                f"peripheral {identifier!r} alignment must be a power of two",
            )
        if alignment != word_bits // 8:
            manifest_error(
                manifest_path,
                f"peripheral {identifier!r} alignment must equal word_bits / 8",
            )

        validated[identifier] = {
            "address_width": address_width,
            "word_bits": word_bits,
            "alignment": alignment,
        }

    configured = set(base_addresses)
    available = set(validated)
    if not available:
        manifest_error(manifest_path, f"manifest contains no peripherals for SoC {soc!r}")
    missing = configured - available
    if missing:
        manifest_error(
            manifest_path,
            f"SoC {soc!r} manifest is missing configured peripherals: "
            f"{', '.join(sorted(missing))}",
        )
    extra = available - configured
    if extra:
        manifest_error(
            manifest_path,
            f"SoC {soc!r} manifest has peripherals without base addresses: "
            f"{', '.join(sorted(extra))}",
        )
    specs = []
    for identifier, base_address in base_addresses.items():
        if isinstance(base_address, bool) or not isinstance(base_address, int):
            manifest_error(
                manifest_path,
                f"base address for peripheral {identifier!r} must be an integer",
            )
        values = validated[identifier]
        specs.append(
            {
                "identifier": identifier,
                "base_address": base_address,
                "address_width": values["address_width"],
                "word_bits": values["word_bits"],
                "alignment": values["alignment"],
            }
        )
    return tuple(specs)


def identify_peripheral(input_path, specs):
    path = Path(input_path)
    components = [part.removesuffix(path.suffix) for part in path.parts]
    matches = []
    for spec in specs:
        if any(
            component == spec["identifier"]
            or component.startswith(f"{spec['identifier']}_")
            or component.startswith(f"{spec['identifier']}-")
            for component in components
        ):
            matches.append(spec)

    if len(matches) == 1:
        return matches[0]

    identifiers = ", ".join(spec["identifier"] for spec in specs)
    if matches:
        matched = ", ".join(spec["identifier"] for spec in matches)
        raise ValueError(
            f"ambiguous peripheral input {input_path}: matched {matched}; "
            f"supported identifiers: {identifiers}"
        )
    raise ValueError(
        f"unknown peripheral input {input_path}; supported identifiers: {identifiers}"
    )


def parse_hex(value, field_name, input_path, line_number):
    try:
        return int(value, 16)
    except ValueError as error:
        raise ValueError(
            f"{input_path}:{line_number}: invalid hexadecimal {field_name}: {value!r}"
        ) from error


def read_mmio_commands(
    input_path,
    specs,
    peripheral_identifier=None,
    replay_mode="compressed-mmio",
):
    if replay_mode not in (
        "compressed-mmio", "direct-mmio", "external-trigger-mmio", "gap-mmio"
    ):
        raise ValueError(f"unknown peripheral replay mode: {replay_mode}")
    if peripheral_identifier is None:
        spec = identify_peripheral(input_path, specs)
    else:
        matches = [
            spec
            for spec in specs
            if spec["identifier"] == peripheral_identifier
        ]
        if len(matches) != 1:
            supported = ", ".join(spec["identifier"] for spec in specs)
            raise ValueError(
                f"unknown peripheral identifier {peripheral_identifier!r}; "
                f"supported identifiers: {supported}"
            )
        spec = matches[0]
    commands = []
    gap_rows = 0
    with Path(input_path).open(newline="") as input_file:
        for line_number, row in enumerate(csv.reader(input_file), start=1):
            if not row:
                continue
            row = [value.strip() for value in row]
            if len(row) < 4:
                raise ValueError(
                    f"{input_path}:{line_number}: expected at least 4 fields for "
                    f"{spec['identifier']}, found {len(row)}"
                )
            chip_select_value, write_enable_value, address_value, write_data_value = row[:4]
            chip_select = parse_hex(
                chip_select_value,
                "chip select",
                input_path,
                line_number,
            )
            if chip_select not in (0, 1):
                raise ValueError(
                    f"{input_path}:{line_number}: chip select must be 0 or 1"
                )
            if chip_select == 0:
                if replay_mode == "gap-mmio":
                    gap_rows += 1
                continue

            write_enable = parse_hex(
                write_enable_value,
                "write enable",
                input_path,
                line_number,
            )
            if write_enable not in (0, 1):
                raise ValueError(
                    f"{input_path}:{line_number}: write enable must be 0 or 1"
                )
            offset = parse_hex(
                address_value,
                "address",
                input_path,
                line_number,
            )
            if offset < 0:
                raise ValueError(
                    f"{input_path}:{line_number}: address offset {offset} is outside "
                    f"the {spec['identifier']} window"
                )
            offset &= (1 << spec["address_width"]) - 1
            offset -= offset % spec["alignment"]
            data = parse_hex(
                write_data_value,
                "write data",
                input_path,
                line_number,
            )
            data &= (1 << spec["word_bits"]) - 1
            command = {
                "write": bool(write_enable),
                "address": spec["base_address"] + offset,
                "data": data,
            }
            if replay_mode == "gap-mmio":
                command["gap_rows_before"] = gap_rows
                gap_rows = 0
            commands.append(command)
    if replay_mode == "external-trigger-mmio":
        trigger = spec.get("external_trigger_mmio")
        if trigger is None:
            raise ValueError(
                f"{spec['identifier']} does not define an external-interface trigger"
            )
        commands.append(
            {
                "write": True,
                "address": trigger["address"],
                "data": trigger["data"],
                "synthetic_control": "external_trigger",
                "wait_nops": trigger["wait_nops"],
            }
        )
    return commands

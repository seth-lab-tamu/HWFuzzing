#!/usr/bin/env python3
"""Export IPFuzzer peripheral CSV interfaces for whole-SoC fuzzing."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "ipfuzzer_output" / "soc_input_manifest.json"
os.environ.setdefault("IPFUZZ_ROOT", str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmarks"))

import config_cal_perif
import config_opn_perif


REQUIRED_ROLES = ("chip_select", "write_enable", "address", "write_data")


def positive_int(value, description):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{description} must be a positive integer")
    return value


def build_peripheral_entry(soc, peripheral, input_format_info, address_width):
    """Build and validate one manifest entry from a refreshed configuration."""
    generated = [item for item in input_format_info if item.get("type") == "gen"]
    csv_fields = [item.get("name") for item in generated]
    if any(not isinstance(name, str) or not name for name in csv_fields):
        raise ValueError(f"{peripheral}: generated fields require nonempty names")
    if len(csv_fields) != len(set(csv_fields)):
        raise ValueError(f"{peripheral}: duplicate generated CSV field")

    roles = {}
    role_items = {}
    for item in input_format_info:
        role = item.get("soc_role")
        if role is None:
            continue
        if item.get("type") != "gen":
            raise ValueError(f"{peripheral}: SoC role {role} is not generated")
        if role in roles:
            raise ValueError(f"{peripheral}: duplicate SoC role {role}")
        roles[role] = item["name"]
        role_items[role] = item
    if set(roles) != set(REQUIRED_ROLES):
        raise ValueError(
            f"{peripheral}: required SoC roles are {', '.join(REQUIRED_ROLES)}"
        )
    actual_prefix = tuple(item.get("soc_role") for item in generated[:4])
    if actual_prefix != REQUIRED_ROLES:
        raise ValueError(
            f"{peripheral}: generated inputs must start with canonical SoC role "
            f"prefix {', '.join(REQUIRED_ROLES)}"
        )

    word_bits = positive_int(
        role_items["write_data"].get("nbits"),
        f"{peripheral} write-data width",
    )
    if word_bits % 8:
        raise ValueError(f"{peripheral}: write-data width must be byte-sized")
    alignment = word_bits // 8
    if alignment & (alignment - 1):
        raise ValueError(f"{peripheral}: alignment must be a power of two")

    return {
        "soc": soc,
        "address_width": positive_int(
            address_width, f"{peripheral} address-window width"
        ),
        "word_bits": word_bits,
        "alignment": alignment,
    }


def build_manifest():
    """Build the complete manifest."""
    peripherals = {}
    for soc, config, names in (
        ("opn", config_opn_perif, config_opn_perif.opn_perifs),
        ("cal", config_cal_perif, config_cal_perif.cal_perifs),
    ):
        for peripheral in names:
            if peripheral in peripherals:
                raise ValueError(f"duplicate peripheral identifier: {peripheral}")
            config.refresh(peripheral)
            peripherals[peripheral] = build_peripheral_entry(
                soc,
                peripheral,
                config.input_format_info,
                config.soc_address_width,
            )
    return {"peripherals": peripherals}


def render_manifest(manifest):
    """Render a deterministic JSON representation."""
    ordered = {
        "peripherals": {
            name: manifest["peripherals"][name]
            for name in sorted(manifest["peripherals"])
        },
    }
    return json.dumps(ordered, indent=2) + "\n"


def write_manifest(path=DEFAULT_OUTPUT):
    """Atomically write the current manifest to *path*."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_manifest(build_manifest())
    if path.exists():
        output_mode = path.stat().st_mode & 0o777
    else:
        current_umask = os.umask(0)
        os.umask(current_umask)
        output_mode = 0o666 & ~current_umask
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as output:
            output.write(rendered)
            temporary = Path(output.name)
        temporary.chmod(output_mode)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    write_manifest(args.output)


if __name__ == "__main__":
    main()

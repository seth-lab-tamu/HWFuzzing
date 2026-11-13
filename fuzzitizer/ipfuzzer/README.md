# IPFuzzer

IPFuzzer is the IP-level fuzzing component of FUZZItizer. It generates hardware sanitizers for all SoC peripherals, performs coverage-guided fuzzing, and records coverage achieved and sanitizer violations. The artifact supports 12 OpenPiton peripherals and 12 Caliptra peripherals.


## Repository Structure

```text
ipfuzzer
├── benchmarks/
│   ├── opn/                    # OpenPiton source repository
│   ├── cal/                    # Caliptra source repository
│   ├── opn_<peripheral>/       # OpenPiton peripheral testbench and assertions
│   ├── cal_<peripheral>/       # Caliptra peripheral testbench and assertions
│   ├── opnAsn/ and calAsn/     # Sanitizers for whole-SoC fuzzing
│   ├── config_opn_perif.py     # OpenPiton peripheral configuration
│   ├── config_cal_perif.py     # Caliptra peripheral configuration
│   └── config_sanitizers.py    # Sanitizer configuration
├── fuzz/                       # Input generation, mutation, simulation, and sanitizer flow
├── setup_scripts/              # Peripheral build and installation scripts
├── utils/                      # Instance lists and supporting utilities
├── sim/                        # Installed VCS peripheral simulation models
├── input_seeds/                # Optional fuzzer input seeds
├── outputs/                    # Coverage summaries and generated inputs
├── outputs_all/                # Detailed sanitizer-replay outputs
├── ipfuzzer_output/            # Stable handoff to whole-SoC fuzzing
└── config.py                   # Shared IPFuzzer configuration
```


## Benchmarks

The OpenPiton benchmark is based on the
[Hack@DAC 2021 OpenPiton SoC](https://github.com/HACK-EVENT/hackatdac21).
The Caliptra source is based on commit `e815e54` of the
[Caliptra SoC](https://github.com/chipsalliance/caliptra-rtl).


## Requirements

- Python 3, Python 2.7 (for legacy OpenPiton preprocessing scripts)
- [Synopsys VCS](https://www.synopsys.com/verification/simulation/vcs.html)
- [Cadence JasperGold](https://www.cadence.com/en_US/home/tools/system-design-and-verification/formal-and-static-verification/jasper-verification-platform/formal-property-verification-app.html)


## Setup

Run the following commands from the FUZZItizer repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
source ./fuzzitizer_setup.sh
python -m pip install -r requirements.txt
cd "$IPFUZZ_ROOT"
```

## Quick start

Build and fuzz all 24 supported peripherals with:

```bash
./setup_scripts/install_perif.sh all
cd "$IPFUZZ_ROOT/fuzz"
./run_ipfuzzer
```

Installation creates unsanitized and sanitizer-enabled simulators under
`sim/`. Fuzzing creates one run directory per peripheral under
`$IPFUZZ_ROOT/outputs/` and `$IPFUZZ_ROOT/outputs_all/`, then updates the
whole-SoC handoff under `$IPFUZZ_ROOT/ipfuzzer_output/`.

## Installing a Peripheral

Run the installer from the IPFuzzer root and name the peripheral to install:

```bash
./setup_scripts/install_perif.sh opn_aes0
```

The installer regenerates the peripheral testbench and sanitizers, builds an
unsanitized simulator for coverage-guided fuzzing, and builds a
sanitizer-enabled simulator for replay. A successful installation ends with:

```text
opn_aes0 installation completed successfully.
Installing opn_aes0 peripheral done
```

The principal installation outputs are:

```text
benchmarks/opn_aes0/tb/tb.sv
benchmarks/opn_aes0/tb/sanitizers.sva
sim/opn_aes0/vcs_0/       # unsanitized simulator
sim/opn_aes0_san/vcs_0/   # sanitizer-enabled simulator
utils/opn_aes0_inst_list.py
```

`install_perif.sh` accepts one or more peripheral names and installs them
sequentially. Use `./setup_scripts/install_perif.sh all` to install all 24.
Do not run multiple installation processes concurrently because they share
generated build state.

## Running IPFuzzer

After installing a peripheral, run it from the `fuzz/` directory:

```bash
cd "$IPFUZZ_ROOT/fuzz"
python3 fuzz.py -co opn_aes0
```

A successful run ends with a coverage summary followed by:

```text
Running fuzzer on given benchmark, opn_aes0 done
```

For the default timestamp-based run ID `<id>`, the principal outputs below are
relative to `$IPFUZZ_ROOT`:

```text
outputs/opn_aes0_fuzz_<id>/
outputs_all/opn_aes0_fuzz_<id>/
ipfuzzer_output/peripheral_runs.json
ipfuzzer_output/Flist.opn.fuzz
```

The `outputs/` run contains generated inputs, coverage results, selected
inputs, violation triage, and the selected whole-SoC sanitizers. The matching
`outputs_all/` run contains coverage vectors and sanitizer-replay traces. See
[Outputs](#outputs) for the complete layout.

Run all 24 installed peripherals sequentially with:

```bash
"$IPFUZZ_ROOT/fuzz/run_ipfuzzer"
```


## Supported peripherals

OpenPiton:

```text
opn_aes0  opn_aes1  opn_aes2  opn_acct  opn_dbg  opn_dma
opn_hmac  opn_reglk opn_rng   opn_rsa   opn_rst  opn_sha256
```

Caliptra:

```text
cal_csrng  cal_doe  cal_dv  cal_ecc  cal_entropy_src  cal_hmac
cal_kv     cal_pv   cal_spi_host  cal_sha256  cal_sha512  cal_uart
```

## Outputs

For target peripheral `<target>`, mode `fuzz`, and run ID `<id>`:

- `outputs/<target>_fuzz_<id>/` contains:
  - `all_progs/`: every generated or mutated peripheral CSV input;
  - `cov_log.jsonl`: the coverage increment and cumulative coverage for each
    simulated input;
  - `merged_cov.json`: the final merged coverage vector;
  - `fuzz_log.txt` and `inputs_log.txt`: run configuration, progress, input
    generation, selection, and mutation logs;
  - `selected_inputs/`: the greedy coverage-preserving corpus and its
    `selected_inputs.json` manifest, intended for whole-SoC fuzzing regardless
    of replay policy;
  - `sanitizer_replay_inputs/`: the corpus and manifest actually replayed
    against the sanitizer-enabled peripheral simulation;
  - `triage/`: `violations.csv` and `summary.json`, including grouped sanitizer
    counts and FSM Rule 2 transition classification;
  - `soc_sanitizers/`: the SoC-hierarchy sanitizer file selected from the
    replay results.
- `outputs_all/<target>_fuzz_<id>/cov_out/` contains the coverage vector for
  every coverage-increasing input from the initial unsanitized fuzzing step.
  These vectors are always retained because greedy input selection requires
  them.
- `outputs_all/<target>_fuzz_<id>/sim_out/` contains the trace for every input
  replayed against the sanitizer-enabled peripheral simulation.
- `outputs_all/trash_<target>_fuzz_<id>/` contains temporary input-generation
  workspaces.

The stable peripheral-to-SoC handoff is under `ipfuzzer_output/`:

- `soc_input_manifest.json` describes the peripheral CSV interfaces;
- `peripheral_runs.json` maps each peripheral to its currently selected run;
- `Flist.opn.fuzz` and `Flist.cal.fuzz` list the selected SoC sanitizer files.

The run index points to the per-run `selected_inputs/` and `soc_sanitizers/`
artifacts without copying them. The parent FUZZItizer flow consumes this
handoff during whole-SoC fuzzing.


## Citation

If you use FUZZItizer in your research, please cite the
[ASIA CCS 2026 paper](https://doi.org/10.1145/3779208.3806078):

```bibtex
@inproceedings{Kande2026FUZZItizer,
  author    = {Rahul Kande and Mohamadreza Rostami and Chen Chen and Hareesh Khattri and Jason M. Fung and Ahmad-Reza Sadeghi and Jeyavijayan Rajendran},
  title     = {{FUZZItizer: Hardware Sanitizer-Assisted Fuzzing for Automated SoC Vulnerability Detection}},
  booktitle = {Proceedings of the 2026 ACM Asia Conference on Computer and Communications Security},
  year      = {2026},
  pages     = {1139--1155},
  doi       = {10.1145/3779208.3806078},
  url       = {https://doi.org/10.1145/3779208.3806078}
}
```

# FUZZItizer: Hardware Sanitizer-Assisted Fuzzing for Automated SoC Vulnerability Detection

FUZZItizer is a coverage-guided fuzzer for complete systems on chip (SoCs).
It adapts the coverage-guided fuzzing foundation of the [TheHuzz processor fuzzer](https://www.usenix.org/conference/usenixsecurity22/presentation/kande) to fuzz SoCs.
This artifact supports OpenPiton and Caliptra-SoC fuzzing.

Developed in the [SETH lab](https://seth.engr.tamu.edu/),  Texas A&M University.

Maintained by [Rahul Kande](https://rahulkande.com).

## Repository Structure

```text
.
├── benchmarks/
│   ├── opn/              # OpenPiton source repository
│   ├── cal/              # Caliptra source repository
│   ├── config_opn.py     # OpenPiton target configuration
│   └── config_cal.py     # Caliptra target configuration
├── fuzz/                 # Program generation, mutation, simulation, and coverage
├── ipfuzzer/             # IPFuzz repository and peripheral-fuzzing handoff
├── setup_scripts/        # OpenPiton and Caliptra build/install scripts
├── software/riscv/       # Target-specific RISC-V runtime and build files
├── sim/                  # Installed VCS simulation models
├── input_seeds/          # Fuzzer input seeds
├── outputs/              # Coverage summaries and generated programs
├── outputs_all/          # Detailed simulator outputs
├── config.py             # Shared FUZZItizer configuration
└── fuzzitizer_setup.sh   # Environment setup
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
- A RISC-V bare-metal GNU toolchain providing
  `riscv64-unknown-elf-gcc`, `riscv64-unknown-elf-objcopy`, and
  `riscv64-unknown-elf-objdump`. Caliptra requires GCC 12.2 with both the `rv32im/ilp32` and
  `rv32imc/ilp32` multilibs.


## Setup

Run the following commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
source ./fuzzitizer_setup.sh
```


## IPFuzzer Execution

We will run IP level fuzzing first because FUZZItizer uses IP level fuzzing output in SoC level fuzzing. Follow these commands to run IP level fuzzing.

```bash
cd "$IPFUZZ_ROOT"
./setup_scripts/install_perif.sh all
cd "$IPFUZZ_ROOT/fuzz"
./run_ipfuzzer
```

This should populate `ipfuzzer/ipfuzzer_output/soc_input_manifest.json`, `ipfuzzer/ipfuzzer_output/peripheral_runs.json`, `ipfuzzer/ipfuzzer_output/Flist.opn.fuzz`, and `ipfuzzer/ipfuzzer_output/Flist.cal.fuzz`, which FUZZItizer uses when fuzzing the SoC. See [IPFuzzer's readme](ipfuzzer/README.md) for more details about IP level fuzzing.


## Build SoC Benchmarks

Build the OpenPiton and Caliptra SoCs with:

```bash
cd "$FUZZITIZER_ROOT"
PATH=/path/to/python2.7/bin:$PATH bash setup_scripts/install_opn.sh
bash setup_scripts/install_cal.sh
```


## Running the Fuzzer

Fuzz OpenPiton SoC with:

```bash
cd <path-to-fuzzitizer>
source ./fuzzitizer_setup.sh
cd "$FUZZITIZER_ROOT/fuzz"
python3 fuzz.py -co opn -rm fuzzitizer
```

The paper also performs Random Regression, TheHuzz, and SoCFuzzer runs with:

- Random Regression `python3 fuzz.py -co opn -rm random`
- TheHuzz `python3 fuzz.py -co opn -rm thehuzz`
- Mimic SoCFuzzer by targeting only one peripheral such as AES0 `python3 fuzz.py -co opn -rm thehuzz --perif-addresses 0xfff5200000`


## Outputs

The primary results are written to:

- `outputs/<target>_<run-mode>_RUN_ID/`
  - `cov_log.jsonl`: cumulative coverage after simulated programs.
  - `fuzz_log.txt`: configuration and fuzzer log.
  - `inputs_log.txt`: input generation, selection, and mutation decisions.
  - `merged_cov.json`: final merged coverage state.
  - `all_progs/`: generated and mutated target programs.
  - `triage/`: FUZZItizer-mode IP/SoC violation comparison.
    - `violations.csv`: one row per peripheral/assertion pair, classified as
      `IP`, `SoC`, or `both`. A `both` classification means the assertion was
      observed somewhere in both campaigns.
    - `summary.json`: occurrence and unique-violation totals.
- `outputs_all/<target>_<run-mode>_RUN_ID/sim_out/`
  - Stored simulation logs.

The exact directory name is printed in `fuzz_log.txt` and includes the selected
run mode and identifier.


### Storage Warning

Fuzzing can consume a large amount of storage. The `sim/` and
`ipfuzzer/sim/` directories may accumulate many `vcs_*` directories. These are
VCS simulation build directories and do not contain fuzzer results, so they can
be deleted after fuzzing to reclaim space.

The `outputs/`, `outputs_all/`, `ipfuzzer/outputs/`, and `ipfuzzer/outputs_all/` directories can also
grow to several gigabytes. Unlike the `vcs_*` directories, these directories
contain actual fuzzer results. Delete old results only after they are no longer
needed.


## Citation

If you use FUZZItizer in your research, cite the
[ASIA CCS 2026 paper](https://doi.org/10.1145/3779208.3806078):

```bibtex
@inproceedings{Kande2026FUZZItizer,
  author    = {Rahul Kande and Mohamadreza Rostami and Chen Chen and
               Hareesh Khattri and Jason M. Fung and Ahmad-Reza Sadeghi and
               Jeyavijayan Rajendran},
  title     = {{FUZZItizer: Hardware Sanitizer-Assisted Fuzzing for Automated
                SoC Vulnerability Detection}},
  booktitle = {Proceedings of the 2026 ACM Asia Conference on Computer and
               Communications Security},
  year      = {2026},
  pages     = {1139--1155},
  doi       = {10.1145/3779208.3806078}
}
```

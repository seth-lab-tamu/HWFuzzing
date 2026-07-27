# HW_Fuzzing
The repository includes hardware fuzzing techniques developed in the SETH lab: [TheHuzz](https://www.usenix.org/conference/usenixsecurity22/presentation/kande), [HyPFuzz](https://www.usenix.org/system/files/usenixsecurity23-chen-chen.pdf), [PSOFuzz](https://arxiv.org/abs/2307.14480), [MABFuzz](https://arxiv.org/abs/2311.14594), and [ReFuzz](https://arxiv.org/pdf/2512.04436).

#### Maintained by [Chen Chen](https://www.chenc.contact/), [Rahul Kande](https://www.rahulkande.com/), [Zeina AbuGhosh](https://www.linkedin.com/in/zeina-abughosh/), [Kody Kovacs](https://www.linkedin.com/in/kodyk5/), [Ted Hong](https://github.com/squishycat92).

## Repository Structure

The main repository directories and entry points are:

```text
ROOT_Repo/
├── fuzz.py                 Main entry point for fuzzing and NOP baseline runs
├── config.py               Shared command-line options and output paths
├── benchmarks/             Per-processor configuration and simulator files
├── setup_scripts/          Chipyard, toolchain, and processor installers
├── thehuzz/                Shared generation, mutation, simulation, and coverage code
├── psofuzz/                PSOFuzz campaign and particle-swarm scheduler
├── mabfuzz/                MABFuzz campaign and bandit policies
├── refuzz/                 ReFuzz collection, training, and testing code
├── software/               RISC-V test-program build support
├── utils/                  Instruction lists, optimizer data, and simulator wrappers
├── input_seeds/            Seeds staged for the current campaign
├── noptest/                Fixed NOP input and per-processor coverage baselines
├── interesting_tests20K/   Offline interesting-test corpus used to train ReFuzz
├── tools/                  Locally installed or packaged build dependencies
├── outputs/                Generated per-run logs, coverage, and testcases
├── outputs_all/            Generated large simulation artifacts
└── sim/                    Generated simulator working directories
```

`outputs/`, `outputs_all/`, and `sim/` are runtime directories and may not
exist until setup or the first campaign. The fuzzer name, target processor,
and run ID determine each output directory name, for example
`outputs/rc_mabfuzz_test_mabfuzz/`.

## Getting Started


## Setup and Install Chipyard v1.13.0 (BOOMV4)
### 1. Install Required Python Packages
python3 -m venv hwfuzzing \
source ./hwfuzzing/bin/activate \
pip3 install gdown openpyxl tqdm pandas numpy matplotlib jsonlines scikit-learn

### 2. Source the setup script for Chipyard 1.13.0:
update paths in thehuzz_setup.sh (Lines 7 and 20)\
source thehuzz_setup.sh

### 3. Install Chipyard Toolchain and Dependencies
# install prerequisites for chipyard 1130 (1 min)
./setup_scripts/install_chipyard_1130_tools.sh

# install chipyard 1.13.0 (20 mins, 10 mins)
./setup_scripts/install_chipyard_1130_pt1.sh\
./setup_scripts/install_chipyard_1130_pt2.sh

### 4. re-source the environment:
source thehuzz_setup.sh

### Setup Benchmarks
Benchmarks currently supported: **Rocket Core**, **CVA6**, **BOOMV3**, and **BOOMV4** processors from the [Chipyard SoC](https://chipyard.readthedocs.io/en/1.13.0/) framework (v1.13.0).

### 5. Install BoomV3:
./setup_scripts/install_boom_v3.sh

### 5. Install BoomV4:
./setup_scripts/install_boom_v4.sh

### 5. Install Rocket Core:
./setup_scripts/install_rc.sh

### 5. Install CVA6:
./setup_scripts/install_cva6.sh


## Generate NOP Coverage Baselines

`noptest` is a special `fuzz.py` run mode that simulates the fixed NOP program
in `noptest/inst_nop_file_0.riscv` exactly once. It records the coverage that
the processor reaches without a generated fuzzing workload. PSOFuzz, MABFuzz,
and ReFuzz initialize their merged coverage with this baseline, so coverage that
is always exercised by the NOP program is not counted as a new reward.
ReFuzz's corpus measurement and training utilities also use these files when
calculating coverage increments.

Generate a baseline after installing each processor that you plan to fuzz.
Run the commands from the repository root after sourcing the environment:

```bash
source thehuzz_setup.sh

python3 fuzz.py -rm noptest -co rc     -sj 1 -j 1 -mp 1 -fd 1
python3 fuzz.py -rm noptest -co cva6   -sj 1 -j 1 -mp 1 -fd 1
python3 fuzz.py -rm noptest -co boomv3 -sj 1 -j 1 -mp 1 -fd 1
python3 fuzz.py -rm noptest -co boomv4 -sj 1 -j 1 -mp 1 -fd 1
```

You only need the commands for the processors used by your workflow:

| Workflow | Required NOP baseline |
| --- | --- |
| TheHuzz or random regression | Not loaded automatically; generating one is optional. |
| PSOFuzz | The target selected with `-co`. |
| MABFuzz | The target selected with `-co`. |
| ReFuzz testing | The target selected with `-co`. |
| ReFuzz collection or training | Every processor whose coverage is collected or scored. |

Each command writes:

```text
noptest/{processor}_nop_cov.json
noptest/{processor}_cov_log.jsonl
```

The JSON baseline contains the coverage bit string for every configured
coverage type. Regenerate it after changing the processor RTL, simulator
coverage configuration, or collected coverage types. The
`{processor}_cov_log.jsonl` file records the coverage result from the baseline
simulation. The `-fd 1` option skips confirmation if an existing run-output
directory is reused; the canonical baseline files for that processor are
rewritten by the command.


## The `interesting_tests20K` Corpus

`interesting_tests20K/` is an offline corpus of tests that increased the
selected feedback coverage when originally collected. It contains tests from
TheHuzz and Cascade across multiple processors and collection rounds. ReFuzz
uses this corpus as input to seed minimization; it then measures the selected
seeds on the training processors and uses their coverage increments to train
its contextual-bandit models.

The current layout is:

```text
interesting_tests20K/
└── {coverage}/
    └── {fuzzer}/
        └── {processor}/
            └── {round}/
                └── test_{id}/
                    ├── inst_file_{id}.riscv
                    ├── inst_file_{id}.hex
                    └── cov_out_{id}.json
```

- `{coverage}` is the target metric used for selection, currently `branch` in
  the included corpus.
- `{fuzzer}` identifies the source, such as `thehuzz` or `cascade`.
- `{processor}` identifies the processor on which the test was collected.
- `{round}` keeps independently collected runs separate because test IDs can
  repeat.
- `cov_out_{id}.json` stores the test's complete simulator coverage, while the
  `.riscv` and `.hex` files store the executable input.

This directory is different from a campaign's
`outputs/<run>/interesting_tests/` directory. Passing `-cit 1` to a supported
fuzzing campaign saves newly discovered coverage-increasing tests under that
run's output directory; it does not automatically add them to the curated
`interesting_tests20K` tree. ReFuzz's Cascade collection utility writes to
`interesting_tests20K/branch/cascade` by default.

For the complete training workflow, command options, expected directory
layouts, and output files, see the [ReFuzz documentation](refuzz/ReadMe.md).


## Run Fuzzers

### TheHuzz

```bash
source thehuzz_setup.sh

python3 fuzz.py \
  -id test_thehuzz \
  -co boomv4 \
  -rm thehuzz \
  -sj 10 \
  -j 10 \
  -mp 30
```

### PSOFuzz

```bash
source thehuzz_setup.sh

python3 fuzz.py \
  -id test_psofuzz \
  -co rc \
  -rm psofuzz \
  -sj 10 \
  -j 10 \
  -mp 200
```

See the [PSOFuzz documentation](psofuzz/ReadMe.md) for its scheduling behavior,
prerequisites, and output files.

### MABFuzz

```bash
source thehuzz_setup.sh

python3 fuzz.py \
  -id test_mabfuzz \
  -co rc \
  -rm mabfuzz \
  -maba EpsilonGreedy \
  -mabns 10 \
  -mabnpr 3 \
  -sj 10 \
  -j 10 \
  -mp 200
```

See the [MABFuzz documentation](mabfuzz/ReadMe.md) for its prerequisites, and output files.

### ReFuzz

```bash
source thehuzz_setup.sh

python3 fuzz.py \
  -id test \
  -co boomv4 \
  -rm refuzztest \
  -maba EpsilonGreedy \
  -rts thehuzzcascade \
  -tp cva6 rc boomv3 \
  -j 10 \
  -mp 100 \
  -cbv 0 \
  -fct branch \
  -fd 1
```

## Publication
BibTeX to cite TheHuzz:
```
@article{kande2022thehuzz,
  title={{TheHuzz: Instruction Fuzzing of Processors Using Golden-Reference Models for Finding Software-Exploitable Vulnerabilities}},
  author={Kande, Rahul and Crump, Addison and Persyn, Garrett and Jauernig, Patrick and Sadeghi, Ahmad-Reza and Tyagi, Aakash and Rajendran, Jeyavijayan},
  journal={USENIX Security Symposium},
  pages={3219--3236},
  year={2022}
}
```
BibTeX to cite HyPFuzz:
```
@article{chen2023hypfuzz,
  title={{HyPFuzz: Formal-Assisted Processor Fuzzing}},
  author={Chen, Chen and Kande, Rahul and Nguyen, Nathan and Andersen, Flemming and Tyagi, Aakash and Sadeghi, Ahmad-Reza and Rajendran, Jeyavijayan},
  journal={USENIX Security Symposium},
  pages={1361--1378},
  year={2023}
}
```
BibTeX to cite PSOFuzz:
```
@article{chen2023psofuzz,
  title={{PSOFuzz: Fuzzing Processors with Particle Swarm Optimization}},
  author={Chen, Chen and Gohil, Vasudev and Kande, Rahul and Sadeghi, Ahmad-Reza and Rajendran, Jeyavijayan},
  journal={IEEE/ACM International Conference on Computer Aided Design},
  pages={1--9},
  year={2023}
}
```
BibTeX to cite MABFuzz:
```
@article{gohil2024mabfuzz,
  title={{MABFuzz: Multi-armed bandit algorithms for fuzzing processors}},
  author={Gohil, Vasudev and Kande, Rahul and Chen, Chen and Sadeghi, Ahmad-Reza and Rajendran, Jeyavijayan},
  journal={IEEE/ACM Design, Automation \& Test in Europe Conference \& Exhibition},
  pages={1--6},
  year={2024}
}
```
BibTeX to cite ReFuzz:
```
@article{chen2025refuzz,
  title={{ReFuzz: Reusing Tests for Processor Fuzzing with Contextual Bandits}},
  author={Chen, Chen and Xu, Zaiyan and Rostami, Mohamadreza and Liu, David and Kalathil, Dileep and Sadeghi, Ahmad-Reza and Rajendran, Jeyavijayan},
  journal={NDSS},
  year={2025}
}
```

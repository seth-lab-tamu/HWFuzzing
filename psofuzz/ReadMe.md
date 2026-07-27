# PSOFuzz

PSOFuzz uses particle swarm optimization (PSO) to learn a probability
distribution over TheHuzz's mutation operators. Each particle owns one seed
lineage and one mutation-weight vector. Coverage discovered by that lineage
updates the particle's local best, while the best particle guides the entire
swarm.

PSOFuzz is integrated into the repository's main `fuzz.py` entry point and
supports Rocket Core (`rc`), CVA6 (`cva6`), BOOMV3 (`boomv3`), and BOOMV4
(`boomv4`).

## How It Works

The particle count is the simulation batch size selected with `-sj`. Each
iteration:

1. Generates a fresh seed for every particle that does not currently own one.
2. Simulates exactly one testcase from every particle.
3. Merges coverage globally and independently for each particle.
4. Updates each particle's local best and the swarm's global best.
5. Advances and normalizes the particle mutation-weight vectors.
6. Mutates each surviving seed once using its particle's weights.

A particle's no-improvement counter is cleared when its configured feedback
coverage increases. When the counter becomes greater than three, that seed is
retired and a fresh generated seed is assigned to the reinitialized particle
on the next iteration. Its lineage-local coverage and local best restart from
the NOP baseline; the swarm's global best is retained.

## Prerequisites

Complete the repository and processor setup, install the Python dependencies,
and source the environment:

```bash
pip3 install gdown openpyxl tqdm pandas numpy matplotlib jsonlines scikit-learn
source thehuzz_setup.sh
```

PSOFuzz starts from the target processor's NOP coverage baseline. Generate the
baseline once before the first campaign:

```bash
python3 fuzz.py -rm noptest -co rc -sj 1 -j 1 -mp 1 -fd 1
```

Replace `rc` with the desired processor. The command writes
`noptest/<processor>_nop_cov.json`. Regenerate it after changing the RTL,
coverage configuration, or selected coverage types.

## Running PSOFuzz

This example runs up to 200 Rocket Core testcases with ten particles:

```bash
python3 fuzz.py \
  -id test_psofuzz \
  -co rc \
  -rm psofuzz \
  -sj 10 \
  -j 10 \
  -mp 200
```

PSOFuzz generates its initial particle seeds; it does not consume the shared
`input_seeds/` pool. Use a unique `-id` for each run. Add `-fd 1` only when an
existing run with the same ID should be replaced without confirmation.

## Shared Options

| Option | Default | Description |
| --- | --- | --- |
| `-co` | `rc` | Target processor. |
| `-sj` | `10` | Particle count and testcases simulated per iteration. |
| `-j` | `10` | Maximum simulation workers; do not exceed `-sj`. |
| `-fct` | all coverage types | Coverage metrics used to update PSO bests. |
| `-mp` | `50000` | Maximum number of simulated testcases. |
| `-mt` | `259200` | Maximum fuzzing time in seconds. |
| `-tc` | repository default | Target total coverage percentage. |
| `-cit` | `0` | Save tests that increase particle-local feedback coverage. |
| `-ccs` | `0` | Save merged coverage at configured percentage intervals. |
| `-db` | `0` | Enable post-campaign mismatch detection. |

Run `python3 fuzz.py --help` for all shared storage, simulator, coverage, and
bug-detection options. PSOFuzz currently exposes no PSO-specific CLI knobs.

## Stopping Conditions

The campaign stops when any one of these conditions is reached:

- The `-mt` time limit expires.
- At least `-mp` testcases have been simulated.
- Total merged coverage reaches `-tc`.

Because a PSOFuzz iteration always simulates one complete particle batch,
choose `-mp` as a multiple of `-sj` when an exact testcase count is required.

## Outputs

For `-co rc -rm psofuzz -id test_psofuzz`, primary outputs are written under:

```text
outputs/rc_psofuzz_test_psofuzz/
```

Important files include:

- `fuzz_log.txt`: configuration, timing, progress, and final statistics.
- `inputs_log.txt`: particle seed generation and mutation activity.
- `cov_log.json`: standard global coverage increments and totals.
- `particle_cov_log.jsonl`: per-iteration cumulative coverage for each particle.
- `particle_status_log.jsonl`: positions, velocities, bests, counters, and resets.
- `merged_cov.json`: final globally merged coverage.
- `all_progs/`: generated and mutated testcase artifacts.
- `interesting_tests/`: optional coverage-increasing tests when `-cit 1` is used.
- `cov_samples/`: optional merged coverage snapshots when `-ccs 1` is used.

Large simulation artifacts are stored in the corresponding
`outputs_all/<processor>_psofuzz_<run_id>/` directory.

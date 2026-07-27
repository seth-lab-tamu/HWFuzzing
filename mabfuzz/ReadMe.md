# MABFuzz

MABFuzz uses multi-armed bandit (MAB) policies to choose which seed family
should receive the next simulation and mutation budget. Each arm represents
one generated seed and the testcases descended from it. Coverage feedback
updates the selected arm so that the fuzzer can balance exploitation of
productive seeds with exploration of other seeds.

MABFuzz is integrated into the repository's main `fuzz.py` entry point and
supports Rocket Core (`rc`), CVA6 (`cva6`), BOOMV3 (`boomv3`), and BOOMV4
(`boomv4`).

## How It Works

Each MABFuzz iteration performs the following steps:

1. Generate a seed for every arm whose testcase queue is empty.
2. Mutate each new seed to populate its arm.
3. Ask the configured MAB policy to select an arm.
4. Simulate up to one batch of testcases from that arm.
5. Merge global and arm-local coverage and update the arm's reward.
6. Select coverage-increasing testcases for further mutation.
7. Reset an arm when it stalls or runs out of queued testcases.

The reward combines coverage discovered globally and coverage that is new to
the selected arm:

```text
reward = 0.75 * global_coverage_increment
       + 0.25 * arm_local_coverage_increment
```

Only the metrics selected by `-fct` contribute to this reward.

## Prerequisites

Complete the repository setup for the target processor and source the
environment from the repository root:

```bash
source thehuzz_setup.sh
```

MABFuzz starts from the target processor's NOP coverage baseline. Generate the
baseline once for each processor before its first MABFuzz run:

```bash
python3 fuzz.py -rm noptest -co rc -sj 1 -j 1 -mp 1 -fd 1
```

Replace `rc` with the desired processor. The command writes
`noptest/<processor>_nop_cov.json`.

## Running MABFuzz

The following example runs 200 Rocket Core testcases using epsilon-greedy
selection:

```bash
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

Use a unique `-id` for each run. To deliberately replace an existing run with
the same ID, add `-fd 1`; this skips the deletion confirmation.

## MAB Options

| Option | Default | Description |
| --- | --- | --- |
| `-maba` | `Greedy` | Arm-selection policy. |
| `-mabns` | `10` | Number of seed arms maintained by MABFuzz. |
| `-mabnpr` | `3` | Number of selected-arm iterations with no local coverage increase before an RC1 reset. |
| `-fct` | all coverage types | Coverage metrics used for mutation feedback and arm rewards. |
| `-sj` | `10` | Maximum number of testcases simulated from the selected arm per batch. |
| `-j` | `10` | Maximum simulation worker count; do not exceed `-sj`. |

Run `python3 fuzz.py --help` for the complete set of campaign, coverage,
storage, and bug-detection options.

## Supported Policies

| Policy | Selection behavior |
| --- | --- |
| `Greedy` | Selects the arm with the highest running mean reward. |
| `UCB` | Adds an upper-confidence exploration bonus to each arm's current value. |
| `EpsilonGreedy` | Selects a random arm with probability 0.2 and otherwise acts greedily. |
| `EXP3` | Samples from adaptive arm weights with an exploration factor of 0.1. |

## Arm Resets

MABFuzz records resets in `particle_status_log.jsonl`:

- `RC1`: the selected arm produced no arm-local coverage increase during its
  last `-mabnpr` selections.
- `RC2`: the selected arm has no remaining queued testcases after mutation.

Resetting clears the arm's learned value and local coverage state. Its testcase
queue is cleared so the next iteration generates a replacement seed.

## Stopping Conditions

The campaign stops when any of these limits is reached:

- `-mt`: maximum fuzzing time in seconds.
- `-mp`: maximum number of simulated testcases.
- `-tc`: target total coverage percentage.

## Outputs

For `-co rc -rm mabfuzz -id test_mabfuzz`, the primary output directory is:

```text
outputs/rc_mabfuzz_test_mabfuzz/
```

Important files include:

- `fuzz_log.txt`: configuration, timing, progress, and final statistics.
- `inputs_log.txt`: seed generation and mutation activity.
- `cov_log.json`: merged coverage increments.
- `particle_cov_log.jsonl`: selected arm, batch size, and arm-local increments.
- `particle_status_log.jsonl`: arm counts, values, selections, and reset records.
- `merged_cov.json`: final merged coverage.
- `all_progs/`: generated and mutated testcase artifacts.

Large reproducible simulation artifacts are stored under the corresponding
`outputs_all/<processor>_mabfuzz_<run_id>/` directory. When
`-cit 1` is enabled, coverage-increasing testcases are also saved under
`interesting_tests/`.

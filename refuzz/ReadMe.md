# ReFuzz

ReFuzz has two main entrypoints:

- `refuzztrain.py` trains contextual-bandit seed databases.
- `refuzztest` runs ReFuzz testing from those trained databases through the top-level `fuzz.py` entrypoint.

## Environment

From the repository root:

```bash
source thehuzz_setup.sh
```

The source selector accepts `-rts` or `--refuzz_train_source`. Selecting
`thehuzzcascade` combines the `thehuzz` and `cascade` inputs for every training
method.

Before a method removes an existing generated destination, it prints the exact
path and requires an explicit `y`. Any other response, including EOF, cancels
the method before any destination is removed.

Cleanup is scoped by method:

- `vul_train` replaces only its `vul_train` directory.
- `seed_mini` replaces its combined corpus and requested solution directories.
- `pre_train_1` replaces the combined `cov_dump` directory.
- `pre_train_2` replaces only `cov_incr_thehuzzcascade.json`, preserving the
  per-processor coverage dumps it consumes.
- `refuzz_train` replaces prior model/context outputs while preserving the
  sibling `vul_train` directory.

## Vulnerability Training

`vul_train` ranks existing vulnerability seeds and writes them into the same trained DB model directory used by `refuzz_train`.

```bash
python3 refuzz/refuzztrain.py \
  --method vul_train \
  -rts thehuzzcascade \
  -tp cva6 rc boomv3 \
  -fct branch
```

The destination is:

```text
refuzz/refuzz_train/trained_db/{refuzz_train_source}/{feedback_cov_type}/{training_processors_joined}_train/vul_train
```

For example:

```text
refuzz/refuzz_train/trained_db/thehuzzcascade/branch/cva6_rc_boomv3_train/vul_train
```

`vul_train` selects top-level seeds from:

```text
refuzz/refuzz_train/existing_bugs
```

Input selection depends on `-rts`:

- `-rts thehuzz`: uses `thehuzz_*.riscv`.
- `-rts thehuzzcascade`: uses both `thehuzz_*.riscv` and `cascade_*.riscv`.

Legacy subdirectories such as `thehuzz_bugs/` and `cascade_bugs/` are not used by the current `vul_train` flow.

Coverage increments are scored from NOP baselines in:

```text
noptest/{processor}_nop_cov.json
```

For example:

```text
noptest/cva6_nop_cov.json
noptest/rc_nop_cov.json
noptest/boomv3_nop_cov.json
```

## Seed Minimization

`seed_mini` builds the minimized seed corpus from precomputed interesting-test coverage. Coverage is loaded from `interesting_tests20K` by default, so the old `input_cov` method is no longer available.

For the current local `interesting_tests20K` tree, combine the `thehuzz` and
`cascade` sources:

```bash
python3 refuzz/refuzztrain.py \
  --method seed_mini \
  -rts thehuzzcascade \
  -tp cva6 rc boomv3 \
  --tar-cov branch
```

The default input layout is:

```text
interesting_tests20K/{coverage}/{fuzzer}/{processor}/{round}/test_{id}/cov_out_{id}.json
interesting_tests20K/{coverage}/{fuzzer}/{processor}/{round}/test_{id}/inst_file_{id}.riscv
```

`--tar-cov` selects the `{coverage}` directory under `interesting_tests20K`. Use `--interesting-tests-root` or `INTEREST_TESTS20K_ROOT` to point at a different collected-coverage tree. The legacy layout without the `{coverage}` component is still accepted as a fallback:

```text
interesting_tests20K/{fuzzer}/{processor}/{round}/test_{id}/cov_out_{id}.json
interesting_tests20K/{fuzzer}/{processor}/{round}/test_{id}/inst_file_{id}.riscv
```

`seed_mini` writes solution JSONs into the legacy solution layout:

```text
refuzz/refuzz_train/interesting_tests/{fuzzer}/{coverage}/{processor}/{fuzzer}_{processor}_solution.json
```

Selected seeds are copied into:

```text
refuzz/refuzz_train/minimized_tests/{refuzz_train_source}/{coverage}/corpus
```

Because test IDs can repeat across collection rounds, copied seed names include the round:

```text
{fuzzer}_{processor}_r{round}_{test_id}.riscv
```

After `seed_mini`, run `pre_train_1` and `pre_train_2` to generate the coverage increment file used by `refuzz_train`:

```bash
python3 refuzz/refuzztrain.py \
  --method pre_train_1 \
  -rts thehuzzcascade \
  -tp cva6 rc boomv3 \
  --tar-cov branch

python3 refuzz/refuzztrain.py \
  --method pre_train_2 \
  -rts thehuzzcascade \
  -tp cva6 rc boomv3 \
  --tar-cov branch
```

Before `pre_train_2`, make sure coverage context JSONs exist for every training processor, threshold, and context sample:

```text
refuzz/refuzz_train/cov_contexts/{coverage}/{processor}/{threshold}/contextN.json
```

If the baseline context collection cannot produce all files, generate missing files from the nearest existing contexts:

```bash
python3 refuzz/refuzz_train/cov_contexts/generate_missing_contexts.py --dry-run
python3 refuzz/refuzz_train/cov_contexts/generate_missing_contexts.py
```

The generator preserves existing files by default. For each missing file, it copies the nearest same-processor `contextN.json` and adjusts only the requested target coverage metric bitstring. Lower synthetic thresholds randomly flip `1` bits to `0`; higher synthetic thresholds randomly flip `0` bits to `1` when no higher baseline context exists.

`pre_train_1` uses `-rts` to choose the minimized corpus and `-tp` to choose which processors to simulate. For example, `-rts thehuzzcascade -tp cva6 rc boomv3 --tar-cov branch` reads:

```text
refuzz/refuzz_train/minimized_tests/thehuzzcascade/branch/corpus
```

and writes coverage dumps under:

```text
refuzz/refuzz_train/minimized_tests/thehuzzcascade/branch/cov_dump/{processor}
```

Coverage dump filenames use the full minimized seed stem, including the collection round:

```text
corpus/thehuzz_boomv3_r0_2.riscv
cov_dump/cva6/cov_out_thehuzz_boomv3_r0_2.json
cov_dump/rc/cov_out_thehuzz_boomv3_r0_2.json
cov_dump/boomv3/cov_out_thehuzz_boomv3_r0_2.json
```

`pre_train_2` reads those per-processor coverage dumps and writes:

```text
refuzz/refuzz_train/minimized_tests/thehuzzcascade/branch/cov_dump/cov_incr_thehuzzcascade.json
```

The coverage-increment JSON keeps the full seed filename as the key, for example `thehuzz_boomv3_r0_2.riscv`, so later `refuzz_train` can look up rewards without re-simulating the seed.

## ReFuzz Training

Run ReFuzz training from the repository root:

```bash
python3 refuzz/refuzztrain.py \
  --method refuzz_train \
  -rts thehuzzcascade \
  -tp cva6 rc boomv3 \
  -fct branch \
  -ren 10000
```

Training uses the same ReFuzz selectors as testing:

- `-rts`: training source, `thehuzz` or `thehuzzcascade`.
- `-tp`: training processors used for reward scoring, eligible source seed processors, and the model name: `cva6 rc boomv3`.
- `-fct`: target feedback coverage metric. ReFuzz training expects exactly one value.
- `-ren`: ReFuzz training epochs.

The minimized corpus and precomputed coverage increment file are resolved as:

```text
refuzz/refuzz_train/minimized_tests/{refuzz_train_source}/{feedback_cov_type}/corpus
refuzz/refuzz_train/minimized_tests/{refuzz_train_source}/{feedback_cov_type}/cov_dump/cov_incr_{refuzz_train_source}.json
```

For example:

```text
refuzz/refuzz_train/minimized_tests/thehuzzcascade/branch/cov_dump/cov_incr_thehuzzcascade.json
```

The trained model is written under:

```text
refuzz/refuzz_train/trained_db/{refuzz_train_source}/{feedback_cov_type}/{training_processors_joined}_train
```

For example:

```text
refuzz/refuzz_train/trained_db/thehuzzcascade/branch/cva6_rc_boomv3_train
```

The training processor set used in this workflow is `cva6`, `rc`, and `boomv3`. Pass this processor set explicitly with `-tp` so training and testing resolve the same trained DB directory. During `refuzz_train`, seeds whose filename source processor is not in `-tp` are excluded from threshold tuning, trained model JSON, and copied trained DB context directories.

## Testing

Run testing through `fuzz.py`:

```bash
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

Use `-fd 1` when reusing an existing `-id`, otherwise `fuzz.py` asks before deleting the old output directory.

## Trained DB Selection

Both training and testing derive the trained model path from the ReFuzz selectors:

```text
refuzz/refuzz_train/trained_db/{refuzz_train_source}/{feedback_cov_type}/{training_processors_joined}_train
```

For example:

```bash
-rts thehuzzcascade -tp cva6 rc boomv3 -fct branch
```

resolves to:

```text
refuzz/refuzz_train/trained_db/thehuzzcascade/branch/cva6_rc_boomv3_train
```

Supported selectors:

- `-rts`: trained DB source, `thehuzz` or `thehuzzcascade`.
- `-tp`: training benchmarks used in the model directory name: `cva6 rc boomv3`.
- `-fct`: target feedback coverage metric. Current ReFuzz test contexts support `branch` and `cond`.
- `-maba`: MAB policy, for example `Greedy` or `EpsilonGreedy`.
- `-cbv`: set to `1` to run the optional `vul_train` phase before contextual seed testing; set to `0` to skip it.

## Outputs

The run writes normal fuzzer outputs under:

```text
outputs/{core}_{run_mode}_{run_id}
outputs_all/{core}_{run_mode}_{run_id}
```

Important ReFuzz logs include:

- `cov_log.json`
- `particle_cov_log.jsonl`
- `particle_status_log.jsonl`
- `inputs_log.txt`
- `merged_cov.json`

`coverage_progress.txt` is also updated in the repository root.

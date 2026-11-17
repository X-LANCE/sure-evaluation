# EAR-1 — Challenge Scoring

Score EAR-1 (ICASSP 2027 Grand Challenge) evaluation submissions with the
official organizer scorer. Input is a submission ZIP and a private reference
directory. No inference is run.

```bash
sure-eval metric routes ear1
```

## Metrics

One route per leaderboard. Lower is better.

| Task | Track | Metric | Pipeline ID |
|:--|:--|:--|:--|
| ESD-ON | D1 | `der` | `ear1.esd.d1.der.ear1_openbench_v1` |
| ESD-ON | R1 | `der` | `ear1.esd.r1.der.ear1_openbench_v1` |
| ESR-ON | D1 | `cpcer` | `ear1.esr.d1.cpcer.ear1_openbench_v1` |
| ESR-ON | R1 | `cpcer` | `ear1.esr.r1.cpcer.ear1_openbench_v1` |

All routes use `scoring/ear1_openbench` with `distance_backend: builtin`.

- DER: collar 0, overlap scored. Missed, false-alarm and confusion time are
  summed over sessions and divided by total reference speaker time.
- cpCER: NFKC, lowercase, whitespace and punctuation removed. Speaker streams
  are matched by minimum character edit distance; errors are summed over
  sessions and divided by total reference characters. Rows overlapping a
  reference `*` interval or an `exclude` interval are dropped.

## Versions

| Item | Version |
|:--|:--|
| Node `scoring/ear1_openbench` | `v1` |
| Organizer scorer | `openbench-integration-0.1` |

The scorer version is written to `details.scoring_result.scorer_version`.
Compare scores only within one scorer version. Source and upgrade notes are in
the [node README](../../src/sure_eval/evaluation/nodes/scoring/ear1_openbench/README.md).

## Input Format

Roles: `submission` (ZIP) and `reference_dir`. Times are in seconds on the
released recording clock.

Reference directory (one per task and track):

```json
{
  "track": "D1",
  "sessions": {
    "EVAL001": {"duration_s": 9, "uem": [[0, 7], [8, 9]]},
    "EVAL002": {"duration_s": 3}
  }
}
```

- ESD-ON: `sessions.json` and `reference.rttm`. `uem` is optional; the whole
  recording is scored without it.
- ESR-ON: `sessions.json` and one `<session_id>.stm` per session. `exclude` is
  optional.

ESD-ON submission: `submission.rttm` at the ZIP root, all sessions in one file.
List sessions with no speech in `empty_sessions.txt`.

```text
SPEAKER EVAL001 1 0.0 3.0 <NA> <NA> spk02 <NA> <NA>
```

ESR-ON submission: one `<session_id>.stm` per session at the ZIP root. An empty
file means no output for that session.

```text
EVAL001 1 spk02 0.0 1.0 你 好
```

The run fails if a session is missing or unknown, the track differs from
`sessions.json`, or a row is malformed.

## Setup

SciPy is required:

```bash
python -m pip install 'scipy>=1.10'
sure-eval env check --node scoring/ear1_openbench
```

`sure-eval env setup` does not install `pip` runtime nodes yet.

## CLI Usage

Run from a repository checkout with the bundled fixtures:

```bash
sure-eval metric describe ear1 --metric der --track D1 --output ear1_esd_d1.json
sure-eval metric run --pipeline ear1_esd_d1.json \
  --submission tests/fixtures/ear1_openbench/esd/submission.zip \
  --reference-dir tests/fixtures/ear1_openbench/esd/reference \
  --output-dir ear1_esd_d1 --validate-env
```

`ear1_esd_d1/report.json` → `details.scoring_result`:

```json
{"scorer_version": "openbench-integration-0.1", "task": "ESD-ON", "track": "D1",
 "metric": "DER", "score": 0.5, "score_pct": 50.0, "session_count": 2,
 "counts": {"miss_s": 3.0, "fa_s": 1.0, "conf_s": 1.0, "ref_s": 10.0}}
```

ESR-ON on R1 (expected `score` 0.625):

```bash
sure-eval metric describe ear1 --metric cpcer --track R1 --output ear1_esr_r1.json
sure-eval metric run --pipeline ear1_esr_r1.json \
  --submission tests/fixtures/ear1_openbench/esr/submission.zip \
  --reference-dir tests/fixtures/ear1_openbench/esr/reference \
  --output-dir ear1_esr_r1 --validate-env
```

`--pipeline-id` also selects a route. A `--track` that does not match the route
is rejected. `--distance-backend agwer` needs the organizer
`requirements-scoring-fast.txt`.

## Python API

```python
from sure_eval.evaluation.scripts import run_task

report = run_task(
    "ear1",
    submission="tests/fixtures/ear1_openbench/esr/submission.zip",
    reference_dir="tests/fixtures/ear1_openbench/esr/reference",
    metric="cpcer",
    track="R1",
    output_dir="ear1_esr_r1",
)
print(report.score)  # 0.625
```

## Output

- `report.json`: `score` (ratio), `pipeline_id`, and
  `details.scoring_result` with `scorer_version`, `task`, `track`, `metric`,
  `score_pct`, `session_count` and `counts`.
- `pipeline_description.json`: metric, `pipeline_id`, node ids and versions.

Reference labels and transcripts are not written to the output.

## Leaderboard Workflow

1. Organizers place one reference directory per leaderboard on the scoring
   worker.
2. The platform installs SURE and SciPy and runs `sure-eval env check --node
   scoring/ear1_openbench`.
3. Run `metric describe` once per leaderboard and keep the pipeline JSON.
4. For each upload, run `metric run --validate-env` with the ZIP and the
   matching reference directory. A non-zero exit means the submission is
   rejected.
5. Store `score_pct`, `scorer_version` and `pipeline_id` with the submission
   and rank ascending.

EAR-1 scores are not comparable with the `sd` DER or `sa_asr` cpWER routes.

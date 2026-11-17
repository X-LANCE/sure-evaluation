# EAR-1 OpenBench Scoring

## Purpose

`scoring/ear1_openbench` scores one EAR-1 submission ZIP for one task and track
against an organizer reference directory. It validates the submission and
returns pooled DER or cpCER counts. It does not run inference.

## Task Scenarios

- ESD-ON: `ear1.esd.d1.der.ear1_openbench_v1`, `ear1.esd.r1.der.ear1_openbench_v1`.
- ESR-ON: `ear1.esr.d1.cpcer.ear1_openbench_v1`, `ear1.esr.r1.cpcer.ear1_openbench_v1`.
- Only backend for these routes.

## Input

- Schema: `ear1_submission_zip_and_reference_directory`.
- Roles: `submission`, `reference_dir`.
- Alignment key: session ID from `sessions.json`.
- ESD-ON: `submission.rttm` and optional `empty_sessions.txt` in the ZIP;
  `reference.rttm` in the reference directory.
- ESR-ON: one `<session_id>.stm` per session in the ZIP and in the reference
  directory.

## Output

- Schema: `ear1_metric_report`.
- Fields: `scorer_version`, `task`, `track`, `metric`, `score`, `score_pct`,
  `session_count`, `counts`.
- DER counts: `miss_s`, `fa_s`, `conf_s`, `ref_s`.
- cpCER counts: `substitutions`, `deletions`, `insertions`,
  `reference_characters`.
- Lower is better.

## Versioned Computation

- Node id: `scoring/ear1_openbench`.
- Version: `v1`.
- Scorer version: `openbench-integration-0.1`.
- Internal stages: `submission_validation`, `reference_validation`,
  `metric_scoring`, `pooled_aggregation`.
- DER: collar 0, overlap scored, optional per-session `uem`. One speaker
  mapping per session; error time pooled over sessions.
- cpCER: NFKC, lowercase, whitespace and punctuation removed. Per-speaker text
  concatenated by time, speakers matched by minimum edit distance, errors
  pooled over reference characters. Rows overlapping a reference `*` interval
  or an `exclude` interval are dropped.
- `distance_backend`: `builtin` (default) or `agwer`. Both give the same
  totals; the S/D/I split can differ on ties.

## Runtime and Assets

- Runtime: `pip`.
- Package: `scipy>=1.10`.

```bash
python -m pip install 'scipy>=1.10'
sure-eval env check --node scoring/ear1_openbench
```

- `agwer` needs the organizer `requirements-scoring-fast.txt`.
- No checkpoints or binaries.

## Source and References

- `scorer.py` and `metrics.py` are copied from the organizer handoff
  `EAR1_OpenBench_Scoring` (`score.py`, `ear1_metrics.py`). `ear1_metrics.py`
  is Git blob `2d2e578d6de56afe319603e7b0e0e56654f931c5` from
  `egs/ear1/local`.
- Local changes: package import, no CLI entry point, `distance_backend=`
  alias on `score()`, one line split for lint. Scoring is unchanged.
- To upgrade, replace both files and refresh `tests/fixtures/ear1_openbench/`.
- https://earchallenge.github.io/ear1/
- https://github.com/earchallenge/ear1-baselines

## Limitations

- The `*` / `exclude` row rule, `empty_sessions.txt` and the final `uem` /
  `exclude` metadata are provisional in `openbench-integration-0.1`.
- Oracle speaker count and VAD are not enforced on submissions.
- Error messages can include session IDs; do not show them to participants
  unfiltered.
- Not comparable with the `sd` DER or `sa_asr` cpWER routes.

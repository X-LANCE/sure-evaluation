# EAR-1 OpenBench scoring

This node implements the EAR-1 OpenBench ESD-ON/DER and ESR-ON/cpCER
submission contract. It validates the participant ZIP and organizer reference
metadata, then returns pooled score counts. It does not run inference.

## Provenance

`scorer.py` and `metrics.py` are vendored from the EAR-1 organizer handoff
`EAR1_OpenBench_Scoring` (`score.py` and `ear1_metrics.py`, scorer version
`openbench-integration-0.1`; `ear1_metrics.py` is Git blob
`2d2e578d6de56afe319603e7b0e0e56654f931c5` from `egs/ear1/local`). The SURE
copy differs only in the package-relative import, the removed standalone CLI
entry point, a `distance_backend=` keyword alias on `score()` and one
lint-only line split. Scoring logic is unchanged. When the organizers publish a
new scorer version, replace both files together and refresh
`tests/fixtures/ear1_openbench/`. Scores are comparable only within one
`scorer_version`.

## Backends

The default `builtin` backend runs in process. Speaker assignment uses SciPy's
`linear_sum_assignment`, exactly as the standalone handoff does, so SciPy must
be installed. SciPy is not a core SURE dependency: `node_env.yaml` declares it
as a pip runtime, so `sure-eval env check` and `metric run --validate-env`
fail when it is missing and print the install command
(`python -m pip install 'scipy>=1.10'`). The optional
`agwer` backend requires the pinned dependencies from the external EAR-1
package (`requirements-scoring-fast.txt`). SURE's `env setup` does not install
the handoff's requirement files.

## CLI

```bash
sure-eval metric routes ear1 --metric der --track D1 --json
sure-eval metric describe ear1 --metric der --track D1 --output ear1_esd_d1.json
sure-eval metric run --pipeline ear1_esd_d1.json \
  --submission submission.zip \
  --reference-dir /private/organizer/esd/D1 \
  --output-dir ear1_esd_d1
```

For ESR-ON use `--metric cpcer` and the corresponding `R1`/`D1` track. The
reference directory must remain on the scoring worker; it is never included
in the participant ZIP.

# Broadband EDT MAE

## Purpose

Reports full-band EDT error in seconds. This optional route is a model
comparison diagnostic and is distinct from ISO octave-band EDT.

## Task Scenarios

- `rir/any/rir_edt_broadband_mae` selects this atomic scoring node.
- It is optional and is not part of the leaderboard ISO JND bundle.

## Input

- Schema: `rir_samples_jsonl`.
- Required roles: `sample_id`, `prediction_rir`, `reference_rir`.
- NumPy inputs require row-level `sample_rate`; rows align by `sample_id`.

## Output

- Schema: `rir_edt_broadband_mae_score`.
- Lower is better; the score unit is seconds.
- Details retain per-channel prediction/reference EDT and absolute errors.

## Versioned Computation

- Node `scoring/rir_edt_broadband_mae`, version `v1`.
- Detect one broadband onset shared by the RIR's channels, compute the full-band
  Schroeder EDC, fit 0 to -10 dB, extrapolate the slope to 60 dB, and average
  channel errors then samples.

## Runtime and Assets

- Runtime: `in_process`.
- Requires NumPy and the optional audio loader; no checkpoint or binary.
- No node-local environment is used.

## Source and References

- Local implementation: `sure_eval.evaluation.tasks.rir.metrics`.
- The companion `rir_edt_m_mae` route follows the RIR leaderboard's octave-band
  benchmark protocol.

## Limitations

This route has no ISO Table A.1 JND normalization. Undefined decay fits fail
the strict route; short RIRs may not contain enough samples for a stable fit.

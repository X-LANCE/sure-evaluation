# ISO 3382 Centre-Time JND Error

## Purpose

Compares predicted and reference energy-weighted centre time (Ts) in the
benchmark's ISO 3382 octave-band protocol. It reports error in multiples of the
10 ms JND; it is not a complete auditorium measurement report.

## Task Scenarios

- `rir/any/rir_ts_jnd_mae` selects this atomic scoring node.
- The node is also available in the RIR ISO 3382 JND metric set.

## Input

- Schema: `rir_samples_jsonl`.
- Required roles: `sample_id`, `prediction_rir`, `reference_rir`.
- NumPy inputs require row-level `sample_rate`; rows align by `sample_id`.

## Output

- Schema: `rir_ts_jnd_mae_score`.
- Lower is better; the score unit is `x_jnd`.
- Details retain per-channel prediction/reference Ts, absolute error, JND
  multiple, pass flag, absolute MAE, and within-one-JND sample percentage.

## Versioned Computation

- Node `scoring/rir_ts_jnd_mae`, version `v1`.
- Detect one broadband onset per RIR, filter at 500 Hz and 1 kHz with the
  zero-phase Butterworth octave-band filters, and compute energy-weighted time
  from the onset in each band.
- Average the two band values per channel, divide absolute error by 10 ms,
  average channels then samples, and require every channel for a sample pass.

## Runtime and Assets

- Runtime: `in_process`.
- Requires NumPy, SoundFile, and SciPy from `sure-evaluation[audio]`.
- No checkpoint, binary, or node-local environment is used.

## Source and References

- Local implementation: `sure_eval.evaluation.tasks.rir.metrics`.
- Threshold: BS EN ISO 3382-1:2009 Annex A Table A.1, applied as a benchmark
  comparison rule.

## Limitations

The channel aggregation and pass-rate rule are benchmark conventions. Missing
or undefined band energy fails the strict route; IEC 61260 certification,
background-noise correction, and auditorium calibration are not claimed.

# RIR Octave-Band EDT MAE

## Purpose

Reports the arithmetic 500 Hz/1 kHz octave-band EDT error in seconds. This is
the main RIR leaderboard acoustic EDT metric; it is not a certified auditorium
measurement report.

## Task Scenarios

- `rir/any/rir_edt_m_mae` selects this atomic scoring node.
- It is part of the RIR ISO-parameter metric set and leaderboard bundle.

## Input

- Schema: `rir_samples_jsonl`.
- Required roles: `sample_id`, `prediction_rir`, `reference_rir`.
- NumPy inputs require row-level `sample_rate`; rows align by `sample_id`.

## Output

- Schema: `rir_edt_m_mae_score`.
- Lower is better; the score unit is seconds.
- Details retain both frequency bands, per-channel prediction/reference EDT,
  and absolute errors.

## Versioned Computation

- Node `scoring/rir_edt_m_mae`, version `v1`.
- Detect the first broadband sample within 20 dB of the peak, filter at 500 Hz
  and 1 kHz using zero-phase sixth-order-prototype Butterworth octave bands,
  fit the initial 0 to -10 dB Schroeder decay, and extrapolate to 60 dB.
- Average the two band values per channel, then channel errors and samples
  arithmetically.

## Runtime and Assets

- Runtime: `in_process`.
- Requires NumPy, SoundFile, and SciPy from `sure-evaluation[audio]`.
- No checkpoint, binary, or node-local environment is used.

## Source and References

- Local implementation: `sure_eval.evaluation.tasks.rir.metrics`.
- Protocol note: `docs/tasks/rir.md` and the RIR leaderboard ISO 3382 analysis.

## Limitations

The frequency and channel averaging rules are benchmark conventions. The
filter is not claimed IEC 61260 certified, and no background-noise correction,
source calibration, or auditorium measurement certification is provided.

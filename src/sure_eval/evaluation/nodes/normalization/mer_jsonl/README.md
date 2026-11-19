# MER JSONL Normalizer

## Purpose

Parses, validates, sorts, and strictly aligns canonical Music Emotion Recognition (MER) JSONL reference and prediction files for continuous Valence-Arousal regression. It supports both static clip-level rows (`music_id`) and 0.5-second dynamic time-series rows (`music_id` + `frame_time`). It does not perform audio decoding, feature extraction, or metric scoring.

## Task Scenarios

- `mer/any/rmse`, `mer/any/mae`, `mer/any/pcc`, `mer/any/r2`, `mer/any/ccc` (static default route family).
- `mer/any/dynamic_rmse`, `mer/any/dynamic_mae`, `mer/any/dynamic_pcc`, `mer/any/dynamic_r2`, `mer/any/dynamic_ccc` (0.5s dynamic time-series route family).

## Input

- Input schema: `mer_jsonl_pair`.
- Required roles: `reference_jsonl`, `sample_output`.
- Static row format (`granularity: static`, aligned by `music_id`):
  `{"music_id": "1", "valence": 0.65, "arousal": 0.72}`
- Dynamic row format (`granularity: dynamic`, aligned by `music_id` and `frame_time` within `timestamp_tolerance_sec`):
  `{"music_id": "1", "frame_time": 15.5, "valence": 0.61, "arousal": 0.70}`
- Accepts `musicId` / `frameTime` field aliases (matching PMEmo CSV headers) and requires finite numeric `valence` and `arousal`.

## Output

- Output schema: `mer_normalized_bundle`.
- Emits a `PipelineNodeResult` trace containing `granularity`, `alignment`, and `input_summary` (`num_songs`, `song_ids`, `num_rows`, `dimensions`, `input_order`).

## Versioned Computation

- Node id and version: `normalization/mer_jsonl` (`v1`).
- Internal stages: `jsonl_parse`, `row_contract`, `finite_value_validation`, `exact_key_alignment`, `timestamp_tolerance_validation`.
- Rejects missing/duplicate keys, non-finite values, mismatched row counts or key sets, and `frame_time` mismatches exceeding `timestamp_tolerance_sec`.

## Runtime and Assets

- Runtime type: `in_process`.
- Pure Python standard library implementation; runs in the base `sure-evaluation` package with no extra packages, binaries, or model checkpoints.

## Source and References

- Local canonical implementation motivated by PMEmo (*The PMEmo Dataset for Music Emotion Recognition*, ACM ICMR 2018; https://github.com/HuiZhangDB/PMEmo).

## Limitations

- Requires pre-formatted JSONL rows with `valence` and `arousal` numeric values; does not convert raw CSV files or discrete emotion labels.
- Does not resample mismatched frame rates between reference and prediction files.

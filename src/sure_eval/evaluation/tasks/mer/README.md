# MER (Music Emotion Recognition)

Model-independent canonical continuous emotion regression task for Music Emotion Recognition (designed for PMEmo and compatible Valence-Arousal benchmarks).

## Supported Routes

- Static clip-level regression (`granularity: static`, aligned by `music_id`):
  - `mer.any.rmse.mer_jsonl_v1.mer_regression_v1` (default)
  - `mer.any.mae.mer_jsonl_v1.mer_regression_v1`
  - `mer.any.pcc.mer_jsonl_v1.mer_regression_v1`
  - `mer.any.r2.mer_jsonl_v1.mer_regression_v1`
  - `mer.any.ccc.mer_jsonl_v1.mer_regression_v1`
- Dynamic 0.5-second time-series regression (`granularity: dynamic`, aligned by `music_id` and `frame_time`):
  - `mer.any.dynamic_rmse.mer_jsonl_v1.mer_regression_v1`
  - `mer.any.dynamic_mae.mer_jsonl_v1.mer_regression_v1`
  - `mer.any.dynamic_pcc.mer_jsonl_v1.mer_regression_v1`
  - `mer.any.dynamic_r2.mer_jsonl_v1.mer_regression_v1`
  - `mer.any.dynamic_ccc.mer_jsonl_v1.mer_regression_v1`

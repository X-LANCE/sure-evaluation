# MER — Music Emotion Recognition

Canonical continuous emotion regression evaluation for Music Emotion Recognition (MER) benchmarks such as **PMEmo** (static chorus annotations and 0.5-second dynamic time-series annotations on `valence` and `arousal`).

## Supported Pipelines

| Metric | Granularity | Pipeline ID | Nodes |
| --- | --- | --- | --- |
| `rmse` (default) | `static` | `mer.any.rmse.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |
| `mae` | `static` | `mer.any.mae.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |
| `pcc` | `static` | `mer.any.pcc.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |
| `r2` | `static` | `mer.any.r2.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |
| `ccc` | `static` | `mer.any.ccc.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |
| `dynamic_rmse` | `dynamic` | `mer.any.dynamic_rmse.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |
| `dynamic_mae` | `dynamic` | `mer.any.dynamic_mae.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |
| `dynamic_pcc` | `dynamic` | `mer.any.dynamic_pcc.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |
| `dynamic_r2` | `dynamic` | `mer.any.dynamic_r2.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |
| `dynamic_ccc` | `dynamic` | `mer.any.dynamic_ccc.mer_jsonl_v1.mer_regression_v1` | `normalization/mer_jsonl`, `scoring/mer_regression` |

## Input Contract

Required roles: `reference_jsonl` and `sample_output`.

Static clip-level JSONL (`granularity: static`):

```json
{"music_id": "1", "valence": 0.65, "arousal": 0.72}
{"music_id": "2", "valence": 0.31, "arousal": 0.44}
```

Dynamic 0.5-second JSONL (`granularity: dynamic`):

```json
{"music_id": "1", "frame_time": 15.5, "valence": 0.61, "arousal": 0.70}
{"music_id": "1", "frame_time": 16.0, "valence": 0.64, "arousal": 0.73}
```

## CLI Example

```bash
sure-eval metric routes mer --json
sure-eval metric describe mer --metric rmse --output pipeline.json
sure-eval metric run --pipeline pipeline.json \
  --reference-jsonl ref_static.jsonl \
  --sample-output pred_static.jsonl \
  --output-dir out/mer_static \
  --json
```

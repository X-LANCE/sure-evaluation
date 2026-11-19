# MER Continuous Regression Scorer

## Purpose

Computes canonical continuous regression metrics (`RMSE`, `MAE`, `PCC`, `R2`, and `CCC`) on aligned `valence` and `arousal` predictions for Music Emotion Recognition (MER). It evaluates both static clip-level bundles and 0.5-second dynamic time-series bundles. It does not parse raw JSONL files or run inference models.

## Task Scenarios

- `mer/any/rmse` (default static route), `mer/any/mae`, `mer/any/pcc`, `mer/any/r2`, `mer/any/ccc`.
- `mer/any/dynamic_rmse`, `mer/any/dynamic_mae`, `mer/any/dynamic_pcc`, `mer/any/dynamic_r2`, `mer/any/dynamic_ccc`.

## Input

- Input schema: `mer_normalized_bundle` (produced by `normalization/mer_jsonl`).
- Required parameters: `metric` (one of the 10 supported MER metrics), `aggregation` (`micro` or `macro_song`, default `micro`).

## Output

- Output schema: `mer_regression_report`.
- Primary `score`: mean of `valence` and `arousal` for the selected metric and aggregation.
- Lower is better for `rmse`, `mae`, `dynamic_rmse`, `dynamic_mae`; higher is better for `pcc`, `r2`, `ccc`, `dynamic_pcc`, `dynamic_r2`, `dynamic_ccc`.
- Trace details expose `by_dimension`, full `micro` (pooled across all aligned rows), and full `macro_song` (per-song average across songs where defined) breakdowns for all five base metrics.

## Versioned Computation

- Node id and version: `scoring/mer_regression` (`v1`).
- Internal stages: `dimension_extraction`, `regression_metric_computation`, `song_grouping`, `macro_song_aggregation`, `primary_score_selection`.
- Uses population variance/covariance ($\frac{1}{N}$) for Lin's CCC and returns `None` instead of raising when correlation or $R^2$ denominators vanish (for example constant series or single-row songs in `macro_song`).

## Runtime and Assets

- Runtime type: `in_process`.
- Pure Python standard library implementation; runs in the base `sure-evaluation` package with no extra packages, binaries, or model checkpoints.

## Source and References

- Standard continuous MER evaluation metrics following PMEmo (*The PMEmo Dataset for Music Emotion Recognition*, ACM ICMR 2018; https://github.com/HuiZhangDB/PMEmo), DEAM, and Lin's Concordance Correlation Coefficient (1989).

## Limitations

- Evaluates two continuous affective dimensions (`valence` and `arousal`); multi-label tagging or discrete classification routes are outside this node's scope.
- `pcc`, `r2`, and `ccc` are undefined (`None`) for zero-variance ground truth or songs with fewer than two frames in `macro_song`.

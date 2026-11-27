"""Pure-Python continuous emotion regression scorer for static and dynamic MER."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from sure_eval.evaluation.core.types import PipelineNodeResult
from sure_eval.evaluation.nodes.normalization.mer_jsonl.node import MERBundle, MERSample

NODE_ID = "scoring/mer_regression"
NODE_VERSION = "v1"
INTERNAL_STAGES = (
    "dimension_extraction",
    "regression_metric_computation",
    "song_grouping",
    "macro_song_aggregation",
    "primary_score_selection",
)
BASE_METRICS = ("rmse", "mae", "pcc", "r2", "ccc")
SUPPORTED_METRICS = (
    "rmse",
    "mae",
    "pcc",
    "r2",
    "ccc",
    "dynamic_rmse",
    "dynamic_mae",
    "dynamic_pcc",
    "dynamic_r2",
    "dynamic_ccc",
)
VALID_AGGREGATIONS = ("micro", "macro_song")


def score_mer_regression(
    bundle: MERBundle,
    *,
    metric: str = "rmse",
    aggregation: str = "micro",
) -> PipelineNodeResult:
    """Compute RMSE, MAE, PCC, R2, and CCC on valence and arousal."""

    normalized_metric = metric.lower().replace("-", "_")
    if normalized_metric not in SUPPORTED_METRICS:
        raise ValueError(f"Unsupported MER metric: {metric}")
    if aggregation not in VALID_AGGREGATIONS:
        raise ValueError(f"aggregation must be one of {VALID_AGGREGATIONS}, got {aggregation!r}")

    base_metric = normalized_metric.removeprefix("dynamic_")
    if normalized_metric.startswith("dynamic_") and bundle.granularity != "dynamic":
        raise ValueError(f"Metric {normalized_metric!r} requires granularity='dynamic'")
    if not normalized_metric.startswith("dynamic_") and bundle.granularity != "static":
        raise ValueError(f"Metric {normalized_metric!r} requires granularity='static'")

    micro = _score_pairs(bundle.reference, bundle.prediction)
    macro_song = _score_macro_song(bundle.reference, bundle.prediction)

    active_view = micro if aggregation == "micro" else macro_song
    score = active_view["overall"][base_metric]

    details: dict[str, Any] = {
        "metric": normalized_metric,
        "base_metric": base_metric,
        "granularity": bundle.granularity,
        "aggregation": aggregation,
        "score": score,
        "by_dimension": {
            dim: active_view["by_dimension"][dim][base_metric] for dim in bundle.dimensions
        },
        "micro": micro,
        "macro_song": macro_song,
        "num_rows": len(bundle.reference),
        "num_songs": bundle.input_summary["num_songs"],
    }
    return PipelineNodeResult(
        stage="scoring",
        node_id=NODE_ID,
        version=NODE_VERSION,
        details=details,
    )


def _score_pairs(
    references: tuple[MERSample, ...] | list[MERSample],
    predictions: tuple[MERSample, ...] | list[MERSample],
) -> dict[str, Any]:
    ref_v = [row.valence for row in references]
    pred_v = [row.valence for row in predictions]
    ref_a = [row.arousal for row in references]
    pred_a = [row.arousal for row in predictions]

    valence_metrics = _compute_all_metrics(ref_v, pred_v)
    arousal_metrics = _compute_all_metrics(ref_a, pred_a)
    overall = {
        name: _mean_defined([valence_metrics[name], arousal_metrics[name]])
        for name in BASE_METRICS
    }
    return {
        "overall": overall,
        "by_dimension": {
            "valence": valence_metrics,
            "arousal": arousal_metrics,
        },
        "num_rows": len(references),
    }


def _score_macro_song(
    references: tuple[MERSample, ...],
    predictions: tuple[MERSample, ...],
) -> dict[str, Any]:
    grouped_ref: dict[str, list[MERSample]] = defaultdict(list)
    grouped_pred: dict[str, list[MERSample]] = defaultdict(list)
    for ref, pred in zip(references, predictions):
        grouped_ref[ref.music_id].append(ref)
        grouped_pred[pred.music_id].append(pred)

    per_song: dict[str, dict[str, Any]] = {}
    for music_id in sorted(grouped_ref):
        per_song[music_id] = _score_pairs(grouped_ref[music_id], grouped_pred[music_id])

    by_dimension: dict[str, dict[str, float | None]] = {}
    for dim in ("valence", "arousal"):
        by_dimension[dim] = {
            name: _mean_defined(
                [per_song[mid]["by_dimension"][dim][name] for mid in sorted(per_song)]
            )
            for name in BASE_METRICS
        }
    overall = {
        name: _mean_defined([by_dimension["valence"][name], by_dimension["arousal"][name]])
        for name in BASE_METRICS
    }
    return {
        "overall": overall,
        "by_dimension": by_dimension,
        "num_songs": len(per_song),
        "per_song": per_song,
    }


def _compute_all_metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float | None]:
    n = len(y_true)
    if n == 0:
        return {name: None for name in BASE_METRICS}

    sq_errors = [(a - b) ** 2 for a, b in zip(y_true, y_pred)]
    abs_errors = [abs(a - b) for a, b in zip(y_true, y_pred)]
    rmse = math.sqrt(sum(sq_errors) / n)
    mae = sum(abs_errors) / n

    mean_true = sum(y_true) / n
    mean_pred = sum(y_pred) / n
    ss_res = sum(sq_errors)
    ss_tot = sum((a - mean_true) ** 2 for a in y_true)
    ss_pred = sum((b - mean_pred) ** 2 for b in y_pred)

    r2: float | None = None if ss_tot == 0.0 else 1.0 - (ss_res / ss_tot)

    pcc: float | None
    ccc: float | None
    if n < 2:
        pcc = None
        ccc = None
    else:
        cov_sum = sum((a - mean_true) * (b - mean_pred) for a, b in zip(y_true, y_pred))
        denom_pcc = math.sqrt(ss_tot * ss_pred)
        pcc = None if denom_pcc == 0.0 else cov_sum / denom_pcc

        var_true = ss_tot / n
        var_pred = ss_pred / n
        cov = cov_sum / n
        denom_ccc = var_true + var_pred + (mean_true - mean_pred) ** 2
        ccc = None if denom_ccc == 0.0 else (2.0 * cov) / denom_ccc

    return {
        "rmse": rmse,
        "mae": mae,
        "pcc": pcc,
        "r2": r2,
        "ccc": ccc,
    }


def _mean_defined(values: list[float | None]) -> float | None:
    defined = [v for v in values if v is not None and math.isfinite(v)]
    if not defined:
        return None
    return sum(defined) / len(defined)

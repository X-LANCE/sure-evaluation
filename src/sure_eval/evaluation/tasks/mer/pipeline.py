"""Model-independent canonical MER (Music Emotion Recognition) task routes."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sure_eval.evaluation.core.types import EvaluationFiles, EvaluationReport, MetricInputContract
from sure_eval.evaluation.nodes.normalization.mer_jsonl import normalize_mer_jsonl
from sure_eval.evaluation.nodes.scoring.mer_regression import (
    SUPPORTED_METRICS,
    score_mer_regression,
)
from sure_eval.evaluation.pipeline_identity import (
    build_atomic_pipeline_id,
    component_trace_ids,
    node_component,
)

_STATIC_CONTRACT = MetricInputContract(
    metric_id="task/mer_static_jsonl",
    required_roles=("reference_jsonl", "sample_output"),
    optional_roles=("aggregation",),
    row_format="mer_static_valence_arousal_jsonl",
    alignment_key="music_id",
    aggregation="micro_mean_valence_arousal",
    purpose="canonical_static_music_emotion_regression",
)

_DYNAMIC_CONTRACT = MetricInputContract(
    metric_id="task/mer_dynamic_jsonl",
    required_roles=("reference_jsonl", "sample_output"),
    optional_roles=("aggregation", "timestamp_tolerance_sec"),
    row_format="mer_dynamic_valence_arousal_jsonl",
    alignment_key="music_id_frame_time",
    aggregation="micro_or_macro_song_mean_valence_arousal",
    purpose="canonical_dynamic_music_emotion_regression",
)


def evaluate_mer_files(
    *,
    reference_jsonl: str | Path | None = None,
    sample_output: str | Path | None = None,
    metric: str = "rmse",
    granularity: str | None = None,
    aggregation: str = "micro",
    timestamp_tolerance_sec: float = 1e-6,
) -> EvaluationReport:
    normalized_metric = metric.lower().replace("-", "_")
    if not reference_jsonl or not sample_output:
        raise ValueError("MER route requires reference_jsonl and sample_output")
    if normalized_metric not in SUPPORTED_METRICS:
        raise ValueError(f"Unsupported MER metric: {metric}")

    resolved_granularity = (
        granularity
        if granularity is not None
        else ("dynamic" if normalized_metric.startswith("dynamic_") else "static")
    )
    contract = _DYNAMIC_CONTRACT if resolved_granularity == "dynamic" else _STATIC_CONTRACT
    input_files = EvaluationFiles(
        roles={
            "reference_jsonl": str(reference_jsonl),
            "sample_output": str(sample_output),
        }
    )
    contract.validate(input_files)

    bundle, normalization_result = normalize_mer_jsonl(
        reference_jsonl,
        sample_output,
        granularity=resolved_granularity,
        timestamp_tolerance_sec=timestamp_tolerance_sec,
    )
    scoring_result = score_mer_regression(
        bundle,
        metric=normalized_metric,
        aggregation=aggregation,
    )
    components = (
        node_component("normalization/mer_jsonl"),
        node_component("scoring/mer_regression"),
    )
    details = {
        "route": "canonical_mer",
        "evaluation_config": {
            "granularity": resolved_granularity,
            "aggregation": aggregation,
            "timestamp_tolerance_sec": timestamp_tolerance_sec,
        },
        "input_sha256": {role: _sha256_file(path) for role, path in input_files.roles.items()},
        "normalization": bundle.as_dict(),
        "scoring": scoring_result.details,
    }
    pipeline_id = build_atomic_pipeline_id("mer", "any", normalized_metric, components)
    score = scoring_result.details.get("score")
    return EvaluationReport(
        task="MER",
        language="n/a",
        metric=normalized_metric,
        score=None if score is None else float(score),
        pipeline_id=pipeline_id,
        pipeline_trace=(normalization_result, scoring_result),
        input_contract=contract,
        input_files=input_files,
        computation_node_ids=component_trace_ids(components),
        details=details,
    )


def pipeline_id_for_metric(metric: str) -> str:
    normalized = metric.lower().replace("-", "_")
    if normalized not in SUPPORTED_METRICS:
        raise ValueError(f"Unsupported MER metric: {metric}")
    components = (
        node_component("normalization/mer_jsonl"),
        node_component("scoring/mer_regression"),
    )
    return build_atomic_pipeline_id("mer", "any", normalized, components)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

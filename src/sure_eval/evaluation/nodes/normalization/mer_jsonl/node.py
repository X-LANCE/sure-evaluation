"""Normalize strict static and dynamic MER JSONL inputs."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sure_eval.evaluation.core.types import PipelineNodeResult

NODE_ID = "normalization/mer_jsonl"
NODE_VERSION = "v1"
INTERNAL_STAGES = (
    "jsonl_parse",
    "row_contract",
    "finite_value_validation",
    "exact_key_alignment",
    "timestamp_tolerance_validation",
)
VALID_GRANULARITIES = ("static", "dynamic")
DEFAULT_DIMENSIONS = ("valence", "arousal")


@dataclass(frozen=True)
class MERSample:
    music_id: str
    valence: float
    arousal: float
    frame_time: float | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "music_id": self.music_id,
            "valence": self.valence,
            "arousal": self.arousal,
        }
        if self.frame_time is not None:
            payload["frame_time"] = self.frame_time
        return payload


@dataclass(frozen=True)
class MERBundle:
    reference: tuple[MERSample, ...]
    prediction: tuple[MERSample, ...]
    granularity: str
    alignment: str
    dimensions: tuple[str, ...]
    input_summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "granularity": self.granularity,
            "alignment": self.alignment,
            "dimensions": list(self.dimensions),
            "input_summary": dict(self.input_summary),
            "num_reference_rows": len(self.reference),
            "num_prediction_rows": len(self.prediction),
        }


def normalize_mer_jsonl(
    reference_jsonl: str | Path,
    sample_output: str | Path,
    *,
    granularity: str = "static",
    timestamp_tolerance_sec: float = 1e-6,
) -> tuple[MERBundle, PipelineNodeResult]:
    """Parse, validate, sort, and align canonical MER static or dynamic JSONL rows."""

    if granularity not in VALID_GRANULARITIES:
        raise ValueError(f"granularity must be one of {VALID_GRANULARITIES}, got {granularity!r}")
    if not math.isfinite(timestamp_tolerance_sec) or timestamp_tolerance_sec < 0:
        raise ValueError("timestamp_tolerance_sec must be finite and non-negative")

    reference = tuple(_load_samples(reference_jsonl, role="reference", granularity=granularity))
    prediction = tuple(_load_samples(sample_output, role="prediction", granularity=granularity))
    if not reference:
        raise ValueError("reference_jsonl must contain at least one row")
    if not prediction:
        raise ValueError("sample_output must contain at least one row")

    if len(reference) != len(prediction):
        raise ValueError(
            f"reference and prediction row count mismatch: {len(reference)} vs {len(prediction)}"
        )

    if granularity == "static":
        ref_ids = [row.music_id for row in reference]
        pred_ids = [row.music_id for row in prediction]
        if ref_ids != pred_ids:
            raise ValueError("reference and prediction rows must have identical music_id keys")
        alignment = "exact_music_id"
    else:
        for ref, pred in zip(reference, prediction):
            if ref.music_id != pred.music_id:
                raise ValueError(
                    f"music_id mismatch during dynamic alignment: {ref.music_id!r} vs {pred.music_id!r}"
                )
            assert ref.frame_time is not None and pred.frame_time is not None
            if abs(ref.frame_time - pred.frame_time) > timestamp_tolerance_sec:
                raise ValueError(
                    f"frame_time mismatch for {ref.music_id}: {ref.frame_time} vs {pred.frame_time}"
                )
        alignment = "exact_music_id_and_frame_time"

    songs = sorted({row.music_id for row in reference})
    summary: dict[str, Any] = {
        "granularity": granularity,
        "num_songs": len(songs),
        "song_ids": songs,
        "num_rows": len(reference),
        "dimensions": list(DEFAULT_DIMENSIONS),
        "input_order": (
            "normalized_by_music_id"
            if granularity == "static"
            else "normalized_by_music_id_then_frame_time"
        ),
    }
    if granularity == "dynamic":
        summary["timestamp_tolerance_sec"] = timestamp_tolerance_sec

    bundle = MERBundle(
        reference=reference,
        prediction=prediction,
        granularity=granularity,
        alignment=alignment,
        dimensions=DEFAULT_DIMENSIONS,
        input_summary=summary,
    )
    result = PipelineNodeResult(
        stage="normalization",
        node_id=NODE_ID,
        version=NODE_VERSION,
        details={
            "backend": "canonical_mer_jsonl",
            "granularity": granularity,
            "alignment": alignment,
            "input_summary": summary,
        },
    )
    return bundle, result


def _load_samples(path: str | Path, *, role: str, granularity: str) -> list[MERSample]:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"{role} JSONL file not found: {file_path}")
    samples: list[MERSample] = []
    seen_keys: set[tuple[str, float | None]] = set()
    for line_no, raw_line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{role} line {line_no}: invalid JSON ({exc})") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{role} line {line_no}: row must be a JSON object")

        raw_id = payload.get("music_id", payload.get("musicId"))
        if raw_id is None or isinstance(raw_id, bool) or not str(raw_id).strip():
            raise ValueError(f"{role} line {line_no}: non-empty music_id is required")
        music_id = str(raw_id).strip()

        valence = _parse_finite_float(payload.get("valence"), field="valence", role=role, line_no=line_no)
        arousal = _parse_finite_float(payload.get("arousal"), field="arousal", role=role, line_no=line_no)

        frame_time: float | None = None
        if granularity == "dynamic":
            raw_time = payload.get("frame_time", payload.get("frameTime"))
            frame_time = _parse_finite_float(raw_time, field="frame_time", role=role, line_no=line_no)
            if frame_time < 0:
                raise ValueError(f"{role} line {line_no}: frame_time must be non-negative")
        else:
            if "frame_time" in payload or "frameTime" in payload:
                raise ValueError(
                    f"{role} line {line_no}: static MER rows must not include frame_time; "
                    "use a dynamic_* route for time-series evaluation"
                )

        dedup_key = (music_id, frame_time)
        if dedup_key in seen_keys:
            raise ValueError(f"{role} line {line_no}: duplicate key {dedup_key!r}")
        seen_keys.add(dedup_key)
        samples.append(
            MERSample(
                music_id=music_id,
                valence=valence,
                arousal=arousal,
                frame_time=frame_time,
            )
        )

    if granularity == "static":
        samples.sort(key=lambda item: item.music_id)
    else:
        samples.sort(key=lambda item: (item.music_id, item.frame_time if item.frame_time is not None else 0.0))
    return samples


def _parse_finite_float(value: Any, *, field: str, role: str, line_no: int) -> float:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{role} line {line_no}: {field} must be a finite number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{role} line {line_no}: {field} must be a finite number")
    return numeric

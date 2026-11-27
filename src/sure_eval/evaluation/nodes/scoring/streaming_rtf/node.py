"""Streaming ASR real-time-factor scoring.

RTF is a performance metric, not a quality metric: the numerator is model
compute time and the denominator is audio duration. Three views are reported
because a single average cannot answer "will it keep up":

    rtf_avg        sum(compute) / sum(audio)   -- comparable, throughput view
    rtf_utt_p99    99th pct of per-utterance RTF -- tail behaviour
    rtf_chunk_p99  99th pct of per-chunk RTF   -- the real real-time criterion

`rtf_avg` is intentionally weighted, never `mean(per_utterance)`: short
utterances carry a fixed per-stream cost and would be over-weighted.
"""

from __future__ import annotations

from typing import Any

from sure_eval.evaluation.core.types import PipelineNodeResult
from sure_eval.evaluation.nodes.scoring.streaming_rtf._contract import (
    TimingBundle,
    TimingRow,
    load_timing,
)

NODE_ID = "scoring/streaming_rtf"
NODE_VERSION = "v1"
INTERNAL_STAGES = ("jsonl_parse", "protocol_check", "aggregate", "percentile", "bucket_summary")

BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 2.0, "0-2s"),
    (2.0, 5.0, "2-5s"),
    (5.0, 10.0, "5-10s"),
    (10.0, float("inf"), ">=10s"),
)


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated percentile over an already sorted list."""
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def _bucket_of(seconds: float) -> str:
    for lo, hi, name in BUCKETS:
        if lo <= seconds < hi:
            return name
    return BUCKETS[-1][2]


def compute_rtf_metrics(bundle: TimingBundle) -> dict[str, Any]:
    """Compute the three RTF views plus per-length buckets."""
    rows: tuple[TimingRow, ...] = bundle.rows

    total_compute = sum(r.total_compute_s for r in rows)
    total_audio = sum(r.audio_seconds for r in rows)
    if total_audio <= 0:
        raise ValueError("total audio duration is zero; refusing to report an RTF")

    per_utt = sorted(r.rtf for r in rows)

    per_chunk: list[float] = []
    for r in rows:
        per_chunk.extend(r.chunk_rtf)
    per_chunk.sort()

    buckets: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = _bucket_of(r.audio_seconds)
        slot = buckets.setdefault(name, {"n_utt": 0, "compute_s": 0.0, "audio_s": 0.0})
        slot["n_utt"] += 1
        slot["compute_s"] += r.total_compute_s
        slot["audio_s"] += r.audio_seconds

    bucket_summary = {
        name: {
            "n_utt": slot["n_utt"],
            "audio_s": round(slot["audio_s"], 3),
            "rtf_avg": round(slot["compute_s"] / slot["audio_s"], 6),
        }
        for name, slot in buckets.items()
        if slot["audio_s"] > 0
    }

    rtf_avg = total_compute / total_audio
    return {
        "score": rtf_avg,
        "rtf": round(rtf_avg, 6),
        "rtf_avg": round(rtf_avg, 6),
        "rtf_utt_p50": round(percentile(per_utt, 50), 6),
        "rtf_utt_p99": round(percentile(per_utt, 99), 6),
        "rtf_utt_max": round(per_utt[-1], 6),
        "rtf_chunk_p50": round(percentile(per_chunk, 50), 6),
        "rtf_chunk_p99": round(percentile(per_chunk, 99), 6),
        "rtf_chunk_max": round(per_chunk[-1], 6) if per_chunk else None,
        "realtime_ok": bool(per_chunk and percentile(per_chunk, 99) < 1.0),
        "n_utt": len(rows),
        "n_chunks": len(per_chunk),
        "audio_seconds": round(total_audio, 3),
        "audio_hours": round(total_audio / 3600.0, 4),
        "compute_seconds": round(total_compute, 3),
        "compute_hours": round(total_compute / 3600.0, 4),
        "buckets": bucket_summary,
        "measurement_protocol": bundle.protocol,
    }


def score_streaming_rtf(bundle: TimingBundle) -> tuple[TimingBundle, PipelineNodeResult]:
    """Framework entry point: score one timing sidecar."""
    metrics = compute_rtf_metrics(bundle)
    return (
        bundle,
        PipelineNodeResult(
            stage="scoring",
            node_id=NODE_ID,
            version=NODE_VERSION,
            details={"metric": "rtf", "result": metrics},
            internal_stages=INTERNAL_STAGES,
        ),
    )


def score_streaming_rtf_file(path: str) -> tuple[TimingBundle, PipelineNodeResult]:
    """Convenience entry point for a sidecar path (used by tests and CLI)."""
    return score_streaming_rtf(load_timing(path))

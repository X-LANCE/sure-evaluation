from __future__ import annotations

import json
from pathlib import Path

import pytest

from sure_eval.evaluation.nodes.scoring.streaming_rtf import (
    ContractError,
    compute_rtf_metrics,
    load_timing,
    percentile,
    score_streaming_rtf,
)


def _row(
    key: str = "utt1",
    *,
    audio_s: float = 4.0,
    chunk_ms: int = 960,
    chunks: tuple[float, ...] = (0.05, 0.05, 0.05, 0.05),
    t_accept: float = 0.01,
    t_decode: float | None = None,
    total: float | None = None,
    schema_version: int = 1,
    warm: bool = True,
    num_threads: int = 1,
) -> dict:
    decode = sum(chunks) if t_decode is None else t_decode
    computed = round(t_accept + decode, 6) if total is None else total
    return {
        "key": key,
        "schema_version": schema_version,
        "audio_samples": int(audio_s * 16000),
        "chunk_ms_model": chunk_ms,
        "feed_ms": 100,
        "num_threads": num_threads,
        "t_accept_s": t_accept,
        "t_decode_s": decode,
        "total_compute_s": computed,
        "num_encoder_chunks": len(chunks),
        "chunk_compute_s": list(chunks),
        "warm": warm,
        "tail_padding_s": 1.5,
    }


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "timing.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_rtf_is_duration_weighted_not_utterance_mean(tmp_path: Path) -> None:
    """一句 1 秒慢句 + 一句 9 秒快句：加权应接近快句，算术平均会被慢句拉高。"""
    short = _row("short", audio_s=1.0, chunks=(0.3,), t_accept=0.0, t_decode=0.3)
    long = _row("long", audio_s=9.0, chunks=(0.01,) * 9, t_accept=0.0, t_decode=0.09)

    bundle = load_timing(_write(tmp_path, [short, long]))
    metrics = compute_rtf_metrics(bundle)

    weighted = (0.3 + 0.09) / (1.0 + 9.0)
    assert metrics["rtf_avg"] == pytest.approx(weighted, rel=1e-6)
    arithmetic = (0.3 / 1.0 + 0.09 / 9.0) / 2
    assert metrics["rtf_avg"] < arithmetic


def test_reports_three_distinct_metrics(tmp_path: Path) -> None:
    rows = [
        _row("a", audio_s=4.0, chunks=(0.05,) * 4),
        _row("b", audio_s=4.0, chunks=(0.08,) * 4),
        _row("c", audio_s=4.0, chunks=(0.2,) * 4),
    ]
    bundle = load_timing(_write(tmp_path, rows))
    metrics = compute_rtf_metrics(bundle)

    assert metrics["rtf_avg"] == pytest.approx((0.21 + 0.33 + 0.81) / 12.0, rel=1e-6)
    assert metrics["n_utt"] == 3
    assert metrics["rtf_utt_p99"] >= metrics["rtf_avg"]
    assert metrics["rtf_chunk_p99"] >= metrics["rtf_avg"]
    assert metrics["realtime_ok"] is True


def test_realtime_not_ok_when_chunk_exceeds_budget(tmp_path: Path) -> None:
    """单块耗时超过 chunk 预算时必须判为不实时。"""
    slow = _row("slow", audio_s=8.0, chunks=(1.5,) * 2, t_accept=0.0, t_decode=3.0)
    bundle = load_timing(_write(tmp_path, [slow]))
    metrics = compute_rtf_metrics(bundle)

    assert metrics["rtf_chunk_p99"] > 1.0
    assert metrics["realtime_ok"] is False


def test_rejects_missing_required_field(tmp_path: Path) -> None:
    bad = _row()
    del bad["audio_samples"]
    with pytest.raises(ContractError, match="audio_samples"):
        load_timing(_write(tmp_path, [bad]))


def test_rejects_bad_schema_version(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="schema_version"):
        load_timing(_write(tmp_path, [_row(schema_version=2)]))


def test_accepts_chunk_size_outside_the_reference_model(tmp_path: Path) -> None:
    """chunk size is model-specific: only the range is validated, not a fixed set."""
    bundle = load_timing(_write(tmp_path, [_row(chunk_ms=320)]))
    assert bundle.rows[0].chunk_ms_model == 320


@pytest.mark.parametrize("bad", [0, -1, 10001])
def test_rejects_out_of_range_chunk_size(tmp_path: Path, bad: int) -> None:
    with pytest.raises(ContractError, match="chunk_ms_model"):
        load_timing(_write(tmp_path, [_row(chunk_ms=bad)]))


def test_rejects_component_sum_mismatch(tmp_path: Path) -> None:
    """total 与 accept+decode 不一致时应拒绝，防止计时被篡改。"""
    bad = _row(total=999.0)
    with pytest.raises(ContractError, match="total_compute_s must equal"):
        load_timing(_write(tmp_path, [bad]))


def test_rejects_chunk_count_mismatch(tmp_path: Path) -> None:
    bad = _row()
    bad["num_encoder_chunks"] = 99
    with pytest.raises(ContractError, match="num_encoder_chunks"):
        load_timing(_write(tmp_path, [bad]))


def test_rejects_duplicate_keys(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="duplicate key"):
        load_timing(_write(tmp_path, [_row("dup"), _row("dup")]))


def test_rejects_negative_timing(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="non-negative"):
        load_timing(_write(tmp_path, [_row(t_accept=-0.1, total=0.1)]))


def test_rejects_invalid_json_line(tmp_path: Path) -> None:
    path = tmp_path / "timing.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ContractError, match="invalid JSON"):
        load_timing(path)


def test_rejects_empty_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "timing.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ContractError):
        load_timing(path)


def test_buckets_cover_all_durations(tmp_path: Path) -> None:
    rows = [
        _row("b0", audio_s=1.0, chunks=(0.05,), t_accept=0.0, t_decode=0.05),
        _row("b1", audio_s=3.0, chunks=(0.05,) * 3, t_accept=0.0, t_decode=0.15),
        _row("b2", audio_s=7.0, chunks=(0.05,) * 7, t_accept=0.0, t_decode=0.35),
        _row("b3", audio_s=12.0, chunks=(0.05,) * 12, t_accept=0.0, t_decode=0.6),
    ]
    bundle = load_timing(_write(tmp_path, rows))
    metrics = compute_rtf_metrics(bundle)

    buckets = metrics["buckets"]
    assert set(buckets) == {"0-2s", "2-5s", "5-10s", ">=10s"}
    assert sum(b["n_utt"] for b in buckets.values()) == 4
    assert sum(b["audio_s"] for b in buckets.values()) == pytest.approx(23.0)


def test_score_streaming_rtf_returns_contract_valid_result(tmp_path: Path) -> None:
    bundle = load_timing(_write(tmp_path, [_row()]))
    _, result = score_streaming_rtf(bundle)

    assert result.details["result"]["rtf_avg"] == pytest.approx(0.21 / 4.0, rel=1e-6)
    assert result.details["metric"] == "rtf"


@pytest.mark.parametrize(
    ("values", "q", "expected"),
    [
        ([1.0], 99, 1.0),
        ([1.0, 2.0, 3.0], 0, 1.0),
        ([1.0, 2.0, 3.0], 100, 3.0),
        ([0.0, 1.0], 50, 0.5),
    ],
)
def test_percentile_boundaries(values: list[float], q: float, expected: float) -> None:
    assert percentile(values, q) == pytest.approx(expected)

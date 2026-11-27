"""Input contract for the streaming-RTF timing sidecar.

The sidecar is produced by the model wrapper, one JSON object per utterance.
Every field that the score depends on is validated here, so a malformed or
partially-written run can never be scored as a clean number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MIN_CHUNK_MS = 1
MAX_CHUNK_MS = 10000
SAMPLE_RATE = 16000
SUM_TOLERANCE = 1e-5


class ContractError(ValueError):
    """Raised when the timing sidecar violates the input contract."""


@dataclass(frozen=True)
class TimingRow:
    key: str
    audio_samples: int
    audio_seconds: float
    chunk_ms_model: int
    feed_ms: int
    num_threads: int
    t_accept_s: float
    t_decode_s: float
    total_compute_s: float
    chunk_compute_s: tuple[float, ...]
    warm: bool
    tail_padding_s: float

    @property
    def rtf(self) -> float:
        return self.total_compute_s / self.audio_seconds

    @property
    def chunk_rtf(self) -> list[float]:
        chunk_audio = self.chunk_ms_model / 1000.0
        return [c / chunk_audio for c in self.chunk_compute_s]


@dataclass(frozen=True)
class TimingBundle:
    rows: tuple[TimingRow, ...]
    protocol: dict[str, Any]

    @property
    def n_utt(self) -> int:
        return len(self.rows)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ContractError(msg)


def _num(row: dict[str, Any], field: str, key: str) -> float:
    val = row.get(field)
    _require(isinstance(val, (int, float)) and not isinstance(val, bool),
             f"{key}: field {field!r} must be a number, got {type(val).__name__}")
    _require(val == val and val not in (float("inf"), float("-inf")),
             f"{key}: field {field!r} must be finite")
    return float(val)


def parse_row(raw: dict[str, Any], line_no: int) -> TimingRow:
    key = raw.get("key")
    _require(isinstance(key, str) and key != "", f"line {line_no}: 'key' must be a non-empty string")

    _require(raw.get("schema_version") == SCHEMA_VERSION,
             f"{key}: schema_version must be {SCHEMA_VERSION}")

    audio_samples = raw.get("audio_samples")
    _require(isinstance(audio_samples, int) and audio_samples > 0,
             f"{key}: audio_samples must be a positive integer")

    chunk_ms = raw.get("chunk_ms_model")
    _require(isinstance(chunk_ms, int) and not isinstance(chunk_ms, bool)
             and MIN_CHUNK_MS <= chunk_ms <= MAX_CHUNK_MS,
             f"{key}: chunk_ms_model must be an integer in "
             f"[{MIN_CHUNK_MS}, {MAX_CHUNK_MS}], got {chunk_ms!r}")

    t_accept = _num(raw, "t_accept_s", key)
    t_decode = _num(raw, "t_decode_s", key)
    total = _num(raw, "total_compute_s", key)
    _require(t_accept >= 0 and t_decode >= 0,
             f"{key}: timings must be non-negative")
    _require(abs((t_accept + t_decode) - total) <= SUM_TOLERANCE,
             f"{key}: total_compute_s must equal t_accept_s + t_decode_s "
             f"(got {total}, parts sum to {t_accept + t_decode})")

    chunks = raw.get("chunk_compute_s")
    _require(isinstance(chunks, list) and chunks, f"{key}: chunk_compute_s must be a non-empty list")
    n_chunks = raw.get("num_encoder_chunks")
    _require(n_chunks == len(chunks),
             f"{key}: num_encoder_chunks ({n_chunks}) != len(chunk_compute_s) ({len(chunks)})")
    for i, c in enumerate(chunks):
        _require(isinstance(c, (int, float)) and not isinstance(c, bool) and c >= 0,
                 f"{key}: chunk_compute_s[{i}] must be a non-negative number")

    audio_seconds = audio_samples / SAMPLE_RATE
    warm = raw.get("warm")
    _require(isinstance(warm, bool), f"{key}: 'warm' must be a boolean")

    return TimingRow(
        key=key,
        audio_samples=audio_samples,
        audio_seconds=audio_seconds,
        chunk_ms_model=int(chunk_ms),
        feed_ms=int(raw.get("feed_ms", 0) or 0),
        num_threads=int(raw.get("num_threads", 0) or 0),
        t_accept_s=t_accept,
        t_decode_s=t_decode,
        total_compute_s=total,
        chunk_compute_s=tuple(float(c) for c in chunks),
        warm=warm,
        tail_padding_s=float(raw.get("tail_padding_s", 0.0) or 0.0),
    )


def load_timing(path: str | Path) -> TimingBundle:
    p = Path(path)
    _require(p.is_file(), f"timing sidecar not found: {p}")

    rows: list[TimingRow] = []
    seen: set[str] = set()
    with p.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ContractError(f"line {line_no}: invalid JSON ({exc})") from exc
            _require(isinstance(raw, dict), f"line {line_no}: expected a JSON object")
            row = parse_row(raw, line_no)
            _require(row.key not in seen, f"duplicate key {row.key!r} at line {line_no}")
            seen.add(row.key)
            rows.append(row)

    _require(rows, f"timing sidecar {p} contains no rows")

    chunk_sizes = {r.chunk_ms_model for r in rows}
    _require(len(chunk_sizes) == 1,
             f"timing sidecar mixes chunk sizes {sorted(chunk_sizes)}; one run must use one chunk size")

    protocols = {
        "chunk_ms_model": rows[0].chunk_ms_model,
        "feed_ms": rows[0].feed_ms,
        "num_threads": rows[0].num_threads,
        "sample_rate": SAMPLE_RATE,
        "tail_padding_s": round(rows[0].tail_padding_s, 3),
        "warm_start": all(r.warm for r in rows),
        "n_utt": len(rows),
        "n_cold_rows": sum(0 if r.warm else 1 for r in rows),
    }

    for field in ("feed_ms", "num_threads"):
        vals = {getattr(r, field) for r in rows}
        _require(len(vals) == 1,
                 f"timing sidecar mixes {field} values {sorted(vals)}; protocol must be constant")

    return TimingBundle(rows=tuple(rows), protocol=protocols)

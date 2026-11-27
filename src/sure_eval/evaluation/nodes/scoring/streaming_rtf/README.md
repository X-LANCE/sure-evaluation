# streaming_rtf

Scores streaming ASR real-time factor from a timing sidecar produced by the
model wrapper. This node does **not** load a model, run inference, or read
audio: it consumes recorded timings and audio sample counts, so scoring the
same sidecar twice is deterministic.

## Why three numbers

A single average RTF cannot answer "will this model keep up". The node reports:

| Field | Definition | Use |
|---|---|---|
| `rtf_avg` | `sum(total_compute_s) / sum(audio_seconds)` | comparable across systems; throughput view |
| `rtf_utt_p99` | 99th percentile of `total_compute_s / audio_seconds` | tail behaviour per utterance |
| `rtf_chunk_p99` | 99th percentile of `chunk_compute_s / (chunk_ms_model/1000)` | **the real-time criterion** |

`rtf_avg` is deliberately weighted, not `mean(per_utterance_rtf)`. Every
utterance pays a fixed per-stream cost (stream construction, first-chunk
warm-up, tail padding), so short utterances have systematically higher RTF and
would be over-weighted by an arithmetic mean. Measured on LibriSpeech
test-clean at 960 ms chunk: `0-2s` utterances score 0.204 while `>=10s`
utterances score 0.136.

`rtf_chunk_p99 < 1.0` is the criterion for keeping up: a front end delivers
audio on a fixed cadence, so a single chunk that takes longer than its own
audio duration causes a backlog even when the average is far below 1.0. The
node exposes `realtime_ok` as a boolean convenience flag, never as a substitute
for the value.

## Input contract

`input_schema: rtf_timing_jsonl` — one JSON object per utterance, UTF-8,
newline-delimited. Required fields:

| Field | Type | Constraint |
|---|---|---|
| `key` | string | non-empty, unique per file |
| `schema_version` | int | must be `1` |
| `audio_samples` | int | `> 0`; denominator is `audio_samples / 16000` |
| `chunk_ms_model` | int | one of `160, 480, 960, 1920` |
| `t_accept_s` | number | `>= 0`, finite |
| `t_decode_s` | number | `>= 0`, finite |
| `total_compute_s` | number | must equal `t_accept_s + t_decode_s` (tol `1e-5`) |
| `chunk_compute_s` | number[] | non-empty, each `>= 0` |
| `num_encoder_chunks` | int | must equal `len(chunk_compute_s)` |
| `warm` | bool | `true` for a warm-start measurement |
| `feed_ms` | int | constant across the file |
| `num_threads` | int | constant across the file |
| `tail_padding_s` | number | recorded for provenance |

Optional but recommended: `provider`.

Rejection rules exist so a partial or mixed run cannot be scored as a clean
number:

- a file mixing chunk sizes, `feed_ms`, or `num_threads` is rejected — such a
  run has no single measurement protocol and its RTF is not comparable;
- `total_compute_s` disagreeing with its parts is rejected — that indicates a
  wrapper bug or a truncated write;
- duplicate keys are rejected;
- an empty file is rejected.

## Measurement protocol

The sidecar records what the score depends on. Fields surfaced in
`details.result.measurement_protocol`:

`chunk_ms_model`, `feed_ms`, `num_threads`, `sample_rate`, `tail_padding_s`,
`warm_start`, `n_utt`, `n_cold_rows`.

Two scores are only comparable when their `measurement_protocol` matches. In
particular:

- **Numerator boundary.** Only `accept_waveform` (which includes fbank) and
  `decode_stream` are timed. File I/O, audio decoding, logging, and model load
  are outside. Feature extraction is inside because it cannot be separated and
  is a real deployment cost.
- **Tail padding.** The trailing silence fed to flush the last encoder chunk is
  counted in the numerator and excluded from the denominator. It must exceed
  one model chunk, otherwise the final partial chunk never becomes ready and
  the transcript is truncated (measured: 0.66 s truncates a 960 ms model;
  `chunk + 0.3` is the threshold).
- **Warm start.** `load()` performs a discarded warm-up so onnxruntime graph
  init never lands in a scored row. Cold-start cost is a separate number.
- **Contention.** Any concurrent heavy task on the measurement host invalidates
  the run. Measured effect of a concurrent 565 MB download plus antivirus scan:
  RTF 0.242 early versus 0.096 late on identical-duration subsets. A run is
  accepted only when the segment drift stays within a few percent.

## Buckets

`details.result.buckets` reports `rtf_avg` per utterance-length bucket
(`0-2s`, `2-5s`, `5-10s`, `>=10s`). This is what makes the weighted-average
choice auditable rather than asserted.

## Scope limits

- CPU numbers are not portable across machines; the report must name the CPU
  model and thread count.
- This node scores timings, not correctness. A fast RTF with a broken decoder
  is still a broken system, so RTF must always be reported alongside WER on the
  same predictions.

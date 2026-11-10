"""Natural-speech no-reference SCOREQ predictions."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any


class SCOREQProvider:
    """Run the released natural-speech no-reference SCOREQ ONNX model."""

    def __init__(self, *, checkpoint: str | None = None, device: str = "cpu") -> None:
        self.checkpoint = checkpoint or os.environ.get("SURE_SE_SCOREQ_CHECKPOINT") or str(
            Path(__file__).resolve().parent / "scoreq" / "checkpoints" / "adapt_nr_telephone.onnx"
        )
        self.device = device
        self._session: Any | None = None
        self._scores: dict[str, float] = {}

    def _load_session(self) -> Any:
        if self._session is None:
            if not Path(self.checkpoint).is_file():
                raise RuntimeError(
                    "SCOREQ requires adapt_nr_telephone.onnx at the declared node "
                    "checkpoint path or SURE_SE_SCOREQ_CHECKPOINT pointing to it"
                )
            import onnxruntime as ort

            providers = ["CPUExecutionProvider"]
            if self.device.startswith("cuda") and "CUDAExecutionProvider" in ort.get_available_providers():
                providers.insert(0, "CUDAExecutionProvider")
            self._session = ort.InferenceSession(self.checkpoint, providers=providers)
        return self._session

    @staticmethod
    def _load_audio(path: str):
        import torch
        import torchaudio

        waveform, rate = torchaudio.load(path)
        waveform = waveform.mean(dim=0, keepdim=True)
        if rate != 16000:
            waveform = torchaudio.functional.resample(waveform, rate, 16000)
        if waveform.shape[1] == 0:
            raise ValueError(f"SCOREQ requires non-empty audio: {path}")
        multiple = 320
        padded = ((waveform.shape[1] + multiple - 1) // multiple) * multiple
        if padded > waveform.shape[1]:
            waveform = torch.nn.functional.pad(waveform, (0, padded - waveform.shape[1]))
        return waveform.numpy()

    def __call__(self, prediction: str, reference: str = "", **kwargs: Any) -> dict[str, Any]:
        if prediction not in self._scores:
            input_name = self._load_session().get_inputs()[0].name
            raw_score = self._load_session().run(None, {input_name: self._load_audio(prediction)})[0]
            score = float(raw_score.reshape(-1)[0])
            if not math.isfinite(score):
                raise ValueError("SCOREQ returned a non-finite prediction")
            self._scores[prediction] = score
        return {"scoreq": self._scores[prediction], "backend": "scoreq-natural-nr"}

    def score_batch(self, rows: list[tuple[str, str]], *, metric_name: str) -> list[dict[str, Any]]:
        return [self(prediction) for _sample_id, prediction in rows]

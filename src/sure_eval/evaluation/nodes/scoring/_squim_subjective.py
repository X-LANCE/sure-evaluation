"""TorchAudio SQUIM subjective MOS predictions."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any


class SQUIMSubjectiveProvider:
    """Predict MOS with SQUIM Subjective and a fixed non-matching reference.

    SQUIM Subjective is not a reference-free model: its second input is a
    clean utterance that need not be the source of the evaluated waveform.
    The reference is staged separately so this metric does not silently use a
    paired clean reference as though it were a no-reference score.
    """

    def __init__(
        self,
        *,
        checkpoint: str | None = None,
        non_matching_reference: str | None = None,
        device: str = "cpu",
    ) -> None:
        self.checkpoint = checkpoint or os.environ.get("SURE_SE_SQUIM_SUBJECTIVE_CKPT")
        self.non_matching_reference = non_matching_reference or os.environ.get(
            "SURE_SE_SQUIM_SUBJECTIVE_NMR"
        )
        self.device = device
        self._model: Any | None = None
        self._reference: Any | None = None
        self._scores: dict[str, float] = {}

    def _load_model(self) -> Any:
        if self._model is None:
            if not self.checkpoint or not Path(self.checkpoint).is_file():
                raise RuntimeError(
                    "SQUIM subjective requires SURE_SE_SQUIM_SUBJECTIVE_CKPT "
                    "pointing to squim_subjective_bvcc_daps.pth"
                )
            import torch
            from torchaudio.models import squim_subjective_base

            model = squim_subjective_base()
            state = torch.load(self.checkpoint, map_location="cpu")
            model.load_state_dict(state, strict=True)
            self._model = model.to(self.device).eval()
        return self._model

    def _load_audio(self, path: str):
        import torch
        import torchaudio

        waveform, rate = torchaudio.load(path)
        waveform = waveform.mean(dim=0)
        if rate != 16000:
            waveform = torchaudio.functional.resample(waveform, rate, 16000)
        if waveform.numel() == 0:
            raise ValueError(f"SQUIM subjective requires non-empty audio: {path}")
        return waveform.to(self.device, dtype=torch.float32)

    def _load_reference(self):
        if self._reference is None:
            if not self.non_matching_reference or not Path(self.non_matching_reference).is_file():
                raise RuntimeError(
                    "SQUIM subjective requires SURE_SE_SQUIM_SUBJECTIVE_NMR "
                    "pointing to a staged clean non-matching reference WAV"
                )
            self._reference = self._load_audio(self.non_matching_reference)
        return self._reference

    def __call__(self, prediction: str, reference: str = "", **kwargs: Any) -> dict[str, Any]:
        if prediction not in self._scores:
            import torch

            waveform = self._load_audio(prediction).unsqueeze(0)
            nmr = self._load_reference().unsqueeze(0)
            with torch.inference_mode():
                raw_score = self._load_model()(waveform, nmr)
            score = float(raw_score.detach().cpu().reshape(-1)[0])
            if not math.isfinite(score):
                raise ValueError("SQUIM subjective returned a non-finite prediction")
            self._scores[prediction] = score
        return {
            "squim_mos": self._scores[prediction],
            "backend": "torchaudio-squim-subjective-bvcc-daps",
        }

    def score_batch(self, rows: list[tuple[str, str]], *, metric_name: str) -> list[dict[str, Any]]:
        return [self(prediction) for _sample_id, prediction in rows]

"""SQ-AST non-intrusive speech-quality predictions."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any


_DIMENSIONS = ("mos", "noi", "dis", "col", "loud")
_DB_MEAN = -10.25446422
_DB_STD = 4.205750774
_TARGET_SAMPLE_RATE = 48_000


class SQASTProvider:
    """Predict SQ-AST overall and perceptual dimensions from audio alone.

    The five heads share the AST feature-extraction contract used by the
    official implementation. Scores are sigmoid outputs mapped to the 1--5
    ACR-like scale and cached by input path.
    """

    def __init__(
        self,
        *,
        dimensions: tuple[str, ...] = _DIMENSIONS,
        weights_dir: str | None = None,
        base_model_dir: str | None = None,
        device: str = "cpu",
    ) -> None:
        if not dimensions or any(dimension not in _DIMENSIONS for dimension in dimensions):
            raise ValueError(f"SQ-AST dimensions must be a non-empty subset of {_DIMENSIONS}")
        self.dimensions = tuple(dict.fromkeys(dimensions))
        anchor = self.dimensions[0]
        node_root = Path(__file__).resolve().parent / f"sq_ast_{anchor}" / "checkpoints"
        self._explicit_weights_dir = weights_dir or os.environ.get("SURE_SE_SQ_AST_WEIGHTS_DIR")
        self.weights_dir = Path(
            self._explicit_weights_dir or node_root / "weights"
        )
        self.base_model_dir = Path(
            base_model_dir
            or os.environ.get("SURE_SE_SQ_AST_BASE_MODEL_DIR")
            or node_root / "ast-base"
        )
        self.device = device
        self._extractor: Any | None = None
        self._models: dict[str, Any] = {}
        self._scores: dict[str, dict[str, float | str]] = {}

    def _weight_path(self, dimension: str) -> Path:
        env_name = f"SURE_SE_SQ_AST_{dimension.upper()}_CKPT"
        declared_default = (
            Path(__file__).resolve().parent
            / f"sq_ast_{dimension}"
            / "checkpoints"
            / "weights"
            / f"{dimension}.pth"
        )
        fallback = (
            self.weights_dir / f"{dimension}.pth"
            if self._explicit_weights_dir
            else declared_default
        )
        return Path(os.environ.get(env_name, str(fallback)))

    def _load_models(self) -> tuple[Any, dict[str, Any]]:
        if self._extractor is not None and len(self._models) == len(self.dimensions):
            return self._extractor, self._models
        if not self.base_model_dir.is_dir():
            raise RuntimeError(
                "SQ-AST requires SURE_SE_SQ_AST_BASE_MODEL_DIR pointing to the "
                "offline MIT/ast-finetuned-audioset-10-10-0.4593 snapshot"
            )
        import torch
        from transformers import ASTFeatureExtractor, ASTModel

        if self.device.startswith("cuda") and not torch.cuda.is_available():
            self.device = "cpu"

        extractor = ASTFeatureExtractor.from_pretrained(str(self.base_model_dir))
        extractor.sampling_rate = _TARGET_SAMPLE_RATE
        extractor.max_length = 1024
        extractor.num_mel_bins = 128
        extractor.return_attention_mask = True
        extractor.mean = _DB_MEAN
        extractor.std = _DB_STD
        models: dict[str, Any] = {}
        for dimension in self.dimensions:
            checkpoint = self._weight_path(dimension)
            if not checkpoint.is_file():
                raise RuntimeError(
                    f"SQ-AST requires {checkpoint} for the {dimension} dimension"
                )
            model = torch.nn.Module()
            model.ast = ASTModel.from_pretrained(str(self.base_model_dir))
            model.fc = torch.nn.Sequential(torch.nn.Linear(768, 1), torch.nn.Sigmoid())

            def forward(features, _model=model):
                hidden = _model.ast(features).pooler_output
                return _model.fc(hidden).squeeze()

            model.forward = forward
            state = torch.load(checkpoint, map_location="cpu", weights_only=True)
            model.load_state_dict(state, strict=True)
            models[dimension] = model.to(self.device).eval()
        self._extractor = extractor
        self._models = models
        return extractor, models

    @staticmethod
    def _load_waveform(path: str):
        import torchaudio

        waveform, rate = torchaudio.load(path)
        waveform = waveform.mean(dim=0)
        if rate != _TARGET_SAMPLE_RATE:
            waveform = torchaudio.functional.resample(waveform, rate, _TARGET_SAMPLE_RATE)
        if waveform.numel() == 0:
            raise ValueError(f"SQ-AST requires non-empty audio: {path}")
        return waveform

    def _score_one(self, path: str) -> dict[str, float | str]:
        import torch

        extractor, models = self._load_models()
        waveform = self._load_waveform(path)
        features = extractor(
            waveform,
            sampling_rate=_TARGET_SAMPLE_RATE,
            return_attention_mask=True,
            return_tensors="pt",
        )["input_values"].to(self.device)
        values: dict[str, float | str] = {"backend": "sq-ast-improved-weights"}
        with torch.inference_mode():
            for dimension in self.dimensions:
                raw = models[dimension](features).reshape(-1)[0]
                score = float(raw.detach().cpu()) * 4.0 + 1.0
                if not math.isfinite(score):
                    raise ValueError(f"SQ-AST returned a non-finite {dimension} score")
                values[f"sq_ast_{dimension}"] = score
        return values

    def __call__(self, prediction: str, reference: str = "", **kwargs: Any) -> dict[str, Any]:
        if prediction not in self._scores:
            self._scores[prediction] = self._score_one(prediction)
        return dict(self._scores[prediction])

    def score_batch(self, rows: list[tuple[str, str]], *, metric_name: str) -> list[dict[str, Any]]:
        return [self(prediction) for _sample_id, prediction in rows]

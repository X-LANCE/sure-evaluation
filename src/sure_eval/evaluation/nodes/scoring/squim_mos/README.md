# SQUIM Subjective MOS Prediction Node

## Purpose

Predict subjective MOS with TorchAudio SQUIM Subjective. The model takes the
evaluated waveform and a clean **non-matching** reference waveform. The second
waveform is staged separately and is not the paired clean reference from the
sample manifest.

## Task Scenarios

- Optional SE metric `squim_mos`, outside the default bundle.
- Exact pipeline: `se.any.squim_mos.squim_mos_v1`.

## Input and Output

- Input schema: `enhanced_audio_rows`; required `enhanced_audio`.
- Output: predicted MOS on the usual 1--5 MOS scale; higher is better.
- Audio is downmixed and resampled to 16 kHz.

## Runtime and Assets

- Optional pip runtime: `torch==2.2.0`, `torchaudio==2.2.0`.
- Stage `squim_subjective_bvcc_daps.pth` and a clean non-matching reference WAV,
  then set `SURE_SE_SQUIM_SUBJECTIVE_CKPT` and
  `SURE_SE_SQUIM_SUBJECTIVE_NMR`.
- The SQUIM Subjective weights are CC BY-NC 4.0.

## Source and References

- [TorchAudio SQUIM Subjective](https://pytorch.org/audio/2.2.0/pipelines.html).

## Limitations

This score is a learned prediction and is not a human listening test. It is
not a pure no-reference model because it uses the separately staged
non-matching reference.

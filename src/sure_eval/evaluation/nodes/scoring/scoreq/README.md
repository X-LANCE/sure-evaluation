# SCOREQ Node

## Purpose

Run the natural-speech, no-reference SCOREQ model for predicted speech quality
and MOS. This is the recommended SCOREQ variant for recorded speech
enhancement and dereverberation.

## Task Scenarios

- Optional SE metric `scoreq`, outside the default bundle.
- Exact pipeline: `se.any.scoreq.scoreq_v1`.

## Input and Output

- Input schema: `enhanced_audio_rows`; required `enhanced_audio`.
- Output: natural-speech SCOREQ MOS prediction; higher is better.
- Audio is downmixed, resampled to 16 kHz, and padded to the wav2vec feature
  extractor stride before inference.

## Runtime and Assets

- Runtime packages: NumPy, ONNX Runtime, Torch, and TorchAudio.
- Run `sure-eval env download --node scoring/scoreq` to stage the released
  `adapt_nr_telephone.onnx` under this node's `checkpoints/` directory, or
  set `SURE_SE_SCOREQ_CHECKPOINT` to an existing local copy.
- The SCOREQ software is MIT licensed; verify the model asset terms before
  redistribution.

## Source and References

- [SCOREQ implementation](https://github.com/alessandroragano/scoreq).
- [SCOREQ model weights](https://zenodo.org/records/15739280).
- Ragano, Skoglund, and Hines, “SCOREQ: Speech Quality Assessment with
  Contrastive Regression,” NeurIPS 2024.

## Limitations

This is a learned no-reference prediction, not a human MOS test and not the
full-reference SCOREQ distance mode.

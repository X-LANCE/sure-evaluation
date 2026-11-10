# SQ-AST LOUD Node

## Purpose

Predict loudness quality from enhanced speech without a paired reference. This is a
learned quality estimate, not a human listening score.

## Task Scenarios

- Optional SE route `se.any.sq_ast_loud.sq_ast_loud_v1`.
- The SE default bundle is unchanged.

## Input

- Schema: `enhanced_audio_rows`; required role: `enhanced_audio`.
- Rows align by `sample_id`; audio is downmixed and resampled to 48 kHz.

## Output

- Schema: `provider_normalized_mos`.
- Per-sample `sq_ast_loud` and arithmetic mean; 1–5 ACR-like scale.
- Higher is better.

## Versioned Computation

- Node `scoring/sq_ast_loud` v1 uses the improved SQ-AST `loud.pth` head.
- Official AST feature normalization uses mean `-10.25446422`, standard
  deviation `4.205750774`, 128 mel bins, and maximum length 1024.
- The sigmoid output is mapped to the reported score by `4 * output + 1`.

## Runtime and Assets

- Optional pip runtime: Torch 2.2.0, TorchAudio 2.2.0, Transformers 4.40.2.
- Stage the improved `loud.pth` checkpoint and the pinned
  `MIT/ast-finetuned-audioset-10-10-0.4593` base snapshot outside git.
- See `node_env.yaml` for local paths and environment overrides.

## Source and References

- [Official SQ-AST implementation](https://github.com/WafaaWardah/SQ-AST).
- Wardah et al., “SQ-AST: A Transformer-Based Model for Speech Quality
  Prediction,” Interspeech 2025, pp. 2335–2339, DOI
  [10.21437/Interspeech.2025-2683](https://doi.org/10.21437/Interspeech.2025-2683).

## Limitations

- The paper describes 4–12 second speech clips; scores outside that duration
  are exploratory.
- Repository code is MIT licensed; the base AST model is BSD-3-Clause. The
  improved head weights have no explicit license statement in the upstream README.

# SLU Task Route

SLU supports default accuracy scoring and optional LLM Judge scoring.

## Accuracy (default)

The `choice_id` and `choice_text` accuracy routes each use two nodes:

1. `normalization/prompt_norm` converts prompt-based raw answers into canonical
   choice ids or choice text.
2. `scoring/classify` computes accuracy over the normalized labels.

The prompt normalization node supports arbitrary choice ids and arbitrary
choice counts. Legacy `A. option` prompt text remains supported as a fallback.

## LLM Judge (optional)

The `slu.any.llm_judge.llm_judge_v1` route uses only
`scoring/llm_judge`. It sends the original textual question and candidate answer,
optional context/choices, and optional aligned reference to a configured API.
It does not normalize answers into choice labels or listen to raw audio.

Set `run_args.llm_config` in the described pipeline JSON to a configuration path.
The configuration must contain a nonempty user-authored `rubric`, API root and
model ID. The node validates input/configuration and accepts finite scores in
`[0, 100]`, with higher being better. Scores are not accuracy percentages.
The aggregate is the unrounded arithmetic mean only if every sample succeeds;
otherwise the score is null and the CLI exits 1 after saving per-sample evidence.
If the Judge identifies insufficient textual evidence, it returns a null score
and a reason. The node records an `insufficient_evidence` sample failure;
remaining samples continue and the batch score is null. Missing evidence is
never assigned a zero score.
The standard report and pipeline description retain the selected route identity.

No extra environment or GPU is needed (`in_process`). Environment checks do not
validate credentials, API reachability or scoring quality.
See the [SLU guide](../../../../../docs/tasks/slu.md) for executable examples,
configuration, evidence requirements and result interpretation.

# SLU — Spoken Language Understanding

Evaluate prompt-based spoken language understanding answers with accuracy
or LLM Judge.

```bash
sure-eval metric routes slu --metric accuracy
```

## Metrics

| Metric | Output mode | Pipeline ID | Nodes |
|:-------|:------------|:------------|:------|
| `accuracy` | `choice_id` | `slu.any.accuracy.prompt_norm_choice_id_v1.classify_v1` | `normalization/prompt_norm` → `scoring/classify` |
| `accuracy` | `choice_text` | `slu.any.accuracy.prompt_norm_choice_text_v1.classify_v1` | `normalization/prompt_norm` → `scoring/classify` |
| `llm_judge` | — | `slu.any.llm_judge.llm_judge_v1` | `scoring/llm_judge` |

Accuracy is the default. Its `choice_id` mode compares normalized choice ids
(`A`, `B`, ...); `choice_text` compares normalized choice text. The prompt
normalizer supports arbitrary choice ids and counts, including legacy
`A. option` text prompts as a fallback. Select an exact pipeline ID from the
table to choose a particular mode.

LLM Judge is opt-in and sends original answer text without choice normalization.
It scores against a user rubric on a 0–100 scale.

## Input Format

Samples are matched by key. Supply aligned hypothesis, reference (when required)
and prompt files. Key-text files use real tabs; `<TAB>` below denotes a tab, not
literal text.

| Role / CLI option | Accuracy | LLM Judge | Format |
|:------------------|:---------|:----------|:-------|
| `hyp` / `--hyp-file` | required | required | `key<TAB>candidate answer` |
| `ref` / `--ref-file` | required | optional | `key<TAB>reference answer` |
| `prompt_jsonl` / `--prompt-jsonl` | required | required | One question/choice object per key |

### Accuracy answers and prompts

Reference file:

```text
utt_001<TAB>A
utt_002<TAB>B
```

Hypothesis file:

```text
utt_001<TAB>A. hello world
utt_002<TAB>B
```

Prompt JSONL:

```jsonl
{"key":"utt_001","prompt":"A. hello world\nB. goodbye\nC. maybe"}
{"key":"utt_002","prompt":"A. yes\nB. no"}
```

### Judge answers and prompts

Hypothesis file:

```text
q1<TAB>Paris
```

Prompt JSONL:

```jsonl
{"key":"q1","prompt":"Which city is mentioned?","context":"Transcript: We will visit Paris."}
```

Reference file (optional):

```text
q1<TAB>Paris
```

Keys and questions must be nonempty; supplied files must have matching unique
keys. `question` is an alias for `prompt`; `context` and `choices`/`options` are
optional. Candidate answers may be empty; supplied reference text must be
nonempty and is sent as `reference_answer`.

## CLI Usage

### Accuracy

```bash
sure-eval metric describe slu --output /tmp/slu.json
sure-eval metric run --pipeline /tmp/slu.json \
  --ref-file ref.txt --hyp-file hyp.txt \
  --prompt-jsonl prompt.jsonl --output-dir /tmp/slu_eval
```

### LLM Judge

Prepare the input files from [Input Format](#input-format) and the configuration
file from [Judge Configuration](#judge-configuration). Generate the pipeline,
set its `run_args.llm_config`, then run:

```bash
sure-eval metric describe slu --pipeline-id slu.any.llm_judge.llm_judge_v1 \
  --output /tmp/slu-judge/pipeline.json
# Set run_args.llm_config in this JSON as shown in Judge Configuration before running.
sure-eval metric run --pipeline /tmp/slu-judge/pipeline.json \
  --hyp-file /tmp/slu-judge/answers.txt \
  --prompt-jsonl /tmp/slu-judge/questions.jsonl \
  --output-dir /tmp/slu-judge/results --json
```

View the generated report:

```bash
python -m json.tool /tmp/slu-judge/results/report.json
```

Add `--ref-file ref.txt` to include aligned references. Relative paths resolve
from the invocation working directory, not the pipeline file's directory.
These examples use `/tmp` paths for Bash on Linux or WSL.

## Python API

### Accuracy

```python
from sure_eval.evaluation.scripts import run_task

report = run_task(
    "slu",
    ref_file="ref.txt",
    hyp_file="hyp.txt",
    prompt_jsonl="prompt.jsonl",
    output_dir="/tmp/slu_eval",
)
print(report.score)
```

### LLM Judge

```python
from sure_eval.evaluation.scripts import run_task

report = run_task(
    "slu",
    metric="llm_judge",
    pipeline_id="slu.any.llm_judge.llm_judge_v1",
    hyp_file="/tmp/slu-judge/answers.txt",
    prompt_jsonl="/tmp/slu-judge/questions.jsonl",
    llm_config="/tmp/slu-judge/llm-config.json",
    output_dir="/tmp/slu-judge/python-results",
    # ref_file="ref.txt",  # optional aligned reference answers
)
print(report.score)
```

## Output

Both routes write:

- `report.json` — canonical `metric`, selected `pipeline_id`, `score`, input
  contract/files, pipeline trace, and metric-specific details.
- `pipeline_description.json` — selected `pipeline_id`, `execution_metrics`,
  `computation_node_ids`, relative `task_config_path` / `route_config_path`,
  `script_entrypoint`, `executor`, and node versions. `output_mode` applies to
  the accuracy routes.

### Accuracy

The score is accuracy, with correct/total counts. Answer comparison follows the
selected `choice_id` or `choice_text` mode.

### LLM Judge

Responses contain exactly `score` and nonempty `reason`. A null score signals
insufficient evidence and is recorded as a failure. Successful scores must be finite
numbers in **[0, 100]**, higher being better. Integers and decimals are accepted
without rounding; booleans, strings, NaN, infinities and out-of-range values are
rejected. Decimal parsing and means use Python binary64 floating-point precision.
The aggregate is `sum(scores) / N` only when all N samples succeed. This is a
rubric-specific 100-point scale, not accuracy.

`pipeline_trace[0].details` includes `score_range`, exact `rubric`,
`rubric_sha256` (exact UTF-8 content), safe `llm_config`, `prompt_sha256`, precision,
aggregation policy, and per-sample scores/reasons/returned model IDs.

HTTP errors, truncated bodies, protocol errors, invalid JSON, refusals, incomplete
model responses and invalid scores become per-sample failures with stable codes.
Other samples continue. Any failed sample makes the total `null`; both reports
are saved before CLI exit 1. One success plus one failure yields `num_scored=1`,
`num_failed=1`, `num_samples=2`. Failed requests never become zero scores.
Input/config errors fail before scoring and do not promise a batch report.

## Environment Notes

- Accuracy uses the in-process prompt normalizer and classification scorer.
- Judge is also `in_process`: it needs no extra packages, GPU, checkpoint or
  empty pip environment. Its configuration and API credentials are still required.
- `env check` verifies runtime availability only, not credentials, API access
  or scoring quality.
- Judge scoring sends text to the configured service and may incur API charges.

Optional runtime checks for the generated Judge pipeline:

```bash
sure-eval env setup --pipeline /tmp/slu-judge/pipeline.json --dry-run --json
sure-eval env check --pipeline /tmp/slu-judge/pipeline.json --json
```

## Judge Configuration

### Configuration file

Create the directory with `mkdir -p /tmp/slu-judge`, then save
`/tmp/slu-judge/llm-config.json` with your API root, model ID
and scoring rubric:

```json
{
  "base_url": "https://YOUR_HOST/v1",
  "model": "YOUR_MODEL_ID",
  "api_key_env": "LLM_JUDGE_API_KEY",
  "rubric": "Score correctness against context/reference: 100 for a complete correct answer, 50 for a partly correct answer, 0 for a contradiction or empty answer. Return null with a reason if evidence is insufficient. Explain the evidence and deductions."
}
```

Set the API key in your Bash shell:

```bash
export LLM_JUDGE_API_KEY='YOUR_API_KEY'
```

Replace `YOUR_API_KEY` with your real credential locally. Save the aligned input examples as
`answers.txt` and `questions.jsonl` in the same directory. No real credentials
belong in these files.

`run_args.llm_config` is a JSON configuration path. Required fields: `base_url`,
`model`, and nonempty user-authored `rubric` text. Missing, blank or non-text
rubric fails before any API request. There is no default correctness rubric.

The provider must support Chat Completions at `<base_url>/chat/completions`.
HTTPS is required except for localhost HTTP tests; redirects are disabled.
`api_key_env` names the credential environment variable (default
`LLM_JUDGE_API_KEY`). A nonempty local `api_key` overrides it, but must not be
committed/shared; reports exclude that field. Optional configuration:
`timeout` (positive seconds, default 60), `temperature` (nonnegative, default 0),
`max_tokens` (positive integer, default 1024), and `instruction` (extra guidance
consistent with the rubric and output contract).

### Pipeline configuration

The following Bash example runs from the repository root after installation.
Discover the route and generate its pipeline description:

```bash
sure-eval metric routes slu --metric llm_judge --json
sure-eval metric describe slu --pipeline-id slu.any.llm_judge.llm_judge_v1 \
  --output /tmp/slu-judge/pipeline.json
```

Set `run_args.llm_config` in the generated pipeline to the configuration path,
keeping the other generated fields:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path('/tmp/slu-judge/pipeline.json')
spec = json.loads(p.read_text(encoding='utf-8'))
spec['run_args']['llm_config'] = '/tmp/slu-judge/llm-config.json'
p.write_text(json.dumps(spec, indent=2) + '\n', encoding='utf-8')
PY
```

The pipeline is now ready for `metric run` in [CLI Usage](#cli-usage).
If it is already configured, run only `metric run`; generating it again with
`describe` replaces the JSON and requires setting `run_args.llm_config` again.

## Limitations

The Judge cannot hear audio. For questions about audio facts, supply sufficient
textual evidence in `context` or aligned references. If the Judge identifies insufficient evidence, it must return `score: null`
with a reason. This becomes an `insufficient_evidence` sample failure and makes
the batch total `null`; it is never a zero score. Without that evidence, the result
cannot establish whether the model understood the original audio. The program
checks input types and key alignment; it does not determine evidence sufficiency
or validate the meaning of the user's rubric.

Compare Judge scores only when rubrics, model/configuration and evidence policies
match. Temperature zero does not guarantee reproducibility. Prompt injection and
model errors remain possible.

The rubric content hash identifies its exact text; it is separate from the node
version. See the [node reference](../../src/sure_eval/evaluation/nodes/scoring/llm_judge/README.md)
for computation, runtime and further limitations.

## Real API Integration Smoke (2026-11-06)

Historical integration record: its rubric predates the current mandatory
null-on-insufficient-evidence policy. The follow-up below verifies that policy.

`slu.any.llm_judge.llm_judge_v1` was exercised through `describe -> metric run -> report`
with model `deepseek-flash` (the returned model ID matched), temperature 0,
max_tokens 1024, and the following user rubric:

> Use only the supplied context/reference as evidence. Score 100 for a complete
> factually correct answer, 50 for a partly correct answer, and 0 for a wrong or
> empty answer or insufficient evidence. Explain the supporting evidence.

The exact single-line rubric SHA-256 was
`9a0ba9b525cbf716633dd1d72a1f1402d5ee37aebc6eb1d1942c51cadebd61d3`.
Both requests used textual context and no separate reference file.

| Question | Context | Candidate | Returned score |
|:--|:--|:--|--:|
| Which city will the speaker visit? | Transcript: I will visit Paris. | Paris | 100 |
| At what hour is the meeting? | Transcript: The meeting is at nine. | Ten | 0 |

The first reason cited the explicit Paris statement; the second identified the
nine-versus-ten contradiction. The aggregate was 50.0, range `[0, 100]`, with two
successful samples, zero failures and CLI exit 0. No credentials are included
here. This small smoke confirms real API integration, not scoring accuracy,
calibration or repeatability across models and rubrics.

### Follow-up: insufficient evidence (2026-11-08)

The current node was exercised through `describe -> configure -> metric run -> report`
with `deepseek-flash`, temperature 0, max_tokens 1024, and score range `[0, 100]`.
The user-supplied rubric was:

> Use only the supplied context/reference as evidence. Score 100 for a complete factually correct answer, 50 for a partly correct answer, and 0 for a wrong or empty answer. Return null with a reason if evidence is insufficient. Explain the supporting evidence.

Its exact UTF-8 SHA-256 was
`27801e640593f7cb8ac9a647e3b717d32bd6522c55a579b369fe131ebdea8ed2`.

| Question | Context | Candidate | Result |
|:--|:--|:--|:--|
| Which city will the speaker visit? | Transcript: I will visit Paris. | Paris | 100; context explicitly supports Paris |
| At what hour is the meeting? | Transcript: The meeting is at nine. | Ten | 0; contradicts the context |
| Which city did the speaker mention in the audio? | Not supplied; no reference | Paris | null; `insufficient_evidence` |

All three samples were recorded: two scored, one failed. The batch score was
null and CLI exit code was 1. The third reason stated that no transcript or
reference was available to verify the answer. This confirms API integration and
the failure policy, not scoring accuracy or reliability on a representative dataset.

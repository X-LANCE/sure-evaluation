# LLM Judge for Textual SLU Answers

## Purpose

Evaluate candidate answers against a user-supplied rubric using an
OpenAI-compatible Chat Completions service. This node evaluates text, not raw
audio, and does not compute classification accuracy.

## Task Scenarios

- Optional `slu/any/llm_judge`, exact route `slu.any.llm_judge.llm_judge_v1`.
- Default SLU choice accuracy continues to use prompt normalization/classify.
- Questions about audio require adequate textual context or references.

## Input

Schema: `task_addressed_text_inputs`. Required roles: `hyp` and `prompt_jsonl`;
optional role: `ref`. Hypotheses and references are `key<TAB>text`. Prompt JSONL
objects contain `key`, `prompt` or `question`, and optional text `context` and
list/object `choices` or `options`. Every supplied file has the same nonempty,
unique key set. Candidate text may be empty; reference text must not be empty.

`run_args.llm_config` points to a JSON configuration with `base_url`, `model`,
and nonempty `rubric` text. All three are user inputs. The rubric defines the
scoring criteria; insufficient evidence is always a failure, not a zero score. Missing/blank rubric fails
before requests. See the [SLU guide](../../../../../../docs/tasks/slu.md) for
configuration defaults and a complete describe/configure/run/report example.

## Output

Schema: `llm_judge_result`, represented as `PipelineNodeResult`. Details contain
the result, `sample_results`, safe configuration, exact rubric, `rubric_sha256`,
`prompt_sha256`, `score_range: [0, 100]`, precision and aggregation policy.
Each successful sample has a finite score, nonempty reason and returned model ID;
each failed sample has a stable error code. API keys and raw server errors are
excluded. Higher scores are better; this scale does not imply accuracy.

## Versioned Computation

Node `scoring/llm_judge`, version `v1` (initial, unreleased implementation).
Internal stages: input validation, prompt construction, LLM judging, response
validation, mean aggregation. No answer normalization is applied.

Each sample makes one request, with no retries or concurrent calls. User rubric
is included in the system prompt; sample fields are treated as data. Responses
must finish with `stop`, without refusal, and contain exactly `score` and `reason`.
Finite integer/decimal scores in `[0, 100]` are accepted without rounding.
Booleans, numeric strings, NaN, infinities and out-of-range values are rejected.
Decimals and the mean use binary64 floating-point arithmetic. The mean is
`sum(scores) / N` only when all N samples succeed. Otherwise it is null; partial
evidence remains in the standard task reports and CLI exit code is 1.

HTTP protocol exceptions, including incomplete reads, are converted at the API
boundary to `api_http_protocol_error`. Other transport/JSON failures and HTTP
status errors retain their existing stable codes. Implementation errors are not
broadly caught. No failure is silently scored as zero.

## Runtime and Assets

Runtime: `in_process`; Python standard library only. No node-local pyproject,
pip setup, checkpoint or GPU is needed. API root and model are configuration,
not fixed providers. The root must use HTTPS except localhost HTTP tests.
Requests use `<base_url>/chat/completions` and do not follow redirects.

Prefer `api_key_env: "LLM_JUDGE_API_KEY"` with the key in the environment. A
nonempty local `api_key` overrides the environment; keep real keys out of Git.
Environment discovery/check/dry-run never checks credentials or sends a request.
An environment status of `ok` does not establish API readiness or scoring quality.

## Source and References

Local implementation: `node.py`; the Chat Completions adapter uses Python's
`urllib.request` and handles `http.client.HTTPException`. Scoring criteria are
provided by the user, not a published standardized rubric or calibrated metric.

## Limitations

No audio access, automatic transcription, provider-specific protocol adapters,
automatic input truncation or retries. Supply adequate textual evidence and
use null with a reason when evidence is insufficient. Scores depend on rubric, prompt,
model and inference configuration; unlike accuracy, they are subjective and not
automatically comparable across configurations. Temperature zero does not ensure
identical runs. Prompt injection and unsupported judgments remain possible.
Real API smoke tests establish integration, not evaluation accuracy.

### Insufficient evidence

Return `{"score": null, "reason": "explain the missing evidence"}` when the
provided text cannot support a judgment. The node records `insufficient_evidence`
as a sample failure, continues other samples, and returns a null batch total.
This policy overrides any rubric instruction to score missing evidence as zero.
Evidence sufficiency is assessed by the Judge, not by deterministic input checks.

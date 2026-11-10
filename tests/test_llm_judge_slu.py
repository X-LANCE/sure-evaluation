"""Offline node and CLI integration tests; never contact a real API."""

from __future__ import annotations

import json
import hashlib
import http.client
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock
import pytest
from typer.testing import CliRunner

from sure_eval.cli import app
from sure_eval.evaluation.cli_adapters import build_pipeline_spec, run_pipeline_spec
from sure_eval.evaluation.nodes.scoring.llm_judge import node
from sure_eval.evaluation.scripts import describe_pipeline, run_task


@pytest.fixture
def inputs(tmp_path):
    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text(
        '\n'.join(json.dumps(row) for row in [
            {"key": "a", "prompt": "What city is mentioned?", "context": "The speaker says Paris.",
             "choices": {"A": "Paris", "B": "London"}, "reference": "must not reach judge"},
            {"key": "b", "question": "What time is the meeting?", "context": "Meeting at nine."},
        ]) + '\n', encoding="utf-8",
    )
    hyp = tmp_path / "hyp.txt"
    hyp.write_text("b\tAt nine.\na\tA\n", encoding="utf-8")
    config = tmp_path / "judge.json"
    config.write_text(json.dumps({"rubric": "Score correctness against the supplied evidence from 0 to 100.", "base_url": "https://example.invalid/v1", "model": "test-judge"}),
                      encoding="utf-8")
    return prompts, hyp, config


def test_slu_judge_routes_and_default_accuracy():
    default = describe_pipeline("slu")
    judge = describe_pipeline("slu", metric="llm_judge")
    assert default.metric == "accuracy"
    assert default.node_ids == ("normalization/prompt_norm", "scoring/classify")
    assert judge.pipeline_id == "slu.any.llm_judge.llm_judge_v1"
    assert judge.required_roles == ("hyp", "prompt_jsonl")
    assert judge.node_ids == ("scoring/llm_judge",)


def test_node_aligns_answers_and_passes_only_explicit_context(inputs):
    prompts, hyp, _ = inputs
    seen = []

    def caller(config, messages):
        data = json.loads(messages[1]["content"])
        seen.append(data)
        return {"score": 4 if data["answer"] == "A" else 2, "reason": "test reason"}

    result = node.score_slu_judge(
        hyp_file=str(hyp), prompt_jsonl=str(prompts),
        config=node.JudgeConfig("https://example.invalid/v1", "fake", rubric="Score correctness from 0 to 100."), caller=caller,
    )
    assert result.details["result"]["score"] == 3
    assert seen[0]["answer"] == "A"
    assert seen[0]["choices"]["A"] == "Paris"
    assert "reference" not in seen[0]
    assert result.details["input_files"] == {"hyp": str(hyp), "prompt_jsonl": str(prompts)}


@pytest.mark.parametrize("value", [True, -1, 101, "5", float("nan"), float("inf"), float("-inf")])
def test_answer_scores_are_validated(value):
    with pytest.raises(node.JudgeError):
        node.validate_answer_judgment({"score": value, "reason": "test"})


@pytest.mark.parametrize("score", [0, 100, 0.125, 99.875, 80])
def test_percent_scale_accepts_boundaries_and_decimals_without_rounding(score):
    assert node.validate_answer_judgment({"score": score, "reason": "ok"})["score"] == score


@pytest.mark.parametrize("rubric", [None, "", " \n\t", 12, False, []])
def test_invalid_rubric_rejected_before_api(inputs, tmp_path, monkeypatch, rubric):
    prompts, hyp, config = inputs
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["rubric"] = rubric
    config.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(node, "call_judge", lambda *args: pytest.fail("API must not be called"))
    with pytest.raises(ValueError, match="rubric"):
        run_task("slu", metric="llm_judge", hyp_file=str(hyp), prompt_jsonl=str(prompts),
                 llm_config=str(config), output_dir=str(tmp_path / "out"))


def test_missing_rubric_has_clear_cli_error_without_api(inputs, tmp_path, monkeypatch):
    prompts, hyp, config = inputs
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload.pop("rubric")
    config.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(node, "call_judge", lambda *args: pytest.fail("API must not be called"))
    spec = build_pipeline_spec("slu", metric="llm_judge")
    spec["run_args"]["llm_config"] = str(config)
    pipeline = tmp_path / "pipeline.json"
    pipeline.write_text(json.dumps(spec), encoding="utf-8")
    result = CliRunner().invoke(app, ["metric", "run", "--pipeline", str(pipeline),
                                     "--hyp-file", str(hyp), "--prompt-jsonl", str(prompts),
                                     "--output-dir", str(tmp_path / "out"), "--json"])
    assert result.exit_code == 1
    assert "rubric" in json.loads(result.stdout)["message"]
    assert not (tmp_path / "out" / "report.json").exists()


def test_rubric_is_sent_and_reported_with_hash_and_percent_mean(inputs, tmp_path, monkeypatch):
    prompts, hyp, path = inputs
    rubric = "Evidence-based correctness: 0 for contradiction; 100 for a complete match."
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(rubric=rubric, api_key="fake-secret-not-for-report")
    path.write_text(json.dumps(payload), encoding="utf-8")
    seen = []
    scores = iter([0.125, 99.875])

    def judge(config, messages):
        seen.append(messages)
        assert config.rubric == rubric
        return {"score": next(scores), "reason": "using the supplied rubric"}

    monkeypatch.setattr(node, "call_judge", judge)
    report = run_task("slu", metric="llm_judge", hyp_file=str(hyp), prompt_jsonl=str(prompts),
                      llm_config=str(path), output_dir=str(tmp_path / "out"))
    assert report.score == 50
    assert all(rubric in messages[0]["content"] for messages in seen)
    assert all("1 to 5" not in messages[0]["content"] for messages in seen)
    details = report.pipeline_trace[0].details
    assert details["rubric"] == details["llm_config"]["rubric"] == rubric
    assert details["rubric_sha256"] == hashlib.sha256(rubric.encode("utf-8")).hexdigest()
    assert details["score_range"] == [0, 100]
    assert [s["score"] for s in details["sample_results"]] == [0.125, 99.875]
    assert "fake-secret-not-for-report" not in (tmp_path / "out" / "report.json").read_text()


@pytest.mark.parametrize("failure", ["short_body", "bad_status"])
def test_real_http_protocol_failure_keeps_partial_batch_report(inputs, tmp_path, monkeypatch, failure):
    prompts, hyp, config = inputs
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            if len(requests) == 2:
                if failure == "bad_status":
                    self.wfile.write(b"invalid HTTP status\r\n\r\n")
                else:
                    self.send_response(200)
                    self.send_header("Content-Length", "9999")
                    self.end_headers()
                    self.wfile.write(b'{"partial":1')
                self.close_connection = True
                return
            body = json.dumps({"model": "local-test-model", "choices": [{
                "finish_reason": "stop", "message": {"content": json.dumps({
                    "score": 80.5, "reason": "valid first answer"})}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_opener = node.urllib.request.build_opener
    monkeypatch.setattr(node.urllib.request, "build_opener",
                        lambda *handlers: original_opener(node.urllib.request.ProxyHandler({}), *handlers))
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload.update(base_url=f"http://127.0.0.1:{server.server_port}/v1", api_key="fake-local-key", timeout=5)
    config.write_text(json.dumps(payload), encoding="utf-8")
    spec = build_pipeline_spec("slu", pipeline_id="slu.any.llm_judge.llm_judge_v1")
    spec["run_args"]["llm_config"] = str(config)
    pipeline = tmp_path / "pipeline.json"
    pipeline.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "out"
    try:
        result = CliRunner().invoke(app, ["metric", "run", "--pipeline", str(pipeline),
                                         "--hyp-file", str(hyp), "--prompt-jsonl", str(prompts),
                                         "--output-dir", str(out), "--json"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.exit_code == 1, result.output
    assert "judge_batch_failed" in json.loads(result.stdout)["message"]
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    description = json.loads((out / "pipeline_description.json").read_text(encoding="utf-8"))
    assert report["pipeline_id"] == description["pipeline_id"] == spec["pipeline_id"]
    assert report["score"] is None
    assert report["details"]["scoring_result"] == {
        "score": None, "llm_judge": None, "status": "failed",
        "num_samples": 2, "num_scored": 1, "num_failed": 1,
    }
    samples = report["pipeline_trace"][0]["details"]["sample_results"]
    assert samples[0]["score"] == 80.5
    assert samples[1] == {"key": "b", "status": "failed", "error_code": "api_http_protocol_error"}
    assert len(requests) == 2
    assert payload["rubric"] in requests[0]["messages"][0]["content"]


@pytest.mark.parametrize("exception", [http.client.IncompleteRead(b"private", 100),
                                       http.client.BadStatusLine("private"),
                                       http.client.HTTPException("private")])
def test_protocol_exceptions_are_sanitized_at_read_boundary(monkeypatch, exception):
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.side_effect = exception
    monkeypatch.setattr(node.urllib.request, "build_opener", lambda *args: opener)
    config = node.JudgeConfig("https://example.invalid", "fake", rubric="0-100", api_key="fake")
    with pytest.raises(node.JudgeError, match="^api_http_protocol_error$"):
        node.call_judge(config, [])


def test_programming_errors_are_not_swallowed(inputs):
    prompts, hyp, path = inputs

    def broken_caller(*args):
        raise RuntimeError("implementation bug")

    with pytest.raises(RuntimeError, match="implementation bug"):
        node.score_slu_judge(hyp_file=str(hyp), prompt_jsonl=str(prompts),
                             config=node.JudgeConfig.from_file(path), caller=broken_caller)


def test_judge_environment_needs_no_setup_or_credentials(tmp_path, monkeypatch):
    from sure_eval.evaluation.env_check import NodeEnvChecker

    monkeypatch.delenv("LLM_JUDGE_API_KEY", raising=False)
    checked = NodeEnvChecker().check_node("scoring/llm_judge")
    assert checked.status == "ok"
    assert checked.runtime == "in_process"
    assert checked.required is False
    runner = CliRunner()
    routes = json.loads(runner.invoke(app, ["metric", "routes", "slu", "--metric", "llm_judge", "--json"]).stdout)
    assert routes["routes"][0]["setup_node_ids"] == []
    pipeline = tmp_path / "pipeline.json"
    pipeline.write_text(json.dumps(build_pipeline_spec("slu", metric="llm_judge")), encoding="utf-8")
    result = runner.invoke(app, ["env", "setup", "--pipeline", str(pipeline), "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    assert "pip install" not in result.stdout


def test_key_mismatch_prevents_api_call(inputs, monkeypatch):
    prompts, hyp, _ = inputs
    hyp.write_text("different\tanswer\n", encoding="utf-8")
    monkeypatch.setattr(node, "call_judge", lambda *args: pytest.fail("must not call API"))
    with pytest.raises(ValueError, match="same non-empty key set"):
        node.score_slu_judge(hyp_file=str(hyp), prompt_jsonl=str(prompts),
                             config=node.JudgeConfig("https://example.invalid/v1", "fake", rubric="Score correctness from 0 to 100."))


@pytest.mark.parametrize("rows", [
    [{"key": "a", "prompt": "question"}, {"key": "a", "prompt": "duplicate"}],
    [{"key": "a", "prompt": ""}],
    [{"key": "a", "prompt": "question", "context": 42}],
])
def test_invalid_questions_prevent_api_call(inputs, monkeypatch, rows):
    prompts, hyp, _ = inputs
    prompts.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    monkeypatch.setattr(node, "call_judge", lambda *args: pytest.fail("must not call API"))
    with pytest.raises(ValueError):
        node.score_slu_judge(hyp_file=str(hyp), prompt_jsonl=str(prompts),
                            config=node.JudgeConfig("https://example.invalid/v1", "fake", rubric="Score correctness from 0 to 100."))


def test_cli_routes_describe_run_and_standard_outputs(inputs, tmp_path, monkeypatch):
    prompts, hyp, config = inputs
    runner = CliRunner()
    seen = []

    def caller(config, messages):
        seen.append(config.model)
        return {"score": 4, "reason": "answers the question"}

    monkeypatch.setattr(node, "call_judge", caller)
    routes = runner.invoke(app, ["metric", "routes", "slu", "--metric", "llm_judge", "--json"])
    assert routes.exit_code == 0, routes.output
    assert json.loads(routes.stdout)["count"] == 1
    pipeline = tmp_path / "pipeline.json"
    describe = runner.invoke(app, ["metric", "describe", "slu", "--metric", "llm_judge",
                                   "--output", str(pipeline), "--json"])
    assert describe.exit_code == 0, describe.output
    spec = json.loads(pipeline.read_text(encoding="utf-8"))
    spec["run_args"]["llm_config"] = str(config)
    pipeline.write_text(json.dumps(spec), encoding="utf-8")
    output = tmp_path / "output"
    run = runner.invoke(app, ["metric", "run", "--pipeline", str(pipeline),
                             "--hyp-file", str(hyp), "--prompt-jsonl", str(prompts),
                             "--output-dir", str(output), "--json"])
    assert run.exit_code == 0, run.output
    assert seen == ["test-judge", "test-judge"]
    summary = json.loads(run.stdout)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    description = json.loads((output / "pipeline_description.json").read_text(encoding="utf-8"))
    assert summary["score"] == report["score"] == 4
    assert report["pipeline_id"] == description["pipeline_id"]
    assert report["computation_node_ids"] == ["scoring/llm_judge"]
    assert report["input_files"] == {"hyp": str(hyp), "prompt_jsonl": str(prompts)}


def test_python_api_and_pipeline_config_parameter(inputs, tmp_path, monkeypatch):
    prompts, hyp, config = inputs
    monkeypatch.setattr(node, "call_judge", lambda *args: {"score": 5, "reason": "good"})
    report = run_task("slu", metric="llm_judge", hyp_file=str(hyp), prompt_jsonl=str(prompts),
                      llm_config=str(config), output_dir=str(tmp_path / "api"))
    assert report.score == 5
    pipeline = build_pipeline_spec("slu", metric="llm_judge")
    pipeline["run_args"]["llm_config"] = str(config)
    summary = run_pipeline_spec(pipeline, hyp_file=str(hyp), prompt_jsonl=str(prompts),
                                output_dir=str(tmp_path / "adapter"))
    assert summary["score"] == 5


def test_pipeline_validates_llm_config_before_api_call(inputs, monkeypatch):
    from sure_eval.evaluation.tasks.slu.pipeline import evaluate_slu_files

    prompts, hyp, config = inputs
    config.write_text(json.dumps({"rubric": "Score from 0 to 100.", "base_url": "http://example.invalid/v1", "model": "test"}),
                      encoding="utf-8")
    monkeypatch.setattr(node, "call_judge", lambda *args: pytest.fail("must not call API"))
    with pytest.raises(ValueError, match="HTTPS"):
        evaluate_slu_files(hyp_file=str(hyp), prompt_jsonl=str(prompts),
                           metric="llm_judge", llm_config=str(config))


def test_cli_passes_aligned_references_to_judge(inputs, tmp_path, monkeypatch):
    prompts, hyp, config = inputs
    ref = tmp_path / "ref.txt"
    ref.write_text("b\tAt nine.\na\tParis\n", encoding="utf-8")
    spec = build_pipeline_spec("slu", metric="llm_judge")
    spec["run_args"]["llm_config"] = str(config)
    assert spec["executor"].endswith(".evaluate_slu_files")
    pipeline = tmp_path / "pipeline.json"
    pipeline.write_text(json.dumps(spec), encoding="utf-8")
    seen = []

    def caller(config, messages):
        seen.append(json.loads(messages[1]["content"]))
        return {"score": 5, "reason": "matches reference"}

    monkeypatch.setattr(node, "call_judge", caller)
    output = tmp_path / "with-ref"
    result = CliRunner().invoke(app, [
        "metric", "run", "--pipeline", str(pipeline), "--hyp-file", str(hyp),
        "--ref-file", str(ref), "--prompt-jsonl", str(prompts), "--output-dir", str(output),
    ])
    assert result.exit_code == 0, result.output
    assert [row["reference_answer"] for row in seen] == ["Paris", "At nine."]
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["input_files"]["ref"] == str(ref)
    assert report["pipeline_trace"][0]["details"]["input_files"]["ref"] == str(ref)


def test_reference_key_mismatch_prevents_api_call(inputs, tmp_path, monkeypatch):
    prompts, hyp, _ = inputs
    ref = tmp_path / "ref.txt"
    ref.write_text("different\tanswer\n", encoding="utf-8")
    monkeypatch.setattr(node, "call_judge", lambda *args: pytest.fail("must not call API"))
    with pytest.raises(ValueError, match="ref and hyp"):
        node.score_slu_judge(
            hyp_file=str(hyp), prompt_jsonl=str(prompts), ref_file=str(ref),
            config=node.JudgeConfig("https://example.invalid/v1", "fake", rubric="Score correctness from 0 to 100."),
        )


def test_missing_config_and_accuracy_reference_checks(inputs, tmp_path):
    prompts, hyp, config = inputs
    with pytest.raises(ValueError, match="llm_config"):
        run_task("slu", metric="llm_judge", hyp_file=str(hyp), prompt_jsonl=str(prompts),
                  output_dir=str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="ref_file"):
        run_task("slu", hyp_file=str(hyp), prompt_jsonl=str(prompts), output_dir=str(tmp_path / "acc"))
    with pytest.raises(ValueError, match="only accepted"):
        pipeline = build_pipeline_spec("slu")
        pipeline["run_args"]["llm_config"] = str(config)
        run_pipeline_spec(pipeline,
                          hyp_file=str(hyp), prompt_jsonl=str(prompts), output_dir=str(tmp_path / "bad"))


def test_failed_batch_preserves_evidence_and_cli_fails(inputs, tmp_path, monkeypatch):
    prompts, hyp, config = inputs

    def caller(config, messages):
        if json.loads(messages[1]["content"])["answer"] == "A":
            return {"score": 4, "reason": "good"}
        raise node.JudgeError("http_error_429")

    monkeypatch.setattr(node, "call_judge", caller)
    pipeline = tmp_path / "pipeline.json"
    spec = build_pipeline_spec("slu", metric="llm_judge")
    spec["run_args"]["llm_config"] = str(config)
    pipeline.write_text(json.dumps(spec), encoding="utf-8")
    output = tmp_path / "failed"
    result = CliRunner().invoke(app, ["metric", "run", "--pipeline", str(pipeline),
                                      "--hyp-file", str(hyp), "--prompt-jsonl", str(prompts),
                                      "--output-dir", str(output), "--json"])
    assert result.exit_code == 1
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["score"] is None
    assert report["details"]["scoring_result"]["num_failed"] == 1
    assert report["pipeline_trace"][0]["details"]["sample_results"][1]["error_code"] == "http_error_429"


@pytest.mark.parametrize("credential_source", ["environment", "config"])
def test_api_protocol_and_returned_model(monkeypatch, credential_source):
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({
        "model": "actual-model", "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"score": 4, "reason": "good"})}}],
    }).encode()
    monkeypatch.setenv("LLM_JUDGE_API_KEY", "fake-test-key")
    monkeypatch.setattr(node.urllib.request, "build_opener", lambda *args: opener)
    config = node.JudgeConfig(
        "https://example.invalid/v1", "test-model", rubric="Score correctness from 0 to 100.",
        api_key="local-test-key" if credential_source == "config" else None,
    )
    result = node.call_judge(config, [{"role": "user", "content": "test"}])
    request = opener.open.call_args.args[0]
    assert request.full_url == "https://example.invalid/v1/chat/completions"
    assert json.loads(request.data)["model"] == "test-model"
    expected_key = "local-test-key" if credential_source == "config" else "fake-test-key"
    assert request.get_header("Authorization") == f"Bearer {expected_key}"
    assert result["response_model"] == "actual-model"
    assert "fake-test-key" not in json.dumps(result)


@pytest.mark.parametrize("failure", ["http", "truncated"])
def test_api_errors_are_sanitized_and_truncation_rejected(monkeypatch, failure):
    opener = MagicMock()
    if failure == "http":
        opener.open.side_effect = urllib.error.HTTPError(
            "https://example.invalid", 401, "sensitive server message", {}, None,
        )
        expected = "^http_error_401$"
    else:
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps({
            "choices": [{"finish_reason": "length", "message": {
                "content": '{"score": 5, "reason": "good"}'}}],
        }).encode()
        expected = "incomplete_or_refused_response"
    monkeypatch.setenv("LLM_JUDGE_API_KEY", "fake-test-key")
    monkeypatch.setattr(node.urllib.request, "build_opener", lambda *args: opener)
    with pytest.raises(node.JudgeError, match=expected):
        node.call_judge(node.JudgeConfig("https://example.invalid/v1", "test", rubric="Score correctness from 0 to 100."), [])


@pytest.mark.parametrize("credential_source", ["environment", "config"])
def test_standalone_cli_runs_slu(inputs, tmp_path, monkeypatch, credential_source):
    prompts, hyp, config = inputs
    output = tmp_path / "node-result.json"
    monkeypatch.setenv("LLM_JUDGE_API_KEY", "fake-test-key")
    if credential_source == "config":
        payload = json.loads(config.read_text(encoding="utf-8"))
        payload["api_key"] = "local-test-key"
        config.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.delenv("LLM_JUDGE_API_KEY")
    monkeypatch.setattr(node, "call_judge", lambda *args: {"score": 4, "reason": "good"})
    code = node.main([
        "--prompt-jsonl", str(prompts), "--hyp-file", str(hyp),
        "--config", str(config), "--output", str(output),
    ])
    assert code == 0
    content = output.read_text(encoding="utf-8")
    assert json.loads(content)["details"]["result"]["score"] == 4
    assert "fake-test-key" not in content
    assert "local-test-key" not in content
    assert "api_key" not in json.loads(content)["details"]["llm_config"]
    assert "local-test-key" not in repr(node.JudgeConfig("https://example.invalid/v1", "test", rubric="Score correctness from 0 to 100.", api_key="local-test-key"))


def test_insufficient_evidence_is_failure_and_later_samples_continue(inputs):
    prompts, hyp, _ = inputs
    seen = []

    def caller(config, messages):
        seen.append(messages)
        if len(seen) == 1:
            return {"score": None, "reason": "The audio fact has no textual evidence."}
        return {"score": 80, "reason": "Supported by context."}

    trace = node.score_slu_judge(
        hyp_file=str(hyp), prompt_jsonl=str(prompts),
        config=node.JudgeConfig("https://example.invalid/v1", "fake", rubric="Score 0 to 100."),
        caller=caller,
    )
    assert len(seen) == 2
    assert '"score": null' in seen[0][0]["content"]
    assert trace.details["sample_results"][0] == {
        "key": "a", "status": "failed", "error_code": "insufficient_evidence",
        "score": None, "reason": "The audio fact has no textual evidence.",
    }
    assert trace.details["sample_results"][1]["score"] == 80
    assert trace.details["result"]["score"] is None
    assert trace.details["result"]["num_failed"] == 1
    assert trace.details["result"]["num_scored"] == 1


def test_null_score_requires_reason():
    with pytest.raises(node.JudgeError, match="invalid_judgment_reason"):
        node.validate_answer_judgment({"score": None, "reason": " "})

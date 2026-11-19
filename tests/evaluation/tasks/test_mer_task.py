from __future__ import annotations

import json
import math
from pathlib import Path

import pytest


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _static_files(tmp_path: Path) -> tuple[Path, Path]:
    reference = tmp_path / "ref_static.jsonl"
    prediction = tmp_path / "pred_static.jsonl"
    _write_jsonl(
        reference,
        [
            {"music_id": "1", "valence": 0.2, "arousal": 0.3},
            {"music_id": "2", "valence": 0.5, "arousal": 0.6},
            {"music_id": "3", "valence": 0.8, "arousal": 0.9},
        ],
    )
    _write_jsonl(
        prediction,
        [
            {"music_id": "1", "valence": 0.3, "arousal": 0.4},
            {"music_id": "2", "valence": 0.5, "arousal": 0.6},
            {"music_id": "3", "valence": 0.7, "arousal": 0.8},
        ],
    )
    return reference, prediction


def _dynamic_files(tmp_path: Path) -> tuple[Path, Path]:
    reference = tmp_path / "ref_dynamic.jsonl"
    prediction = tmp_path / "pred_dynamic.jsonl"
    _write_jsonl(
        reference,
        [
            {"music_id": "1", "frame_time": 15.5, "valence": 0.2, "arousal": 0.4},
            {"music_id": "1", "frame_time": 16.0, "valence": 0.4, "arousal": 0.6},
            {"music_id": "1", "frame_time": 16.5, "valence": 0.6, "arousal": 0.8},
            {"music_id": "2", "frame_time": 15.5, "valence": 0.3, "arousal": 0.2},
            {"music_id": "2", "frame_time": 16.0, "valence": 0.5, "arousal": 0.5},
            {"music_id": "2", "frame_time": 16.5, "valence": 0.7, "arousal": 0.8},
        ],
    )
    _write_jsonl(
        prediction,
        [
            {"music_id": "1", "frame_time": 15.5, "valence": 0.25, "arousal": 0.45},
            {"music_id": "1", "frame_time": 16.0, "valence": 0.45, "arousal": 0.65},
            {"music_id": "1", "frame_time": 16.5, "valence": 0.65, "arousal": 0.85},
            {"music_id": "2", "frame_time": 15.5, "valence": 0.35, "arousal": 0.25},
            {"music_id": "2", "frame_time": 16.0, "valence": 0.55, "arousal": 0.55},
            {"music_id": "2", "frame_time": 16.5, "valence": 0.75, "arousal": 0.85},
        ],
    )
    return reference, prediction


def test_mer_routes_describe_static_and_dynamic() -> None:
    from sure_eval.evaluation.scripts import describe_pipeline

    static = describe_pipeline("mer", metric="rmse")
    assert static.task == "MER"
    assert static.pipeline_id == "mer.any.rmse.mer_jsonl_v1.mer_regression_v1"
    assert static.node_ids == ("normalization/mer_jsonl", "scoring/mer_regression")

    dynamic = describe_pipeline("mer", metric="dynamic_pcc")
    assert dynamic.task == "MER"
    assert dynamic.pipeline_id == "mer.any.dynamic_pcc.mer_jsonl_v1.mer_regression_v1"
    assert dynamic.node_ids == ("normalization/mer_jsonl", "scoring/mer_regression")


def test_mer_nodes_are_in_process_and_require_no_node_environment() -> None:
    from sure_eval.evaluation.env_check import NodeEnvChecker

    checker = NodeEnvChecker()
    for node_id in ("normalization/mer_jsonl", "scoring/mer_regression"):
        result = checker.check_node(node_id)
        assert result.status == "ok"
        assert result.runtime == "in_process"
        assert result.required is False


def test_mer_static_run_computes_all_five_metrics_and_writes_report(tmp_path: Path) -> None:
    from sure_eval.evaluation.scripts import run_task

    reference, prediction = _static_files(tmp_path)
    output_dir = tmp_path / "out_static"
    report = run_task(
        "mer",
        reference_jsonl=str(reference),
        sample_output=str(prediction),
        metric="rmse",
        output_dir=str(output_dir),
    )

    expected_rmse = math.sqrt((0.1**2 + 0.0**2 + 0.1**2) / 3.0)
    expected_mae = (0.1 + 0.0 + 0.1) / 3.0
    assert report.task == "MER"
    assert report.pipeline_id == "mer.any.rmse.mer_jsonl_v1.mer_regression_v1"
    assert report.score == pytest.approx(expected_rmse)

    payload = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    overall = payload["details"]["scoring"]["micro"]["overall"]
    assert overall["rmse"] == pytest.approx(expected_rmse)
    assert overall["mae"] == pytest.approx(expected_mae)
    assert overall["pcc"] == pytest.approx(1.0)
    assert overall["r2"] == pytest.approx(1.0 - (0.02 / 0.18))
    assert overall["ccc"] == pytest.approx((2.0 * (0.12 / 3.0)) / ((0.18 / 3.0) + (0.08 / 3.0)))
    assert [item["node_id"] for item in payload["pipeline_trace"]] == [
        "normalization/mer_jsonl",
        "scoring/mer_regression",
    ]
    assert set(payload["details"]["input_sha256"]) == {"reference_jsonl", "sample_output"}


def test_mer_dynamic_run_supports_micro_and_macro_song_aggregation(tmp_path: Path) -> None:
    from sure_eval.evaluation.scripts import run_task

    reference, prediction = _dynamic_files(tmp_path)
    report_micro = run_task(
        "mer",
        reference_jsonl=str(reference),
        sample_output=str(prediction),
        metric="dynamic_rmse",
        output_dir=str(tmp_path / "out_dyn_micro"),
    )
    assert report_micro.pipeline_id == "mer.any.dynamic_rmse.mer_jsonl_v1.mer_regression_v1"
    assert report_micro.score == pytest.approx(0.05)

    report_macro = run_task(
        "mer",
        reference_jsonl=str(reference),
        sample_output=str(prediction),
        metric="dynamic_pcc",
        aggregation="macro_song",
        output_dir=str(tmp_path / "out_dyn_macro"),
    )
    assert report_macro.pipeline_id == "mer.any.dynamic_pcc.mer_jsonl_v1.mer_regression_v1"
    assert report_macro.score == pytest.approx(1.0)
    assert report_macro.details["scoring"]["macro_song"]["num_songs"] == 2


def test_mer_rejects_mismatched_keys_and_malformed_rows(tmp_path: Path) -> None:
    from sure_eval.evaluation.tasks.mer.pipeline import evaluate_mer_files

    ref = tmp_path / "ref.jsonl"
    pred = tmp_path / "pred.jsonl"
    _write_jsonl(ref, [{"music_id": "1", "valence": 0.5, "arousal": 0.5}])
    _write_jsonl(pred, [{"music_id": "2", "valence": 0.5, "arousal": 0.5}])
    with pytest.raises(ValueError, match="identical music_id"):
        evaluate_mer_files(reference_jsonl=ref, sample_output=pred, metric="rmse")

    _write_jsonl(pred, [{"music_id": "1", "valence": "bad", "arousal": 0.5}])
    with pytest.raises(ValueError, match="valence must be a finite number"):
        evaluate_mer_files(reference_jsonl=ref, sample_output=pred, metric="rmse")

    _write_jsonl(pred, [{"music_id": "1", "frame_time": 15.5, "valence": 0.5, "arousal": 0.5}])
    with pytest.raises(ValueError, match="static MER rows must not include frame_time"):
        evaluate_mer_files(reference_jsonl=ref, sample_output=pred, metric="rmse")


def test_mer_cli_routes_describe_and_run(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from sure_eval.cli import app

    reference, prediction = _dynamic_files(tmp_path)
    pipeline_path = tmp_path / "mer_dynamic_pipeline.json"
    output_dir = tmp_path / "cli_out"
    runner = CliRunner()

    routes_res = runner.invoke(app, ["metric", "routes", "mer", "--json"])
    assert routes_res.exit_code == 0, routes_res.stdout
    routes_payload = json.loads(routes_res.stdout)
    assert routes_payload["count"] == 10

    describe_res = runner.invoke(
        app,
        [
            "metric",
            "describe",
            "mer",
            "--metric",
            "dynamic_ccc",
            "--output",
            str(pipeline_path),
            "--json",
        ],
    )
    assert describe_res.exit_code == 0, describe_res.stdout

    run_res = runner.invoke(
        app,
        [
            "metric",
            "run",
            "--pipeline",
            str(pipeline_path),
            "--reference-jsonl",
            str(reference),
            "--sample-output",
            str(prediction),
            "--output-dir",
            str(output_dir),
            "--json",
        ],
    )
    assert run_res.exit_code == 0, run_res.stdout
    run_payload = json.loads(run_res.stdout)
    assert run_payload["pipeline_id"] == "mer.any.dynamic_ccc.mer_jsonl_v1.mer_regression_v1"
    expected_ccc_v = (2.0 * (0.175 / 6.0)) / (2.0 * (0.175 / 6.0) + 0.05**2)
    expected_ccc_a = (2.0 * (0.275 / 6.0)) / (2.0 * (0.275 / 6.0) + 0.05**2)
    assert run_payload["score"] == pytest.approx((expected_ccc_v + expected_ccc_a) / 2.0)


def test_mer_generated_catalog_contains_all_ten_routes() -> None:
    catalog_path = Path("docs/pipeline_catalog.jsonl")
    rows = [json.loads(line) for line in catalog_path.read_text(encoding="utf-8").splitlines()]
    mer_rows = [row for row in rows if row["task"] == "MER"]

    assert len(mer_rows) == 10
    assert {row["metric"] for row in mer_rows} == {
        "rmse",
        "mae",
        "pcc",
        "r2",
        "ccc",
        "dynamic_rmse",
        "dynamic_mae",
        "dynamic_pcc",
        "dynamic_r2",
        "dynamic_ccc",
    }
    assert all(
        row["nodes"] == ["normalization/mer_jsonl", "scoring/mer_regression"] for row in mer_rows
    )


def test_mer_pipeline_id_helper_rejects_unknown_metric() -> None:
    from sure_eval.evaluation.tasks.mer.pipeline import pipeline_id_for_metric

    with pytest.raises(ValueError, match="Unsupported MER metric"):
        pipeline_id_for_metric("not_a_metric")

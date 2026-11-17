import json
from pathlib import Path

import pytest

from sure_eval.evaluation.cli_adapters import build_pipeline_spec, run_pipeline_spec
from sure_eval.evaluation.nodes.scoring.ear1_openbench.scorer import score

# Synthetic organizer handoff fixtures (EAR1_OpenBench_Scoring examples).
EAR1 = Path(__file__).parent / "fixtures" / "ear1_openbench"


@pytest.mark.parametrize("example", ["esd", "esr"])
def test_ear1_fixture_scores_match_openbench_contract(example):
    expected = json.loads((EAR1 / example / "expected.json").read_text())
    result = score(
        expected["task"],
        expected["track"],
        EAR1 / example / "submission.zip",
        EAR1 / example / "reference",
    )
    assert result == expected


@pytest.mark.parametrize(
    ("example", "metric", "track", "pipeline_id", "score_pct"),
    [
        ("esd", "der", "D1", "ear1.esd.d1.der.ear1_openbench_v1", 50.0),
        ("esr", "cpcer", "R1", "ear1.esr.r1.cpcer.ear1_openbench_v1", 62.5),
    ],
)
def test_ear1_describe_and_run_report(tmp_path, example, metric, track, pipeline_id, score_pct):
    pipeline = build_pipeline_spec(
        "ear1", metric=metric, track=track, output_path=tmp_path / "pipeline.json"
    )
    assert pipeline["pipeline_id"] == pipeline_id
    result = run_pipeline_spec(
        pipeline,
        output_dir=str(tmp_path / "out"),
        submission=str(EAR1 / example / "submission.zip"),
        reference_dir=str(EAR1 / example / "reference"),
    )
    assert result["score"] == pytest.approx(score_pct / 100)
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["pipeline_id"] == pipeline_id
    assert report["details"]["scoring_result"]["score_pct"] == score_pct
    assert report["details"]["scoring_result"]["track"] == track
    assert report["input_files"]["submission"].endswith("submission.zip")


def test_ear1_run_rejects_track_that_differs_from_route(tmp_path):
    pipeline = build_pipeline_spec("ear1", metric="der", track="D1")
    with pytest.raises(ValueError, match="scores track D1, not R1"):
        run_pipeline_spec(
            pipeline,
            output_dir=str(tmp_path / "out"),
            submission=str(EAR1 / "esd" / "submission.zip"),
            reference_dir=str(EAR1 / "esd" / "reference"),
            track="R1",
        )

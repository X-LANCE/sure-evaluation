from __future__ import annotations

from pathlib import Path

from sure_eval.evaluation.rps import EvaluationDatabase, EvaluationRecord, RPSCalculator


def test_rps_calculator_uses_sota_baseline() -> None:
    calculator = RPSCalculator()

    # aishell1 SOTA in reports/sota/sota_baseline.yaml is CER 0.80, lower is better.
    assert calculator.calculate("aishell1", 1.6) == 0.5


def test_rps_calculator_handles_zero_error_as_better_than_sota() -> None:
    calculator = RPSCalculator()

    assert calculator.calculate("aishell1", 0.0) == float("inf")


def test_evaluation_database_ranking_uses_latest_result(tmp_path: Path) -> None:
    db = EvaluationDatabase(tmp_path / "evaluations.json")
    db.add_record(EvaluationRecord(tool_name="tool_a", model_name=None, dataset="aishell1", metric="cer", score=1.0, rps=0.8, timestamp="2026-01-01T00:00:00"))
    db.add_record(EvaluationRecord(tool_name="tool_a", model_name=None, dataset="aishell1", metric="cer", score=2.0, rps=0.4, timestamp="2026-02-01T00:00:00"))
    db.add_record(EvaluationRecord(tool_name="tool_b", model_name=None, dataset="aishell1", metric="cer", score=1.2, rps=0.7, timestamp="2026-01-15T00:00:00"))

    assert db.get_best_tool("aishell1") == ("tool_b", 0.7)
    assert db.get_tool_ranking("aishell1") == [("tool_b", 0.7), ("tool_a", 0.4)]


def _record(tool_name: str) -> EvaluationRecord:
    return EvaluationRecord(tool_name=tool_name, model_name=None, dataset="aishell1", metric="cer", score=1.0, rps=None)


def test_evaluation_database_keeps_a_truncated_file_when_a_new_record_is_added(tmp_path: Path) -> None:
    db_path = tmp_path / "evaluations.json"
    EvaluationDatabase(db_path).add_record(_record("old_tool"))
    original = db_path.read_bytes()
    truncated = original[: len(original) // 2]
    db_path.write_bytes(truncated)

    EvaluationDatabase(db_path).add_record(_record("new_tool"))

    kept = [path.read_bytes() for path in tmp_path.iterdir() if path != db_path]
    assert truncated in kept
    assert [record.tool_name for record in EvaluationDatabase(db_path).get_records()] == ["new_tool"]


def test_evaluation_database_failed_write_leaves_the_previous_file_intact(tmp_path: Path, monkeypatch) -> None:
    from sure_eval.evaluation import rps

    db_path = tmp_path / "evaluations.json"
    db = EvaluationDatabase(db_path)
    db.add_record(_record("old_tool"))
    original = db_path.read_bytes()

    def fail_dump(*args, **kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(rps.json, "dump", fail_dump)
    db.add_record(_record("new_tool"))

    assert db_path.read_bytes() == original

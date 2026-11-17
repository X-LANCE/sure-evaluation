from __future__ import annotations

from pathlib import Path

from sure_eval.evaluation.sure_evaluator import SUREEvaluator


def test_asr_char_metric_is_reported_as_cer(tmp_path: Path) -> None:
    ref_file = tmp_path / "ref.txt"
    hyp_file = tmp_path / "hyp.txt"
    ref_file.write_text("utt1\tabc\n", encoding="utf-8")
    hyp_file.write_text("utt1\tadc\n", encoding="utf-8")

    result = SUREEvaluator(language="en").evaluate("ASR", str(ref_file), str(hyp_file), tochar=True)

    assert "cer" in result
    assert "wer" not in result
    assert result["score"] == result["cer"]


def _write_rows(path: Path, rows: list[str]) -> str:
    path.write_text("".join(f"{row}\n" for row in rows), encoding="utf-8")
    return str(path)


def test_asr_counts_an_empty_prediction_as_deletions(tmp_path: Path) -> None:
    ref = _write_rows(tmp_path / "ref.txt", ["u1\thello world", "u2\tgood morning everyone"])
    hyp = _write_rows(tmp_path / "hyp.txt", ["u1\thello world", "u2\t"])

    result = SUREEvaluator(language="en").evaluate("ASR", ref, hyp)

    assert (result["all"], result["del"]) == (5, 3)
    assert result["wer"] == 0.6


def test_codeswitch_asr_counts_an_empty_prediction_as_deletions(tmp_path: Path) -> None:
    ref = _write_rows(tmp_path / "ref.txt", ["u1\thello world", "u2\tgood morning everyone"])
    hyp = _write_rows(tmp_path / "hyp.txt", ["u1\thello world", "u2\t"])

    result = SUREEvaluator(language="cs").evaluate("ASR", ref, hyp)

    assert (result["mer_details"]["all"], result["mer_details"]["del"]) == (5, 3)
    assert result["mer"] == 0.6


def test_slu_counts_an_empty_prediction_as_a_wrong_answer(tmp_path: Path) -> None:
    import json

    prompts = tmp_path / "prompts.jsonl"
    prompts.write_text(
        "".join(
            json.dumps({"key": key, "prompt": f"What does the speaker want?\nA. {a}\nB. {b}"}) + "\n"
            for key, a, b in [("u1", "book a flight", "cancel a flight"), ("u2", "play music", "stop music")]
        ),
        encoding="utf-8",
    )
    ref = _write_rows(tmp_path / "ref.txt", ["u1\tB", "u2\tA"])
    hyp = _write_rows(tmp_path / "hyp.txt", ["u1\tB", "u2\t"])

    assert SUREEvaluator(language="en").evaluate("SLU", ref, hyp, prompt_jsonl=str(prompts)) == 0.5


def test_ser_keeps_rows_aligned_when_a_prediction_is_empty(tmp_path: Path) -> None:
    ref = _write_rows(tmp_path / "ref.txt", ["u1\tangry", "u2\thappy"])
    hyp = _write_rows(tmp_path / "hyp.txt", ["u1\t", "u2\thappy"])

    assert SUREEvaluator(language="en").evaluate("SER", ref, hyp) == 0.5


def test_gr_keeps_rows_aligned_when_a_prediction_is_empty(tmp_path: Path) -> None:
    ref = _write_rows(tmp_path / "ref.txt", ["u1\tmale", "u2\tfemale"])
    hyp = _write_rows(tmp_path / "hyp.txt", ["u1\t", "u2\tfemale"])

    assert SUREEvaluator(language="en").evaluate("GR", ref, hyp) == 0.5

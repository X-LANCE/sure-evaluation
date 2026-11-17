from __future__ import annotations

from sure_eval.evaluation.nodes.normalization.aispeech_norm.normalization_impl import asr_simple_tn as tn


def test_tn_zh_reads_a_digit_by_digit_pair_as_a_two_digit_number() -> None:
    assert tn.preprocess_zh_text("二零") == "二十"


def test_tn_zh_leaves_a_longer_digit_by_digit_run_alone() -> None:
    """A year or a phone number read digit by digit is not a two-digit number."""

    assert tn.preprocess_zh_text("二零二三年") == "二零二三年"
    assert tn.preprocess_zh_text("一三八一二") == "一三八一二"
    assert tn.preprocess_zh_text("二〇二三年") == "二〇二三年"

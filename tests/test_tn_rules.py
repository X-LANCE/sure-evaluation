from __future__ import annotations

from pathlib import Path

from sure_eval.evaluation.nodes.normalization.aispeech_norm.normalization_impl import asr_simple_tn as tn, default_map_dir


def test_tn_zh_reads_a_digit_by_digit_pair_as_a_two_digit_number() -> None:
    assert tn.preprocess_zh_text("二零") == "二十"


def test_tn_zh_leaves_a_longer_digit_by_digit_run_alone() -> None:
    """A year or a phone number read digit by digit is not a two-digit number."""

    assert tn.preprocess_zh_text("二零二三年") == "二零二三年"
    assert tn.preprocess_zh_text("一三八一二") == "一三八一二"
    assert tn.preprocess_zh_text("二〇二三年") == "二〇二三年"


def test_tn_maps_load_as_utf8_whatever_the_locale_encoding(monkeypatch) -> None:
    """On Windows with a Chinese locale, open() without an encoding decodes files as GBK."""

    import builtins

    def locale_open(file, mode="r", *args, encoding=None, **kwargs):
        if "b" not in mode and encoding is None:
            encoding = "gbk"
        return builtins.open(file, mode, *args, encoding=encoding, **kwargs)

    monkeypatch.setattr(tn, "open", locale_open, raising=False)

    pairs = tn.load_and_sort_map(str(Path(default_map_dir()) / "zh" / "symbol.map"), "zh")

    assert ("℃", "摄氏度") in pairs


def test_tn_en_rules_do_not_read_quotes_or_slashes_as_words() -> None:
    """Recognisers do not say "inches" for a quotation mark or "slash" for and/or."""

    en_rules = str(Path(default_map_dir()) / "en")

    assert "inches" not in tn.asr_num2words('he said "hello" to me', "en", en_rules, debug=False)
    assert "slash" not in tn.asr_num2words("we need both and/or rules", "en", en_rules, debug=False)

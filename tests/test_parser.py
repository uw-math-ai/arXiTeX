"""Parser behaviors: source handling, focus, validation, fallback, guards."""

import pytest

import arxitex as arx
from arxitex import Parser, Tex
from conftest import FIXTURE_PATHS


def test_positional_source_autodetects_local_path():
    res = Parser(method="regex", focus="statements").parse(str(FIXTURE_PATHS["simple"]))
    assert res.statements


def test_fallback_chain_records_method_used():
    # a bogus engine makes the tex method unavailable -> falls back to regex
    res = Parser(
        method=[Tex(engine="not-a-real-engine"), "regex"],
        focus="statements",
    ).parse(path=FIXTURE_PATHS["simple"])
    assert res.method_used == "regex"
    assert res.statements


def test_focus_preamble_only():
    res = Parser(method="regex", focus="preamble").parse(path=FIXTURE_PATHS["simple"])
    assert res.statements is None
    assert res.preamble is not None
    assert "documentclass" in res.preamble


def test_focus_bibliography_only():
    res = Parser(method="regex", focus="bibliography").parse(path=FIXTURE_PATHS["simple"])
    assert res.statements is None
    assert res.preamble is None
    assert res.bibliography is not None  # empty dict when there is no bibliography


def test_context_guard_rejects_non_regex():
    with pytest.raises(ValueError):
        Parser(method="tex", context=50)


def test_unknown_method_string_rejected():
    with pytest.raises(ValueError):
        Parser(method="banana")


def test_requires_exactly_one_source():
    with pytest.raises(ValueError):
        Parser(method="regex").parse()  # nothing given
    with pytest.raises(ValueError):
        Parser(method="regex").parse("x", path="y")  # positional AND keyword


def test_bad_source_is_rejected():
    with pytest.raises(ValueError):
        Parser(method="regex").parse("this is not an id, path, or uri")


def test_validation_none_keeps_everything():
    res = Parser(method="regex", focus="statements", validation="none").parse(
        path=FIXTURE_PATHS["simple"]
    )
    assert res.statements


def test_kinds_filter():
    # keep only theorems -> lemmas/definitions/remarks dropped
    res = Parser(method="regex", focus="statements", kinds={"theorem"}).parse(
        path=FIXTURE_PATHS["simple"]
    )
    assert res.statements
    assert {s.kind for s in res.statements} == {"theorem"}

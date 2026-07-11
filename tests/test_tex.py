"""Real-TeX-engine parsing. Skipped when tectonic is not installed."""

import pytest

import arXiTeX as arx
from conftest import FIXTURE_PATHS, by_label, requires_tectonic

pytestmark = requires_tectonic


def parse(name, **kw):
    return arx.Parser(method="tex", focus="statements", timeout=180, **kw).parse(
        path=FIXTURE_PATHS[name]
    )


def test_simple_numbering_matches_real_counters():
    res = parse("simple")
    assert res.method_used == "tex"
    labeled = by_label(res.statements)

    assert labeled["def:norm"].ref == "1.1"
    assert labeled["thm:main"].ref == "1.2"
    assert labeled["lem:aux"].ref == "1.3"
    assert labeled["thm:main"].note == "Nonnegativity"
    assert labeled["thm:main"].proof is not None
    # unnumbered remark: no stale ref leaking from section counter
    assert any(s.kind == "remark" and s.ref is None for s in res.statements)


def test_multifile_native_input_resolution():
    res = parse("multifile")
    labeled = by_label(res.statements)
    assert labeled["prop:even"].ref == "1.1"
    assert labeled["thm:prelim"].ref == "1.1"
    assert labeled["thm:key"].ref == "2.1"
    assert labeled["thm:key"].proof is not None


def test_thmtools_native():
    res = parse("thmtools")
    labeled = by_label(res.statements)
    assert labeled["thm:t1"].ref == "1.1"
    assert labeled["cor:c1"].ref == "1.2"
    assert any(s.kind == "remark" and s.ref is None for s in res.statements)


def test_macros_fully_expanded_to_fixed_point():
    # tex expands user macros to a fixed point, including nested definitions
    res = parse("macros")
    labeled = by_label(res.statements)
    body = labeled["thm:macros"].body
    assert "\\operatorname{deg}" in body   # \deg -> \operatorname{deg}
    assert "\\mathbb{F}" in body           # \field -> \mathbb{F}
    assert "\\poly" not in body            # nested macro fully resolved
    assert "\\field" not in body


def test_no_statements_raises():
    with pytest.raises(RuntimeError):
        parse("no_statements")


def test_tex_matches_regex_on_simple():
    """The real engine and the regex fallback should agree on structure."""
    tex = by_label(parse("simple").statements)
    reg = by_label(
        arx.Parser(method="regex", focus="statements").parse(path=FIXTURE_PATHS["simple"]).statements
    )
    for key in ("def:norm", "thm:main", "lem:aux"):
        assert tex[key].ref == reg[key].ref
        assert tex[key].kind == reg[key].kind

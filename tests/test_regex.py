"""Regex-method parsing across the fixtures."""

import pytest

import arxitex as arx
from conftest import FIXTURE_PATHS, by_label, by_kind


def parse(name, **kw):
    return arx.Parser(method="regex", focus="statements", **kw).parse(
        path=FIXTURE_PATHS[name]
    )


def test_simple_numbering_and_kinds():
    res = parse("simple")
    assert res.method_used == "regex"
    labeled = by_label(res.statements)

    # definition/theorem/lemma share the section-based theorem counter
    assert labeled["def:norm"].ref == "1.1"
    assert labeled["thm:main"].ref == "1.2"
    assert labeled["lem:aux"].ref == "1.3"

    kinds = by_kind(res.statements)
    # second section theorem restarts at 2.1
    assert any(s.ref == "2.1" for s in kinds["theorem"])
    # unnumbered remark carries no ref
    assert any(s.kind == "remark" and s.ref is None for s in res.statements)


def test_simple_proof_and_note_and_macros():
    res = parse("simple")
    labeled = by_label(res.statements)

    # proof follows the theorem -> attached by adjacency
    assert labeled["thm:main"].proof is not None
    assert "positive-definiteness" in labeled["thm:main"].proof
    # note captured from the optional bracket argument
    assert labeled["thm:main"].note == "Nonnegativity"
    # user macros expanded (\R -> \mathbb{R}, \norm -> \left\lVert ...)
    assert "\\mathbb{R}" in labeled["def:norm"].body
    assert "\\left\\lVert" in labeled["def:norm"].body


def test_multifile_input_resolution():
    res = parse("multifile")
    labeled = by_label(res.statements)

    # statements from both \input files are present and numbered per section
    assert labeled["prop:even"].ref == "1.1"
    assert labeled["thm:prelim"].ref == "1.1"
    assert labeled["thm:key"].ref == "2.1"
    # proof attached, macro (\Z) expanded, nested align preserved
    assert labeled["thm:key"].proof is not None
    assert "\\mathbb{Z}" in labeled["thm:prelim"].body


def test_thmtools_sibling_and_unnumbered():
    res = parse("thmtools")
    labeled = by_label(res.statements)

    assert labeled["thm:t1"].ref == "1.1"
    assert labeled["cor:c1"].ref == "1.2"        # sibling shares the counter
    assert any(s.kind == "remark" and s.ref is None for s in res.statements)


def test_proof_attached_by_reference_not_adjacency():
    res = parse("proof_by_ref")
    labeled = by_label(res.statements)

    # the proof names Theorem \ref{thm:key}, even though a lemma sits between them
    assert labeled["thm:key"].proof is not None
    assert "4k^2" in labeled["thm:key"].proof
    assert labeled["lem:filler"].proof is None


def test_no_statements_raises():
    with pytest.raises(RuntimeError):
        parse("no_statements")


def test_context_capture():
    res = arx.Parser(method="regex", focus="statements", context=120).parse(
        path=FIXTURE_PATHS["simple"]
    )
    # at least one statement gets surrounding context populated
    assert any(s.pre_context or s.post_context for s in res.statements)


def test_collect_macros_let_def_csname():
    from arxitex.lib.statement.methods.regex.log_envs import (
        _collect_macros,
        _expand_macros,
    )

    src = r"""
    \newcommand{\field}{\mathbb{F}}
    \def\ring#1{\field[#1]}
    \let\F\field
    \let\Ring\ring
    \def\weird#1;#2.{DELIMITED}
    \let\prim\relax
    """
    macros = _collect_macros(src)

    # parameterised \def is collected with its arg count
    assert macros["\\ring"] == (1, r"\field[#1]")
    # \let aliases copy the target's definition
    assert macros["\\F"] == macros["\\field"]
    assert macros["\\Ring"] == macros["\\ring"]
    # delimited \def and \let to an unknown primitive are left out
    assert "\\weird" not in macros
    assert "\\prim" not in macros

    # aliases and \csname both expand
    assert _expand_macros(r"\F and \Ring{x}", macros) == r"\mathbb{F} and \field[x]"
    assert _expand_macros(r"\csname field\endcsname", macros) == r"\mathbb{F}"

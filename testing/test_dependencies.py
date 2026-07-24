"""Intra- and inter-paper dependency extraction (arxitex.lib.statement.dependencies)."""

from arxitex.types import Statement, DependencyScope
from arxitex.lib.statement.dependencies import resolve_dependencies


def _stmt(kind, body, *, labels=None, proof=None, note=None, begin=None, end=None):
    return Statement(
        kind=kind,
        body=body,
        labels=labels or [],
        proof=proof,
        note=note,
        begin_pos=begin,
        end_pos=end,
    )


# --- intra-paper -----------------------------------------------------------

def test_ref_in_proof_links_to_the_referenced_statement():
    statements = [
        _stmt("theorem", "The main result.", labels=["thm:main"]),
        _stmt("lemma", "A helper.", labels=["lem:help"],
              proof=r"Apply \ref{thm:main} to conclude."),
    ]
    edges = resolve_dependencies(statements)
    assert len(edges) == 1
    e = edges[0]
    assert e.scope == DependencyScope.INTRA
    assert e.source_index == 1 and e.target_index == 0
    assert e.target_label == "thm:main"
    assert e.origin == "proof"


def test_cref_in_body_is_recognized():
    statements = [
        _stmt("definition", "A widget.", labels=["def:widget"]),
        _stmt("theorem", r"Every \Cref{def:widget} is finite.", labels=["thm:x"]),
    ]
    edges = resolve_dependencies(statements)
    assert [e.target_index for e in edges] == [0]


def test_self_reference_is_dropped():
    statements = [
        _stmt("theorem", r"As in \ref{thm:main}, done.", labels=["thm:main"]),
    ]
    assert resolve_dependencies(statements) == []


def test_synthetic_inner_label_is_ignored():
    statements = [
        _stmt("lemma", "Inner.", labels=["inner-abc123"]),
        _stmt("theorem", r"See \ref{inner-abc123}.", labels=["thm:x"]),
    ]
    assert resolve_dependencies(statements) == []


def test_eqref_to_equation_is_dropped():
    # \eqref points at an equation, which is not a parsed statement, so nothing
    # resolves.
    statements = [
        _stmt("theorem", r"By \eqref{eq:1}, the claim holds.", labels=["thm:x"]),
    ]
    assert resolve_dependencies(statements) == []


def test_nested_child_reference_is_dropped():
    # A parent proof that states an auxiliary lemma along the way gets a spliced-in
    # \ref{child}; the child's span sits inside the parent, so it's not a real dep.
    statements = [
        _stmt("lemma", "Auxiliary.", labels=["lem:aux"], begin=100, end=150),
        _stmt("theorem", r"Big result. \ref{lem:aux}", labels=["thm:big"],
              begin=10, end=200),
    ]
    edges = resolve_dependencies(statements)
    assert edges == []


# --- inter-paper -----------------------------------------------------------
# Edges carry only cite_key (+ best-effort target_name); paper identity is
# resolved by keying cite_key into ParseResult.bibliography, not stored here.

def test_cite_with_optional_note_extracts_theorem_name():
    statements = [
        _stmt("theorem", r"By \cite[Theorem 3.2]{Smith}, this holds.",
              labels=["thm:x"]),
    ]
    edges = resolve_dependencies(statements)
    assert len(edges) == 1
    e = edges[0]
    assert e.scope == DependencyScope.INTER
    assert e.cite_key == "Smith"
    assert e.target_name == "Theorem 3.2"


def test_preceding_prose_name_is_captured():
    statements = [
        _stmt("theorem", r"By Lemma 2.1 of \cite{Jones} we are done.",
              labels=["thm:x"]),
    ]
    edges = resolve_dependencies(statements)
    assert len(edges) == 1
    assert edges[0].cite_key == "Jones"
    assert edges[0].target_name == "Lemma 2.1"


def test_cite_without_name_leaves_target_name_none():
    statements = [
        _stmt("theorem", r"See \cite{Unknown}.", labels=["thm:x"]),
    ]
    edges = resolve_dependencies(statements)
    assert len(edges) == 1
    e = edges[0]
    assert e.cite_key == "Unknown"
    assert e.target_name is None


def test_multi_key_cite_yields_one_edge_per_key():
    statements = [
        _stmt("theorem", r"See \cite{Smith,Jones}.", labels=["thm:x"]),
    ]
    edges = resolve_dependencies(statements)
    assert sorted(e.cite_key for e in edges) == ["Jones", "Smith"]


def test_duplicate_reference_is_deduplicated():
    statements = [
        _stmt("theorem", "Result.", labels=["thm:main"]),
        _stmt("lemma", r"Uses \ref{thm:main} and again \ref{thm:main}.",
              labels=["lem:x"]),
    ]
    edges = resolve_dependencies(statements)
    assert len(edges) == 1


def test_no_dependencies_when_nothing_references():
    statements = [
        _stmt("theorem", "A standalone claim.", labels=["thm:x"]),
    ]
    assert resolve_dependencies(statements) == []

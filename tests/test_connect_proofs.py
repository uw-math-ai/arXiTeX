"""Attaching proofs to the statements they prove."""

from arxitex.lib.statement.connect_proofs import connect_proofs
from arxitex.types import Statement


def _stmt(kind, label=None, note=None, body="body"):
    return Statement(kind=kind, label=label, note=note, body=body)


def test_proof_follows_its_statement_by_adjacency():
    out = connect_proofs([
        _stmt("theorem", label="thm:a"),
        _stmt("proof", body="Because reasons."),
    ])
    assert len(out) == 1                       # the proof is folded in, not returned
    assert out[0].proof == "Because reasons."


def test_proof_attaches_by_reference_across_an_intervening_statement():
    out = connect_proofs([
        _stmt("theorem", label="thm:key"),
        _stmt("lemma", label="lem:filler"),
        _stmt("proof", note=r"Proof of Theorem \ref{thm:key}", body="Odd squared is odd."),
    ])
    by_label = {s.label: s for s in out}
    assert by_label["thm:key"].proof == "Odd squared is odd."
    assert by_label["lem:filler"].proof is None   # adjacency must not win over the ref


def test_one_proof_covering_several_statements_attaches_to_all_of_them():
    # e.g. \begin{proof}[Proof of \Cref{prop:main} and \Cref{cor:main}]
    out = connect_proofs([
        _stmt("proposition", label="prop:main"),
        _stmt("corollary", label="cor:main"),
        _stmt("proof", note=r"Proof of \Cref{prop:main} and \Cref{cor:main}", body="Shared argument."),
    ])
    by_label = {s.label: s for s in out}
    assert by_label["prop:main"].proof == "Shared argument."
    assert by_label["cor:main"].proof == "Shared argument."


def test_a_statement_keeps_the_first_proof_it_is_given():
    out = connect_proofs([
        _stmt("theorem", label="thm:a"),
        _stmt("proof", note=r"Proof of \Cref{thm:a}", body="First proof."),
        _stmt("proof", note=r"Proof of \Cref{thm:a}", body="Second proof."),
    ])
    assert len(out) == 1
    assert out[0].proof == "First proof."


def test_a_multi_reference_proof_does_not_clobber_an_existing_proof():
    # thm:a already has its own proof; the shared proof only fills in cor:b
    out = connect_proofs([
        _stmt("theorem", label="thm:a"),
        _stmt("proof", body="Dedicated proof."),
        _stmt("corollary", label="cor:b"),
        _stmt("proof", note=r"Proof of \Cref{thm:a} and \Cref{cor:b}", body="Shared argument."),
    ])
    by_label = {s.label: s for s in out}
    assert by_label["thm:a"].proof == "Dedicated proof."
    assert by_label["cor:b"].proof == "Shared argument."


def test_unresolvable_reference_falls_back_to_adjacency():
    out = connect_proofs([
        _stmt("theorem", label="thm:a"),
        _stmt("proof", note=r"Proof of \Cref{does:not:exist}", body="Orphan-ish."),
    ])
    assert out[0].proof == "Orphan-ish."


def test_proof_after_a_non_theorem_attaches_to_nothing():
    out = connect_proofs([
        _stmt("remark", label="rem:a"),
        _stmt("proof", body="Dangling."),
    ])
    assert out[0].proof is None

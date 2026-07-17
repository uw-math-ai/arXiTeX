"""Attaching proofs to the statements they prove."""

from arxitex.lib.statement.connect_proofs import connect_proofs
from arxitex.types import Statement


def _stmt(kind, label=None, note=None, body="body", labels=None):
    return Statement(kind=kind, note=note, body=body,
                     labels=labels if labels is not None else ([label] if label else []))


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
    by_label = {lab: s for s in out for lab in s.labels}
    assert by_label["thm:key"].proof == "Odd squared is odd."
    assert by_label["lem:filler"].proof is None   # adjacency must not win over the ref


def test_one_proof_covering_several_statements_attaches_to_all_of_them():
    # e.g. \begin{proof}[Proof of \Cref{prop:main} and \Cref{cor:main}]
    out = connect_proofs([
        _stmt("proposition", label="prop:main"),
        _stmt("corollary", label="cor:main"),
        _stmt("proof", note=r"Proof of \Cref{prop:main} and \Cref{cor:main}", body="Shared argument."),
    ])
    by_label = {lab: s for s in out for lab in s.labels}
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
    by_label = {lab: s for s in out for lab in s.labels}
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


def test_proof_connects_via_a_statements_second_label():
    # a restated theorem carries two \labels; the proof references the second.
    # Mirrors Theorem 1.13 of arXiv:2402.10823.
    out = connect_proofs([
        _stmt("theorem", label="thm:intro-name",
              labels=["thm:intro-name", "thm:body-name"]),
        _stmt("proof", note=r"Proof of \Cref{thm:body-name}", body="The argument."),
    ])
    by_label = {lab: s for s in out for lab in s.labels}
    assert by_label["thm:intro-name"].proof == "The argument."


def test_adjacency_walks_back_past_a_remark_to_the_corollary():
    # a remark wedged between a corollary and its (note-less) proof must not
    # block the connection. Mirrors Corollary 5.1 of arXiv:2402.10823.
    out = connect_proofs([
        _stmt("corollary", label="cor:x"),
        _stmt("remark", label="rmk:aside"),
        _stmt("proof", body="Hence the result."),
    ])
    by_label = {lab: s for s in out for lab in s.labels}
    assert by_label["cor:x"].proof == "Hence the result."
    assert by_label["rmk:aside"].proof is None


def test_adjacency_skips_the_proofs_own_nested_statement():
    # a fact restated inside the proof is spliced out and \ref'd in the proof
    # body, so it appears just before the proof in the list even though it's
    # part of it. Walk past it to the lemma. Mirrors arXiv:1010.3812.
    out = connect_proofs([
        _stmt("lemma", label="lem:main"),
        _stmt("fact", label="fct:inner"),
        _stmt("proof", body=r"We use the following. \ref{fct:inner} Hence the claim."),
    ])
    by_label = {lab: s for s in out for lab in s.labels}
    assert by_label["lem:main"].proof is not None
    assert by_label["fct:inner"].proof is None


def test_adjacency_does_not_walk_back_past_a_definition():
    # only commentary (remark/note/...) is skipped; a definition is substantive,
    # so a proof after one does not reach back to an earlier theorem
    out = connect_proofs([
        _stmt("theorem", label="thm:a"),
        _stmt("definition", label="def:b"),
        _stmt("proof", body="Unrelated."),
    ])
    by_label = {lab: s for s in out for lab in s.labels}
    assert by_label["thm:a"].proof is None
    assert by_label["def:b"].proof is None

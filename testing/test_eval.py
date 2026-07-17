"""The eval engine itself: elided-pattern matching, alignment, and field checks.

Pure and offline — synthetic statements only, no parser and no network. Guards
the harness that `test_parsers.py` relies on.
"""

import pytest

from arxitex.types import Statement

from eval import (
    PdfGroundTruth,
    PdfStatement,
    TexGroundTruth,
    pattern_score,
    score_pdf,
    score_tex,
)
from eval.annotate import _extract_json
from eval.normalize import norm_body, to_words


# --- normalization ---------------------------------------------------------

def test_norm_body_absorbs_benign_spacing_differences():
    # the tex engine emits detokenize spacing; regex does not. They must agree.
    assert norm_body(r"$\mathbb{R} ^n$ and $\mathbb{Z} $") == norm_body(r"$\mathbb{R}^n$ and $\mathbb{Z}$")
    assert norm_body(r"\mathbb {R}") == norm_body(r"\mathbb{R}")
    assert norm_body("a  \n  b") == "a b"
    assert norm_body(None) is None


def test_to_words_strips_math_and_markup():
    assert to_words(r"A \emph{norm} on $\mathbb{R}^n$ is nice") == ["a", "norm", "on", "is", "nice"]


# --- elided pattern matching (pdf mode) ------------------------------------

def test_pattern_score_matches_elided_transcription():
    body = to_words(r"Let $R$ and $K$ be as above and let $\cX$ be a thing that is a further root stack.")
    assert pattern_score("Let $R$ and $K$ be as above and let ... is a further root stack.", body) == 1.0


def test_pattern_score_tolerates_a_transcription_typo():
    body = to_words("maps to the closed point of the space")
    # "poitn" is a typo; overlap degrades gracefully instead of failing outright
    assert 0.6 < pattern_score("maps to the closed poitn of ...", body) < 1.0


def test_pattern_score_rejects_an_unrelated_body():
    body = to_words("Something completely different about elliptic curves.")
    assert pattern_score("Let $R$ be a discrete valuation ring ... root stack.", body) < 0.6


# --- pdf mode: only recorded fields are checked ----------------------------

def _pdf_gt(**stmt):
    return PdfGroundTruth(arxiv_id="0000.00000", statements=[stmt])


def test_pdf_ignores_fields_that_were_not_recorded():
    # no `number` and no `proof` recorded -> parser's ref/proof are not checked
    gt = _pdf_gt(kind="theorem", body="Every bounded sequence ... converges.")
    parsed = [Statement(kind="theorem", ref="9.9", body="Every bounded sequence of reals converges.",
                        proof="Trivial.")]
    report = score_pdf(parsed, gt)
    assert report.tp == 1 and report.clean


def test_pdf_flags_a_wrong_number_when_recorded():
    gt = _pdf_gt(kind="theorem", number="1.1", body="Every bounded sequence ... converges.")
    parsed = [Statement(kind="theorem", ref="9.9", body="Every bounded sequence of reals converges.")]
    report = score_pdf(parsed, gt)
    assert [d.field for d in report.matched[0].diffs] == ["number"]


def test_blank_proof_or_number_is_treated_as_not_recorded():
    # a vision model emitting `"proof": ""` must not read as "a proof exists",
    # or the eval fails parsers that correctly found none
    s = PdfStatement.model_validate(
        {"kind": "theorem", "number": "  ", "body": "Alpha ... omega.", "proof": ""}
    )
    assert s.proof is None
    assert s.number is None

    gt = _pdf_gt(kind="theorem", body="Alpha ... omega.", proof="")
    parsed = [Statement(kind="theorem", ref="1.1", body="Alpha beta gamma omega.")]
    report = score_pdf(parsed, gt)
    assert report.clean, "blank proof must not be scored as a missing proof"


def test_pdf_flags_a_missing_proof_when_recorded():
    gt = _pdf_gt(kind="corollary", number="1.6", body="Let $C$ be as above ... root stack.",
                 proof="... The result then follows from ...")
    parsed = [Statement(kind="corollary", ref="1.6", body="Let $C$ be as above and take a root stack.")]
    report = score_pdf(parsed, gt)
    assert [d.field for d in report.matched[0].diffs] == ["proof"]


def test_pdf_reports_phantoms_and_misses():
    gt = PdfGroundTruth(arxiv_id="0000.00000", statements=[
        {"kind": "theorem", "number": "1.1", "body": "Alpha beta gamma delta epsilon."},
        {"kind": "lemma", "number": "1.2", "body": "Zeta eta theta iota kappa."},
    ])
    parsed = [
        Statement(kind="theorem", ref="1.1", body="Alpha beta gamma delta epsilon."),
        Statement(kind="remark", ref="9.9", body="Totally unrelated filler sentence here."),
    ]
    report = score_pdf(parsed, gt)
    assert report.tp == 1
    assert report.fp == 1 and report.phantoms[0].ref == "9.9"
    assert report.fn == 1 and report.misses[0].number == "1.2"
    assert not report.clean


# --- tex mode: every field is checked --------------------------------------

def _tex_gt(*statements):
    return TexGroundTruth(tex_source="testing/fixtures/simple", statements=list(statements))


def test_tex_checks_every_field():
    gt = _tex_gt(Statement(kind="theorem", ref="1.1", note="Nice", labels=["thm:a"],
                           body="Alpha beta gamma delta.", proof="Because."))
    parsed = [Statement(kind="lemma", ref="9.9", note=None, labels=["thm:b"],
                        body="Alpha beta gamma delta.", proof=None)]
    report = score_tex(parsed, gt)
    assert report.tp == 1
    assert {d.field for d in report.matched[0].diffs} == {"kind", "ref", "note", "labels", "proof"}


# --- annotate: lenient JSON extraction from a model response ---------------

def test_extract_json_accepts_a_bare_object():
    assert _extract_json('{"note": "x", "statements": []}') == {"note": "x", "statements": []}


def test_extract_json_unwraps_a_markdown_fence():
    assert _extract_json('```json\n{"note": "x", "statements": []}\n```')["note"] == "x"


def test_extract_json_ignores_prose_around_the_object():
    content = 'Sure! Here is the annotation:\n{"note": "x", "statements": []}\nHope that helps.'
    assert _extract_json(content)["note"] == "x"


def test_extract_json_raises_when_there_is_no_object():
    with pytest.raises(ValueError, match="no JSON object"):
        _extract_json("I could not read that paper, sorry.")


def test_extract_json_tolerates_raw_newlines_inside_strings():
    # models routinely emit literal newlines in transcribed text; strict JSON
    # rejects them ("Invalid control character"), so the extractor must not.
    content = '{"note": "line one\nline two", "statements": []}'
    assert _extract_json(content)["note"] == "line one\nline two"


def test_extract_json_tolerates_raw_newlines_inside_a_fence():
    content = '```json\n{"note": "a\nb", "statements": []}\n```'
    assert _extract_json(content)["note"] == "a\nb"


# --- annotate: page batching + merge -------------------------------------

def test_batches_cover_every_page_and_overlap_by_one():
    from eval.annotate import _batches

    for n_pages in range(1, 20):
        for per_call in range(2, 6):
            ranges = _batches(n_pages, per_call, overlap=1)
            covered = {p for first, last in ranges for p in range(first, last)}
            assert covered == set(range(n_pages)), (n_pages, per_call)
            assert all(last - first <= per_call for first, last in ranges)
            # consecutive batches share exactly one page, so nothing straddling
            # a page break is only ever seen split
            for (a_first, a_last), (b_first, b_last) in zip(ranges, ranges[1:]):
                assert b_first < a_last, (n_pages, per_call)


def test_batches_single_page_and_short_paper():
    from eval.annotate import _batches

    assert _batches(1, 4) == [(0, 1)]
    assert _batches(3, 4) == [(0, 3)]


def test_batches_rejects_zero_pages_per_call():
    from eval.annotate import _batches

    with pytest.raises(ValueError, match="pages_per_call"):
        _batches(5, 0)


def test_merge_drops_overlap_duplicates_by_number():
    from eval.annotate import _merge

    a = [PdfStatement(kind="theorem", number="1.1", body="alpha ... omega"),
         PdfStatement(kind="lemma", number="1.2", body="beta ... psi")]
    b = [PdfStatement(kind="lemma", number="1.2", body="beta ... psi"),   # overlap dup
         PdfStatement(kind="corollary", number="1.3", body="gamma ... chi")]
    merged = _merge([a, b])
    assert [s.number for s in merged] == ["1.1", "1.2", "1.3"]


def test_merge_dedupes_unnumbered_statements_by_body():
    from eval.annotate import _merge

    s = PdfStatement(kind="remark", body="This unnumbered remark says something.")
    merged = _merge([[s], [s]])
    assert len(merged) == 1


def test_merge_keeps_a_proof_only_a_later_batch_could_see():
    # the theorem is on page 4 (batch 1) but its proof starts on page 5, so only
    # batch 2 sees the proof at all — dropping the duplicate would lose it
    from eval.annotate import _merge

    early = PdfStatement(kind="theorem", number="1.5", body="Let $R$ ... is proper.")
    late = PdfStatement(kind="theorem", number="1.5", body="Let $R$ ... is proper.",
                        proof="We first assume ... hence the claim.")
    merged = _merge([[early], [late]])
    assert len(merged) == 1
    assert merged[0].proof == "We first assume ... hence the claim."


def test_merge_prefers_a_finished_proof_over_one_that_runs_off():
    # batch 1 saw the proof start but no QED marker (trails off); batch 2 saw it
    # end. The finished transcription wins.
    from eval.annotate import _merge

    runs_off = PdfStatement(kind="theorem", number="2.1", body="Alpha ... omega.",
                            proof="We first assume ...")
    finished = PdfStatement(kind="theorem", number="2.1", body="Alpha ... omega.",
                            proof="We first assume ... which concludes the argument.")
    assert _merge([[runs_off], [finished]])[0].proof.endswith("concludes the argument.")
    # order must not matter
    assert _merge([[finished], [runs_off]])[0].proof.endswith("concludes the argument.")


def test_merge_prefers_a_body_seen_whole_over_a_tail_only_view():
    from eval.annotate import _merge

    tail_only = PdfStatement(kind="lemma", number="3.1", body="... and therefore it is flat.")
    whole = PdfStatement(kind="lemma", number="3.1", body="Let $X$ be smooth ... it is flat.")
    assert _merge([[tail_only], [whole]])[0].body.startswith("Let $X$")


def test_completeness_ranks_run_off_transcriptions():
    from eval.annotate import _completeness

    assert _completeness("Let X ... it is flat.") == 2      # both ends seen
    assert _completeness("Let X be a scheme ...") == 1      # runs past the page
    assert _completeness("... it is flat.") == 1            # started earlier
    assert _completeness("... middle of a proof ...") == 0  # neither end seen
    assert _completeness(None) == -1


def test_a_run_off_proof_still_matches_a_parser_that_found_the_whole_proof():
    # the payoff: a proof the model could only half-see must not fail the parser
    gt = _pdf_gt(kind="theorem", number="1.1", body="Alpha ... omega.",
                 proof="We first assume the ring is henselian ...")
    parsed = [Statement(
        kind="theorem", ref="1.1", body="Alpha beta gamma omega.",
        proof="We first assume the ring is henselian, and then reduce to that case "
              "by a limit argument, which concludes the proof.",
    )]
    report = score_pdf(parsed, gt)
    assert report.clean, "a run-off proof transcription must score leniently"


def test_annotated_response_validates_into_ground_truth():
    # the shape the prompt asks the model for must satisfy the schema
    data = _extract_json(
        '{"note": "uses tikz", "statements": ['
        '{"kind": "theorem", "number": "1.1", "body": "Let ... be a space ... is proper.",'
        ' "proof": "We first assume ... concludes the argument."},'
        '{"kind": "remark", "number": "1.2", "body": "We can factor ... representable."}]}'
    )
    gt = PdfGroundTruth(arxiv_id="2507.08642", annotator="anthropic/claude-opus-4-8",
                        note=data["note"], statements=data["statements"])
    assert gt.annotator == "anthropic/claude-opus-4-8"
    assert len(gt.statements) == 2
    assert gt.statements[0].proof is not None
    assert gt.statements[1].proof is None      # omitted -> ignored by the eval


def test_tex_passes_when_the_parse_matches_exactly():
    s = Statement(kind="theorem", ref="1.1", labels=["thm:a"], body=r"$\mathbb{R}^n$ is fine.")
    gt = _tex_gt(s)
    # same content, benign tex-engine spacing -> still clean
    parsed = [Statement(kind="theorem", ref="1.1", labels=["thm:a"], body=r"$\mathbb{R} ^n$ is fine.")]
    report = score_tex(parsed, gt)
    assert report.clean

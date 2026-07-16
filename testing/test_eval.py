"""The eval engine itself: elided-pattern matching, alignment, and field checks.

Pure and offline — synthetic statements only, no parser and no network. Guards
the harness that `test_parsers.py` relies on.
"""

import pytest

from arxitex.types import Statement

from eval import PdfGroundTruth, TexGroundTruth, pattern_score, score_pdf, score_tex
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
    gt = _tex_gt(Statement(kind="theorem", ref="1.1", note="Nice", label="thm:a",
                           body="Alpha beta gamma delta.", proof="Because."))
    parsed = [Statement(kind="lemma", ref="9.9", note=None, label="thm:b",
                        body="Alpha beta gamma delta.", proof=None)]
    report = score_tex(parsed, gt)
    assert report.tp == 1
    assert {d.field for d in report.matched[0].diffs} == {"kind", "ref", "note", "label", "proof"}


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
    s = Statement(kind="theorem", ref="1.1", label="thm:a", body=r"$\mathbb{R}^n$ is fine.")
    gt = _tex_gt(s)
    # same content, benign tex-engine spacing -> still clean
    parsed = [Statement(kind="theorem", ref="1.1", label="thm:a", body=r"$\mathbb{R} ^n$ is fine.")]
    report = score_tex(parsed, gt)
    assert report.clean

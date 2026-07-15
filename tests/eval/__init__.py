"""
Parser eval: score arXiTeX parser configurations against ground truth.

This scores parser *output* — it is a measurement tool, driven from the CLI::

    cd tests && python -m eval.run --mode pdf -m regex

It is deliberately *not* a pytest suite: tests for the parser itself live in
ordinary ``tests/test_*.py`` files and have nothing to do with ground truth.

Ground truth lives under ``tests/ground_truth/``, split by what the parser is
scored against, with different strictness for each:

    tex/   a local .tex file/folder. Ground truth is the *full expected parse* —
           every field of every statement is checked. Catches runtime bugs.
    pdf/   a real arXiv paper. Ground truth is only what a reader sees in the
           PDF (kind, number, an elided body/proof); anything not recorded is
           ignored.
"""

from .schema import (
    PdfGroundTruth,
    PdfStatement,
    TexGroundTruth,
    load_ground_truth,
)
from .compare import (
    FieldDiff,
    PairVerdict,
    PaperReport,
    MATCH_THRESHOLD,
    pattern_score,
    score,
    score_pdf,
    score_tex,
)
from .harness import resolve_source, run

__all__ = [
    "PdfGroundTruth",
    "PdfStatement",
    "TexGroundTruth",
    "load_ground_truth",
    "FieldDiff",
    "PairVerdict",
    "PaperReport",
    "MATCH_THRESHOLD",
    "pattern_score",
    "score",
    "score_pdf",
    "score_tex",
    "resolve_source",
    "run",
]

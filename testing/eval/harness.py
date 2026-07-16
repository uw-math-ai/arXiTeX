"""
Run a parser over ground truth and collect the reports.

This is the measurement layer behind ``python -m eval.run``. It never asserts —
scoring parser *output* is a thing you look at, not a pass/fail test. (Tests for
the parser itself are ordinary pytest files under ``testing/``.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional

from .compare import PaperReport, score
from .schema import load_ground_truth

REPO_ROOT = Path(__file__).resolve().parents[2]
GT_DIR = Path(__file__).resolve().parent.parent / "ground_truth"


def gt_dir(mode: str) -> Path:
    return GT_DIR / mode


def resolve_source(gt, overrides: Optional[Dict[str, str]] = None) -> dict:
    """Return the kwargs to hand to ``Parser.parse`` for this ground truth."""
    overrides = overrides or {}
    if gt.name in overrides:
        return {"path": overrides[gt.name]}
    if getattr(gt, "tex_source", None):                  # local .tex file/folder
        return {"path": str(REPO_ROOT / gt.tex_source)}
    if getattr(gt, "arxiv_id", None):                    # download from arXiv
        return {"arxiv_id": gt.arxiv_id}
    raise ValueError(f"ground truth {gt.name!r} has no tex_source or arxiv_id")


def run(
    parser,
    mode: str,
    only: Optional[Iterable[str]] = None,
    overrides: Optional[Dict[str, str]] = None,
    config: str = "",
) -> list[PaperReport]:
    """Score *parser* against every ground truth of *mode*; return the reports.

    *only* filters to specific ground-truth file stems.
    """
    truths = load_ground_truth(mode, gt_dir(mode))
    if only is not None:
        truths = {k: v for k, v in truths.items() if k in set(only)}

    reports: list[PaperReport] = []
    for stem, gt in truths.items():
        try:
            result = parser.parse(**resolve_source(gt, overrides))
            if result.statements is None:
                raise ValueError("parser returned no statements; use focus='statements'")
            report = score(result.statements, gt, config=config or mode)
        except Exception as exc:  # a parse failure is a total miss for this paper
            report = PaperReport(gt.name, config or mode, mode,
                                 misses=list(gt.statements), error=str(exc))
        report.name = stem
        reports.append(report)
    return reports

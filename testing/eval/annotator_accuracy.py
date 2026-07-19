"""
Measure how well the vision-LLM annotator reproduces the human ground truth.

For every *human*-annotated paper under ``ground_truth/pdf/``, this re-annotates
the same paper with the vision model and scores the model's annotation against
the human one (treated as fact). If the model agrees closely, it's safe to use
it to expand the test set without hand-annotating every paper.

The human annotation is the ground truth; the model's annotation is the thing
under test. The model records only kind, number, and body (proofs are left to
human annotators), so that's what we grade. Per paper:

    detection recall     did the model find the statements the human recorded?
    detection precision  are the model's statements real (in the human set)?
    kind / number        on the statements both found, do they agree?

Run it from the ``testing/`` directory (needs NEBIUS_API_KEY in .env):

    cd testing
    python -m eval.annotator_accuracy
    python -m eval.annotator_accuracy --model google/gemma-3-27b-it
    python -m eval.annotator_accuracy --only 2503.05363 --max-pages 4   # cheap smoke test

Results are printed and written to a .txt file (``--out``).
"""

from __future__ import annotations

import datetime
import sys
from argparse import ArgumentParser
from pathlib import Path

from arxitex.types import Statement

from .annotate import DEFAULT_BASE_URL, DEFAULT_MODEL, annotate
from .compare import PaperReport, score_pdf
from .harness import gt_dir
from .schema import PdfGroundTruth, load_ground_truth

_RULE = "=" * 78


def is_human(gt: PdfGroundTruth) -> bool:
    """Human annotators are recorded by name; LLMs by a ``provider/model`` id."""
    return "/" not in gt.annotator


def as_statements(gt: PdfGroundTruth) -> list[Statement]:
    """View a PDF annotation as parser output, so score_pdf can grade it."""
    return [
        Statement(kind=s.kind, ref=s.number, body=s.body, proof=s.proof)
        for s in gt.statements
    ]


def _field_ok(verdict, field: str) -> bool:
    return not any(d.field == field for d in verdict.diffs)


class Tally:
    """Running counts for the fields we grade, so we can print per-field rates."""

    def __init__(self) -> None:
        self.tp = self.fp = self.fn = 0
        self.kind_ok = 0
        self.num_ok = self.num_total = 0

    def add(self, report: PaperReport) -> None:
        self.tp += report.tp
        self.fp += report.fp
        self.fn += report.fn
        for v in report.matched:
            self.kind_ok += _field_ok(v, "kind")
            if v.gt.number is not None:
                self.num_total += 1
                self.num_ok += _field_ok(v, "number")


def _pct(n: int, d: int) -> str:
    return f"{(100 * n / d):5.1f}%" if d else "   n/a"


def _paper_lines(name: str, human: int, report: PaperReport) -> list[str]:
    if report.error:
        return [f"{name}", f"  ! annotation failed: {report.error}"]
    model_n = report.tp + report.fp
    kind_ok = sum(_field_ok(v, "kind") for v in report.matched)
    num_ok = sum(_field_ok(v, "number") for v in report.matched if v.gt.number is not None)
    num_tot = sum(1 for v in report.matched if v.gt.number is not None)
    return [
        f"{name}   human={human} stmts, model={model_n} stmts",
        f"  detection : found {report.tp}/{human} (recall {_pct(report.tp, human)}), "
        f"precision {report.tp}/{model_n} ({_pct(report.tp, model_n)})   "
        f"missed {report.fn}, invented {report.fp}",
        f"  kind      : {kind_ok}/{report.tp}",
        f"  number    : {num_ok}/{num_tot}   (pairs where the human recorded a number)",
    ]


def _header(model: str, n_papers: int) -> list[str]:
    return [
        "arXiTeX vision-annotator accuracy vs human ground truth",
        f"  model  : {model}",
        f"  papers : {n_papers}",
        f"  date   : {datetime.date.today()}",
        _RULE,
    ]


def _overall(tally: Tally) -> list[str]:
    out = [
        "",
        _RULE,
        "OVERALL",
        f"  statements (human)   : {tally.tp + tally.fn}",
        f"  detection recall     : {_pct(tally.tp, tally.tp + tally.fn)}   "
        f"(model found this share of the human statements)",
        f"  detection precision  : {_pct(tally.tp, tally.tp + tally.fp)}   "
        f"(this share of the model's statements are real)",
        f"  kind accuracy        : {_pct(tally.kind_ok, tally.tp)}",
        f"  number accuracy      : {_pct(tally.num_ok, tally.num_total)}",
        "",
        "Human ground truth is treated as fact. 'invented' = a statement the model",
        "reported that the human did not; 'missed' = a human statement the model did not.",
    ]
    return out


def main(argv=None) -> None:
    ap = ArgumentParser(
        prog="eval.annotator_accuracy",
        description="Score the vision annotator against the human PDF ground truth.",
    )
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"vision model (default: {DEFAULT_MODEL})")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--dpi", type=int, default=None, help="render resolution (annotator default if unset)")
    ap.add_argument("--pages-per-call", type=int, default=None)
    ap.add_argument("--max-pages", type=int, default=None, help="only the first N pages (cheap smoke test)")
    ap.add_argument("--only", nargs="+", default=None, help="restrict to these arxiv ids")
    ap.add_argument("--out", default=None, help="results .txt path (default: annotator_accuracy_<ts>.txt)")
    args = ap.parse_args(argv)

    # the annotator loads .env itself; do it here too so the key is available
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    except ImportError:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    truths = {stem: gt for stem, gt in load_ground_truth("pdf", gt_dir("pdf")).items()
              if is_human(gt)}
    if args.only:
        truths = {k: v for k, v in truths.items() if k in set(args.only)}
    if not truths:
        print("No human-annotated pdf ground truth found.", file=sys.stderr)
        return

    kw = {k: v for k, v in {
        "model": args.model, "base_url": args.base_url, "api_key": args.api_key,
        "dpi": args.dpi, "pages_per_call": args.pages_per_call, "max_pages": args.max_pages,
    }.items() if v is not None}

    from tqdm import tqdm

    out = Path(args.out) if args.out else Path(
        f"annotator_accuracy_{datetime.datetime.now():%Y%m%d-%H%M}.txt")

    # Stream results: each paper is printed and appended to the .txt the moment
    # it finishes, so a long run is watchable rather than silent until the end.
    def emit(lines: list[str], f) -> None:
        block = "\n".join(lines)
        tqdm.write(block)
        f.write(block + "\n")
        f.flush()

    tally = Tally()
    with out.open("w", encoding="utf-8") as f:
        emit(_header(args.model, len(truths)), f)
        bar = tqdm(sorted(truths.items()), desc="annotating", unit="paper")
        for stem, human_gt in bar:
            try:
                model_gt = annotate(human_gt.arxiv_id, verbose=False, **kw)
                report = score_pdf(as_statements(model_gt), human_gt, config=args.model)
            except Exception as exc:
                report = PaperReport(stem, args.model, "pdf",
                                     misses=list(human_gt.statements), error=str(exc))
            report.name = stem
            if not report.error:
                tally.add(report)
            emit([""] + _paper_lines(stem, len(human_gt.statements), report), f)
        emit(_overall(tally), f)

    print(f"\nWrote results to {out}")


if __name__ == "__main__":
    main()

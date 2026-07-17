"""
Score a parser's *output* against ground truth and print the results.

This is a measurement tool, not a test — it always exits 0 and just reports.
Configure the parser exactly as you would to actually parse (same flags as the
``arxitex`` CLI), then look at what it got wrong.

Run it from the ``testing/`` directory so the ``eval`` package is importable:

    cd testing

    python -m eval.run --mode pdf -m regex
    python -m eval.run --mode tex  -m tex -m regex --engine pdflatex
    python -m eval.run --mode pdf -m regex --only 2507.08642
    python -m eval.run --mode pdf -m regex --out results.txt   # also save to a .txt

Ground truth lives in ``testing/ground_truth/{pdf,tex}/``. ``pdf`` papers are
downloaded from arXiv; ``tex`` ones are parsed from local sources.
"""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path

from arxitex import Llm, Parser, Tex

from .compare import PaperReport
from .harness import run

_RULE = "=" * 78


def _build_methods(args) -> list:
    """Same construction as the arxitex CLI, so flags mean the same thing."""
    methods = []
    for name in args.method:
        if name == "tex":
            methods.append(Tex(engine=args.engine, timeout=args.timeout))
        elif name == "llm":
            methods.append(Llm(model=args.model, api_key=args.api_key, base_url=args.base_url))
        else:
            methods.append(name)
    return methods


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def format_report(reports: list[PaperReport], mode: str, method: str) -> str:
    tp = sum(r.tp for r in reports)
    fp = sum(r.fp for r in reports)
    fn = sum(r.fn for r in reports)
    ok = sum(r.field_ok for r in reports)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    out = [
        "arXiTeX parser eval",
        f"  mode   : {mode}",
        f"  method : {method}",
        f"  papers : {len(reports)}",
        _RULE,
    ]

    for r in reports:
        out.append("")
        out.append(f"{r.name}")
        if r.error:
            out.append(f"  ! parse error: {r.error}")
            continue
        out.append(
            f"  matched {r.tp}/{r.tp + r.fn}   phantom {r.fp}   miss {r.fn}   "
            f"fields {r.field_ok}/{r.tp}"
        )
        detail = r.format().splitlines()[1:]     # drop the header line
        out.extend(detail or ["  all correct"])

    out += [
        "",
        _RULE,
        f"TOTAL   TP={tp}  FP={fp}  FN={fn}",
        f"        precision {_pct(prec)}   recall {_pct(rec)}   F1 {_pct(f1)}",
        f"        fields    {ok}/{tp} ({_pct(ok / tp if tp else 1.0)})",
        "",
        "TP=matched  FP=phantom (parsed, not in ground truth)  FN=miss (in ground truth, not parsed)",
        "fields=matched statements with every checked field correct",
    ]
    return "\n".join(out)


def main(argv=None) -> None:
    ap = ArgumentParser(
        prog="eval.run",
        description="Score a parser's output against PDF/TeX ground truth.",
    )
    ap.add_argument("--mode", choices=("pdf", "tex"), default="pdf",
                    help="which ground truth to score against (default: pdf)")
    ap.add_argument("-m", "--method", action="append", default=None,
                    help="Parsing method: regex, tex, or llm. Repeat for a fallback chain. "
                         "Default: tex then regex.")
    ap.add_argument("--engine", default="tectonic",
                    help="TeX engine for the 'tex' method (tectonic or pdflatex).")
    ap.add_argument("--model", default="deepseek-ai/DeepSeek-V4-Pro",
                    help="Model name for the 'llm' method (as the host names it).")
    ap.add_argument("--base-url", default="https://api.studio.nebius.com/v1",
                    help="OpenAI-compatible endpoint for the 'llm' method.")
    ap.add_argument("--api-key", default=None,
                    help="API key for the 'llm' method (else NEBIUS_API_KEY, then OPENAI_API_KEY).")
    ap.add_argument("--timeout", type=int, default=None, help="Max seconds per parse.")
    ap.add_argument("--only", nargs="+", default=None,
                    help="Only score these ground-truth files (by name, e.g. 2507.08642).")
    ap.add_argument("--source", action="append", default=[], metavar="ID=PATH",
                    help="Parse a local path for this paper instead of downloading it.")
    ap.add_argument("--out", default=None,
                    help="Also write the results to this .txt file.")
    args = ap.parse_args(argv)

    if args.method is None:
        args.method = ["tex", "regex"]

    parser = Parser(method=_build_methods(args), focus="statements", timeout=args.timeout)
    overrides = dict(s.split("=", 1) for s in args.source)
    method_label = " -> ".join(args.method)

    reports = run(parser, args.mode, only=args.only, overrides=overrides, config=method_label)
    if not reports:
        print(f"No {args.mode} ground truth found"
              + (f" matching {args.only}." if args.only else "."), file=sys.stderr)
        return

    text = format_report(reports, args.mode, method_label)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"\nWrote results to {args.out}")


if __name__ == "__main__":
    main()

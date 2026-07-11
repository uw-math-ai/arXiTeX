"""
Command-line interface for arxitex.

Examples
--------
    arxitex 2109.06451
    arxitex path/to/paper/ -o statements.jsonl
    arxitex 2109.06451 -m tex -m regex          # fallback chain
    arxitex 2109.06451 -m tex --engine pdflatex
    arxitex 2109.06451 -m llm --model openai/gpt-4o
"""

import sys
from argparse import ArgumentParser
from pathlib import Path

from arxitex import Parser, Tex, Llm, STATEMENT_KINDS


def _build_methods(args):
    methods = []
    for name in args.method:
        if name == "tex":
            methods.append(Tex(engine=args.engine, timeout=args.timeout))
        elif name == "llm":
            methods.append(Llm(model=args.model, api_key=args.api_key))
        else:
            methods.append(name)
    return methods


def main() -> None:
    ap = ArgumentParser(prog="arxitex", description="Parse an arXiv/LaTeX paper into structured statements.")
    ap.add_argument("source", help="arXiv id, local path, or s3:// URI")
    ap.add_argument("-o", "--output", help="Write statements as JSONL to this file (default: stdout)")
    ap.add_argument(
        "-m", "--method", action="append", default=None,
        help="Parsing method: regex, tex, or llm. Repeat for a fallback chain. Default: tex then regex.",
    )
    ap.add_argument("--engine", default="tectonic", help="TeX engine for the 'tex' method (tectonic or pdflatex).")
    ap.add_argument("--model", default="anthropic/claude-sonnet-5", help="litellm model string for the 'llm' method.")
    ap.add_argument("--api-key", default=None, help="API key for the 'llm' method (else uses the provider's env var).")
    ap.add_argument("--kinds", nargs="+", default=None, help="Statement kinds to keep (default: broad preset).")
    ap.add_argument("--focus", default="all", help="all | statements | preamble | bibliography")
    ap.add_argument("--validation", default="paper", help="paper | statement | none")
    ap.add_argument("--context", type=int, default=0, help="Chars of surrounding text (regex method only).")
    ap.add_argument("--timeout", type=int, default=None, help="Max seconds for the parse.")
    ap.add_argument("--full-error", action="store_true", help="Show the full traceback on error.")
    args = ap.parse_args()

    if args.method is None:
        args.method = ["tex", "regex"]

    try:
        parser = Parser(
            method=_build_methods(args),
            kinds=set(args.kinds) if args.kinds else STATEMENT_KINDS,
            focus=args.focus,
            validation=args.validation,
            context=args.context,
            timeout=args.timeout,
        )
        result = parser.parse(args.source)
        statements = result.statements or []

        jsonl = "\n".join(s.model_dump_json() for s in statements)
        if args.output:
            Path(args.output).write_text(jsonl, encoding="utf-8")
            print(f"Wrote {len(statements)} statements (method={result.method_used}) to {args.output}")
        else:
            print(jsonl)
    except Exception as e:
        if args.full_error:
            raise
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

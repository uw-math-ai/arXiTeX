"""
Script for parsing a single paper. Not useful for parsing many papers quickly.

This is a thin convenience wrapper around the arxitex ``Parser``. For most uses
prefer the installed CLI:  ``arxitex <source> -o out.jsonl``  (see ``arxitex -h``).
"""

from argparse import ArgumentParser
from pathlib import Path

from arxitex import Parser


if __name__ == "__main__":
    arg_parser = ArgumentParser(description="Parse one paper into a JSONL of statements.")
    arg_parser.add_argument("-a", "--arxiv-id", default=None, help="arXiv id of a paper")
    arg_parser.add_argument("-p", "--paper-path", default=None, help="Path to a LaTeX file or directory")
    arg_parser.add_argument("-o", "--output-file", required=True, help="Path to output JSONL file")
    arg_parser.add_argument(
        "-m", "--method", action="append", default=None,
        help="Method: regex, tex, or llm. Repeat for a fallback chain. Default: tex then regex.",
    )
    arg_parser.add_argument("-v", "--validation", default="paper", help="paper (default), statement, or none")
    arg_parser.add_argument("-fe", "--full-error", action="store_true", help="Show the whole stack trace on error")
    args = arg_parser.parse_args()

    try:
        parser = Parser(
            method=args.method or ("tex", "regex"),
            validation=args.validation,
        )
        result = parser.parse(
            arxiv_id=args.arxiv_id,
            path=args.paper_path,
        )
        statements = result.statements or []

        Path(args.output_file).write_text(
            "\n".join(s.model_dump_json() for s in statements),
            encoding="utf-8",
        )
    except Exception as e:
        if args.full_error:
            raise
        print(e)

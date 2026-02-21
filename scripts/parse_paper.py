"""
Script for parsing a single paper. Not useful for parsing many papers quickly.
"""

from argparse import ArgumentParser
from arXiTeX.types import TheoremValidationLevel, Theorem
from typing import List
from arXiTeX.lib.theorem import parse_paper
from pathlib import Path

if __name__ == "__main__":
    arg_parser = ArgumentParser()

    arg_parser.add_argument(
        "-a",
        "--arxiv-id",
        type=str,
        required=False,
        default="",
        help="arXiv id of a paper"
    )

    arg_parser.add_argument(
        "-p",
        "--paper-path",
        type=str,
        required=False,
        default="",
        help="Path to a LaTeX file or directory of LaTeX files"
    )

    arg_parser.add_argument(
        "-o",
        "--output-file",
        type=str,
        required=True,
        help="Path to output JSONL file"
    )

    arg_parser.add_argument(
        "-v",
        "--validation-level",
        type=TheoremValidationLevel,
        required=False,
        default="paper",
        help="Level to validate theorems. Supported: paper (default), theorem"
    )

    arg_parser.add_argument(
        "-fe",
        "--full-error",
        action="store_true",
        help="Whether to show the whole stack trace on parsing error or just a simple message"
    )

    args = arg_parser.parse_args()

    try:
        theorems: List[Theorem] = parse_paper(
            arxiv_id=args.arxiv_id or None,
            paper_path=args.paper_path or None,
            validation_level=args.validation_level
        )

        json_out = "\n".join(theorem.model_dump_json() for theorem in theorems)
        out_path = Path(args.output_file)
        
        out_path.write_text(json_out)
    except Exception as e:
        if args.full_error:
            raise e
        else:
            print(e)
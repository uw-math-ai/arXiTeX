"""
Main file of statement module. Provides a helper to parse a paper for statements.
"""

import re
import shutil
from pathlib import Path
from typing import List, Optional, Set, Tuple
from tempfile import TemporaryDirectory
from arXiTeX.types import Statement, StatementValidationLevel, ParsingMethod
from arXiTeX.lib.utils.download_arxiv_paper import download_arxiv_paper
from .validate_statements import validate_statement, validate_statements
from .run_with_timeout import run_with_timeout
from .errors import ParseError, format_error
from .guess_main_file import guess_main_file
from .connect_proofs import connect_proofs

STATEMENT_KINDS = {
    "theorem", "lemma", "proposition", "corollary",
    "definition",
    "axiom", "postulate",
    "conjecture", "hypothesis",
    "proof",
    "remark", "note", "observation",
    "claim",
    "fact",
    "assumption",
    "notation", "convention"
}

_DOC_BEGIN_RE = re.compile(r'\\begin\s*\{document\}', re.IGNORECASE)


def _extract_preamble(tex: str) -> Optional[str]:
    m = _DOC_BEGIN_RE.search(tex)
    if not m:
        return None
    return tex[:m.start()].strip() or None


def parse_paper(
    arxiv_id: Optional[str] = None,
    s3_bundle_key: Optional[str] = None,
    s3_bytes_range: Optional[str] = None,
    paper_path: Optional[Path | str] = None,
    statement_kinds: Set[str] = STATEMENT_KINDS,
    parsing_method: ParsingMethod = ParsingMethod.PLASTEX,
    validation_level: StatementValidationLevel = StatementValidationLevel.Paper,
    timeout : Optional[int] = None
) -> Tuple[List[Statement], Optional[str]]:
    """
    Parses a LaTeX paper (from arXiv or a local file) for statements. Validates the parsed, filtered
    statements at a specified level.

    Parameters
    ----------
    arxiv_id : str, optional
        arXiv id of a paper. Either this or paper_path must be used.
    s3_bundle_key: str, optional
        Bundle key of paper in arXiv's S3 bucket. Default, None.
    s3_bytes_range: str, optional
        Bytes range of paper in arXiv's S3 bucket. Default, None.
    paper_path : Path | str, optional
        Path to a paper's LaTeX file or a folder of LaTeX files. Either this or arxiv_id must be
        used.
    statement_kinds : Set[str], optional
        Set of statement kinds to capture. Default, preset list.
    parsing_method : ParsingMethod, optional
        Method to parse. By default, plasTeX.
    validation_level : StatementValidationLevel, optional
        Level at which to validate statements. By default, paper-level.
    timeout : int, optional
        Maximum number of seconds to attempt parsing. By default, infinity.

    Returns
    -------
    statements : List[Statement]
        Parsed statements, all checked for validity.
    preamble : str, optional
        Raw LaTeX preamble (everything before \\begin{document}), or None if not found.
    """

    if timeout is not None and timeout > 0:
        @run_with_timeout(seconds=timeout)
        def _timed():
            return parse_paper(
                arxiv_id=arxiv_id,
                s3_bundle_key=s3_bundle_key,
                s3_bytes_range=s3_bytes_range,
                paper_path=paper_path,
                statement_kinds=statement_kinds,
                parsing_method=parsing_method,
                validation_level=validation_level,
                timeout=None,
            )
        return _timed()

    if arxiv_id is not None:
        with TemporaryDirectory() as temp_dir:
            try:
                paper_dir = download_arxiv_paper(
                    cwd=Path(temp_dir),
                    arxiv_id=arxiv_id,
                    s3_bundle_key=s3_bundle_key,
                    s3_bytes_range=s3_bytes_range
                )
            except Exception as e:
                raise RuntimeError(format_error(
                    ParseError.DOWNLOAD,
                    str(e)
                ))

            return _parse_paper(
                paper_dir,
                statement_kinds=statement_kinds,
                parsing_method=parsing_method,
                validation_level=validation_level
            )
    elif paper_path is not None:
        if isinstance(paper_path, str):
            paper_path = Path(paper_path)

        if paper_path.is_dir():
            return _parse_paper(
                paper_path,
                statement_kinds=statement_kinds,
                parsing_method=parsing_method,
                validation_level=validation_level
            )
        elif paper_path.is_file():
            with TemporaryDirectory() as temp_dir:
                paper_dir = Path(temp_dir)
                shutil.copy2(paper_path, paper_dir / paper_path.name)

                return _parse_paper(
                    paper_dir,
                    statement_kinds=statement_kinds,
                    parsing_method=parsing_method,
                    validation_level=validation_level
                )
        else:
            raise FileNotFoundError(format_error(
                ParseError.DOWNLOAD,
                "Downloaded paper source not found"
            ))
    else:
        raise FileNotFoundError(format_error(
            ParseError.SYNTAX,
            "arxiv_id and paper_path are both None"
        ))

def _parse_paper(
    paper_dir: Path,
    statement_kinds: Set[str] = STATEMENT_KINDS,
    parsing_method: ParsingMethod = ParsingMethod.PLASTEX,
    validation_level: StatementValidationLevel = StatementValidationLevel.Paper
) -> Tuple[List[Statement], Optional[str]]:

    try:
        main_file = guess_main_file(paper_dir)
    except Exception as e:
        raise RuntimeError(format_error(
            ParseError.PARSING,
            str(e)
        ))

    # Extract preamble from the flattened source, independent of parsing method.
    preamble = None
    try:
        from .methods.regex.flatten import flatten_tex
        flat = flatten_tex(paper_dir, main_file, ignore_errors=True)
        preamble = _extract_preamble(flat)
    except Exception:
        pass

    if parsing_method == ParsingMethod.PLASTEX:
        from .methods.plasTeX import parse
        error_type = ParseError.PLASTEX
    else:
        from .methods.regex import parse
        error_type = ParseError.REGEX

    try:
        statements: List[Statement] = parse(paper_dir, main_file)
    except Exception as e:
        raise RuntimeError(format_error(
            error_type,
            str(e)
        ))

    if len(statements) == 0:
        raise RuntimeError(format_error(
            ParseError.EMPTY,
            "No environments found"
        ))

    statements = [
        statement.model_copy(update={"kind": sk})
        for statement in statements
        if (sk := next((sk for sk in statement_kinds if sk in statement.kind), None)) is not None
    ]

    if len(statements) == 0:
        raise RuntimeError(format_error(
            ParseError.EMPTY,
            "No statements found"
        ))

    match validation_level:
        case StatementValidationLevel.Statement:
            valid_statements: List[Statement] = []

            for statement in statements:
                try:
                    validate_statement(statement)
                    valid_statements.append(statement)
                except Exception:
                    pass

            if len(valid_statements) == 0:
                raise ValueError(format_error(
                    ParseError.VALIDATION,
                    "All statements are invalid"
                ))

            statements = valid_statements

        case StatementValidationLevel.Paper:
            validate_statements(statements)

    return connect_proofs(statements), preamble

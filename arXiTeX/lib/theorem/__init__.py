"""
Main file of theorem module. Provides a helper to parse a paper for theorems.
"""

import shutil
from pathlib import Path
from typing import List, Optional
from tempfile import TemporaryDirectory
from argparse import ArgumentParser
from arXiTeX.types import Theorem, TheoremValidationLevel
from arXiTeX.lib.utils.download_arxiv_paper import download_arxiv_paper
from .parse_by_plastex import parse_by_plastex
from .validate_theorems import validate_theorems, validate_theorem
from .run_with_timeout import run_with_timeout
from .errors import ParseError, format_error

def parse_paper(
    arxiv_id: Optional[str] = None,
    s3_bundle_key: Optional[str] = None,
    s3_bytes_range: Optional[str] = None,
    paper_path: Optional[Path | str] = None,
    validation_level: TheoremValidationLevel = TheoremValidationLevel.Paper,
    timeout : Optional[int] = None
) -> List[Theorem]:
    """
    Parses a LaTeX paper (from arXiv or a local file) for theorems. Validates the parsed theorems
    at a specified level.

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
    validation_level : TheoremValidationLevel, optional
        Level at which to validate theorems. By default, paper-level.
    timeout : int, optional
        Maximum number of seconds to attempt parsing. By default, infinity.
    
    Returns
    -------
    theorems : List[Theorem]
        Parsed theorems, all checked for validity.
    """

    if timeout is not None and timeout > 0:
        @run_with_timeout(seconds=timeout)
        def parse_paper_with_timeout():
            return parse_paper(
                arxiv_id=arxiv_id,
                s3_bundle_key=s3_bundle_key,
                s3_bytes_range=s3_bytes_range,
                paper_path=paper_path,
                validation_level=validation_level,
                timeout=None
            )

        return parse_paper_with_timeout()

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
                
            return _parse_paper(paper_dir, validation_level=validation_level)
    elif paper_path is not None:
        if isinstance(paper_path, str):
            paper_path = Path(paper_path)
        
        if paper_path.is_dir():
            return _parse_paper(paper_path, validation_level=validation_level)
        elif paper_path.is_file():
            with TemporaryDirectory() as temp_dir:
                paper_dir = Path(temp_dir)
                shutil.copy2(paper_path, paper_dir / paper_path.name)

                return _parse_paper(paper_dir, validation_level=validation_level)
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
    validation_level: TheoremValidationLevel = TheoremValidationLevel.Paper
) -> List[Theorem]:
    try:
        theorems: List[Theorem] = parse_by_plastex(paper_dir)
    except Exception as e:
        raise RuntimeError(format_error(
            ParseError.PLASTEX,
            str(e)
        ))

    match validation_level:
        case TheoremValidationLevel.Theorem:
            valid_theorems: List[Theorem] = []

            for theorem in theorems:
                try:
                    validate_theorem(theorem)
                    valid_theorems.append(theorem)
                except Exception:
                    pass

            if len(valid_theorems) == 0:
                raise ValueError(format_error(
                    ParseError.VALIDATION,
                    "All theorems are invalid"
                ))

            return valid_theorems
        
        case TheoremValidationLevel.Paper:
            validate_theorems(theorems)

            return theorems

from pydantic import BaseModel
from typing import Optional, List, Dict
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

class ArXivPaper(BaseModel):
    arxiv_id: str
    title: str
    authors: List[str]
    url: str
    categories: List[str]
    updated_at: datetime
    journal_ref: Optional[str]
    doi: Optional[str]
    license: Optional[str]
    abstract: str
    citation_count: Optional[int]
    reference_ids: List[str]

class ParsingMethod(str, Enum):
    PLASTEX = "plasTeX"
    REGEX = "regex"

class Statement(BaseModel):
    """
    Statement object.

    Attributes
    ----------
    kind : str
        The statement's type
    ref : str
        The statement's number (e.g. 1.1 or A.1)
    note : str, optional
        The statement's note, usually representing a title or caption
    label : str, optional
        The statement's label. Used to reference a theorem
    body : str
        The statement's raw LaTeX body with simple macros resolved
    proof : str, optional
        The statement's proof, if it exists
    """

    kind: str
    ref: Optional[str] = None
    note: Optional[str] = None
    label: Optional[str] = None
    body: str
    proof: Optional[str]
    pre_context: Optional[str] = None
    post_context: Optional[str] = None

class StatementValidationLevel(Enum):
    """
    Level to check if parsed statements are valid. Supported: Statement, Paper
    """

    Statement = "statement"
    Paper = "paper"


class ParseFocus(str, Enum):
    """
    Which parts of a paper to parse. Supported: all, statements, preamble, bibliography
    """

    ALL = "all"
    STATEMENTS = "statements"
    PREAMBLE = "preamble"
    BIBLIOGRAPHY = "bibliography"


@dataclass
class ParseResult:
    """
    Result of parsing a paper. Fields are None when not requested by the focus.
    """

    statements: Optional[List[Statement]] = None
    preamble: Optional[str] = None
    bibliography: Optional[Dict[str, Dict[str, str]]] = None
    bibliography_bibtex: Optional[bool] = None

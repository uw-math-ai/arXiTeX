from pydantic import BaseModel
from typing import Optional, List, Dict
from enum import Enum
from dataclasses import dataclass
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


class Statement(BaseModel):
    """
    A mathematical statement (theorem, lemma, definition, proof, ...) parsed
    from a paper's LaTeX source.

    Attributes
    ----------
    kind : str
        The statement's type, e.g. "theorem", "lemma", "proof".
    ref : str, optional
        The statement's number as it appears in the document (e.g. "1.1", "A.2").
    note : str, optional
        The statement's note, usually a title or caption.
    label : str, optional
        The statement's ``\\label{...}`` key, used to reference it.
    body : str
        The statement's LaTeX body, with user macros expanded where possible.
    proof : str, optional
        The statement's proof, if one was found and attached.
    pre_context : str, optional
        Text immediately before the statement (only populated by the ``regex`` method
        when ``context`` > 0).
    post_context : str, optional
        Text immediately after the statement (only populated by the ``regex`` method
        when ``context`` > 0).
    """

    kind: str
    ref: Optional[str] = None
    note: Optional[str] = None
    label: Optional[str] = None
    body: str
    proof: Optional[str] = None
    pre_context: Optional[str] = None
    post_context: Optional[str] = None


class ValidationLevel(str, Enum):
    """
    How strictly to validate parsed statements.

    - ``PAPER``: validate every statement and cross-check the paper as a whole
      (fails the parse if any statement looks malformed).
    - ``STATEMENT``: validate statements individually, dropping invalid ones.
    - ``NONE``: no validation; return whatever the method produced.
    """

    PAPER = "paper"
    STATEMENT = "statement"
    NONE = "none"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value == value.lower():
                    return member
        return None


class ParseFocus(str, Enum):
    """
    Which parts of a paper to parse. Fields not requested are left ``None`` in the
    returned :class:`ParseResult`.
    """

    ALL = "all"
    STATEMENTS = "statements"
    PREAMBLE = "preamble"
    BIBLIOGRAPHY = "bibliography"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value == value.lower():
                    return member
        return None


@dataclass
class ParseResult:
    """
    Result of parsing a paper. Fields are ``None`` when not requested by the focus.

    Attributes
    ----------
    statements : list of Statement, optional
        Parsed statements in document order.
    preamble : str, optional
        The paper's LaTeX preamble (everything before ``\\begin{document}``).
    bibliography : dict, optional
        Maps cite keys to metadata dicts (``title``, ``arxiv_id`` where found).
    bibliography_bibtex : bool, optional
        ``True`` when the bibliography came from a ``.bib`` file.
    method_used : str, optional
        Name of the parsing method that produced ``statements`` (useful with
        fallback chains, e.g. ``"tex"`` or ``"regex"``).
    """

    statements: Optional[List[Statement]] = None
    preamble: Optional[str] = None
    bibliography: Optional[Dict[str, Dict[str, str]]] = None
    bibliography_bibtex: Optional[bool] = None
    method_used: Optional[str] = None

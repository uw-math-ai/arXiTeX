from pydantic import BaseModel, Field
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
    number : str, optional
        The statement's number as it appears in the document (e.g. "1.1", "A.2").
    note : str, optional
        The statement's note, usually a title or caption.
    labels : list of str
        Every ``\\label{...}`` key on the statement, in source order (a restated
        theorem may carry several; most have one; some have none).
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
    number: Optional[str] = None
    note: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    body: str
    proof: Optional[str] = None
    pre_context: Optional[str] = None
    post_context: Optional[str] = None
    # Character span in the flattened source, when the method knows it. Used to
    # tell whether one statement sits inside another (a proof that states an
    # auxiliary lemma along the way). Runtime-only: kept out of the output.
    begin_pos: Optional[int] = Field(default=None, exclude=True, repr=False)
    end_pos: Optional[int] = Field(default=None, exclude=True, repr=False)


class DependencyScope(str, Enum):
    """
    Where a :class:`Dependency` points.

    - ``INTRA``: to another statement in the *same* paper (a resolved
      ``\\ref``/``\\cref``).
    - ``INTER``: to another, *cited* paper (a ``\\cite``), identified as far as
      the bibliography allows.
    """

    INTRA = "intra"
    INTER = "inter"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value == value.lower():
                    return member
        return None


class Dependency(BaseModel):
    """
    A directed dependency edge: statement ``source_index`` relies on the thing
    this edge points at (another statement, or a result in a cited paper).

    Attributes
    ----------
    source_index : int
        Index of the depending statement in :attr:`ParseResult.statements`.
    scope : DependencyScope
        ``INTRA`` (same paper) or ``INTER`` (cited paper).
    origin : str
        Which part of the source statement the reference was found in:
        ``"body"``, ``"proof"``, or ``"note"``.
    raw : str
        The raw LaTeX command matched, e.g. ``\\ref{thm:main}`` or
        ``\\cite[Theorem 3.2]{Smith}``.
    target_index : int, optional
        (INTRA) Index of the referenced statement in
        :attr:`ParseResult.statements`.
    target_label : str, optional
        (INTRA) The ``\\label`` key that was resolved.
    cite_key : str, optional
        (INTER) The bibliography key cited. Use it to look up the cited paper in
        :attr:`ParseResult.bibliography` (``title``, ``arxiv_id``, ``raw``);
        paper identity is intentionally *not* duplicated onto every edge.
    target_name : str, optional
        (INTER) The specific result cited, e.g. ``"Theorem 3.2"`` — best-effort,
        from the ``\\cite`` optional argument or nearby prose. This is
        citation-site-specific, so it lives on the edge rather than the
        bibliography.
    """

    source_index: int
    scope: DependencyScope
    origin: str
    raw: str

    # INTRA
    target_index: Optional[int] = None
    target_label: Optional[str] = None

    # INTER
    cite_key: Optional[str] = None
    target_name: Optional[str] = None


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
    dependencies : list of Dependency, optional
        Dependency edges between statements (intra-paper) and to cited papers
        (inter-paper). ``None`` unless the parser was created with
        ``dependencies=True``; otherwise a (possibly empty) list.
    """

    statements: Optional[List[Statement]] = None
    preamble: Optional[str] = None
    bibliography: Optional[Dict[str, Dict[str, str]]] = None
    bibliography_bibtex: Optional[bool] = None
    method_used: Optional[str] = None
    dependencies: Optional[List["Dependency"]] = None

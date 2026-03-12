from pydantic import BaseModel
from typing import Optional, List
from enum import Enum
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

class StatementValidationLevel(Enum):
    """
    Level to check if parsed statements are valid. Supported: Statement, Paper
    """

    Statement = "statement"
    Paper = "paper"

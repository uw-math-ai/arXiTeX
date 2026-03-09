from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class ArXivPaper(BaseModel):
    arxiv_id: str
    title: str
    authors: List[str]
    url: str
    categories: List[str]
    updated_at: str
    journal_ref: Optional[str]
    doi: Optional[str]
    license: Optional[str]
    abstract: str
    citation_count: Optional[int]
    reference_ids: List[str]

class TheoremType(str, Enum):
    Theorem = "theorem"
    Lemma = "lemma"
    Corollary = "corollary"
    Proposition = "proposition"

class ParsingMethod(str, Enum):
    PLASTEX = "plasTeX"
    REGEX = "regex"

class Theorem(BaseModel):
    """
    Theorem object.

    Attributes
    ----------
    type : TheoremType
        The theorem's type
    ref : str
        The theorem's number (e.g. 1.1 or A.1)
    note : str, optional
        The theorem's note, usually representing a title or caption
    label : str, optional
        The theorem's label. Used to reference a theorem
    body : str
        The theorem's raw LaTeX body with simple macros resolved
    proof : str, optional
        The theorem proof's raw LaTeX body with simple macros resolved
    """

    type: TheoremType
    ref: Optional[str] = None
    note: Optional[str] = None
    label: Optional[str] = None
    body: str
    proof: Optional[str] = None

class TheoremValidationLevel(Enum):
    """
    Level to check if parsed theorems are valid. Supported: Theorem, Paper
    """

    Theorem = "theorem"
    Paper = "paper"

from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class Paper(BaseModel):
    """
    Paper object.

    Attributes
    ----------
    id : str
        The paper's identifier (i.e. the arXiv id)
    title : str
        The paper's title
    license : str, optional
        The paper's license, a link
    authors : List[str]
        The paper's authors. Names are formatted '<first> <middle> <last>'
    link : str
        A link to the paper
    abstract : str
        The paper's abstract
    journal_ref : str, optional
        The paper's journal reference, if published
    categories : List[str]
        The paper's categories. The first is the primary category followed by cross-listings
    citations : int, optional
        The paper's citation count
    """

    id: str
    title: str
    license: Optional[str]
    authors: List[str]
    link: str
    abstract: str
    journal_ref: Optional[str]
    categories: List[str]
    citations: Optional[int]

class TheoremType(str, Enum):
    Theorem = "theorem"
    Lemma = "lemma"
    Corollary = "corollary"
    Proposition = "proposition"

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
    ref: str
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

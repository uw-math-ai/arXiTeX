from arXiTeX.types import Theorem, TheoremType
from typing import List
from .errors import ParseError, format_error

def _validate_type(theorem: Theorem):
    if not theorem.type in [t.value for t in TheoremType]:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Theorem has invalid type `{theorem.type}`"
        ))
    
def _validate_ref(theorem: Theorem):
    if not theorem.ref:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            "Theorem has no ref"
        ))
    
def _validate_body(theorem: Theorem, do_proof: bool = False):
    if do_proof:
        if theorem.proof is None:
            return
        body = theorem.proof
        w = "proof"
    else:
        body = theorem.body
        w = "body"

    clean_body = body.lower().strip()

    if not clean_body:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Theorem {w} is empty"
        ))

    dollar_count = clean_body.count("$")
    if dollar_count % 2 == 1:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Theorem {w} has unbalanced math delimeters: `{body}`"
        ))

    if len(clean_body) < 8:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Theorem {w} is too short: `{body}`"
        ))

    if len(clean_body) < 32 and not clean_body.endswith(".") and dollar_count == 0:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Theorem {w} is likely truncated: `{body}`"
        ))

    if clean_body.endswith((
        " and", " or", "such that", " where", " let", " then", "for all", 
        "(", "[", "{", ",", ":", ";", "=", "<", "%")
    ):
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Theorem {w} is likely truncated: `{body}`"
        ))
    
def _validate_uniqueness(theorems: List[Theorem]):
    names = set()

    for theorem in theorems:
        name = " ".join(p for p in [
            theorem.type.capitalize(),
            theorem.ref,
            f"({theorem.note})" if theorem.note else None
        ] if p is not None)

        if name in names:
            raise ValueError(format_error(
                ParseError.VALIDATION,
                f"Multiple theorems have the same name: `{name}`"
            ))

        else:
            names.add(name)

def validate_theorem(theorem: Theorem):
    """
    Raises an error if the theorem is likely incorrectly parsed:
    - If type is not a valid theorem type
    - If there is no ref
    - If body is likely truncated
    - If proof is likely truncated (if it exists)

    Parameters
    ----------
    theorems : List[Theorem]
        Theorems to validate
    """

    _validate_type(theorem)
    _validate_ref(theorem)
    _validate_body(theorem)
    _validate_body(theorem, do_proof=True)

def validate_theorems(theorems: List[Theorem]):
    """
    Raises an error if the theorems are likely incorrectly parsed:
    - If type is not a valid theorem type
    - If body is likely truncated
    - If name-conflicts exist

    Parameters
    ----------
    theorems : List[Theorem]
        Theorems to validate
    """

    for theorem in theorems:
        validate_theorem(theorem)

    _validate_uniqueness(theorems)
    
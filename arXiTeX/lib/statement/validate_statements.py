import re
from arXiTeX.types import Statement
from typing import List
from .errors import ParseError, format_error

_UNESCAPED_DOLLAR_RE = re.compile(r'(?<!\\)\$')

def _validate_body(statement: Statement):
    body = statement.body
    clean_body = body.lower().strip()

    if not clean_body:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Statement body is empty"
        ))

    dollar_count = len(_UNESCAPED_DOLLAR_RE.findall(clean_body))
    if dollar_count % 2 == 1:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Statement body has unbalanced math delimeters: `{body}`"
        ))

    if len(clean_body) < 8:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Statement body is too short: `{body}`"
        ))

    if len(clean_body) < 32 and not clean_body.endswith(".") and dollar_count == 0:
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Statement is likely truncated: `{body}`"
        ))

    if clean_body.endswith((
        " and", " or", "such that", " where", " let", " then", "for all", 
        "(", "[", "{", ",", ":", ";", "=", "<", "%")
    ):
        raise ValueError(format_error(
            ParseError.VALIDATION,
            f"Statement is likely truncated: `{body}`"
        ))
    
def _validate_uniqueness(statements: List[Statement]):
    names = set()

    for statement in statements:
        name = " ".join(p for p in [
            statement.kind.capitalize(),
            statement.ref,
            f"({statement.note})" if statement.note else None
        ] if p is not None)

        if name in names:
            raise ValueError(format_error(
                ParseError.VALIDATION,
                f"Multiple statements have the same name: `{name}`"
            ))

        elif statement.ref or statement.note:
            names.add(name)

def validate_statement(statement: Statement):
    """
    Raises an error if the statement is likely incorrectly parsed:
    - If body is likely truncated

    Parameters
    ----------
    statements : List[Statement]
        Statements to validate
    """

    _validate_body(statement)

def validate_statements(statements: List[Statement]):
    """
    Raises an error if the statements are likely incorrectly parsed:
    - If body is likely truncated
    - If name-conflicts exist

    Parameters
    ----------
    statements : List[Statemnet]
        Statements to validate
    """

    for statement in statements:
        validate_statement(statement)

    _validate_uniqueness(statements)
    
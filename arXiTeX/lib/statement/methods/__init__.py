"""
Parsing methods and helpers to resolve a user-facing method spec into concrete
:class:`Method` instances.

Public method classes:
    - :class:`Regex` — fast, dependency-free pattern matching.
    - :class:`Tex`   — real TeX engine (tectonic/pdflatex), macros expanded natively.
    - :class:`Llm`   — provider-agnostic LLM extraction via litellm.
"""

from typing import List, Set, Union

from arXiTeX.types import Statement
from .base import Method, ParseContext, UnsupportedOption
from .tex import Tex
from .llm import Llm
from .regex.flatten import flatten_tex


class Regex(Method):
    """Fast, dependency-free regex-based parsing (supports pre/post context)."""

    name = "regex"
    supports_context = True

    def parse(self, ctx: ParseContext) -> List[Statement]:
        from .regex import parse as _regex_parse

        flat = ctx.flat_tex or flatten_tex(ctx.paper_dir, ctx.main_file, ignore_errors=True)
        return _regex_parse(
            ctx.paper_dir,
            ctx.main_file,
            ctx.context,
            flat,
            statement_kinds=ctx.kinds,
        )


_STRING_TO_METHOD = {
    "regex": Regex,
    "tex": Tex,
    "llm": Llm,
}

#: A method spec is a name, a configured Method, or a list of either (fallback chain).
MethodSpec = Union[str, Method, "list", "tuple"]


def resolve_methods(spec: MethodSpec) -> List[Method]:
    """Normalize a method spec into an ordered list of :class:`Method` instances.

    Accepts a string (``"tex"``), a configured instance (``Tex(engine="pdflatex")``),
    or a list/tuple mixing the two for a fallback chain.
    """
    if spec is None:
        raise ValueError("method must not be None")
    if isinstance(spec, (list, tuple)):
        items = list(spec)
    else:
        items = [spec]
    if not items:
        raise ValueError("method list must not be empty")

    methods: List[Method] = []
    for item in items:
        if isinstance(item, Method):
            methods.append(item)
        elif isinstance(item, str):
            key = item.lower()
            if key not in _STRING_TO_METHOD:
                raise ValueError(
                    f"Unknown method {item!r}. Choose from: {', '.join(_STRING_TO_METHOD)}."
                )
            methods.append(_STRING_TO_METHOD[key]())
        else:
            raise TypeError(f"Invalid method spec element: {item!r}")
    return methods


__all__ = [
    "Method", "ParseContext", "UnsupportedOption",
    "Regex", "Tex", "Llm",
    "resolve_methods", "MethodSpec",
]

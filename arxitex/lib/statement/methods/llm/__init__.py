"""
The ``llm`` parsing method: provider-agnostic statement extraction via litellm.

The paper is flattened, split into section-aware chunks that fit the model's
context, and each chunk is sent to the model with a strict JSON schema. Results
are merged in document order and de-duplicated. litellm is an optional
dependency (``pip install 'arxitex[llm]'``); the model string and API key follow
litellm conventions (e.g. ``"anthropic/claude-sonnet-5"`` +
``ANTHROPIC_API_KEY``, ``"openai/gpt-4o"`` + ``OPENAI_API_KEY``).
"""

import json
import re
from pathlib import Path
from typing import List, Optional, Set

from arxitex.types import Statement
from arxitex.lib.statement.methods.base import ParseContext, Method
from arxitex.lib.statement.methods.regex.flatten import flatten_tex
from arxitex.lib.statement.extract_context import strip_comments

_DEFAULT_MODEL = "anthropic/claude-sonnet-5"
_DOC_BEGIN_RE = re.compile(r"\\begin\s*\{document\}")
_SECTION_RE = re.compile(r"(?=\\(?:sub)*section\*?\s*[\{\[])")
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)

_SYSTEM_PROMPT = (
    "You are a precise LaTeX parser. You extract mathematical statements "
    "(theorems, lemmas, definitions, proofs, etc.) from LaTeX source and return "
    "them as structured JSON. You never invent content and you copy LaTeX bodies "
    "verbatim from the source."
)


def _chunk(body: str, max_chars: int) -> List[str]:
    """Split LaTeX source into section-aligned chunks no larger than max_chars."""
    if len(body) <= max_chars:
        return [body]

    pieces = _SECTION_RE.split(body)
    chunks: List[str] = []
    cur = ""
    for piece in pieces:
        if cur and len(cur) + len(piece) > max_chars:
            chunks.append(cur)
            cur = piece
        elif len(piece) > max_chars:
            # A single section is bigger than the budget: hard-split it.
            if cur:
                chunks.append(cur)
                cur = ""
            for i in range(0, len(piece), max_chars):
                chunks.append(piece[i : i + max_chars])
        else:
            cur += piece
    if cur:
        chunks.append(cur)
    return chunks


def _build_prompt(chunk: str, kinds: Set[str]) -> str:
    kind_list = ", ".join(sorted(kinds))
    return (
        "Extract every mathematical statement of these kinds from the LaTeX "
        f"source below: {kind_list}.\n\n"
        "Return ONLY a JSON array. Each element is an object with keys:\n"
        '  "kind"  (one of the kinds above, lowercased),\n'
        '  "ref"   (the statement number as displayed, e.g. "1.1", or null),\n'
        '  "note"  (the title/note in brackets, or null),\n'
        '  "label" (the \\label key, or null),\n'
        '  "body"  (the LaTeX body, copied verbatim, without the \\begin/\\end tags),\n'
        '  "proof" (the LaTeX of its proof if present in this source, else null).\n\n'
        "Do not include environments that are not among the requested kinds. "
        "If there are none, return [].\n\n"
        "```latex\n" + chunk + "\n```"
    )


def _parse_response(content: str, kinds: Set[str]) -> List[Statement]:
    m = _JSON_ARRAY_RE.search(content)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []

    out: List[Statement] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        body = (it.get("body") or "").strip()
        kind = (it.get("kind") or "").strip().lower()
        if not body or not kind:
            continue
        out.append(Statement(
            kind=kind,
            ref=(it.get("ref") or None),
            note=(it.get("note") or None),
            label=(it.get("label") or None),
            body=body,
            proof=(it.get("proof") or None),
        ))
    return out


def llm_parse(
    ctx: ParseContext,
    model: str = _DEFAULT_MODEL,
    api_key: Optional[str] = None,
    max_chunk_chars: int = 30_000,
    temperature: float = 0.0,
) -> List[Statement]:
    try:
        import litellm
    except ImportError as e:
        raise ImportError(
            "The 'llm' method requires litellm. Install it with: "
            "pip install 'arxitex[llm]'"
        ) from e

    flat = ctx.flat_tex or flatten_tex(ctx.paper_dir, ctx.main_file, ignore_errors=True)
    m = _DOC_BEGIN_RE.search(flat)
    body_src = strip_comments(flat[m.end():] if m else flat)

    statements: List[Statement] = []
    seen: set = set()
    for chunk in _chunk(body_src, max_chunk_chars):
        if not chunk.strip():
            continue
        kwargs = {"api_key": api_key} if api_key else {}
        resp = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(chunk, ctx.kinds)},
            ],
            temperature=temperature,
            **kwargs,
        )
        content = resp.choices[0].message.content or ""
        for stmt in _parse_response(content, ctx.kinds):
            key = (stmt.kind, stmt.label, re.sub(r"\s+", " ", stmt.body).strip()[:120])
            if key in seen:
                continue
            seen.add(key)
            statements.append(stmt)

    return statements


class Llm(Method):
    """Parse with an LLM (provider-agnostic via litellm).

    Parameters
    ----------
    model : str
        A litellm model string, e.g. ``"anthropic/claude-sonnet-5"`` or
        ``"openai/gpt-4o"``.
    api_key : str, optional
        API key. If omitted, the provider's usual environment variable is used.
    max_chunk_chars : int
        Maximum characters of LaTeX per model call.
    temperature : float
        Sampling temperature (default 0 for determinism).
    """

    name = "llm"
    supports_context = False

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_key: Optional[str] = None,
        max_chunk_chars: int = 30_000,
        temperature: float = 0.0,
    ):
        self.model = model
        self.api_key = api_key
        self.max_chunk_chars = max_chunk_chars
        self.temperature = temperature

    def parse(self, ctx: ParseContext) -> List[Statement]:
        return llm_parse(
            ctx,
            model=self.model,
            api_key=self.api_key,
            max_chunk_chars=self.max_chunk_chars,
            temperature=self.temperature,
        )

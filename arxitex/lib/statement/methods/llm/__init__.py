"""
The ``llm`` parsing method: statement extraction via any OpenAI-compatible API.

The paper is flattened, split into section-aware chunks that fit the model's
context, and each chunk is sent to the model with a strict JSON schema. Results
are merged in document order and de-duplicated.

Uses the ``openai`` SDK (optional: ``pip install 'arxitex[llm]'``) pointed at a
``base_url``, so any OpenAI-compatible host works — Nebius (the default),
Together, Groq, Fireworks, OpenRouter, a local vLLM/Ollama, or OpenAI itself.
Model names are the host's own (e.g. ``"deepseek-ai/DeepSeek-V4-Pro"``), not
provider-prefixed.

The key is taken from ``api_key`` if given, else ``NEBIUS_API_KEY``, else
``OPENAI_API_KEY``. This module never reads a ``.env`` file — a library should
not mutate the process environment; load it in your entry point if you want that.
"""

import json
import os
import re
from typing import List, Optional, Set

from arxitex.types import Statement
from arxitex.lib.statement.methods.base import ParseContext, Method
from arxitex.lib.statement.methods.regex.flatten import flatten_tex
from arxitex.lib.statement.extract_context import strip_comments

_DEFAULT_BASE_URL = "https://api.studio.nebius.com/v1"
_DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Pro"
_API_KEY_ENVS = ("NEBIUS_API_KEY", "OPENAI_API_KEY")

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
        # strict=False: models routinely emit literal newlines inside strings
        # when echoing LaTeX, which strict JSON rejects.
        items = json.loads(m.group(0), strict=False)
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


def _make_client(api_key: Optional[str], base_url: str, max_retries: int = 2):
    """Build an OpenAI-SDK client for an OpenAI-compatible host.

    *max_retries* is the SDK's own exponential backoff over connection errors,
    429s and 5xx (shared hosts return 529 "overloaded" under load). Raise it for
    long multi-call jobs, where one transient blip would otherwise discard every
    call made so far.
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError(
            "The 'llm' method requires the openai package. Install it with: "
            "pip install 'arxitex[llm]'"
        ) from e

    key = api_key or next((os.environ[v] for v in _API_KEY_ENVS if os.environ.get(v)), None)
    if not key:
        raise ValueError(
            "No API key for the 'llm' method. Pass api_key=..., or set one of: "
            + ", ".join(_API_KEY_ENVS)
        )
    return OpenAI(base_url=base_url, api_key=key, max_retries=max_retries)


def llm_parse(
    ctx: ParseContext,
    model: str = _DEFAULT_MODEL,
    api_key: Optional[str] = None,
    base_url: str = _DEFAULT_BASE_URL,
    max_chunk_chars: int = 30_000,
    temperature: float = 0.0,
) -> List[Statement]:
    client = _make_client(api_key, base_url)

    flat = ctx.flat_tex or flatten_tex(ctx.paper_dir, ctx.main_file, ignore_errors=True)
    m = _DOC_BEGIN_RE.search(flat)
    body_src = strip_comments(flat[m.end():] if m else flat)

    statements: List[Statement] = []
    seen: set = set()
    for chunk in _chunk(body_src, max_chunk_chars):
        if not chunk.strip():
            continue
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(chunk, ctx.kinds)},
            ],
            temperature=temperature,
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
    """Parse with an LLM on any OpenAI-compatible host.

    Parameters
    ----------
    model : str
        The host's own model name, e.g. ``"deepseek-ai/DeepSeek-V4-Pro"``.
    api_key : str, optional
        API key. If omitted, ``NEBIUS_API_KEY`` then ``OPENAI_API_KEY`` are tried.
    base_url : str
        The OpenAI-compatible endpoint (default: Nebius AI Studio). Point this at
        Together, Groq, OpenRouter, a local vLLM/Ollama, or OpenAI as needed.
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
        base_url: str = _DEFAULT_BASE_URL,
        max_chunk_chars: int = 30_000,
        temperature: float = 0.0,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_chunk_chars = max_chunk_chars
        self.temperature = temperature

    def parse(self, ctx: ParseContext) -> List[Statement]:
        return llm_parse(
            ctx,
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            max_chunk_chars=self.max_chunk_chars,
            temperature=self.temperature,
        )

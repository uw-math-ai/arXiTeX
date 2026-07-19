"""
Annotate a paper with a vision LLM, producing the same ground-truth JSON a human
would write by hand.

The paper's PDF is downloaded and each page **rendered to an image** (PyMuPDF),
then shown to a vision model — so it reads the typeset page exactly as a human
annotator does, rather than a mangled text layer. It lists every theorem-like
statement with its printed number and a words-only, math-free elided body.
Output goes to ``ground_truth/pdf/<arxiv_id>.json`` with ``annotator`` set to the
model id, so LLM- and human-annotated papers stay distinguishable.

The model does **not** record proofs — proof capture is left to human
annotators. An LLM annotation validates only kind, number, and statement body.

Pages are sent in **batches** (a whole paper at once is both too many image
tokens and too large a request), with a one-page **overlap** so a statement
spanning a page break is still seen whole by at least one batch. Results are
merged and de-duplicated by printed number.

Run it from the ``testing/`` directory:

    cd testing

    # NEBIUS_API_KEY is read from the repo's .env (or pass --api-key)
    python -m eval.annotate 2507.08642
    python -m eval.annotate 2507.08642 --model google/gemma-3-27b-it
    python -m eval.annotate 2507.08642 --dpi 200 --pages-per-call 2
    python -m eval.annotate 2507.08642 --max-pages 4 --dry-run   # cheap smoke test

Requires the ``llm`` extra (``pip install 'arxitex[llm]'``) and PyMuPDF. The
model must accept images — on Nebius that means ``Qwen/Qwen2.5-VL-72B-Instruct``
(default), ``google/gemma-3-27b-it``, or ``openbmb/MiniCPM-V-4_5``.

Existing annotations are never overwritten without ``--force`` — a hand-made
annotation is expensive and must not be clobbered by a model run.
"""

from __future__ import annotations

import base64
import datetime
import json
import re
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import List, Tuple

import requests

from arxitex.lib.statement.methods.llm import (
    _API_KEY_ENVS,
    _DEFAULT_BASE_URL,
    _make_client,
)

from .harness import REPO_ROOT, gt_dir
from .schema import PdfGroundTruth, PdfStatement

# A vision model on Nebius — it must be able to read a rendered page.
DEFAULT_MODEL = "Qwen/Qwen2.5-VL-72B-Instruct"
DEFAULT_BASE_URL = _DEFAULT_BASE_URL
# 150dpi renders a US-Letter page at 1275x1650 — subscripts and primes stay
# legible without the token cost of 200dpi+.
DEFAULT_DPI = 150
# ~4 pages/call keeps each request near 1.6MB of base64 and well inside context.
DEFAULT_PAGES_PER_CALL = 4
# A whole-paper run is many slow, expensive calls; one transient 529 from a busy
# shared host would otherwise bin every call made so far. Ride it out.
DEFAULT_MAX_RETRIES = 8

_SYSTEM_PROMPT = """\
You are a meticulous mathematician building ground-truth annotations of a research paper.

You will be shown consecutive PAGES of the paper as images. List EVERY
theorem-like statement visible on them, in the order they appear, exactly as a
reader sees them on the typeset page.

Statement kinds to record (lowercase): theorem, lemma, proposition, corollary,
definition, remark, claim, fact, observation, conjecture, hypothesis, axiom,
example, notation, convention.

Do NOT record proofs, in any form.

Rules:
- Record the statement's PRINTED number in "number" (e.g. "1.1", "A.3"), exactly
  as shown. If a statement is genuinely unnumbered, omit "number".
- "body" is an ELIDED transcription of the statement: copy the opening WORDS,
  write " ... " wherever you skip content, and copy the closing WORDS. Aim for
  roughly 5-12 words at each end. Never invent words.
- Use WORDS ONLY in "body" -- ordinary prose. NEVER use mathematical symbols,
  LaTeX, backslashes, dollar signs, superscripts, or subscripts. When you reach
  something that is not a word:
    * write it as a word if you can ("R to the n" -> "R to the n", not "R^n");
    * if no word fits, use its plain LETTER(s) ("the group G" -> "the group G");
    * if not even a letter fits, use a plain NUMBER.
  Example: for "Let $X$ be a compact $n$-manifold" write "Let X be a compact
  n manifold".
- Mark anything you cannot see with a run-off ellipsis, and never guess past it:
    * If the statement starts before the first page shown, BEGIN with "... ".
    * If it runs past the last page shown, END with " ...".
- Skip nothing: record every statement shown on these pages, whether in the
  introduction, a later section, or an appendix. Numbers may have gaps; that is
  fine, record what is shown.
- Ignore proofs, figures, tables, equations, and bare section headings.
- Read the printed number off the page. Do not renumber, infer, or continue a
  sequence yourself.

Return ONLY a JSON object, no prose and no markdown fence:

{
  "note": "<one short remark about the paper, e.g. 'uses tikz'; may be empty>",
  "statements": [
    {"kind": "theorem", "number": "1.1", "body": "Let X be a good moduli space ... maps to the closed point of Y"},
    {"kind": "remark", "number": "1.2", "body": "We can factor the resulting morphism ... is representable"}
  ]
}
"""

_USER_PROMPT = (
    "These are pages {first}-{last} of {total} from arXiv paper {arxiv_id}, in "
    "order. List every theorem-like statement visible on them, with its printed "
    "number and elided body/proof, as JSON."
)


def download_pdf(arxiv_id: str) -> bytes:
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    resp = requests.get(url, timeout=120, headers={"User-Agent": "arxitex-eval/1.0"})
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise RuntimeError(f"{url} did not return a PDF (got {resp.content[:20]!r})")
    return resp.content


def pdf_to_images(pdf: bytes, dpi: int = DEFAULT_DPI, max_pages: int | None = None) -> List[bytes]:
    """Render each PDF page to a PNG. PNG, not JPEG: text stays crisp."""
    try:
        import fitz  # PyMuPDF
    except ImportError as e:  # pragma: no cover
        raise ImportError("annotate needs PyMuPDF: pip install pymupdf") from e
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        n = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
        return [doc[i].get_pixmap(dpi=dpi).tobytes("png") for i in range(n)]


def _batches(n_pages: int, per_call: int, overlap: int = 1) -> List[Tuple[int, int]]:
    """Half-open [start, end) page ranges covering n_pages, overlapping by *overlap*.

    The overlap means a statement straddling a page break is seen whole by at
    least one batch; the merge step drops the resulting duplicate.
    """
    if per_call <= 0:
        raise ValueError("pages_per_call must be >= 1")
    step = max(1, per_call - overlap)
    out: List[Tuple[int, int]] = []
    start = 0
    while start < n_pages:
        end = min(start + per_call, n_pages)
        out.append((start, end))
        if end >= n_pages:
            break
        start += step
    return out


def _image_blocks(images: List[bytes]) -> List[dict]:
    return [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(img).decode("ascii")},
        }
        for img in images
    ]


def _completeness(text: str | None) -> int:
    """How well anchored a transcription is: 2 = both ends seen, 0 = neither.

    A run-off ellipsis means the model could not see that end of the text (the
    statement started before, or continued past, the pages it was shown).
    """
    if not text or not text.strip():
        return -1
    t = text.strip()
    return (0 if t.startswith("...") else 1) + (0 if t.endswith("...") else 1)


def _fuller(a: str | None, b: str | None) -> str | None:
    """Of two transcriptions of the same text, the one that saw more of it."""
    ca, cb = _completeness(a), _completeness(b)
    if ca != cb:
        return a if ca > cb else b
    return a if len(a or "") >= len(b or "") else b


def _merge(batches: List[List[PdfStatement]]) -> List[PdfStatement]:
    """Concatenate per-batch statements, reconciling duplicates from page overlap.

    Keyed on the printed number when there is one (it is unique within a paper);
    unnumbered statements fall back to their body opening.

    Duplicates are *reconciled*, not dropped: batches see different amounts of a
    statement, and proofs in particular often run past the one-page overlap. A
    later batch may be the only one that sees a proof at all (it starts below the
    earlier batch's last page), or that sees where it ends. So for body and proof
    keep whichever view is better anchored — dropping the later copy outright
    would silently lose proofs.
    """
    out: List[PdfStatement] = []
    at: dict = {}
    for batch in batches:
        for s in batch:
            key = s.number.strip() if s.number else "body:" + " ".join(s.body.split()[:8]).lower()
            if key not in at:
                at[key] = len(out)
                out.append(s)
                continue
            prev = out[at[key]]
            out[at[key]] = prev.model_copy(update={
                "body": _fuller(prev.body, s.body) or prev.body,
                "proof": _fuller(prev.proof, s.proof),
            })
    return out


# A backslash that begins a valid JSON escape: \" \\ \/ \b \f \n \r \t \uXXXX.
_VALID_ESCAPE = re.compile(r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})')


def _sanitize_json(content: str) -> str:
    r"""Escape backslashes that don't begin a valid JSON escape.

    Models sometimes leak a LaTeX control sequence into a string (``\alpha``,
    ``\geq``), which is an invalid JSON escape and aborts the whole parse. Doubling
    any such lone backslash makes the string parseable (it decodes back to the
    literal ``\alpha``); genuine escapes are left untouched, so valid JSON is
    unchanged.
    """
    out: list[str] = []
    i = 0
    while i < len(content):
        if content[i] == "\\":
            m = _VALID_ESCAPE.match(content, i)
            if m:
                out.append(m.group(0))
                i = m.end()
            else:
                out.append("\\\\")
                i += 1
        else:
            out.append(content[i])
            i += 1
    return "".join(out)


def _extract_json(content: str) -> dict:
    """Pull the JSON object out of a model response, tolerating stray prose.

    ``strict=False`` permits raw control characters (models emit literal newlines
    in transcribed text); ``_sanitize_json`` repairs invalid backslash escapes.
    """
    content = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fence:
        content = fence.group(1).strip()
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in model response:\n{content[:500]}")
    blob = content[start : end + 1]
    try:
        return json.loads(blob, strict=False)
    except json.JSONDecodeError:
        return json.loads(_sanitize_json(blob), strict=False)


def annotate(
    arxiv_id: str,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    dpi: int = DEFAULT_DPI,
    pages_per_call: int = DEFAULT_PAGES_PER_CALL,
    max_pages: int | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    verbose: bool = True,
) -> PdfGroundTruth:
    """Show *model* the paper's rendered pages and return validated ground truth.

    Raises if any batch ultimately fails. That is deliberate: a partial
    annotation is worse than none, because every statement on the pages that
    never made it would silently score as a parser "phantom".
    """
    client = _make_client(api_key, base_url, max_retries=max_retries)
    images = pdf_to_images(download_pdf(arxiv_id), dpi=dpi, max_pages=max_pages)
    if not images:
        raise RuntimeError(f"{arxiv_id}: no pages rendered")

    ranges = _batches(len(images), pages_per_call)
    if verbose:
        print(f"{arxiv_id}: {len(images)} pages @ {dpi}dpi -> {len(ranges)} call(s) "
              f"of <={pages_per_call} pages", file=sys.stderr)

    per_batch: List[List[PdfStatement]] = []
    notes: List[str] = []
    for first, last in ranges:
        prompt = _USER_PROMPT.format(
            first=first + 1, last=last, total=len(images), arxiv_id=arxiv_id
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": [{"type": "text", "text": prompt}]
                                                + _image_blocks(images[first:last])},
                ],
                temperature=0.0,
            )
        except Exception as e:
            raise RuntimeError(
                f"pages {first + 1}-{last} of {arxiv_id} failed after {max_retries} "
                f"retries: {e}"
            ) from e
        data = _extract_json(resp.choices[0].message.content or "")
        # Proof capture is left to human annotators; drop any proof the model
        # emits so an LLM annotation only ever validates kind/number/body.
        found = []
        for s in data.get("statements", []):
            if isinstance(s, dict):
                s.pop("proof", None)
            found.append(PdfStatement.model_validate(s))
        per_batch.append(found)
        if data.get("note"):
            notes.append(str(data["note"]).strip())
        if verbose:
            print(f"  pages {first + 1}-{last}: {len(found)} statement(s)", file=sys.stderr)

    statements = _merge(per_batch)
    if verbose:
        dropped = sum(len(b) for b in per_batch) - len(statements)
        print(f"  merged: {len(statements)} unique ({dropped} duplicate(s) from "
              f"page overlap)", file=sys.stderr)

    return PdfGroundTruth(
        arxiv_id=arxiv_id,
        annotator=model,
        date=datetime.date.today(),
        note=notes[0] if notes else None,
        statements=statements,
    )


def _force_utf8_stdio() -> None:
    """Windows consoles default to cp1252, but annotated math is full of →, ⊂, √.

    Without this, printing a perfectly good annotation dies with
    UnicodeEncodeError. (The file write already pins utf-8.)
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):  # pragma: no cover - not a real tty
            pass


def _load_env() -> None:
    """Load the repo's .env into os.environ (best effort).

    The library itself never does this — only this CLI, which is a dev tool.
    (litellm used to do it implicitly on import; that magic left with it.)
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env")


def main(argv=None) -> None:
    ap = ArgumentParser(
        prog="eval.annotate",
        description="Annotate an arXiv paper with an LLM, producing ground-truth JSON.",
    )
    ap.add_argument("arxiv_id", help="arXiv id, e.g. 2507.08642")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"Model name as the host names it (default: {DEFAULT_MODEL})")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL,
                    help=f"OpenAI-compatible endpoint (default: {DEFAULT_BASE_URL})")
    ap.add_argument("--api-key", default=None,
                    help="API key (else " + ", then ".join(_API_KEY_ENVS) + ", read from .env)")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI,
                    help=f"Render resolution (default: {DEFAULT_DPI}). Higher reads "
                         f"small type better but costs more image tokens.")
    ap.add_argument("--pages-per-call", type=int, default=DEFAULT_PAGES_PER_CALL,
                    help=f"Pages per request (default: {DEFAULT_PAGES_PER_CALL}); "
                         f"batches overlap by one page.")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="Only annotate the first N pages (for cheap smoke tests).")
    ap.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES,
                    help=f"Retries per call over 429/5xx (default: {DEFAULT_MAX_RETRIES}). "
                         f"Shared hosts return 529 when busy.")
    ap.add_argument("--out", default=None,
                    help="Write here instead of ground_truth/pdf/<arxiv_id>.json")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing annotation (refused by default)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the JSON instead of writing it")
    args = ap.parse_args(argv)

    _force_utf8_stdio()
    _load_env()

    out = Path(args.out) if args.out else gt_dir("pdf") / f"{args.arxiv_id}.json"
    if out.exists() and not (args.force or args.dry_run):
        existing = PdfGroundTruth.model_validate_json(out.read_text(encoding="utf-8"))
        print(
            f"{out} already exists (annotator: {existing.annotator}, "
            f"{len(existing.statements)} statements).\n"
            f"Refusing to overwrite. Pass --force, or --out to write elsewhere.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        gt = annotate(args.arxiv_id, model=args.model, api_key=args.api_key,
                      base_url=args.base_url, dpi=args.dpi,
                      pages_per_call=args.pages_per_call, max_pages=args.max_pages,
                      max_retries=args.max_retries)
    except Exception as e:
        print(f"annotation failed: {e}", file=sys.stderr)
        sys.exit(1)

    payload = gt.model_dump_json(indent=2, exclude_none=True)
    if args.dry_run:
        print(payload)
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload + "\n", encoding="utf-8")
    print(f"Wrote {len(gt.statements)} statements to {out} (annotator: {gt.annotator})")
    print(f"Score a parser against it:  python -m eval.run --mode pdf -m regex --only {args.arxiv_id}")


if __name__ == "__main__":
    main()

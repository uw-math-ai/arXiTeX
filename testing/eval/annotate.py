"""
Annotate a paper's PDF with a powerful LLM, producing the same ground-truth
JSON a human would write by hand.

The model is shown the actual PDF (as a document, so it sees the rendered
paper — the same thing a human annotator reads) and asked to list every
theorem-like statement with its printed number and an elided transcription.
Output goes to ``ground_truth/pdf/<arxiv_id>.json`` with ``annotator`` set to
the model id, so LLM- and human-annotated papers are distinguishable.

Run it from the ``testing/`` directory:

    cd testing

    export ANTHROPIC_API_KEY=sk-...            # or pass --api-key
    python -m eval.annotate 2507.08642
    python -m eval.annotate 2507.08642 --model openai/gpt-5 --out /tmp/x.json
    python -m eval.annotate 2507.08642 --text      # send extracted text, not the PDF
    python -m eval.annotate 2507.08642 --dry-run   # print, don't write

Requires the ``llm`` extra: ``pip install 'arxitex[llm]'``. Model strings and
API-key env vars follow litellm conventions (``anthropic/...`` +
``ANTHROPIC_API_KEY``, ``openai/...`` + ``OPENAI_API_KEY``, ...).

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

import requests

from .harness import gt_dir
from .schema import PdfGroundTruth

# Default to a strong reasoning model: annotation quality matters far more than
# its (one-off, per-paper) cost.
DEFAULT_MODEL = "anthropic/claude-opus-4-8"

_SYSTEM_PROMPT = """\
You are a meticulous mathematician building ground-truth annotations of a research paper.

You will be given a paper. List EVERY theorem-like statement it contains, in the
order they appear, exactly as a reader sees them in the rendered document.

Statement kinds to record (lowercase): theorem, lemma, proposition, corollary,
definition, remark, claim, fact, observation, conjecture, hypothesis, axiom,
example, notation, convention.

Rules:
- Record the statement's PRINTED number in "number" (e.g. "1.1", "A.3"), exactly
  as shown. If a statement is genuinely unnumbered, omit "number".
- Do NOT record proofs as their own statements. If a statement has a proof, put
  an elided transcription of that proof in the statement's "proof" field. If it
  has no proof, omit "proof".
- A proof that covers several statements ("Proof of Theorem 1.5 and Corollary
  1.6") belongs to each of them: give each statement that same proof text.
- "body" and "proof" are ELIDED transcriptions: copy the opening words verbatim,
  write " ... " wherever you skip content, and copy the closing words verbatim.
  Aim for roughly 5-12 words at each end. Never invent words.
- Skip nothing: include statements in the introduction AND in later sections,
  including appendices. Numbers may have gaps; that is fine, record what is shown.
- Ignore figures, tables, equations, and bare section headings.

Return ONLY a JSON object, no prose and no markdown fence:

{
  "note": "<one short remark about the paper, e.g. 'uses tikz'; may be empty>",
  "statements": [
    {"kind": "theorem", "number": "1.1", "body": "Let ... be a good moduli space ... maps to the closed point of ...", "proof": "We first assume ... which concludes the argument ..."},
    {"kind": "remark", "number": "1.2", "body": "We can factor the resulting morphism ... is representable."}
  ]
}
"""

_USER_PROMPT = (
    "Annotate this paper (arXiv {arxiv_id}). List every theorem-like statement, "
    "in order, with its printed number and elided body/proof, as JSON."
)


def download_pdf(arxiv_id: str) -> bytes:
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    resp = requests.get(url, timeout=120, headers={"User-Agent": "arxitex-eval/1.0"})
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise RuntimeError(f"{url} did not return a PDF (got {resp.content[:20]!r})")
    return resp.content


def pdf_to_text(pdf: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:  # pragma: no cover
        raise ImportError("--text needs PyMuPDF: pip install pymupdf") from e
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def _content_blocks(arxiv_id: str, pdf: bytes, as_text: bool) -> list[dict]:
    """The user message: the paper itself, either as a document or as text."""
    prompt = _USER_PROMPT.format(arxiv_id=arxiv_id)
    if as_text:
        return [{"type": "text", "text": f"{prompt}\n\n--- PAPER TEXT ---\n{pdf_to_text(pdf)}"}]
    b64 = base64.b64encode(pdf).decode("ascii")
    return [
        {"type": "text", "text": prompt},
        {
            "type": "file",
            "file": {
                "file_data": f"data:application/pdf;base64,{b64}",
                "filename": f"{arxiv_id}.pdf",
                "format": "application/pdf",
            },
        },
    ]


def _extract_json(content: str) -> dict:
    """Pull the JSON object out of a model response, tolerating stray prose."""
    content = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fence:
        content = fence.group(1).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in model response:\n{content[:500]}")
    return json.loads(content[start : end + 1])


def annotate(
    arxiv_id: str,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    as_text: bool = False,
) -> PdfGroundTruth:
    """Ask *model* to annotate the paper's PDF and return validated ground truth."""
    try:
        import litellm
    except ImportError as e:
        raise ImportError(
            "The annotate CLI needs litellm: pip install 'arxitex[llm]'"
        ) from e

    pdf = download_pdf(arxiv_id)
    resp = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _content_blocks(arxiv_id, pdf, as_text)},
        ],
        temperature=0.0,
        **({"api_key": api_key} if api_key else {}),
    )
    data = _extract_json(resp.choices[0].message.content)

    return PdfGroundTruth(
        arxiv_id=arxiv_id,
        annotator=model,
        date=datetime.date.today(),
        note=data.get("note") or None,
        statements=data.get("statements", []),
    )


def main(argv=None) -> None:
    ap = ArgumentParser(
        prog="eval.annotate",
        description="Annotate an arXiv paper's PDF with an LLM, producing ground-truth JSON.",
    )
    ap.add_argument("arxiv_id", help="arXiv id, e.g. 2507.08642")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"litellm model string (default: {DEFAULT_MODEL})")
    ap.add_argument("--api-key", default=None,
                    help="API key (else the provider's env var, e.g. ANTHROPIC_API_KEY)")
    ap.add_argument("--text", action="store_true",
                    help="Send the PDF's extracted text instead of the PDF itself "
                         "(cheaper; for models without document support)")
    ap.add_argument("--out", default=None,
                    help="Write here instead of ground_truth/pdf/<arxiv_id>.json")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing annotation (refused by default)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the JSON instead of writing it")
    args = ap.parse_args(argv)

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
        gt = annotate(args.arxiv_id, model=args.model, api_key=args.api_key, as_text=args.text)
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

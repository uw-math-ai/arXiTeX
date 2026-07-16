"""
Compare parser output against ground truth, in two modes.

Both modes align parsed statements to ground-truth statements by *body content*
(not by number — a misnumbered statement must still align so the bad number can
be flagged), then check fields on the aligned pairs. What differs is strictness:

* ``tex`` — exhaustive. Ground truth is the full expected parse; every field is
  checked (kind, ref, note, label, full body, proof). Catches runtime bugs.
* ``pdf`` — lenient. Ground truth only has what's visible in the PDF; only kind,
  ref, and the body snippet are checked, everything else ignored.

Unmatched parsed statements are phantoms (false positives); unmatched ground
truth are misses (false negatives). A *terribly wrong body* fails to align and
so shows up as a phantom + a miss; a mildly-wrong body still aligns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from arxitex.types import Statement

from .normalize import norm_body, overlap, to_words
from .schema import PdfGroundTruth, PdfStatement, TexGroundTruth

# Extra words of window when matching a pdf snippet, to absorb math gaps.
_SLACK = 4
# Minimum body overlap for two statements to be considered the same one.
MATCH_THRESHOLD = 0.6
# Statement kinds parsed but not scored in pdf mode (proofs attach to their statement).
_EXCLUDED_KINDS = frozenset({"proof"})


def _norm_ref(ref: Optional[str]) -> Optional[str]:
    return ref.strip() or None if ref else None


def _norm_kind(kind: Optional[str]) -> str:
    return (kind or "").strip().lower()


@dataclass
class FieldDiff:
    field: str
    expected: object
    actual: object

    def __str__(self) -> str:
        return f"{self.field}: expected {self.expected!r}, got {self.actual!r}"


@dataclass
class PairVerdict:
    """A matched (ground-truth, parsed) pair and the fields that disagree."""

    gt: object              # Statement (tex) or PdfStatement (pdf)
    parsed: Statement
    diffs: List[FieldDiff]
    body_score: float

    @property
    def ok(self) -> bool:
        return not self.diffs


@dataclass
class PaperReport:
    name: str
    config: str
    mode: str
    matched: List[PairVerdict] = field(default_factory=list)
    phantoms: List[Statement] = field(default_factory=list)      # false positives
    misses: List[object] = field(default_factory=list)           # false negatives
    error: Optional[str] = None                                  # parse failure, if any

    @property
    def tp(self) -> int: return len(self.matched)
    @property
    def fp(self) -> int: return len(self.phantoms)
    @property
    def fn(self) -> int: return len(self.misses)

    @property
    def field_ok(self) -> int:
        return sum(v.ok for v in self.matched)

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 1.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def clean(self) -> bool:
        """True iff nothing is wrong: no phantoms, no misses, no field diffs."""
        return not self.error and self.fp == 0 and self.fn == 0 and self.field_ok == self.tp

    def format(self) -> str:
        """A human-readable summary of everything that went wrong."""
        lines = [f"[{self.config}/{self.mode}] {self.name}"]
        if self.error:
            lines.append(f"  ! parse error: {self.error}")
        for v in self.matched:
            for d in v.diffs:
                lines.append(f"  ~ {_gt_ref(v.gt)} {_gt_kind(v.gt)}: {d}")
        for p in self.phantoms:
            lines.append(f"  + phantom (parsed, not in ground truth): {p.kind} {p.ref!r} '{_snippet(p.body)}'")
        for m in self.misses:
            lines.append(f"  - miss (in ground truth, not parsed): {_gt_kind(m)} {_gt_ref(m)!r} '{_gt_snippet(m)}'")
        return "\n".join(lines)


# --- helpers for formatting either Statement (tex) or PdfStatement (pdf) ----

def _snippet(body: Optional[str]) -> str: return (body or "")[:50]
def _gt_kind(g) -> str: return getattr(g, "kind", "?")
def _gt_ref(g):
    """The expected number: Statement calls it `ref`, PdfStatement `number`."""
    return getattr(g, "ref", None) if hasattr(g, "ref") else getattr(g, "number", None)
def _gt_snippet(g) -> str: return _snippet(getattr(g, "body", ""))


# --- alignment -------------------------------------------------------------

def _greedy_align(scores: list[tuple[float, int, int]]):
    """Assign gt<->parsed pairs greedily, best score first, above threshold."""
    scores.sort(reverse=True)
    used_g: set[int] = set()
    used_p: set[int] = set()
    pairs: list[tuple[int, int, float]] = []
    for sc, gi, pi in scores:
        if sc < MATCH_THRESHOLD or gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        pairs.append((gi, pi, sc))
    return pairs, used_g, used_p


# --- tex mode: exhaustive field check --------------------------------------

def _tex_diffs(g: Statement, p: Statement) -> List[FieldDiff]:
    checks = [
        ("kind", g.kind, p.kind, _norm_kind),
        ("ref", g.ref, p.ref, _norm_ref),
        ("note", g.note, p.note, norm_body),
        ("label", g.label, p.label, lambda x: x),
        ("body", g.body, p.body, norm_body),
        ("proof", g.proof, p.proof, norm_body),
    ]
    return [FieldDiff(name, exp, act) for name, exp, act, f in checks if f(exp) != f(act)]


def score_tex(parsed: Sequence[Statement], gt: TexGroundTruth, config: str = "") -> PaperReport:
    gts = gt.statements
    pw = [to_words(p.body) for p in parsed]
    scores = [
        (overlap(to_words(g.body), pw[i]), gi, i)
        for gi, g in enumerate(gts)
        for i in range(len(parsed))
    ]
    pairs, used_g, used_p = _greedy_align(scores)
    matched = [
        PairVerdict(gts[gi], parsed[pi], _tex_diffs(gts[gi], parsed[pi]), sc)
        for gi, pi, sc in sorted(pairs)
    ]
    phantoms = [parsed[i] for i in range(len(parsed)) if i not in used_p]
    misses = [gts[gi] for gi in range(len(gts)) if gi not in used_g]
    return PaperReport(gt.name, config, "tex", matched, phantoms, misses)


# --- pdf mode: elided-pattern + visible-field check -------------------------

ELLIPSIS = "..."
# A recorded body must overlap this well to count as the same statement.
BODY_THRESHOLD = 0.6


def pattern_score(pattern: str, parsed_words: list[str]) -> float:
    """Score an elided transcription against a parsed body's prose tokens.

    The pattern is split on ``...``; the literal segments must appear in the
    parsed body. The first/last segments are anchored to the body's start/end
    when the pattern doesn't begin/end with an ellipsis. Scoring is by word
    overlap (math stripped from both sides), so it tolerates small transcription
    slips rather than demanding an exact quote.
    """
    segments = [to_words(s) for s in pattern.split(ELLIPSIS)]
    scores: list[float] = []

    every = [w for seg in segments for w in seg]
    if not every:
        return 1.0                      # nothing recorded but "..." — no signal
    scores.append(overlap(every, parsed_words))          # all anchors present?

    if segments[0]:                                       # pattern starts with text
        head = segments[0]
        scores.append(overlap(head, parsed_words[: len(head) + _SLACK]))
    if len(segments) > 1 and segments[-1]:                # pattern ends with text
        tail = segments[-1]
        window = parsed_words[-(len(tail) + _SLACK):] if parsed_words else []
        scores.append(overlap(tail, window))

    return sum(scores) / len(scores)


def score_pdf(parsed: Sequence[Statement], gt: PdfGroundTruth, config: str = "") -> PaperReport:
    kept = [p for p in parsed if _norm_kind(p.kind) not in _EXCLUDED_KINDS]
    pw = [to_words(p.body) for p in kept]
    scores = [
        (pattern_score(g.body, pw[i]), gi, i)
        for gi, g in enumerate(gt.statements)
        for i in range(len(kept))
    ]
    pairs, used_g, used_p = _greedy_align(scores)

    matched = []
    for gi, pi, sc in sorted(pairs):
        g, p = gt.statements[gi], kept[pi]
        diffs = []
        if _norm_kind(g.kind) != _norm_kind(p.kind):
            diffs.append(FieldDiff("kind", g.kind, p.kind))
        # number/proof are only checked when recorded; absent means "ignore".
        if g.number is not None and _norm_ref(g.number) != _norm_ref(p.ref):
            diffs.append(FieldDiff("number", g.number, p.ref))
        if g.proof is not None:
            if p.proof is None:
                diffs.append(FieldDiff("proof", "<a proof>", None))
            elif pattern_score(g.proof, to_words(p.proof)) < BODY_THRESHOLD:
                diffs.append(FieldDiff("proof", g.proof[:40] + "…", p.proof[:40] + "…"))
        matched.append(PairVerdict(g, p, diffs, sc))

    phantoms = [kept[i] for i in range(len(kept)) if i not in used_p]
    misses = [gt.statements[gi] for gi in range(len(gt.statements)) if gi not in used_g]
    return PaperReport(gt.name, config, "pdf", matched, phantoms, misses)


def score(parsed: Sequence[Statement], gt, config: str = "") -> PaperReport:
    """Dispatch to the tex or pdf scorer based on the ground-truth type."""
    if isinstance(gt, TexGroundTruth):
        return score_tex(parsed, gt, config)
    return score_pdf(parsed, gt, config)

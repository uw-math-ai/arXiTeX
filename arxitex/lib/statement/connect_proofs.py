import re
from typing import List
from arxitex.types import Statement

_REF_RE = re.compile(
    r'\\(?:[a-zA-Z]*[Rr]ef|autoref|cref|Cref|eqref)\s*\{([^}]*)\}'
    r'|\\hyperref\s*\[([^\]]*)\]'
)

THEOREM_KINDS = { "theorem", "proposition", "lemma", "corollary" }

# Commentary environments that may sit between a statement and its proof. The
# adjacency fallback walks back over these to reach the statement being proved —
# a proof proves a theorem/lemma/prop/corollary, not the remark next to it.
_COMMENTARY_KINDS = { "remark", "note", "observation", "convention", "notation" }


def _referenced_labels(text: str) -> set:
    """Labels the text points at via \\ref/\\Cref/\\hyperref."""
    out = set()
    for m in _REF_RE.finditer(text or ""):
        for group in m.groups():
            if group:
                out.update(part.strip() for part in group.split(",") if part.strip())
    return out


def _inside(inner: Statement, outer: Statement) -> bool:
    """Whether *inner* sits within *outer* in the source (when spans are known)."""
    if None in (inner.begin_pos, inner.end_pos, outer.begin_pos, outer.end_pos):
        return False
    return outer.begin_pos < inner.begin_pos and inner.end_pos <= outer.end_pos


def _adjacent_target(statements: List[Statement], proof_idx: int):
    """Index of the statement a note-less proof proves: the nearest preceding
    provable statement, skipping over commentary and over the proof's own nested
    content. None if there isn't one."""
    proof = statements[proof_idx]
    # A long proof may state and prove auxiliary lemmas along the way. Those are
    # part of the proof, but they close before it does, so they sit just before
    # it in the list. Step over them — by source span where we have one, else by
    # the \refs the proof body makes to the statements spliced out of it.
    referenced = _referenced_labels(proof.body)
    j = proof_idx - 1
    while j >= 0:
        prev = statements[j]
        if _inside(prev, proof):
            j -= 1                      # the proof's own nested statement or proof
            continue
        if prev.kind in THEOREM_KINDS:
            return j
        if prev.kind in _COMMENTARY_KINDS or any(l in referenced for l in prev.labels):
            j -= 1                      # a digression between statement and proof
            continue
        return None                     # a definition, example, another proof, ... — stop
    return None


def connect_proofs(statements: List[Statement]):
    # Index by every label a statement carries: a restated theorem may have more
    # than one, and a proof can reference any of them.
    label_to_idx = {}
    for idx, statement in enumerate(statements):
        if statement.kind == "proof":
            continue
        for label in statement.labels:
            label_to_idx.setdefault(label, idx)

    for proof_idx, proof, in enumerate(statements):
        if proof.kind != "proof":
            continue

        # A proof's note may name several statements ("Proof of Theorem 1.5 and
        # Corollary 1.6"); collect every label it resolves.
        targets = []
        if proof.note:
            for m in _REF_RE.finditer(proof.note):
                content = m.group(1) or m.group(2)
                if not content:
                    continue
                statement_idx = label_to_idx.get(content.strip())
                if statement_idx is not None:
                    targets.append(statement_idx)

        # A proof that names nothing belongs to the statement it follows.
        if not targets:
            adj = _adjacent_target(statements, proof_idx)
            if adj is not None:
                targets.append(adj)

        # Attach to every statement the proof covers, but never overwrite: a
        # statement keeps the first proof it is given.
        for statement_idx in targets:
            if statements[statement_idx].proof is None:
                statements[statement_idx].proof = proof.body

    return [statement for statement in statements if statement.kind != "proof"]
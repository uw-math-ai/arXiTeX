import re
from typing import List
from arxitex.types import Statement

_REF_RE = re.compile(
    r'\\(?:[a-zA-Z]*[Rr]ef|autoref|cref|Cref|eqref)\s*\{([^}]*)\}'
    r'|\\hyperref\s*\[([^\]]*)\]'
)

THEOREM_KINDS = { "theorem", "proposition", "lemma", "corollary" }
    
def connect_proofs(statements: List[Statement]):
    label_to_idx = {
        statement.label: idx
        for idx, statement in enumerate(statements)
        if statement.kind != "proof" and statement.label is not None
    }

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
        if not targets and proof_idx > 0 and statements[proof_idx - 1].kind in THEOREM_KINDS:
            targets.append(proof_idx - 1)

        # Attach to every statement the proof covers, but never overwrite: a
        # statement keeps the first proof it is given.
        for statement_idx in targets:
            if statements[statement_idx].proof is None:
                statements[statement_idx].proof = proof.body

    return [statement for statement in statements if statement.kind != "proof"]
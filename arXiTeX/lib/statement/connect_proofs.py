import re
from typing import List
from arXiTeX.types import Statement

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
        matched = False

        if proof.note:
            for m in _REF_RE.finditer(proof.note):
                content = m.group(1) or m.group(2)

                for label, statement_idx in label_to_idx.items():
                    if statement_idx == proof_idx:
                        continue

                    if content.strip() == label:
                        statements[statement_idx].proof = proof.body
                        matched = True
                        break

                break

        if not matched:
            if proof_idx > 0 and statements[proof_idx - 1].kind in THEOREM_KINDS:
                statements[proof_idx - 1].proof = proof.body

    return [statement for statement in statements if statement.kind != "proof"]
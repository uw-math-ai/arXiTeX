import re
from typing import List, Dict
from pathlib import Path
from .log_envs import log_envs
from .flatten import flatten_tex
from arXiTeX.types import Theorem

_REF_RE = re.compile(
    r'\\(?:[a-zA-Z]*[Rr]ef|autoref|cref|Cref|eqref)\s*\{([^}]*)\}'
    r'|\\hyperref\s*\[([^\]]*)\]'
)

def parse(paper_dir: Path, main_file: Path, theorem_envs: Dict) -> List[Theorem]:
    flat_tex = flatten_tex(paper_dir, main_file, ignore_errors=True)

    theorems: List[Theorem] = []

    envs = log_envs(flat_tex)

    attach_proof = False

    for env in envs:
        if env.env == "proof":
            # proofs that occur right after a theorem environment belong to that theorem
            if attach_proof:
                attach_proof = False
                
                theorems[-1].proof = env.body

            # proofs that reference a theorem in its note belong to that theorem
            # only takes first reference and requries theorem is before the proof
            else:
                ref_match = _REF_RE.search(env.note or "")
                
                if not ref_match:
                    continue

                for theorem in theorems:
                    if theorem.label == ref_match.group(1):
                        theorem.proof = env.body

        if env.env not in theorem_envs:
            attach_proof = False
            continue

        theorems.append(Theorem(
            type=theorem_envs[env.env],
            ref=env.ref,
            note=env.note,
            label=env.label,
            body=env.body
        ))

        attach_proof = True

    return theorems
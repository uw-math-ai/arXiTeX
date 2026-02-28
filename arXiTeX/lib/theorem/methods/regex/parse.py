from pathlib import Path
from typing import List
from arXiTeX.types import Theorem
from .flatten import flatten_tex
from .log_envs import log_envs
from ...guess_main_file import guess_main_file
from ...extract_theorem_envs import extract_theorem_envs

def parse_by_regex(
    paper_dir: Path
) -> List[Theorem]:
    """
    Parses a paper's source files into a list of theorems using regex.

    Parameters
    ----------
    paper_dir : Path
        The path to all of a paper's source files

    Returns
    -------
    theorems: List[Theorem]
        A list of regex-parsed theorems
    """

    main_file = guess_main_file(paper_dir)
    theorem_envs = extract_theorem_envs(paper_dir)

    theorems: List[Theorem] = []

    flat_tex = flatten_tex(paper_dir, main_file, ignore_errors=True)

    envs = log_envs(flat_tex)

    attach_proof = False

    for env in envs:
        if env.env == "proof" and attach_proof:
            attach_proof = False
            
            theorems[-1].proof = env.body

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

    theorems.sort(key=lambda t: (t.ref is None, t.ref or ""))

    return theorems
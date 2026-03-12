from typing import List
from pathlib import Path
from .log_envs import log_envs
from .flatten import flatten_tex
from arXiTeX.types import Statement

def parse(paper_dir: Path, main_file: Path) -> List[Statement]:
    flat_tex = flatten_tex(paper_dir, main_file, ignore_errors=True)

    return [
        Statement(
            kind=env.env,
            ref=env.ref,
            note=env.note,
            label=env.label,
            body=env.body,
            proof=None
        )
        for env in log_envs(flat_tex)
    ]
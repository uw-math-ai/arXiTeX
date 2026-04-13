from typing import List, Optional
from pathlib import Path
from .log_envs import log_envs
from .flatten import flatten_tex
from arXiTeX.types import Statement
from arXiTeX.lib.statement.extract_context import extract_contexts, strip_comments

def parse(
    paper_dir: Path,
    main_file: Path,
    context: int = 0,
    flat_tex: Optional[str] = None,
) -> List[Statement]:
    if flat_tex is None:
        flat_tex = flatten_tex(paper_dir, main_file, ignore_errors=True)

    envs = log_envs(flat_tex)

    if context > 0:
        # log_envs works on a comment-stripped version of flat_tex internally;
        # begin_pos/end_pos are positions in that same cleaned string.
        clean = strip_comments(flat_tex)
        return [
            Statement(
                kind=env.env,
                ref=env.ref,
                note=env.note,
                label=env.label,
                body=env.body,
                proof=None,
                pre_context=clean[max(0, env.begin_pos - context) : env.begin_pos] or None,
                post_context=clean[env.end_pos : env.end_pos + context] or None,
            )
            for env in envs
        ]

    return [
        Statement(
            kind=env.env,
            ref=env.ref,
            note=env.note,
            label=env.label,
            body=env.body,
            proof=None,
        )
        for env in envs
    ]

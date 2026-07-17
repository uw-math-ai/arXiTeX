"""Counter/numbering behavior of the regex environment logger."""

from arxitex.lib.statement.methods.regex.log_envs import _parse_theorem_defs, log_envs


def test_theorem_env_name_with_spaces_is_recognized():
    src = r"\newtheorem{primary statistics}[theorem]{Primary Statistics}"
    defs = _parse_theorem_defs(src)
    assert "primary statistics" in defs
    assert defs["primary statistics"]["shared"] == "theorem"
    assert defs["primary statistics"]["display"] == "Primary Statistics"


def test_space_named_env_advances_the_shared_counter():
    # A theorem-like env whose name contains a space (and which a caller may
    # filter out of the output) must still consume the shared counter, so the
    # statements after it are numbered correctly. Mirrors arXiv:1708.03871,
    # where three `primary statistics` blocks sit before Theorem 9.
    src = r"""
    \newtheorem{theorem}{Theorem}
    \newtheorem{definition}[theorem]{Definition}
    \newtheorem{primary statistics}[theorem]{Primary Statistics}
    \begin{document}
    \begin{definition}\label{d1}A norm is nonnegative.\end{definition}
    \begin{primary statistics}\label{s1}First statistic.\end{primary statistics}
    \begin{primary statistics}\label{s2}Second statistic.\end{primary statistics}
    \begin{theorem}\label{t1}The main result holds.\end{theorem}
    \end{document}
    """
    defs = _parse_theorem_defs(src)
    by_label = {lab: e for e in log_envs(src) if e.raw_env in defs for lab in e.labels}
    assert by_label["d1"].ref == "1"
    assert by_label["s1"].ref == "2"
    assert by_label["s2"].ref == "3"
    # the theorem is 4, not 2 — the two space-named blocks were counted
    assert by_label["t1"].ref == "4"
    # and the space-named env keeps its display name, so a kinds filter can drop it
    assert by_label["s1"].env == "primary statistics"


def test_starred_env_names_still_match():
    # the widened begin/end matcher must not regress starred environments
    src = r"""
    \newtheorem{theorem}{Theorem}
    \newtheorem*{remark}{Remark}
    \begin{document}
    \begin{theorem}\label{t}Body.\end{theorem}
    \begin{remark}\label{r}An unnumbered remark.\end{remark}
    \end{document}
    """
    defs = _parse_theorem_defs(src)
    by_label = {lab: e for e in log_envs(src) if e.raw_env in defs for lab in e.labels}
    assert by_label["t"].ref == "1"
    assert by_label["r"].ref is None

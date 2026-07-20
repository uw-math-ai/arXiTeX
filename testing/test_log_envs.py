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


def test_nested_statement_is_extracted_and_referenced_in_the_outer():
    # a fact restated inside a proof: extracted on its own, and the proof body
    # references it (\ref) instead of embedding a duplicate copy of it.
    src = r"""
    \newtheorem{lemma}{Lemma}
    \newtheorem{fact}[lemma]{Fact}
    \begin{document}
    \begin{lemma}\label{lem:main}The main lemma statement is here.\end{lemma}
    \begin{proof}
    We rely on the following.
    \begin{fact}\label{fct:helper}Every group has an identity element.\end{fact}
    Applying the fact finishes the proof.
    \end{proof}
    \end{document}
    """
    envs = log_envs(src)
    by_label = {lab: e for e in envs for lab in e.labels}
    # the nested fact is extracted, numbered on the shared counter (lemma 1, fact 2)
    assert by_label["fct:helper"].env == "fact"
    assert by_label["fct:helper"].ref == "2"
    proof = next(e for e in envs if e.raw_env == "proof")
    assert r"\ref{fct:helper}" in proof.body
    assert "identity element" not in proof.body   # inner body not duplicated into outer
    assert proof.labels == []                       # proof does not steal the inner label


def test_unlabeled_nested_statement_gets_a_synthetic_label():
    src = r"""
    \newtheorem{lemma}{Lemma}
    \newtheorem{fact}[lemma]{Fact}
    \begin{document}
    \begin{proof}
    \begin{fact}A nameless nested fact with no label at all here.\end{fact}
    That concludes the argument.
    \end{proof}
    \end{document}
    """
    envs = log_envs(src)
    fact = next(e for e in envs if e.raw_env == "fact")
    assert len(fact.labels) == 1 and fact.labels[0].startswith("inner-")
    proof = next(e for e in envs if e.raw_env == "proof")
    assert fact.labels[0] in proof.body            # the synthetic label is what's referenced


def test_top_level_unlabeled_statement_gets_no_synthetic_label():
    # synthetic labels are only for *nested* statements that need a reference
    src = r"""
    \newtheorem{theorem}{Theorem}
    \begin{document}
    \begin{theorem}An ordinary unlabeled top-level theorem statement.\end{theorem}
    \end{document}
    """
    thm = next(e for e in log_envs(src) if e.raw_env == "theorem")
    assert thm.labels == []


def test_counter_format_markup_is_stripped_from_the_ref():
    # \renewcommand{\thesubsection}{{\bf\arabic{subsection}}} only *styles* the
    # printed number -- a reader sees "1.1", not "{\bf1}.1". Mirrors 1604.07787.
    from arxitex.lib.statement.methods.regex.log_envs import _clean_ref

    assert _clean_ref(r"{\bf5}") == "5"
    assert _clean_ref(r"{\bf1}.2") == "1.2"
    assert _clean_ref(r"\textbf{A}.3") == "A.3"
    assert _clean_ref("1.2") == "1.2"          # ordinary refs pass through

    src = r"""
    \newtheorem{theorem}{Theorem}[subsection]
    \renewcommand{\thesubsection}{{\bf\arabic{subsection}}}
    \begin{document}
    \subsection{First}
    \begin{theorem}\label{t}A real statement of a theorem.\end{theorem}
    \end{document}
    """
    thm = next(e for e in log_envs(src) if e.raw_env == "theorem")
    assert thm.ref == "1.1"


def test_leading_parenthetical_is_captured_as_a_note():
    # some authors open a proof body with "(of Theorem ...)" instead of the
    # bracketed [..] argument; it serves the same role, so capture it as a note.
    src = r"""
    \newtheorem{theorem}{Theorem}
    \begin{document}
    \begin{theorem}\label{thm:x}A real statement of some theorem here.\end{theorem}
    \begin{proof}(of Theorem~\ref{thm:x}) The argument goes as follows.\end{proof}
    \end{document}
    """
    proof = next(e for e in log_envs(src) if e.raw_env == "proof")
    assert proof.note == r"of Theorem~\ref{thm:x}"
    assert proof.body.startswith("The argument")   # the parenthetical is not in the body


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

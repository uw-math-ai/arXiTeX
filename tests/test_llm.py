"""LLM-method parsing with a mocked litellm backend (no network / API key)."""

from types import SimpleNamespace

import litellm

import arXiTeX as arx
from arXiTeX.lib.statement.methods.llm import _chunk, _parse_response
from conftest import FIXTURE_PATHS, by_label


def _fake_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_llm_parse_with_mocked_backend(monkeypatch):
    canned = """[
      {"kind":"theorem","ref":"1.1","note":"Nonnegativity","label":"thm:main",
       "body":"For every $x$ we have $\\\\|x\\\\| \\\\geq 0$.","proof":"By definition."},
      {"kind":"definition","ref":"1.1","note":null,"label":"def:norm",
       "body":"A norm is a nonnegative function.","proof":null}
    ]"""

    def fake_completion(*args, **kwargs):
        assert "messages" in kwargs
        return _fake_response(canned)

    monkeypatch.setattr(litellm, "completion", fake_completion)

    res = arx.Parser(method="llm", focus="statements").parse(path=FIXTURE_PATHS["simple"])
    assert res.method_used == "llm"
    labeled = by_label(res.statements)
    assert labeled["thm:main"].kind == "theorem"
    assert labeled["thm:main"].proof == "By definition."
    assert labeled["def:norm"].kind == "definition"


def test_llm_deduplicates_across_chunks(monkeypatch):
    canned = ('[{"kind":"theorem","label":"t",'
              '"body":"For all integers $n$, the identity $n + 0 = n$ holds."}]')
    monkeypatch.setattr(litellm, "completion", lambda *a, **k: _fake_response(canned))

    # even if every chunk returns the same statement, it appears once
    res = arx.Parser(method="llm", focus="statements", validation="none").parse(
        path=FIXTURE_PATHS["multifile"]
    )
    assert len([s for s in res.statements if s.label == "t"]) == 1


def test_chunker_respects_budget_and_sections():
    src = "intro " * 5 + "".join(f"\\section{{S{i}}}\n" + "x" * 300 for i in range(5))
    chunks = _chunk(src, 400)
    assert len(chunks) > 1
    # no chunk exceeds the budget unless it is a single oversized section
    assert all(len(c) <= 400 or c.count("\\section") <= 1 for c in chunks)


def test_response_parser_is_lenient():
    # tolerates prose around the JSON, bad/empty entries, and casing
    resp = 'Here:\n[{"kind":"Lemma","body":"a real lemma body"},{"kind":"x","body":""}]'
    stmts = _parse_response(resp, {"lemma"})
    assert len(stmts) == 1
    assert stmts[0].kind == "lemma"

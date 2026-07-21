"""LLM-method parsing with a mocked OpenAI-compatible backend (no network / API key)."""

from types import SimpleNamespace

import pytest

import arxitex as arx
from arxitex.lib.statement.methods import llm as llm_mod
from arxitex.lib.statement.methods.llm import _chunk, _parse_response
from conftest import FIXTURE_PATHS, by_label


def _fake_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _fake_client(content: str, on_call=None):
    """A stand-in for openai.OpenAI exposing just .chat.completions.create."""
    def create(**kwargs):
        if on_call is not None:
            on_call(kwargs)
        return _fake_response(content)

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _patch_client(monkeypatch, content, on_call=None):
    monkeypatch.setattr(
        llm_mod, "_make_client", lambda api_key, base_url: _fake_client(content, on_call)
    )


def test_llm_parse_with_mocked_backend(monkeypatch):
    canned = """[
      {"kind":"theorem","number":"1.1","note":"Nonnegativity","label":"thm:main",
       "body":"For every $x$ we have $\\\\|x\\\\| \\\\geq 0$.","proof":"By definition."},
      {"kind":"definition","number":"1.1","note":null,"label":"def:norm",
       "body":"A norm is a nonnegative function.","proof":null}
    ]"""
    seen = []
    _patch_client(monkeypatch, canned, on_call=lambda kw: seen.append(kw))

    res = arx.Parser(method="llm", focus="statements").parse(path=FIXTURE_PATHS["simple"])
    assert res.method_used == "llm"
    labeled = by_label(res.statements)
    assert labeled["thm:main"].kind == "theorem"
    assert labeled["thm:main"].proof == "By definition."
    assert labeled["def:norm"].kind == "definition"
    # the request carries the chat-completions shape
    assert seen and "messages" in seen[0] and "model" in seen[0]


def test_llm_deduplicates_across_chunks(monkeypatch):
    canned = ('[{"kind":"theorem","label":"t",'
              '"body":"For all integers $n$, the identity $n + 0 = n$ holds."}]')
    _patch_client(monkeypatch, canned)

    # even if every chunk returns the same statement, it appears once
    res = arx.Parser(method="llm", focus="statements", validation="none").parse(
        path=FIXTURE_PATHS["multifile"]
    )
    assert len([s for s in res.statements if s.labels == ["t"]]) == 1


def test_llm_defaults_to_nebius_and_an_open_model():
    m = arx.Llm()
    assert m.base_url == "https://api.studio.nebius.com/v1"
    assert m.model == "deepseek-ai/DeepSeek-V4-Pro"


def test_make_client_errors_clearly_without_a_key(monkeypatch):
    for var in llm_mod._API_KEY_ENVS:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValueError, match="No API key"):
        llm_mod._make_client(None, llm_mod._DEFAULT_BASE_URL)


def test_make_client_retries_are_configurable(monkeypatch):
    # long multi-call jobs must ride out a transient 529 rather than bin the run
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    assert llm_mod._make_client(None, llm_mod._DEFAULT_BASE_URL).max_retries == 2
    assert llm_mod._make_client(None, llm_mod._DEFAULT_BASE_URL, max_retries=8).max_retries == 8


def test_make_client_prefers_explicit_key_then_env(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "from-env")
    client = llm_mod._make_client(None, llm_mod._DEFAULT_BASE_URL)
    assert client.api_key == "from-env"
    client = llm_mod._make_client("explicit", llm_mod._DEFAULT_BASE_URL)
    assert client.api_key == "explicit"


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


def test_response_parser_tolerates_raw_newlines_in_bodies():
    # a multi-line LaTeX body echoed with literal newlines is not strict JSON,
    # but must still parse rather than silently yielding zero statements
    resp = '[{"kind":"lemma","body":"first line\nsecond line of the body"}]'
    stmts = _parse_response(resp, {"lemma"})
    assert len(stmts) == 1
    assert "second line" in stmts[0].body

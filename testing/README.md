# Tests

Run the suite with:

```
pip install -e ".[dev]"
pytest
```

## Layout

`fixtures/` holds small, self-contained LaTeX projects that double as readable
examples of what each method handles. Each is valid, compilable LaTeX:

| Fixture | What it showcases |
|---|---|
| `simple/` | Section numbering, a shared theorem/lemma/definition counter, an unnumbered `\newtheorem*`, an adjacent proof, and user macros to expand. |
| `multifile/` | Statements split across `\input` files, `\numberwithin` per-section resets, and a nested `align` inside a theorem body. |
| `thmtools.tex` | `\declaretheorem` with a `sibling` counter and a `numbered=no` environment. |
| `proof_by_ref/` | A proof attached to its theorem by `\ref` (with an unrelated lemma in between, so adjacency can't be the reason). |
| `macros.tex` | Zero-arg / multi-arg `\newcommand` and `\def`, plus a macro defined via another macro (nested expansion). |
| `no_statements/` | A paper with no statements — the parser must fail cleanly, not invent output. |

## Test files

- `test_regex.py` — the dependency-free `regex` method over every fixture.
- `test_tex.py` — the real-TeX `tex` method (auto-skipped when `tectonic` is not
  on `PATH`), including a parity check against `regex`.
- `test_llm.py` — the `llm` method with a **mocked** litellm backend (no network
  or API key needed), plus the chunker and response parser.
- `test_parser.py` — `Parser` behaviors: source auto-detection, fallback chains,
  `focus`, `validation`, and input guards.

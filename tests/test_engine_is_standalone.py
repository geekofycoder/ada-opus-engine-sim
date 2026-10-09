"""The architectural claim, enforced.

engine/ must never import from llm/. The whole design rests on the reasoning
being pure arithmetic with no model involved - if that boundary erodes, the
claim quietly becomes false.
"""

import ast
from conftest import ROOT

ENGINE = ROOT / "engine"


def imported_modules(path):
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


def test_engine_never_imports_llm():
    for f in sorted(ENGINE.glob("*.py")):
        assert "llm" not in imported_modules(f), f"{f.name} imports llm"


def test_engine_never_imports_anthropic():
    for f in sorted(ENGINE.glob("*.py")):
        mods = imported_modules(f)
        for banned in ("anthropic", "pydantic", "requests", "httpx"):
            assert banned not in mods, f"{f.name} imports {banned}"


def test_bayes_imports_only_stdlib_math():
    assert imported_modules(ENGINE / "bayes.py") == {"math"}

"""The harness must not import the cost model or the simulator (harness/__init__.py).

The cluster replaces the cost model; importing it would invite reporting a
modelled number as a measured one. Checked on the source, so a lazy import
inside a function is caught too.
"""
import ast
from pathlib import Path

import pytest

FORBIDDEN = ("fragalloc.cost", "fragalloc.simulator")
HARNESS = Path(__file__).resolve().parents[1] / "src" / "fragalloc" / "harness"


def imported(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


@pytest.mark.parametrize("path", sorted(HARNESS.glob("*.py")), ids=lambda p: p.name)
def test_harness_module_keeps_the_dependency_rule(path):
    bad = {n for n in imported(ast.parse(path.read_text())) if n.startswith(FORBIDDEN)}
    assert not bad, f"{path.name} imports {sorted(bad)}"


def test_the_check_can_fail():
    tree = ast.parse("def f():\n    from fragalloc.cost import evaluate\n")
    assert {n for n in imported(tree) if n.startswith(FORBIDDEN)}

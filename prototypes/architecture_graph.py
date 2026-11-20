"""Inspect local Python dependencies without importing Qt or evaluating application code."""

import argparse
import ast
import json
from importlib.util import resolve_name
from pathlib import Path


def module_imports(name, path):
    """Resolve import syntax, including package aliases, without evaluating any code."""
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    imports = set()
    for node in ast.walk(ast.parse(path.read_text("utf-8-sig"))):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module
            )
            if base:
                imports.add(base)
                imports.update(f"{base}.{a.name}" for a in node.names if a.name != "*")
    return imports


def module_paths(root):
    result = {}
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        result[".".join((root.name, *parts))] = path
    return result


def dependency_graph(root):
    modules = module_paths(root)
    return {
        name: sorted((module_imports(name, path) & modules.keys()) - {name})
        for name, path in modules.items()
    }


def cycles(graph):
    complete, active, found = set(), [], []

    def visit(key):
        if key in active:
            found.append(active[active.index(key) :] + [key])
            return
        if key in complete:
            return
        active.append(key)
        for target in graph[key]:
            visit(target)
        active.pop()
        complete.add(key)

    for key in graph:
        visit(key)
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    graph = dependency_graph(Path("lodandsy"))
    result = dict(
        modules=len(graph), edges=sum(map(len, graph.values())), cycles=cycles(graph), imports=graph
    )
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "imports"}))


if __name__ == "__main__":
    main()

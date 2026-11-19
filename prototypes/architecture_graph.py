"""Inspect local Python dependencies without importing Qt or evaluating application code."""

import argparse
import ast
import json
from pathlib import Path


def dependency_graph(root):
    modules = {".".join(p.with_suffix("").parts): p for p in root.rglob("*.py")}
    result = {}
    for name, path in modules.items():
        imports = set()
        for node in ast.walk(ast.parse(path.read_text("utf-8-sig"))):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        result[name] = sorted(item for item in imports if item in modules)
    return result


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

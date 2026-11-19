"""Check compiled application code against this checkout before packaging a candidate."""

import argparse
import json
import types
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def normalized(code):
    return code.replace(
        co_filename="<source>",
        co_consts=tuple(
            normalized(value) if isinstance(value, types.CodeType) else value
            for value in code.co_consts
        ),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    executable = ROOT / ".prototype-deps/mvp-dist/LODANDSY/LODANDSY.exe"
    pyz = CArchiveReader(str(executable)).open_embedded_archive("PYZ.pyz")
    mismatches, count = [], 0
    for folder in ("lodandsy", "build_support"):
        for path in (ROOT / folder).rglob("*.py"):
            name = ".".join(path.relative_to(ROOT).with_suffix("").parts)
            if name.endswith(".__init__"):
                name = name[:-9]
            if name not in pyz.toc:
                continue
            actual = normalized(pyz.extract(name))
            expected = normalized(compile(path.read_bytes(), str(path), "exec", dont_inherit=True))
            count += 1
            if actual != expected:
                mismatches.append(name)
    obsolete = [
        name
        for name in pyz.toc
        if name
        in {
            "lodandsy.application.markdown_commands",
            "lodandsy.application.markdown_links",
            "lodandsy.ui.markdown_source_edit",
            "lodandsy.ui.markdown_toolbar",
            "lodandsy.ui.card_tree_model",
            "lodandsy.ui.tools_widgets",
            "lodandsy.domain.tools",
            "lodandsy.domain.card_templates",
            "lodandsy.domain.dice_document",
            "lodandsy.application.dice_payload_codec",
        }
    ]
    result = {
        "compiled_modules_compared": count,
        "mismatches": mismatches,
        "obsolete_modules": obsolete,
        "passed": not mismatches and not obsolete and count >= 60,
    }
    if args.report:
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    if not result["passed"]:
        raise RuntimeError("Frozen code differs from checkout; rebuild after edits finish")


if __name__ == "__main__":
    main()

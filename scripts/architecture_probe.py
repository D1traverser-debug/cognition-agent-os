"""Read-only AST import inventory; intentionally NOT a runtime call graph."""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path


def inspect(root: Path) -> dict:
    root = root.resolve(strict=True)
    package = root / "src" / "cognition_agent_os"
    if not package.is_dir():
        raise ValueError("Expected cognition_agent_os source package")
    files = sorted(package.glob("*.py"))
    known = {p.stem for p in files}
    modules, errors = [], []
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_bytes(), filename=rel)
        except (SyntaxError, UnicodeError, ValueError) as exc:
            errors.append({"path": rel, "error": type(exc).__name__})
            continue
        imports, dynamic = set(), []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level == 1:
                    if node.module:
                        imports.add(node.module.split(".")[0])
                    else:
                        imports.update(x.name for x in node.names if x.name in known)
                elif node.level == 0 and node.module and node.module.startswith("cognition_agent_os."):
                    imports.add(node.module.split(".")[1])
            elif isinstance(node, ast.Import):
                for item in node.names:
                    if item.name.startswith("cognition_agent_os."):
                        imports.add(item.name.split(".")[1])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
                dynamic.append(node.lineno)
        modules.append({
            "name": path.stem, "path": rel,
            "imports": sorted(imports & known),
            "unresolved_local_imports": sorted(imports - known),
            "dynamic_import_lines": sorted(dynamic),
            "definitions": sorted(n.name for n in tree.body
                                  if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))),
        })
    return {"schema_version": 1,
            "kind": "static_python_ast_import_inventory_not_execution_graph",
            "file_count": len(files), "parsed_count": len(modules),
            "parse_errors": errors, "modules": modules}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, default=Path("."))
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = inspect(args.repo)
    data = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(data, encoding="utf-8")
    else:
        print(data, end="")
    if result["parse_errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

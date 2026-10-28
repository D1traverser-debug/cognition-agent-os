"""Read-only AST import inventory; intentionally NOT a runtime call graph."""
from __future__ import annotations
import argparse
import ast
import hashlib
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
            source_bytes = path.read_bytes()
            tree = ast.parse(source_bytes, filename=rel)
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
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "description_origin": "UNVERIFIED_SOURCE_DOCSTRING",
            "source_description": (" ".join(ast.get_docstring(tree).split())[:240]
                                   if ast.get_docstring(tree) else None),
            "imports": sorted(imports & known),
            "unresolved_local_imports": sorted(imports - known),
            "dynamic_import_lines": sorted(dynamic),
            "definitions": sorted(n.name for n in tree.body
                                  if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))),
        })
    reverse = {item["name"]: [] for item in modules}
    for item in modules:
        for imported in item["imports"]:
            if imported in reverse:
                reverse[imported].append(item["name"])
    for item in modules:
        item["imported_by"] = sorted(reverse[item["name"]])
    return {"schema_version": 2,
            "kind": "static_python_ast_import_inventory_not_execution_graph",
            "file_count": len(files), "parsed_count": len(modules),
            "parse_errors": errors, "modules": modules}


def focus(report: dict, names: list[str], *, hops: int = 1) -> dict:
    """Bounded source neighborhood; this is NOT a semantic/AOCI whole index."""
    by_name = {m["name"]: m for m in report["modules"]}
    if (type(hops) is not int or not 0 <= hops <= 2
            or not isinstance(names, list) or not 1 <= len(names) <= 8
            or any(not isinstance(n, str) for n in names)
            or len(set(names)) != len(names)
            or any(n not in by_name for n in names)):
        raise ValueError("INVALID_ARCHITECTURE_FOCUS")
    selected, frontier = set(names), set(names)
    for _ in range(hops):
        neighbors = set()
        for name in frontier:
            neighbors.update(by_name[name]["imports"])
            neighbors.update(by_name[name]["imported_by"])
        frontier = (neighbors & by_name.keys()) - selected
        selected.update(frontier)
    return {"schema_version": report["schema_version"],
            "kind": "FOCUSED_AST_SOURCE_LOCATORS_NOT_WHOLE_SYSTEM_COGNITION",
            "source_scan_file_count": report["file_count"],
            "source_scan_parsed_count": report["parsed_count"],
            "parse_errors": report["parse_errors"],
            "selected_count": len(selected), "focus": names, "hops": hops,
            "modules": [by_name[n] for n in sorted(selected)]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, default=Path("."))
    p.add_argument("--output", type=Path)
    p.add_argument("--focus", nargs="+", metavar="MODULE")
    p.add_argument("--hops", type=int, default=1)
    args = p.parse_args()
    result = inspect(args.repo)
    if args.focus is not None:
        result = focus(result, args.focus, hops=args.hops)
    data = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(data, encoding="utf-8")
    else:
        print(data, end="")
    if result["parse_errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

"""Fail closed on unregistered local-effect callsites in cognition-agent-os.

This is a *source-shape change gate*, not a semantic, grant, or runtime oracle.
Every allowed entry below has its own independently executable regressions.
The remaining actual security authority is ledger.current_guard at effect time.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys


# Legacy implementation shares one filesystem sink. This list is a code-owner
# contract: new call sites must not silently become unreviewed effect gateways.
DIRECT_STAGES = frozenset({
    ("runner", "store_once"),
    ("sandbox_effect", "_atomic_stage"),
    ("pipeline_oracle", "_stage"),
    ("repair_oracle", "_stage_patch"),
    ("repo_repair", "_stage"),
})

ARTIFACT_STORES = frozenset({
    ("capability_dispatch", "_snapshot_diff"),
    ("goal_loop", "run_goal_case"),
    ("investigation", "run_investigation"),
    ("research_gap", "run_research_gap"),
    ("research_assessment", "run_assessment"),
    ("reconciliation", "run_reconciliation"),
    ("pipeline_repair", "run_pipeline_case"),
    ("repair_search", "run_repair_case"),
    ("repo_repair", "run_repo_candidate"),
    ("repo_refinement", "_freeze_revision"),
})

# Review effect boundaries must call the shared *live* authority gate inside
# the same SQLite immediate transaction that encloses their actual file stage.
REVIEW_EFFECTS = frozenset({
    ("sandbox_effect", "stage_one"),
    ("pipeline_oracle", "review_pipeline"),
    ("repair_oracle", "review_patch"),
    ("repo_repair", "review_repo"),
    ("repo_refinement", "_freeze_revision"),
})


class _Effects(ast.NodeVisitor):
    def __init__(self, module: str):
        self.module = module
        self.stack: list[str] = []
        self.direct: list[tuple[str, str, int]] = []
        self.store: list[tuple[str, str, int]] = []
        self.functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self.aliases: dict[str, str] = {
            "stage_immutable": "stage_immutable", "store_once": "store_once"
        }

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Import aliases are no loophole in the boundary inventory.
        if node.level == 1 and node.module in ("runner", "isolated_filesystem"):
            for value in node.names:
                if value.name in ("store_once", "stage_immutable"):
                    self.aliases[value.asname or value.name] = value.name

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self.stack:
            self.functions[node.name] = node
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        callee = node.func
        if isinstance(callee, ast.Name):
            name = self.aliases.get(callee.id, callee.id)
        elif isinstance(callee, ast.Attribute):
            name = callee.attr
        else:
            name = None
        owner = self.stack[0] if self.stack else "<module>"
        if name == "stage_immutable":
            self.direct.append((self.module, owner, node.lineno))
        elif name == "store_once":
            self.store.append((self.module, owner, node.lineno))
        self.generic_visit(node)


def _calls_guard_in_transaction(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    seen_guard = False
    seen_lock = False
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "current_guard":
                seen_guard = True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == "BEGIN IMMEDIATE":
                seen_lock = True
    return seen_guard and seen_lock


def inspect(root: Path) -> list[str]:
    """Return violations, never self-sign a source or effect as safe."""
    pkg = root / "src" / "cognition_agent_os"
    if not pkg.is_dir():
        return ["MISSING_SOURCE_ROOT"]
    findings: list[str] = []
    direct: list[tuple[str, str, int]] = []
    stores: list[tuple[str, str, int]] = []
    functions: dict[tuple[str, str], ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for path in sorted(pkg.glob("*.py")):
        try:
            parsed = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            findings.append(f"UNREADABLE_OR_INVALID_AST:{path.name}:{type(exc).__name__}")
            continue
        visitor = _Effects(path.stem)
        visitor.visit(parsed)
        direct.extend(visitor.direct)
        stores.extend(visitor.store)
        functions.update({(path.stem, name): node
                          for name, node in visitor.functions.items()})
    for category, observed, expected in (
        ("STAGE", direct, DIRECT_STAGES),
        ("ARTIFACT", stores, ARTIFACT_STORES),
    ):
        counted: dict[tuple[str, str], int] = {}
        for module, function, lineno in observed:
            key = module, function
            counted[key] = counted.get(key, 0) + 1
            if key not in expected:
                findings.append(f"UNREGISTERED_{category}_EFFECT:{module}:{function}:{lineno}")
        for key in sorted(expected):
            # Exactly one reviewed callsite per entry: adding a second call
            # bypasses the intended bounded single-file effect contract.
            if counted.get(key, 0) != 1:
                findings.append(
                    f"{category}_EFFECT_COUNT:{key[0]}:{key[1]}:{counted.get(key, 0)}")
    for key in sorted(REVIEW_EFFECTS):
        fn = functions.get(key)
        if fn is None or not _calls_guard_in_transaction(fn):
            findings.append(f"REVIEW_GUARD_MISSING:{key[0]}:{key[1]}")
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    faults = inspect(root)
    print(json.dumps({
        "status": "EFFECT_BOUNDARY_STRUCTURE_FAIL" if faults else
                  "EFFECT_BOUNDARY_STRUCTURE_CHECKED",
        "violations": faults,
        "independent_semantic_proof": False,
        "verified_runtime_effect": False,
    }, sort_keys=True))
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())

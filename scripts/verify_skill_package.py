#!/usr/bin/env python3
"""Enforce CAOS Skill entrypoint budgets and exact on-demand package closure.

The platform ceiling applies to SKILL.md entrypoints, not reference modules.
Reference modules have a separate bound and must be explicitly declared.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath


class SkillPackageError(ValueError):
    pass


def _relative_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise SkillPackageError(f"{label}: expected a non-empty relative path")
    if "\\" in value:
        raise SkillPackageError(f"{label}: use POSIX '/' separators: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise SkillPackageError(f"{label}: path traversal/absolute path is forbidden: {value!r}")
    if not path.parts:
        raise SkillPackageError(f"{label}: empty path")
    return path


def _checked_path(root: Path, value: object, label: str) -> Path:
    if value == ".":
        return root
    relative = _relative_path(value, label)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SkillPackageError(f"{label}: symlink is forbidden: {value}")
    resolved_root = root.resolve()
    resolved = current.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise SkillPackageError(f"{label}: path escapes repository root: {value}")
    return current


def _read_utf8(path: Path, label: str) -> tuple[bytes, str]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SkillPackageError(f"{label}: invalid UTF-8: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise SkillPackageError(f"{label}: UTF-8 BOM is not permitted")
    # Canonicalize checkout line endings before counting or packaging so
    # Linux and Windows produce identical UTF-8 byte budgets and ZIP content.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.encode("utf-8"), text


def _frontmatter(text: str, label: str, max_description: int) -> None:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise SkillPackageError(f"{label}: YAML frontmatter is missing or malformed")
    header = text[4:text.index("\n---\n", 4)]
    fields = {}
    for line in header.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    if not fields.get("name") or not fields.get("description"):
        raise SkillPackageError(f"{label}: frontmatter requires name and description")
    if len(fields["description"]) > max_description:
        raise SkillPackageError(
            f"{label}: description is {len(fields['description'])} characters; "
            f"limit is {max_description}"
        )



def _local_markdown_links(root: Path, skill_path: str, text: str, label: str) -> set[str]:
    linked: set[str] = set()
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
        target = target.strip()
        if target.startswith(("https://", "http://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0].split("?", 1)[0]
        if not target:
            continue
        relative = PurePosixPath(skill_path).parent / target
        relative_text = relative.as_posix()
        candidate = _checked_path(root, relative_text, f"local link in {label}")
        if not candidate.is_file():
            raise SkillPackageError(f"{label}: broken local Markdown link: {target}")
        linked.add(relative_text)
    return linked


def load_policy(root: Path, policy_path: str) -> dict:
    path = _checked_path(root, policy_path, "policy")
    if not path.is_file():
        raise SkillPackageError(f"policy file does not exist: {policy_path}")
    _, text = _read_utf8(path, "policy")
    try:
        policy = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SkillPackageError(f"policy JSON is invalid: {exc}") from exc

    required_positive = (
        "platform_entrypoint_limit_bytes",
        "operational_entrypoint_budget_bytes",
        "preferred_entrypoint_budget_bytes",
        "reference_module_limit_bytes",
        "package_uncompressed_limit_bytes",
        "max_description_characters",
    )
    for key in required_positive:
        value = policy.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise SkillPackageError(f"policy {key} must be a positive integer")

    platform = policy["platform_entrypoint_limit_bytes"]
    operational = policy["operational_entrypoint_budget_bytes"]
    preferred = policy["preferred_entrypoint_budget_bytes"]
    if not preferred <= operational < platform:
        raise SkillPackageError(
            "budget order must be preferred <= operational < platform ceiling"
        )
    if platform != 12000:
        raise SkillPackageError(
            "the documented platform ceiling is 12000 bytes; do not raise it "
            "to make an oversized Skill pass"
        )
    if operational > 10500 or preferred > 9000:
        raise SkillPackageError(
            "child policies may tighten but must not relax the shared "
            "10,500-byte operational / 9,000-byte preferred budgets"
        )
    if policy["reference_module_limit_bytes"] > 32768:
        raise SkillPackageError("reference module limit may not exceed 32768 bytes")
    if policy["package_uncompressed_limit_bytes"] > 131072:
        raise SkillPackageError("package uncompressed limit may not exceed 131072 bytes")
    scan_roots = policy.get("scan_roots")
    if not isinstance(scan_roots, list) or "." not in scan_roots:
        raise SkillPackageError(
            "scan_roots must include the repository root '.' so new Skills "
            "cannot escape the inventory by using an unlisted directory"
        )
    return policy


def audit_skill_package(root: Path, policy: dict) -> dict:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    entrypoints = policy.get("entrypoints")
    packages = policy.get("packages")
    scan_roots = policy.get("scan_roots")
    excluded = set(policy.get("excluded_directory_names", []))
    if not isinstance(entrypoints, list) or not entrypoints:
        raise SkillPackageError("policy entrypoints must be a non-empty array")
    if not isinstance(packages, list) or not isinstance(scan_roots, list):
        raise SkillPackageError("policy packages and scan_roots must be arrays")
    ids = [item.get("id") for item in entrypoints if isinstance(item, dict)]
    paths = [item.get("path") for item in entrypoints if isinstance(item, dict)]
    if len(ids) != len(entrypoints) or len(set(ids)) != len(ids):
        errors.append("entrypoint ids must be present and unique")
    if len(paths) != len(entrypoints) or len(set(paths)) != len(paths):
        errors.append("entrypoint paths must be present and unique")

    declared = {str(path) for path in paths if isinstance(path, str)}
    discovered: set[str] = set()
    for scan_root_value in scan_roots:
        try:
            scan_root = _checked_path(root, scan_root_value, "scan_root")
        except SkillPackageError as exc:
            errors.append(str(exc))
            continue
        if not scan_root.is_dir():
            errors.append(f"scan root is not a directory: {scan_root_value}")
            continue
        for candidate in scan_root.rglob("SKILL.md"):
            relative = candidate.relative_to(root).as_posix()
            if any(part in excluded for part in PurePosixPath(relative).parts):
                continue
            if candidate.is_symlink():
                errors.append(f"active Skill entrypoint is a symlink: {relative}")
                continue
            discovered.add(relative)

    for missing in sorted(declared - discovered):
        errors.append(f"declared Skill entrypoint was not discovered: {missing}")
    for unregistered in sorted(discovered - declared):
        errors.append(f"unregistered active SKILL.md discovered: {unregistered}")

    package_map = {}
    for package in packages:
        if not isinstance(package, dict) or not package.get("id"):
            errors.append("each package requires an id")
            continue
        package_id = package["id"]
        if package_id in package_map:
            errors.append(f"duplicate package id: {package_id}")
        package_map[package_id] = package

    entrypoint_report = []
    reference_report = []
    package_membership = {}
    for entry in entrypoints:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id", "<missing>")
        path_value = entry.get("path")
        linked_references: set[str] = set()
        try:
            path = _checked_path(root, path_value, f"entrypoint {entry_id}")
            if not path.is_file():
                raise SkillPackageError(f"entrypoint {entry_id}: file does not exist: {path_value}")
            raw, text = _read_utf8(path, f"entrypoint {entry_id}")
            _frontmatter(text, f"entrypoint {entry_id}", policy["max_description_characters"])
            linked_references = _local_markdown_links(root, str(path_value), text, entry_id)
            size = len(raw)
            platform = policy["platform_entrypoint_limit_bytes"]
            operational = policy["operational_entrypoint_budget_bytes"]
            preferred = policy["preferred_entrypoint_budget_bytes"]
            if size > platform:
                errors.append(
                    f"{entry_id}: {size} UTF-8 bytes exceeds platform limit {platform}"
                )
                status = "FAIL_PLATFORM_LIMIT"
            elif size > operational:
                errors.append(
                    f"{entry_id}: {size} UTF-8 bytes exceeds operational budget {operational}; "
                    f"refactor into on-demand references (platform ceiling {platform})"
                )
                status = "FAIL_OPERATIONAL_BUDGET"
            elif size > preferred:
                warnings.append(
                    f"{entry_id}: {size} UTF-8 bytes exceeds preferred budget {preferred}; "
                    "keep headroom for future changes"
                )
                status = "WARN_HEADROOM"
            else:
                status = "PASS"
            entrypoint_report.append({
                "id": entry_id,
                "path": str(path_value),
                "utf8_bytes": size,
                "preferred_budget_bytes": preferred,
                "operational_budget_bytes": operational,
                "platform_limit_bytes": platform,
                "status": status,
            })
        except (OSError, SkillPackageError) as exc:
            errors.append(str(exc))
            entrypoint_report.append({
                "id": entry_id,
                "path": path_value,
                "status": "FAIL",
                "error": str(exc),
            })

        references = entry.get("references", [])
        if not isinstance(references, list):
            errors.append(f"{entry_id}: references must be an array")
            continue
        for reference_value in references:
            if str(reference_value) not in linked_references:
                errors.append(
                    f"{entry_id}: declared reference is not linked from the Skill entrypoint: "
                    f"{reference_value}"
                )
            try:
                reference = _checked_path(root, reference_value, f"reference for {entry_id}")
                if not reference.is_file():
                    raise SkillPackageError(
                        f"{entry_id}: declared reference does not exist: {reference_value}"
                    )
                raw, _ = _read_utf8(reference, f"reference {reference_value}")
                size = len(raw)
                if size > policy["reference_module_limit_bytes"]:
                    raise SkillPackageError(
                        f"{reference_value}: {size} bytes exceeds reference module limit "
                        f"{policy['reference_module_limit_bytes']}"
                    )
                reference_report.append({
                    "owner_skill": entry_id,
                    "path": str(reference_value),
                    "utf8_bytes": size,
                    "status": "PASS",
                })
            except (OSError, SkillPackageError) as exc:
                errors.append(str(exc))

        package_id = entry.get("package_id")
        if package_id is not None:
            if package_id not in package_map:
                errors.append(f"{entry_id}: unknown package_id {package_id!r}")
            else:
                package_membership.setdefault(package_id, []).append(entry)

    package_report = []
    for package_id, package in package_map.items():
        try:
            package_root_value = package.get("root")
            package_root = _checked_path(root, package_root_value, f"package root {package_id}")
            if not package_root.is_dir():
                raise SkillPackageError(f"package root is not a directory: {package_root_value}")
            members = package.get("paths")
            if not isinstance(members, list) or not members:
                raise SkillPackageError(f"package {package_id}: paths must be a non-empty array")
            if any(not isinstance(member, str) for member in members):
                raise SkillPackageError(f"package {package_id}: every path must be a string")
            if len(members) != len(set(members)):
                raise SkillPackageError(f"package {package_id}: duplicate package paths")
            total = 0
            normalized_members = set()
            for member in members:
                rel = _relative_path(member, f"package {package_id} member")
                candidate = _checked_path(root, f"{package_root_value}/{member}", f"package {package_id} member")
                if not candidate.is_file():
                    raise SkillPackageError(f"package {package_id}: missing file {member}")
                package_bytes, _ = _read_utf8(candidate, f"package member {member}")
                total += len(package_bytes)
                normalized_members.add(rel.as_posix())
            if total > policy["package_uncompressed_limit_bytes"]:
                raise SkillPackageError(
                    f"package {package_id}: {total} uncompressed bytes exceeds "
                    f"{policy['package_uncompressed_limit_bytes']}"
                )
            for entry in package_membership.get(package_id, []):
                entry_rel = Path(entry["path"]).relative_to(Path(package_root_value)).as_posix()
                if entry_rel not in normalized_members:
                    raise SkillPackageError(
                        f"package {package_id}: missing Skill entrypoint {entry_rel}"
                    )
                for reference_value in entry.get("references", []):
                    reference_rel = Path(reference_value).relative_to(Path(package_root_value)).as_posix()
                    if reference_rel not in normalized_members:
                        raise SkillPackageError(
                            f"package {package_id}: missing on-demand reference {reference_rel}"
                        )
            package_report.append({
                "id": package_id,
                "root": package_root_value,
                "paths": members,
                "uncompressed_bytes": total,
                "status": "PASS",
            })
        except (OSError, ValueError, SkillPackageError) as exc:
            errors.append(str(exc))
            package_report.append({
                "id": package_id,
                "status": "FAIL",
                "error": str(exc),
            })

    return {
        "contract": policy.get("contract"),
        "policy_version": policy.get("policy_version"),
        "status": "FAIL" if errors else "PASS",
        "platform_entrypoint_limit_bytes": policy["platform_entrypoint_limit_bytes"],
        "operational_entrypoint_budget_bytes": policy["operational_entrypoint_budget_bytes"],
        "preferred_entrypoint_budget_bytes": policy["preferred_entrypoint_budget_bytes"],
        "line_endings": "CANONICAL_LF_FOR_UTF8_BYTE_COUNTS_AND_PACKAGES",
        "entrypoints": entrypoint_report,
        "references": reference_report,
        "packages": package_report,
        "warnings": warnings,
        "errors": errors,
    }


def build_package(root: Path, policy: dict, report: dict, package_id: str, output: Path) -> dict:
    package = next((item for item in report["packages"] if item["id"] == package_id), None)
    if package is None:
        raise SkillPackageError(f"unknown package id: {package_id}")
    if package["status"] != "PASS":
        raise SkillPackageError(f"package {package_id} did not pass audit")
    config = next(item for item in policy["packages"] if item["id"] == package_id)
    package_root = _checked_path(root, config["root"], f"package root {package_id}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in config["paths"]:
            source = _checked_path(root, f"{config['root']}/{member}", f"package {package_id} member")
            info = zipfile.ZipInfo(member, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package_bytes, _ = _read_utf8(source, f"package member {member}")
            archive.writestr(info, package_bytes)
    with zipfile.ZipFile(output, "r") as archive:
        expected = list(config["paths"])
        actual = archive.namelist()
        if actual != expected:
            raise SkillPackageError(
                f"package {package_id}: ZIP membership/order mismatch: {actual!r}"
            )
        for member in expected:
            source = _checked_path(root, f"{config['root']}/{member}", f"package {package_id} member")
            expected_bytes, _ = _read_utf8(source, f"package member {member}")
            if archive.read(member) != expected_bytes:
                raise SkillPackageError(f"package {package_id}: ZIP readback mismatch: {member}")
    return {
        "id": package_id,
        "zip_path": str(output),
        "zip_bytes": output.stat().st_size,
        "readback": "PASS_EXACT_MEMBERSHIP_AND_BYTES",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--policy", default="config/skill_package_policy.json")
    parser.add_argument("--report", help="optional JSON report path")
    parser.add_argument("--package", dest="package_id", help="build one declared package")
    parser.add_argument("--zip-output", help="output ZIP path; requires --package")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        policy = load_policy(root, args.policy)
        report = audit_skill_package(root, policy)
        if bool(args.package_id) != bool(args.zip_output):
            raise SkillPackageError("--package and --zip-output must be supplied together")
        if args.package_id and report["status"] == "PASS":
            report["built_package"] = build_package(
                root, policy, report, args.package_id, Path(args.zip_output).resolve()
            )
        if args.report:
            report_path = Path(args.report).resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["status"] != "PASS" else 0
    except (OSError, SkillPackageError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

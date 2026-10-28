"""Deterministic decision adapter; NOT an LLM and NOT semantic proof."""
from __future__ import annotations

import difflib


def propose(old: bytes, new: bytes, evidence: dict) -> dict:
    if old == new:
        return {"decision": "NO_CHANGE", "model": "deterministic-diff-v1", "change": False, "needs_semantic_review": False, "evidence": evidence}
    old_text = old.decode("utf-8", "replace").splitlines(keepends=True)
    new_text = new.decode("utf-8", "replace").splitlines(keepends=True)
    excerpt = "".join(list(difflib.unified_diff(old_text, new_text, fromfile="old", tofile="new", n=2))[:100])[:10000]
    return {"decision": "CHANGE_REQUIRES_REVIEW", "model": "deterministic-diff-v1", "change": True,
            "needs_semantic_review": True, "diff_excerpt": excerpt, "evidence": evidence,
            "warning": "No LLM or independent semantic reviewer ran; ADR impact unverified."}

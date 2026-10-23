"""Research-only competing *retrieval* algorithms. Not an authority or judge.

Grounded in Robertson/Zaragoza's probabilistic BM25 framework. Neither method
can prove semantic entailment, detect all injections, or authorize operations.
Full documents are in memory under the owner's existing source scope. This
module never opens directories, contacts a model, or persists task state.
"""
from __future__ import annotations

from collections import Counter
import math
import re

_STOP = frozenset("""
a an and are as at be by can do does for from how in is it of on or the
their this to was were what when where which who why will with would
source sources document documents exact reported report
""".split())
_TERM = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]", re.IGNORECASE)
_SUFFIX = 650
_MAX_DOCUMENTS = 24
_MAX_DOC_BYTES = 12_000


def tokens(value: str) -> list[str]:
    if not isinstance(value, str):
        raise ValueError("text must be string")
    return [v for v in _TERM.findall(value.casefold())
            if v not in _STOP and (len(v) > 1 or '\u3400' <= v <= '\u9fff')]


def windows(text: str, *, width: int = 650, stride: int = 500) -> list[str]:
    if not 100 <= width <= 1200 or not 1 <= stride <= width:
        raise ValueError("Invalid retrieval window")
    if len(text) <= width:
        return [text]
    last = len(text) - width
    starts = list(range(0, last + 1, stride))
    if not starts or starts[-1] != last:
        starts.append(last)
    return [text[s:s+width] for s in starts]


def _validate(query: str, docs: dict[str, str]) -> None:
    if (not isinstance(query, str) or not 1 <= len(query.strip()) <= 500
        or not isinstance(docs, dict) or not 1 <= len(docs) <= _MAX_DOCUMENTS):
        raise ValueError("Invalid retrieval scope")
    for name, value in docs.items():
        if (not isinstance(name, str) or not name
            or not isinstance(value, str)
            or len(value.encode("utf-8")) > _MAX_DOC_BYTES):
            raise ValueError("Invalid bounded evidence document")


def prefix_overlap(query: str, docs: dict[str, str]) -> dict[str, float]:
    """Old 650-char-prefix candidate ranking, for A/B comparison only."""
    _validate(query, docs)
    q = set(tokens(query))
    return {name: float(sum(1 for term in q if term in set(tokens(text[:650]))))
            for name, text in docs.items()}


def chunk_bm25(query: str, docs: dict[str, str]) -> dict[str, float]:
    """BM25 over bounded overlapping passages; maximum passage score/doc.

    No neural embedding, no trust labels, no regex-based attack blocking.
    The max is a retrieval score ONLY: do not interpret it as calibrated
    answer probability or semantic correctness.
    """
    _validate(query, docs)
    chunks = [(name, tokens(piece))
              for name, text in docs.items()
              for piece in windows(text)]
    if not chunks:
        return {name: 0.0 for name in docs}
    total = len(chunks)
    lengths = [len(t) for _name, t in chunks]
    avg_len = max(sum(lengths) / total, 1.0)
    df: Counter[str] = Counter()
    for _name, terms in chunks:
        df.update(set(terms))
    query_terms = set(tokens(query))
    result = {name: 0.0 for name in docs}
    for (name, ts), length in zip(chunks, lengths):
        frequency = Counter(ts)
        score = 0.0
        for term in query_terms:
            if term not in frequency:
                continue
            idf = math.log(1 + (total - df[term] + 0.5) / (df[term] + 0.5))
            tf = frequency[term]
            score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / avg_len))
        result[name] = max(result[name], score)
    return result


def select_docs(question: str, docs: dict[str, str], *,
                method: str, cutoff: float) -> list[str]:
    """Select zero/one/two candidate documents, never permit an action."""
    if not isinstance(cutoff, (float, int)) or not 0 <= cutoff <= 32:
        raise ValueError("Invalid pre-calibrated cutoff")
    if method == "prefix_overlap":
        ranked = prefix_overlap(question, docs)
    elif method == "chunk_bm25":
        ranked = chunk_bm25(question, docs)
    else:
        raise ValueError("Unknown competing method")
    ordered = sorted(ranked, key=lambda n: (-ranked[n], n))
    keep = [name for name in ordered if ranked[name] > float(cutoff)]
    # This is a general query-structure hint, not a domain-specific solution.
    # Two-source needs are *not* always signaled by a "two" token.
    q = set(tokens(question))
    needs_pair = bool(q & {"two", "both", "different", "compare", "conflicting"})
    return keep[:2 if needs_pair else 1]

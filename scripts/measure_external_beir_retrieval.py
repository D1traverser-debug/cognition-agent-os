"""External, primary-label, cross-domain retrieval A/B; research only.

BEIR: Thakur et al., NeurIPS Datasets & Benchmarks 2021.
https://github.com/beir-cellar/beir

Run with --smoke for deterministic local algorithm checks, without network.
Default run downloads three official *full corpora* with verified BEIR MD5,
and tests a pre-fixed SHA256 sample of up to 80 BEIR test queries each.
Qrels never enter the retrievers. No model, embeddings, paid APIs, write grant,
production repo action, or business outcome is involved.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
import math
from pathlib import Path
import random
import re
import statistics
import time
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation" / "beir_external_retrieval_results.json"
HOST = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets"
# MD5 from the official beir-cellar/beir README; not inferred from downloaded data.
CORPORA = {
    "scifact": "5f7d1de60b170fc8027bb7898e2efca1",
    "nfcorpus": "a89dba18a62ef92f7d323ec890a0d38d",
    "arguana": "8ad3e3c2a5867cdced806d6503f29b99",
}
SEED = "beir-external-eval-20261023-locked-before-first-run"
QUERY_LIMIT = 80
STOP = frozenset("""a an and are as at be by for from how in is it of on or that
the their then these this to was were what when where which who why with would""".split())
WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
METHODS = ("prefix_overlap", "bm25_document", "bm25_passage")
DATASET_MAX_COMPRESSED = 32_000_000
DATASET_MAX_RAW_ENTRY = 60_000_000
DATASET_MAX_DOCS = 20_000


def tokenize(s: str) -> list[str]:
    return [t for t in WORD.findall(s.lower()) if t not in STOP]


class InvertedIndex:
    def __init__(self, corpus: dict[str, str], *, passage: bool):
        self.n = 0
        self.postings = defaultdict(list)
        self.doc_owner: list[str] = []
        self.lengths: list[int] = []
        self.df = Counter()
        if len(corpus) > DATASET_MAX_DOCS:
            raise ValueError("Dataset over bounded evaluation corpus limit")
        for docid in sorted(corpus):
            ts = tokenize(corpus[docid])
            if passage:
                # Passage-level lexical recall, not a model reranker.
                segments = [ts[k:k+180] for k in range(0, len(ts), 120)]
                if not segments:
                    segments = [[]]
            else:
                segments = [ts]
            for terms in segments:
                if not terms:
                    continue
                idx = len(self.doc_owner)
                self.doc_owner.append(docid)
                self.lengths.append(len(terms))
                tf = Counter(terms)
                self.df.update(tf.keys())
                for term, freq in tf.items():
                    self.postings[term].append((idx, freq))
        self.n = len(self.doc_owner)
        self.avgdl = max(sum(self.lengths) / max(self.n, 1), 1.0)

    def rank(self, query: str, k: int) -> list[str]:
        scores = defaultdict(float)
        for term in set(tokenize(query)):
            rows = self.postings.get(term, ())
            df = self.df.get(term, 0)
            if not rows:
                continue
            idf = math.log1p((self.n - df + 0.5) / (df + 0.5))
            for chunk_idx, tf in rows:
                dl = self.lengths[chunk_idx]
                scores[chunk_idx] += idf * tf * 2.2 / (
                    tf + 1.2 * (0.25 + 0.75 * dl / self.avgdl))
        collapsed: dict[str, float] = {}
        for idx, score in scores.items():
            owner = self.doc_owner[idx]
            collapsed[owner] = max(score, collapsed.get(owner, 0.0))
        return sorted(collapsed, key=lambda name: (-collapsed[name], name))[:k]


class PrefixOverlap:
    def __init__(self, corpus: dict[str, str]):
        self.postings = defaultdict(set)
        for docid, text in corpus.items():
            for term in set(tokenize(text[:650])):
                self.postings[term].add(docid)

    def rank(self, question: str, k: int) -> list[str]:
        scores = Counter()
        for term in set(tokenize(question)):
            scores.update(self.postings.get(term, ()))
        return sorted(scores, key=lambda name: (-scores[name], name))[:k]


def ndcg_at(ranked: list[str], qrels: dict[str, int], k: int) -> float:
    scores = [float(qrels.get(name, 0)) for name in ranked[:k]]
    dcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(scores))
    ideal = sorted((r for r in qrels.values() if r > 0), reverse=True)[:k]
    idcg = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def recall_at(ranked: list[str], qrels: dict[str, int], k: int) -> float:
    positives = {d for d, score in qrels.items() if score > 0}
    return len(positives & set(ranked[:k])) / len(positives) if positives else 0.0


def mrr_at(ranked: list[str], qrels: dict[str, int], k: int) -> float:
    return next((1.0/i for i, doc in enumerate(ranked[:k], start=1)
                 if qrels.get(doc, 0) > 0), 0.0)


def _fetch_checked(dataset: str, md5: str) -> bytes:
    url = f"{HOST}/{dataset}.zip"
    req = Request(url, headers={"User-Agent": "cognition-agent-os-BEIR-offline-eval/1.0"})
    with urlopen(req, timeout=110) as r:
        raw = r.read(DATASET_MAX_COMPRESSED + 1)
    if len(raw) > DATASET_MAX_COMPRESSED:
        raise ValueError("Oversized official benchmark ZIP")
    digest = hashlib.md5(raw).hexdigest()  # Official BEIR transport identifier.
    if digest != md5:
        raise ValueError(f"{dataset} archive MD5 mismatch; no evaluation")
    return raw


def _read_dataset(raw: bytes, dataset: str):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        if len(names) > 35 or any(
            ".." in Path(name).parts or name.startswith("/") or "\\" in name
            for name in names
        ):
            raise ValueError("Malformed dataset ZIP directory")
        def find(suffix):
            matches = [n for n in names if n.endswith(suffix)]
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one {suffix}: {matches[:5]}")
            n = matches[0]
            if z.getinfo(n).file_size > DATASET_MAX_RAW_ENTRY:
                raise ValueError("Dataset member exceeds bound")
            return z.read(n)
        corpus_raw = find("/corpus.jsonl")
        queries_raw = find("/queries.jsonl")
        qrels_raw = find("/qrels/test.tsv")
    docs = {}
    for line in corpus_raw.splitlines():
        item = json.loads(line)
        docid = str(item["_id"])
        if docid in docs:
            raise ValueError("Duplicate document identifier")
        docs[docid] = str(item.get("title") or "") + " " + str(item.get("text") or "")
    queries = {}
    for line in queries_raw.splitlines():
        item = json.loads(line)
        queries[str(item["_id"])] = str(item["text"])
    qrels = defaultdict(dict)
    lines = qrels_raw.decode("utf-8").splitlines()
    if not lines or "query-id" not in lines[0]:
        raise ValueError("Invalid official qrels header")
    orphan_qrels = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError("Qrels row invalid")
        qid, docid, grade = parts
        if qid not in queries or docid not in docs:
            orphan_qrels.append({
                "query_id": qid[:90], "document_id": docid[:90],
                "query_available": qid in queries,
                "document_available": docid in docs,
            })
            continue
        qrels[qid][docid] = int(grade)
    if orphan_qrels:
        diagnostic = {
            "dataset": dataset, "orphan_qrels_count": len(orphan_qrels),
            "qrels_rows": len(lines) - 1, "query_total": len(queries),
            "document_total": len(docs), "first_6_orphans": orphan_qrels[:6]
        }
        print("OFFICIAL_QRELS_INTEGRITY_DIAGNOSTIC "
              + json.dumps(diagnostic, sort_keys=True), flush=True)
        raise ValueError("Official qrels include IDs not found in parsed files; "
                         "dataset scoring stopped for source-integrity diagnosis")
    eligible = [qid for qid in qrels if any(s > 0 for s in qrels[qid].values())]
    if not eligible or len(docs) > DATASET_MAX_DOCS:
        raise ValueError("Empty/oversized external benchmark")
    return docs, queries, qrels, eligible


def _choose_ids(dataset: str, available: list[str]):
    # Use only query IDs. No gold relevance or question content influences
    # the test subset. The sample is deterministic, not representative at scale.
    return sorted(available, key=lambda qid: hashlib.sha256(
        (SEED + "|" + dataset + "|" + qid).encode()).hexdigest())[:QUERY_LIMIT]


def _bootstrap_delta(a: list[float], b: list[float]) -> tuple[float, float]:
    # Paired confidence interval for descriptive uncertainty, NOT a release gate.
    rng = random.Random(20261023)
    deltas = [v-u for u, v in zip(a, b)]
    if not deltas:
        return (0.0, 0.0)
    draws = [statistics.mean(rng.choice(deltas) for _ in deltas)
             for _ in range(800)]
    draws.sort()
    return (round(draws[20], 4), round(draws[779], 4))


def eval_dataset(dataset: str, md5: str) -> dict:
    started = time.perf_counter()
    raw = _fetch_checked(dataset, md5)
    docs, queries, qrels, eligible = _read_dataset(raw, dataset)
    ids = _choose_ids(dataset, eligible)
    retrievers = {
        "prefix_overlap": PrefixOverlap(docs),
        "bm25_document": InvertedIndex(docs, passage=False),
        "bm25_passage": InvertedIndex(docs, passage=True),
    }
    metrics = {method: {"ndcg10": [], "recall100": [], "mrr10": [],
                        "latency_ms": [], "failures": []} for method in METHODS}
    for qid in ids:
        # Qrels are read ONLY AFTER the retriever returns document IDs.
        query = queries[qid]
        for method in METHODS:
            begin = time.perf_counter()
            retrieved = retrievers[method].rank(query, 100)
            elapsed = 1000 * (time.perf_counter() - begin)
            label = qrels[qid]
            group = metrics[method]
            group["ndcg10"].append(ndcg_at(retrieved, label, 10))
            group["recall100"].append(recall_at(retrieved, label, 100))
            group["mrr10"].append(mrr_at(retrieved, label, 10))
            group["latency_ms"].append(elapsed)
            if recall_at(retrieved, label, 100) < 1:
                group["failures"].append({
                    "qid": qid,
                    "ranked_top10": retrieved[:10],
                    "missed_qrels": sorted(
                        docid for docid, score in label.items()
                        if score > 0 and docid not in retrieved),
                })
    scores = {}
    for method, v in metrics.items():
        scores[method] = {
            "mean_ndcg_at_10": round(statistics.mean(v["ndcg10"]), 4),
            "mean_recall_at_100": round(statistics.mean(v["recall100"]), 4),
            "mean_mrr_at_10": round(statistics.mean(v["mrr10"]), 4),
            "median_query_latency_ms": round(statistics.median(v["latency_ms"]), 2),
            "failure_count": len(v["failures"]),
            "failures_first_8": v["failures"][:8],
        }
    return {
        "dataset": dataset, "archive_md5_matches_beir": True,
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "corpus_count": len(docs), "test_qrels_total": len(qrels),
        "sample_query_ids_sha256": hashlib.sha256(
            "\n".join(ids).encode()).hexdigest(),
        "sample_query_count": len(ids),
        "qrels_label_source": "original BEIR test.tsv, never fed to methods",
        "scores": scores,
        "paired_95pct_bootstrap_delta_passage_minus_document_ndcg10":
            _bootstrap_delta(metrics["bm25_document"]["ndcg10"],
                             metrics["bm25_passage"]["ndcg10"]),
        "elapsed_seconds": round(time.perf_counter() - started, 2)
    }


def smoke() -> None:
    docs = {
        "a": "Another unrelated sentence about a meal schedule.",
        "b": "The pressure setting for the compressor is 42 kilopascals.",
        "c": "The sensor was serviced in 2011.",
    }
    for method in (PrefixOverlap(docs),
                   InvertedIndex(docs, passage=False),
                   InvertedIndex(docs, passage=True)):
        assert method.rank("What is the compressor pressure setting?", 2)[0] == "b"
    qrels = {"b": 2, "c": 1}
    assert abs(ndcg_at(["b", "c"], qrels, 2) - 1) < 1e-12
    assert recall_at(["b"], qrels, 2) == 0.5
    assert mrr_at(["a", "b"], qrels, 2) == 0.5
    assert _choose_ids("example", ["2","1","3"]) == _choose_ids(
        "example", ["3","1","2"])
    print("BEIR_EXTERNAL_RETRIEVAL_SMOKE_PASS")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    if args.smoke:
        smoke()
        return 0
    output = {
        "status": "EXTERNAL_RETRIEVAL_MEASURED_NO_PRODUCT_ACCEPTANCE",
        "official_benchmark": "BEIR Thakur et al NeurIPS 2021",
        "official_dataset_md5_source": "beir-cellar/beir README official table",
        "sample_protocol": "80 test query IDs per dataset sorted by fixed seeded SHA256",
        "methods": list(METHODS),
        "model_inference_executed": False,
        "test_labels_fed_to_retrievers": False,
        "external_business_outcome_verified": False,
        "authorization_to_promote_method": False,
        "datasets": {},
    }
    for ds, md5 in CORPORA.items():
        result = eval_dataset(ds, md5)
        output["datasets"][ds] = result
        print("DATASET " + json.dumps({
            "name": ds, "queries": result["sample_query_count"],
            "docs": result["corpus_count"], "scores": {
                method: {k: result["scores"][method][k] for k in (
                    "mean_ndcg_at_10", "mean_recall_at_100", "failure_count"
                )} for method in METHODS
            }, "bootstrap_delta": result[
                "paired_95pct_bootstrap_delta_passage_minus_document_ndcg10"]
        }, sort_keys=True), flush=True)
        # Preserve partial results in addition to log, with clear status.
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(output, indent=2, sort_keys=True)
                            + "\n", encoding="utf-8")
    print("RESULT " + json.dumps({
        ds: {method: r["scores"][method]["mean_ndcg_at_10"]
             for method in METHODS}
        for ds, r in output["datasets"].items()
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

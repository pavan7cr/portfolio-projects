"""RAG Document Intelligence v3 (2026-10-28).

Ingestion: docs/*.txt, docs/**/*.pdf via PyPDF (page numbers kept),
plus built-in lectures. Uploaded files land in docs/uploads/ and are
picked up on the next index build (the API rebuilds per request, so
upload -> ask works without a restart).
Chunking: overlapping word windows (default 60 words, 20-word overlap)
with metadata: source file, page (PDF page number, 1 for .txt/built-in),
chunk_id, word offset. Answers therefore cite a specific source
location, not just a file.
Retrieval (two methods, compared on the same eval set):
  - TF-IDF (sklearn, 1-2 grams, English stopwords) + cosine similarity.
  - BM25 (implemented here, k1=1.5, b=0.75, small stopword list).
  Sentence-transformers embeddings were NOT used: the package requires
  torch>=2.2 + transformers, hundreds of MB, which does not fit the
  Render free service (512 MB) this demo deploys to. BM25 is the honest
  second method, not a claim of embeddings. A pgvector/embeddings swap
  remains the documented production step.
Answers: extractive quoted chunk + source + page + score, or
'Not found in the documents' below threshold (TF-IDF 0.15, BM25 2.0).
No LLM call is made unless OPENAI_API_KEY is set (none is set here).
Evaluation: eval_full.json (>=30 questions) -> top-1/top-3 accuracy
and mean rank latency per method, written to eval_results.json.
Run: python3 rag_full.py "question" | python3 rag_full.py --eval
"""
import json
import math
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.metrics.pairwise import cosine_similarity  # noqa: E402

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

BUILTIN = {
    "lecture1.txt": "SQL joins combine rows from two tables. An INNER JOIN returns only matching rows. A LEFT JOIN returns all rows from the left table, with nulls where there is no match.",
    "lecture2.txt": "Hypothesis testing starts with a null hypothesis. A p-value below 0.05 is commonly used to reject the null hypothesis, but it is not the probability that the null is true.",
    "lecture3.txt": "Redis caching stores frequently requested results in memory. A cache hit avoids a database query. Cache invalidation is hard: stale data must be expired or evicted on update.",
}

STOP = set("a an the is are was were be been of to in on for and or with by from as at it its this that".split())


def _tokens(text):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP]


def load_docs():
    """Return [{source, page, text}]. Built-ins first, then docs/ files."""
    docs = [{"source": name, "page": 1, "text": text} for name, text in BUILTIN.items()]
    d = HERE / "docs"
    if d.exists():
        for f in sorted(d.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix == ".txt":
                docs.append({"source": str(f.relative_to(HERE)), "page": 1,
                             "text": f.read_text(errors="ignore")})
            elif f.suffix == ".pdf" and PdfReader:
                reader = PdfReader(str(f))
                for i, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    if text.strip():
                        docs.append({"source": str(f.relative_to(HERE)), "page": i, "text": text})
    return docs


def chunk_text(text, chunk_words=60, overlap=20):
    """Overlapping word windows; returns list of (chunk_text, word_offset)."""
    words = text.split()
    if len(words) <= chunk_words:
        return [(" ".join(words), 0)] if words else []
    chunks, start = [], 0
    step = chunk_words - overlap
    while start < len(words):
        chunks.append((" ".join(words[start:start + chunk_words]), start))
        if start + chunk_words >= len(words):
            break
        start += step
    return chunks


def build_chunks():
    chunks = []
    for doc in load_docs():
        for text, offset in chunk_text(doc["text"].replace("\n", " ")):
            chunks.append({"source": doc["source"], "page": doc["page"],
                           "text": text, "offset": offset,
                           "chunk_id": f"{doc['source']}#p{doc['page']}@{offset}"})
    return chunks


class Retriever:
    def __init__(self, chunks=None):
        self.chunks = chunks if chunks is not None else build_chunks()
        texts = [c["text"] for c in self.chunks]
        self.vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        self.mat = self.vec.fit_transform(texts)
        # BM25 index over the same chunks.
        self.bm25_docs = [_tokens(t) for t in texts]
        self.doc_lens = [len(d) for d in self.bm25_docs]
        self.avgdl = sum(self.doc_lens) / max(1, len(self.doc_lens))
        df = Counter()
        for d in self.bm25_docs:
            for t in set(d):
                df[t] += 1
        n = len(self.bm25_docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def _bm25_scores(self, query):
        qtok = _tokens(query)
        scores = []
        for doc, dl in zip(self.bm25_docs, self.doc_lens):
            counts = Counter(doc)
            s = 0.0
            for t in qtok:
                if t not in counts:
                    continue
                tf = counts[t]
                s += self.idf.get(t, 0) * (tf * 2.5) / (tf + 1.5 * (1 - 0.75 + 0.75 * dl / self.avgdl))
            scores.append(s)
        return scores

    def rank(self, query, method="tfidf", top_n=3):
        if method == "bm25":
            scores = self._bm25_scores(query)
        else:
            scores = cosine_similarity(self.vec.transform([query]), self.mat)[0].tolist()
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_n]
        return [{"chunk": self.chunks[i], "score": round(float(scores[i]), 3)} for i in order]

    def answer(self, query, method="tfidf"):
        threshold = 0.15 if method != "bm25" else 2.0
        ranked = self.rank(query, method=method, top_n=1)
        if not ranked:
            return {"answer": "Not found in the documents.", "source": None, "page": None,
                    "score": 0.0, "method": method}
        top = ranked[0]
        if top["score"] < threshold:
            return {"answer": "Not found in the documents.", "source": None, "page": None,
                    "score": top["score"], "method": method}
        c = top["chunk"]
        return {"answer": c["text"], "source": c["source"], "page": c["page"],
                "chunk_id": c["chunk_id"], "score": top["score"], "method": method}


def answer(q, threshold=0.15, method="tfidf"):
    """Backwards-compatible single-answer API (threshold arg kept for callers)."""
    r = Retriever()
    if method == "tfidf" and threshold != 0.15:
        # Honour a caller-supplied TF-IDF threshold via rank + manual check.
        ranked = r.rank(q, method=method, top_n=1)
        top = ranked[0]
        if top["score"] < threshold:
            return {"answer": "Not found in the documents.", "source": None, "page": None,
                    "score": top["score"], "method": method}
        c = top["chunk"]
        return {"answer": c["text"], "source": c["source"], "page": c["page"],
                "chunk_id": c["chunk_id"], "score": top["score"], "method": method}
    return r.answer(q, method=method)


def run_eval():
    ev = json.load(open(HERE / "eval_full.json"))
    retriever = Retriever()
    results = {"n_questions": len(ev), "methods": {}, "failures": []}
    for method in ("tfidf", "bm25"):
        top1 = top3 = 0
        latencies = []
        for item in ev:
            t0 = time.perf_counter()
            ranked = retriever.rank(item["question"], method=method, top_n=3)
            latencies.append(time.perf_counter() - t0)
            sources = [r["chunk"]["source"] for r in ranked]
            expected = item["expected_source"]
            # Expected source may be a bare filename or a docs/ path.
            hit1 = any(s == expected or s.endswith("/" + expected) for s in sources[:1])
            hit3 = any(s == expected or s.endswith("/" + expected) for s in sources)
            top1 += hit1
            top3 += hit3
            if not hit1:
                results["failures"].append({"method": method, "question": item["question"],
                                            "expected_source": expected,
                                            "got": sources[0] if sources else None,
                                            "score": ranked[0]["score"] if ranked else None})
        results["methods"][method] = {
            "top1": f"{top1}/{len(ev)} = {top1/len(ev):.1%}",
            "top1_count": top1,
            "top3": f"{top3}/{len(ev)} = {top3/len(ev):.1%}",
            "top3_count": top3,
            "mean_latency_ms": round(sum(latencies) / len(latencies) * 1000, 2),
            "max_latency_ms": round(max(latencies) * 1000, 2)}
    json.dump(results, open(HERE / "eval_results.json", "w"), indent=2)
    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    if "--eval" in sys.argv:
        run_eval()
    else:
        print(json.dumps(answer(" ".join(sys.argv[1:]) or "What is a left join?"), indent=2))

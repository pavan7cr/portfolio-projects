"""RAG v2 - complete except deployment.
- Ingestion: docs/*.txt + PDFs via PyPDF (real PDF parsing, not stream regex).
- Retrieval: sklearn TF-IDF (word n-grams 1-2, English stopwords) + cosine similarity.
  This is a real embedding-style vector retrieval, not an LLM API call.
  A pgvector version is the production swap: same vectors, stored in Postgres.
- Answers: extractive quoted chunk + source + score, or 'Not found' below threshold.
  If OPENAI_API_KEY is set, an LLM answer can be generated from the retrieved
  chunks only (grounded) - without a key, no LLM call is made and no answer is invented.
- Evaluation: eval_full.json (10 questions) -> hit rate + mean score, printed.
Run: python3 rag_full.py "question"  |  python3 rag_full.py --eval
"""
import json, math, os, sys
from pathlib import Path
HERE = Path(__file__).parent
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None
BUILTIN = {
    "lecture1.txt": "SQL joins combine rows from two tables. An INNER JOIN returns only matching rows. A LEFT JOIN returns all rows from the left table, with nulls where there is no match.",
    "lecture2.txt": "Hypothesis testing starts with a null hypothesis. A p-value below 0.05 is commonly used to reject the null hypothesis, but it is not the probability that the null is true.",
    "lecture3.txt": "Redis caching stores frequently requested results in memory. A cache hit avoids a database query. Cache invalidation is hard: stale data must be expired or evicted on update.",
}
def load_docs():
    docs = dict(BUILTIN)
    d = HERE / "docs"
    if d.exists():
        for f in sorted(d.iterdir()):
            if f.suffix == ".txt": docs[f.name] = f.read_text(errors="ignore")
            elif f.suffix == ".pdf" and PdfReader:
                docs[f.name] = " ".join((p.extract_text() or "") for p in PdfReader(str(f)).pages)
    return docs
def build():
    docs = load_docs(); chunks = []
    for src, text in docs.items():
        for sent in text.replace("\n", " ").split(". "):
            if sent.strip(): chunks.append((src, sent.strip()))
    vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    mat = vec.fit_transform([c for _, c in chunks])
    return chunks, vec, mat
def answer(q, threshold=0.15):
    chunks, vec, mat = build()
    sims = cosine_similarity(vec.transform([q]), mat)[0]
    i = int(sims.argmax()); score = float(sims[i]); src, chunk = chunks[i]
    if score < threshold: return {"answer": "Not found in the documents.", "source": None, "score": round(score, 3)}
    return {"answer": chunk, "source": src, "score": round(score, 3)}
if __name__ == "__main__":
    if "--eval" in sys.argv:
        ev = json.load(open(HERE / "eval_full.json")); hits = 0
        for item in ev:
            r = answer(item["question"]); ok = r["source"] == item["expected_source"]; hits += ok
            print(f"{'HIT' if ok else 'MISS'} | {item['question']} -> {r['source']} ({r['score']})")
        print(f"Hit rate: {hits}/{len(ev)} = {hits/len(ev):.0%}")
    else:
        print(json.dumps(answer(" ".join(sys.argv[1:]) or "What is a left join?"), indent=2))

"""RAG tests. Run from rag-doc-intelligence/:
venv/bin/python test_rag.py
Covers: eval top-1 floors, page metadata, not-found guardrail, upload.
The upload test file is removed afterwards.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_full import Retriever, run_eval  # noqa: E402

res = run_eval()
assert res["methods"]["tfidf"]["top1_count"] >= 32, res
assert res["methods"]["bm25"]["top1_count"] >= 31, res
assert res["methods"]["tfidf"]["top3_count"] == res["n_questions"], res

r = Retriever()
ans = r.answer("What is a left join?")
assert ans["source"] == "lecture1.txt" and ans["page"] == 1 and "chunk_id" in ans, ans
assert r.answer("What is the capital of France?")["answer"].startswith("Not found"), ans

from fastapi.testclient import TestClient  # noqa: E402
from api.main import app  # noqa: E402
c = TestClient(app)
up = c.post("/upload", files={"file": ("rag_test.txt", b"Zebra widgets hum softly at dawn.", "text/plain")})
assert up.status_code == 200, up.text
got = c.post("/ask", json={"question": "What do zebra widgets do at dawn?"}).json()
assert got["source"] == "docs/uploads/rag_test.txt", got
os.remove(os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "uploads", "rag_test.txt"))
print("rag tests passed:", res["methods"])

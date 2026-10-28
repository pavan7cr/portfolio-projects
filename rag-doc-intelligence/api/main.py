"""RAG API - FastAPI wrapper around rag_full.py.
Run: venv/bin/uvicorn api.main:app --port 8000  (from rag-doc-intelligence/)
Endpoints: GET /health, POST /ask {question, method?},
POST /upload (multipart .txt/.pdf, ingested + reindexed on next ask),
GET /docs (FastAPI docs).
Answers are grounded extractive chunks with source + page + score,
or 'Not found' below threshold. No LLM call is made without a key.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from rag_full import Retriever, answer, chunk_text  # noqa: E402

HERE = Path(__file__).parent.parent
app = FastAPI(title="RAG Document Intelligence")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class AskIn(BaseModel):
    question: str
    method: str = "tfidf"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(d: AskIn):
    if d.method not in ("tfidf", "bm25"):
        raise HTTPException(400, "method must be tfidf or bm25")
    return answer(d.question, method=d.method)


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() not in (".txt", ".pdf"):
        raise HTTPException(400, "only .txt and .pdf uploads are accepted")
    dest_dir = HERE / "docs" / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Strip any path components from the client-supplied filename.
    dest = dest_dir / Path(file.filename).name
    data = await file.read()
    dest.write_bytes(data)
    if dest.suffix == ".txt":
        text = data.decode(errors="ignore")
        chunks = len(chunk_text(text.replace("\n", " ")))
    else:
        from pypdf import PdfReader
        import io
        pages = PdfReader(io.BytesIO(data)).pages
        text = " ".join((p.extract_text() or "") for p in pages)
        chunks = sum(len(chunk_text((p.extract_text() or "").replace("\n", " "))) for p in pages)
    # Verify the new document is retrievable in the rebuilt index.
    found = Retriever().rank(text[:80] or file.filename, method="tfidf", top_n=1)
    return {"filename": dest.name, "source": f"docs/uploads/{dest.name}",
            "chars": len(text), "chunks_added": chunks,
            "retrievable_as": found[0]["chunk"]["source"] if found else None}

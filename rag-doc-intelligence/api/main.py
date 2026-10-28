"""RAG API - FastAPI wrapper around rag_full.py.
Run: venv/bin/uvicorn api.main:app --port 8000  (from rag-doc-intelligence/)
Endpoints: GET /health, POST /ask {question}, GET /docs (FastAPI docs).
Answers are grounded extractive chunks with source + score, or 'Not found'.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rag_full import answer
app = FastAPI(title="RAG Document Intelligence")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
class AskIn(BaseModel): question: str
@app.get("/health")
def health(): return {"status": "ok"}
@app.post("/ask")
def ask(d: AskIn): return answer(d.question)

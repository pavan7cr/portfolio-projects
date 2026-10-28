# RAG Document Intelligence MVP - what was built
- Three lecture documents, chunked by sentence, TF-IDF cosine retrieval (stdlib only, no API key).
- Answers are the best chunk quoted with its source, or "Not found in the documents" below threshold - no hallucinated answer.
- Evaluation: python3 rag.py --eval measures hit rate against eval.json (4 questions).
- Next step for the evening build: replace TF-IDF with real embeddings + pgvector, and add PDF upload.
- Run: python3 rag.py "What is a left join?"
## Round 2 (2026-10-28)
- Added ingest.py: loads docs/*.txt and extracts text from simple PDFs (stdlib zlib). Built-in lectures are kept and merged with ingested docs - an earlier version replaced them and broke eval to 0/4, which was caught and fixed; eval is back to 4/4.
- Added docs/lecture4.txt (PostgreSQL indexes) and verified it answers correctly.
- Still to do: real embeddings + pgvector, LLM answers, PDF upload UI, deployment. TF-IDF is still the retrieval method - not yet real embeddings.

## 2026-10-28 upgrades
- Overlapping chunking (60 words, 20-word overlap) with source + page + chunk_id metadata, so answers cite a specific location.
- Eval expanded to 33 questions: TF-IDF top-1 33/33 (100%), top-3 33/33; BM25 top-1 32/33 (97.0%), top-3 33/33. Mean rank latency: TF-IDF 1.14 ms, BM25 0.03 ms (index-build time excluded; API rebuilds the index per request).
- Second retrieval method is BM25, NOT embeddings: sentence-transformers requires torch>=2.2 + transformers (hundreds of MB), which does not fit the Render free 512 MB service. This is stated here so no one claims embeddings were run.
- Honest failures recorded in eval_results.json: BM25 misses the ambiguous "caching or indexing?" question (returns lecture3.txt, expected lecture4.txt), plus 3 cross-topic probes with no single grounding chunk.
- Upload endpoint POST /upload (.txt/.pdf) ingests into docs/uploads/ and the document is retrievable on the next ask; tested locally with a new .txt document. Extractive, citation-grounded answers and the not-found threshold are unchanged. No LLM call is made (no key set).
- New doc docs/lecture6.txt (FastAPI) added so the eval covers a sixth topic.

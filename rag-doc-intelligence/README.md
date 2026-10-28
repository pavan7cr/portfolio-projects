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

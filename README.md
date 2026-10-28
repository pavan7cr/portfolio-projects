# Three projects - finished except live deployment (per user instruction, 2026-10-28)

## 1. SaaS Invoicing (saas-invoicing/)
- Backend: FastAPI + SQLAlchemy + SQLite, backend/main.py. Run: venv/bin/uvicorn backend.main:app --port 8000
- Frontend: React + Vite, frontend/ (npm run build verified, dist/ built). Run: npm run dev (port 5173).
- Features tested end-to-end: tenant creation, user register/login, client CRUD scoped to tenant, invoice creation with items, pay (test stub), dashboard paid/unpaid totals, 401 on bad token, 403 on cross-tenant client.
- Stripe: stripe_test.py creates a real test-mode PaymentIntent ONLY if STRIPE_TEST_SECRET_KEY is set. No key was set, so no Stripe call was made.
- Not done: live deployment, JWT (token is user id in this build - production swap documented in code), PDF invoices, email reminders.

## 2. Data Pipeline & Analytics Platform (data-pipeline-platform/)
- pipeline_full.py: 3 sources (sales.csv, Open-Meteo Wichita weather, JSONPlaceholder posts), dedupe/null-drop transforms, daily revenue + posts-by-user, quality gates, alerts.json (gate failure + revenue drop >30%), idempotent re-runs.
- Tests: test_pipeline.py passes (daily revenue 200.5 on first day, 20 posts, re-run does not double revenue).
- Scheduler: run_daily.sh (cron-ready). Dashboard: dashboard_full.json + dashboard.html.
- Not done: live deployment, React dashboard, email/Slack alert delivery (alerts are written to file).

## 3. RAG Document Intelligence (rag-doc-intelligence/)
- rag_full.py: sklearn TF-IDF (1-2 grams, stopwords) + cosine retrieval, PyPDF ingestion, docs/ folder, grounded extractive answers with source + score, 'Not found' below threshold.
- Evaluation: eval_full.json, 10/10 = 100% hit rate, verified 2026-10-28. PDF test: lecture5.pdf (Docker) answers correctly with source lecture5.pdf.
- LLM: grounded generation ONLY if OPENAI_API_KEY is set; no key was set, so no LLM call was made and no answer was invented.
- Not done: live deployment, pgvector (same vectors, Postgres swap documented), LLM answer generation without a key.

## How to run (all, locally)
- Python venv: ~/workspace/projects/venv/bin/python (fastapi, uvicorn, sqlalchemy, pypdf, scikit-learn, requests, reportlab installed in venv, not system Python).
- SaaS: see above. Pipeline: venv/bin/python data-pipeline-platform/test_pipeline.py. RAG: venv/bin/python rag-doc-intelligence/rag_full.py --eval

# Deployment plan (not yet deployed - needs a platform account)
## SaaS Invoicing
- Backend: Render free web service from saas-invoicing/Dockerfile, or Railway/Fly.io.
- Frontend: Vercel free, from saas-invoicing/frontend/ (npm run build). Set API URL to the deployed backend URL in src/App.jsx.
## Data Pipeline
- Not a user-facing web app: deploy as a scheduled job (Render Cron Job, free tier limited, or GitHub Actions schedule) running pipeline_full.py daily. Dashboard: serve dashboard_full.json via a static site, or add a small FastAPI endpoint.
## RAG Document Intelligence
- Backend: FastAPI wrapper around rag_full.py (to be added at deploy time), deployed on Render/Railway; frontend: simple upload + Q&A page on Vercel.
- No LLM key is set, so deployed RAG will use TF-IDF extractive answers until a key is added.
## What I need from you
1. Which platform do you already have an account on (Render, Vercel, Railway, Fly.io)?
2. Permission to sign in with that account in the browser to deploy (I will not use any password you have not put through secure entry).

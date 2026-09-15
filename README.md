# EMISSIQ — AI Methane Intelligence Platform

Full-stack prototype demonstrating one methane-management workflow end to end:
INGEST → DETECT → ATTRIBUTE → QUANTIFY → INVESTIGATE → PRIORITIZE → ACT → VERIFY.

All data is **simulated demonstration data**, clearly labelled throughout the UI.

## Stack

- `services/api/` — FastAPI + SQLAlchemy backend: sensor simulator, deterministic
  detection/attribution/quantification/priority/verification engines, AI
  investigator + copilot (Groq → Ollama → offline scripted fallback), REST API,
  WebSocket live feed.
- `apps/web/` — Next.js 14 (App Router) + TypeScript + Tailwind + Recharts
  frontend, English/Arabic (RTL) via next-intl.

## Run it

**Backend** (Python 3.11+):
```bash
cd services/api
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
# DATABASE_URL in the repo-root .env defaults to local SQLite so this runs with
# no external services. Point it at Postgres (docker compose up, or Supabase)
# for the pgvector-backed retrieval path.
python -m emissiq.db.seed
uvicorn emissiq.main:app --reload --port 8000
```

**Frontend**:
```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:3000/en/dashboard (or `/ar/dashboard`).

## Demo

Press **Run Demo Event** in the top bar. It resets to baseline and replays the
Compressor C-03 seal-release scenario at Fahud: pressure anomaly → methane at
S3 → methane at S4 → event confirmed → source attributed → quantified →
prioritised → AI-investigated → action recommended. From the event page you can
then create a work order, mark the repair complete (which triggers an
automatic post-repair sensor replay and verification), and generate a report.

Set `GROQ_API_KEY` in `.env` for live AI investigation/copilot reasoning; with
no key the system runs an equivalent offline scripted investigator so the demo
never depends on network access.

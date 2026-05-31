# MissionControl

AI-powered SEO content pipeline management panel for ReviewHandy. Orchestrates a 4-agent pipeline (researcher → validator → writer → reviewer) that discovers topics, writes blog posts, and publishes them to Notion — autonomously.

---

## Prerequisites

- Python 3.13+
- Node.js 18+
- MongoDB (local or Atlas)
- Redis (used as Celery broker)

Start Redis with Docker:

```bash
cd missioncontrol-be
docker-compose up -d
```

---

## Backend

```bash
cd missioncontrol-be

# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set MONGODB_URL, SECRET_KEY, CORS_ORIGINS at minimum

# 4. Seed the database (creates admin user + pipeline agents)
python -m app.seed

# 5. Start the API server
uvicorn app.main:app --reload --port 8001
```

API is available at **http://localhost:8001**  
Interactive docs at **http://localhost:8001/docs**

Default admin credentials (from seed): `admin@reviewhandy.com` / `admin123456`

---

## Celery Worker

The worker runs the content pipeline tasks. Open **two separate terminals** (with the virtual environment activated in each):

**Terminal 1 — Worker** (executes pipeline tasks):

```bash
cd missioncontrol-be
source venv/bin/activate
celery -A app.celery_app.celery worker --loglevel=info
```

**Terminal 2 — Beat scheduler** (triggers periodic + cron tasks):

```bash
cd missioncontrol-be
source venv/bin/activate
celery -A app.celery_app.celery beat --loglevel=info
```

> Both the worker and beat must be running for the pipeline to operate automatically. Beat dispatches the daily Content Researcher and the 30-second agent poll; the worker executes them.

---

## Frontend

```bash
cd missioncontrol-fe

# 1. Install dependencies
npm install

# 2. Configure environment
cp .env.example .env
# VITE_API_URL=http://localhost:8001  ← point to your backend port

# 3. Start the dev server
npm run dev
```

Frontend is available at **http://localhost:5173**

### Other frontend commands

```bash
npm run build    # production build (output: dist/)
npm run preview  # serve the production build locally
npm run lint     # run ESLint
```

---

## Running Everything Together

Open 4 terminals:

| Terminal | Command |
|---|---|
| 1 — Redis | `cd missioncontrol-be && docker-compose up` |
| 2 — Backend | `cd missioncontrol-be && source venv/bin/activate && uvicorn app.main:app --reload --port 8001` |
| 3 — Celery Worker | `cd missioncontrol-be && source venv/bin/activate && celery -A app.celery_app.celery worker --loglevel=info` |
| 4 — Celery Beat | `cd missioncontrol-be && source venv/bin/activate && celery -A app.celery_app.celery beat --loglevel=info` |
| 5 — Frontend | `cd missioncontrol-fe && npm run dev` |

---

## First-Time Setup After Login

1. Log in at http://localhost:5173 with the admin credentials
2. Go to **Settings → API Keys** — add your OpenAI / Gemini / Claude key
3. Go to **Settings → Notion** — add your Notion integration token and database ID
4. Create a **Space** and set its **Niche** (e.g. "AI & Machine Learning") and **Topic Count**
5. Go to the space's **Agents** tab — configure provider and model for each of the 4 pipeline agents
6. The Content Researcher runs daily at 6:00 AM UTC, or you can trigger it manually by assigning any task to the Content Researcher agent

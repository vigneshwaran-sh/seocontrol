# MissionControl Backend

Admin / mission-control panel backend for ReviewHandy, built with FastAPI and MongoDB.

## Setup

```bash
cd missioncontrol-be
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit as needed
```

## Run

```bash
uvicorn app.main:app --reload --port 8001
```

API docs: http://localhost:8001/docs

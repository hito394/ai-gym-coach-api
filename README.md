# AI Gym Coach API

## Setup
1) Create .env from .env.example
2) Install deps: pip install -r requirements.txt
3) Run: uvicorn app.main:app --reload

## Endpoints
- GET /v1/health
- POST /v1/users/profile
- POST /v1/workouts/generate
- POST /v1/chat/coach
- POST /v1/progression/adjust
- POST /v1/progression/readiness

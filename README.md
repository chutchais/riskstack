# Container Yard Safety Verification System

A full-stack scaffold for ingesting EDIFACT COEDOR container data, evaluating yard safety rules, and exposing upload plus historical APIs for visualization and reporting.

## Overview

This project includes:

- FastAPI backend with async SQLAlchemy models and API routes
- Safety evaluation engine for yard/container checks
- EDIFACT COEDOR parser for uploaded files
- React frontend package setup for UI and heatmap rendering
- Docker Compose orchestration for frontend, backend, and PostgreSQL

## Repository Structure

- backend/
  - requirements.txt
  - app/
    - api/
      - upload.py
      - historical.py
    - core/
      - edi_parser.py
      - safety_engine.py
    - models/
      - database.py
- frontend/
  - package.json
  - src/
    - components/
      - Heatmap.jsx
- docker-compose.yml
- setup.sh

## Backend Stack

- FastAPI
- Uvicorn
- SQLAlchemy asyncio + asyncpg
- Pydantic
- python-jose

## Frontend Stack

- React
- TypeScript tooling
- Tailwind CSS
- Axios
- TanStack Query
- Vite

## Quick Start

## 1) Initialize folders

If needed:

bash setup.sh

## 2) Run with Docker Compose

docker compose up --build

Expected service ports:

- Frontend: 5173
- Backend: 8000
- PostgreSQL: 5432

## 3) Local backend (without Docker)

From backend folder:

python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

## 4) Local frontend (without Docker)

From frontend folder:

npm install
npm run dev

## API Endpoints Implemented

Upload routes:

- POST /upload/edi

Historical routes:

- GET /historical/batches
- GET /historical/batches/{batch_id}
- GET /historical/containers/{container_id}/evaluations

## Notes

- Current project specification file in this workspace contains prompt blocks but not the detailed Section 4-7 schema text.
- Model and API implementations are therefore aligned to the prompt requirements and container yard safety domain assumptions.

# Claude AI Developer Instructions: Container Yard Safety Verification System

## 1. Role & Objective
You are an expert senior full-stack engineer and software architect. Your goal is to implement the **Container Yard Safety Verification System** exactly as defined in `project_specification.md`. 

You must write production-ready, clean, modular, and secure code. Do not use shortcuts, placeholder comments (`# TODO`), or abbreviated snippets. Write out the full file contents when requested.

---

## 2. Global Code Style & Guardrails

### Backend (Python/FastAPI)
* **Strict Typing:** Use Python type hinting (`str`, `int`, `dict`, `list`) and Pydantic v2 schemas for all request/response models.
* **Async by Default:** Use `async def` for endpoints and database operations using an asynchronous SQLAlchemy driver where appropriate.
* **Error Handling:** Wrap core logic blocks in `try-except` blocks. Return explicit HTTP exceptions using FastAPI's `HTTPException` with clear, actionable error text.
* **Database Conventions:** Use UUIDs as primary keys for all models. Implement clean relational mappings.

### Frontend (React/TypeScript/Tailwind)
* **TypeScript Typing:** Do not use `any`. Explicitly type all component props, API response hooks, and state vectors.
* **Styling:** Use strict Tailwind CSS utility classes. Avoid inline style dictionaries.
* **State Management:** Use Axios for HTTP transport and React Query (`@tanstack/react-query`) for handling server-side cache state and uploads.

---

## 3. Operational Implementation Prompts

When I ask you to generate a part of the application, follow these exact prompt instructions:

### [Prompt Block A: Infrastructure & Setup]
"Read both `project_specification.md` and `claude_instructions.md`. Generate the foundational files to scaffold our architecture. Provide the complete code blocks for:
1. `backend/requirements.txt` (including FastAPI, Uvicorn, SQLAlchemy, Pydantic, and python-jose)
2. `frontend/package.json` (including React, TypeScript, Tailwind, Axios, and TanStack Query)
3. The root `docker-compose.yml` stringing together the frontend, backend, and PostgreSQL backend instances."

### [Prompt Block B: Backend Core Logic & Models]
"Based on Section 4 and Section 5 of `project_specification.md`, write the complete Python implementation for:
1. `backend/app/models/database.py` (SQLAlchemy async engine setup) and the entity relationship models.
2. `backend/app/core/edi_parser.py` to parse EDIFACT COEDOR messages.
3. `backend/app/core/safety_engine.py` evaluating the 5 strict ISO 1496-1 rules ( raching, wind, weights distribution, tier metrics, corner post stress)."

### [Prompt Block C: API Layer]
"Write the complete FastAPI endpoint architecture mapping onto Section 6 of `project_specification.md`. Ensure that `backend/app/api/upload.py` passes ingested files cleanly to your parsed EDI utility and saves safety data to PostgreSQL. Include complete pagination mechanisms for historical endpoints."

### [Prompt Block D: Frontend Layouts]
"Generate the fully styled React TypeScript components required by Section 7 of `project_specification.md`. Focus specifically on `Heatmap.tsx`. Use a CSS grid array to accurately plot rows/bays/blocks, dynamically shading cells (Red/Yellow/Green) mapping directly to backend evaluation statuses."
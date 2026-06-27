#!/usr/bin/env bash
set -euo pipefail

# Directories inferred from Section 3 file paths:
# - backend/requirements.txt
# - backend/app/models/database.py
# - backend/app/core/edi_parser.py
# - backend/app/core/safety_engine.py
# - backend/app/api/upload.py
# - frontend/package.json

dirs=(
  "backend"
  "backend/app"
  "backend/app/models"
  "backend/app/core"
  "backend/app/api"
  "frontend"
)

for dir in "${dirs[@]}"; do
  mkdir -p "$dir"
done

echo "Directory structure initialized successfully."

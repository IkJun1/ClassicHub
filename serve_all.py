"""Serve ClassicHub backend API and frontend static files together.

Usage:
    python serve_all.py

Then open:
    http://127.0.0.1:8000/app/main.html

API remains available under:
    http://127.0.0.1:8000/api/...
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend__v3"
FRONTEND_DIR = ROOT_DIR / "front_v3"

if not BACKEND_DIR.exists():
    raise RuntimeError(f"Backend directory not found: {BACKEND_DIR}")
if not FRONTEND_DIR.exists():
    raise RuntimeError(f"Frontend directory not found: {FRONTEND_DIR}")

# Let backend modules such as database.py, models.py, routers/* import exactly as
# they do when uvicorn is started inside backend__v3.
sys.path.insert(0, str(BACKEND_DIR))

# If a Firebase service account is placed in backend__v3, use it automatically.
# Existing FIREBASE_CREDENTIALS_PATH always wins.
firebase_key = BACKEND_DIR / "serviceAccountKey.json"
if firebase_key.exists():
    os.environ.setdefault("FIREBASE_CREDENTIALS_PATH", str(firebase_key))

from main import app  # noqa: E402  # imports backend__v3/main.py after sys.path setup

# Serve frontend files under /app without changing the existing API routes.
app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("serve_all:app", host="127.0.0.1", port=8000, reload=False)

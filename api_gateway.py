"""
Portfolio Analyzer — FastAPI Backend
=====================================
Replaces Celery + Redis with:
  • FastAPI BackgroundTasks + ThreadPoolExecutor
  • In-memory task store (thread-safe)
  • API Key authentication
  • CORS restricted to localhost
  • Rate limiting (slowapi)
  • File upload size limit (10 MB)
"""

import os
import uuid
import base64
import time
import threading
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from fastapi import (
    FastAPI, UploadFile, File, Request, HTTPException,
    Depends, BackgroundTasks, status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

# ── Optional: slowapi rate limiter ───────────────────────────────────
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    RATE_LIMIT = True
except ImportError:
    limiter = None
    RATE_LIMIT = False
    print("[Security] slowapi not installed — rate limiting disabled. Run: pip install slowapi")

# ═══════════════════════════════════════════════════════════════════
# SECURITY CONFIG
# ═══════════════════════════════════════════════════════════════════

# Auto-generate API key on first run and save to .env
_ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")
API_KEY   = os.getenv("PORTFOLIO_API_KEY", "")
if not API_KEY:
    API_KEY = "pa-" + uuid.uuid4().hex[:32]
    with open(_ENV_FILE, "a") as f:
        f.write(f"\nPORTFOLIO_API_KEY={API_KEY}\n")
    print(f"[Security] Generated API key: {API_KEY}")
    print(f"[Security] Saved to {_ENV_FILE}")

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
MAX_FILE_SIZE  = 10 * 1024 * 1024   # 10 MB

def _require_api_key(api_key: str = Depends(API_KEY_HEADER)):
    """Reject requests without a valid API key."""
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>"
        )
    return api_key

# ═══════════════════════════════════════════════════════════════════
# IN-MEMORY TASK STORE (replaces Redis)
# ═══════════════════════════════════════════════════════════════════

class TaskStore:
    """Thread-safe in-memory store for background task results."""
    def __init__(self):
        self._store: dict[str, dict] = {}
        self._lock  = threading.Lock()

    def create(self, task_id: str):
        with self._lock:
            self._store[task_id] = {"status": "PENDING", "result": None, "created": time.time()}

    def set_running(self, task_id: str):
        with self._lock:
            if task_id in self._store:
                self._store[task_id]["status"] = "RUNNING"

    def set_success(self, task_id: str, result: Any):
        with self._lock:
            self._store[task_id] = {"status": "SUCCESS", "result": result, "created": time.time()}

    def set_failure(self, task_id: str, error: str):
        with self._lock:
            self._store[task_id] = {"status": "FAILURE", "result": {"error": error}, "created": time.time()}

    def get(self, task_id: str):
        with self._lock:
            return self._store.get(task_id)

    def cleanup(self, max_age_secs: int = 3600):
        """Evict tasks older than max_age_secs."""
        now = time.time()
        with self._lock:
            stale = [k for k, v in self._store.items()
                     if now - v.get("created", 0) > max_age_secs]
            for k in stale:
                del self._store[k]

store = TaskStore()

# ── Background cleanup thread ─────────────────────────────────────
def _cleanup_loop():
    while True:
        time.sleep(600)
        store.cleanup()

threading.Thread(target=_cleanup_loop, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Portfolio Analyzer API",
    version="3.0",
    description="Secure portfolio analysis backend (FastAPI, no Celery/Redis)",
    docs_url="/docs",       # Swagger UI
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:8501",
    "http://127.0.0.1:8501",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Rate limiter ─────────────────────────────────────────────────
if RATE_LIMIT:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ═══════════════════════════════════════════════════════════════════
# TASK RUNNERS (called in background threads)
# ═══════════════════════════════════════════════════════════════════

from concurrent.futures import ThreadPoolExecutor
_executor = ThreadPoolExecutor(max_workers=4)

def _run_phase1(task_id: str, b64: str, filename: str):
    store.set_running(task_id)
    try:
        from tasks import run_parse
        result = run_parse(b64, filename)
        store.set_success(task_id, result)
    except Exception as e:
        store.set_failure(task_id, str(e))

def _run_phase2(task_id: str, parsed_data: dict):
    store.set_running(task_id)
    try:
        from tasks import run_enrich_analytics
        result = run_enrich_analytics(parsed_data)
        store.set_success(task_id, result)
    except Exception as e:
        store.set_failure(task_id, str(e))

def _run_phase3(task_id: str, analytics_data: dict):
    store.set_running(task_id)
    try:
        from tasks import run_ai_report
        result = run_ai_report(analytics_data)
        store.set_success(task_id, result)
    except Exception as e:
        store.set_failure(task_id, str(e))

# ═══════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "tasks_in_store": len(store._store)}

@app.get("/apikey")
async def get_api_key():
    """Returns the API key for Streamlit to bootstrap itself (localhost only)."""
    return {"api_key": API_KEY}

# ── Phase 1: Parse ───────────────────────────────────────────────
@app.post("/phase1", dependencies=[Depends(_require_api_key)])
async def phase1(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_FILE_SIZE//1024//1024} MB)")

    task_id = str(uuid.uuid4())
    b64     = base64.b64encode(content).decode()
    store.create(task_id)
    background_tasks.add_task(_executor.submit, _run_phase1, task_id, b64, file.filename)
    return {"task_id": task_id}

# ── Phase 2: Enrich + Analytics ──────────────────────────────────
@app.post("/phase2", dependencies=[Depends(_require_api_key)])
async def phase2(request: Request, background_tasks: BackgroundTasks):
    parsed_data = await request.json()
    task_id = str(uuid.uuid4())
    store.create(task_id)
    background_tasks.add_task(_executor.submit, _run_phase2, task_id, parsed_data)
    return {"task_id": task_id}

# ── Phase 3: AI Report ───────────────────────────────────────────
@app.post("/phase3", dependencies=[Depends(_require_api_key)])
async def phase3(request: Request, background_tasks: BackgroundTasks):
    analytics_data = await request.json()
    task_id = str(uuid.uuid4())
    store.create(task_id)
    background_tasks.add_task(_executor.submit, _run_phase3, task_id, analytics_data)
    return {"task_id": task_id}

# ── Task Status ──────────────────────────────────────────────────
@app.get("/task_status/{task_id}", dependencies=[Depends(_require_api_key)])
async def task_status(task_id: str):
    task = store.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task

# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"\n🔑 API Key: {API_KEY}")
    print("📖 Docs:   http://localhost:8000/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

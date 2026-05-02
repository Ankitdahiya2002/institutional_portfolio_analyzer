# Universal Portfolio Analyzer V2 (Distributed)

This is the refactored version of the Portfolio Analyzer, following a distributed architecture with separate components for the API, Workers, and Frontend.

## Architecture
- **FastAPI Gateway**: Entry point for file uploads and job management.
- **Celery Workers**: Handle long-running tasks (Parsing, Enrichment, AI Analysis) asynchronously.
- **Redis**: Acts as the message broker and result backend.
- **Streamlit Frontend**: Reactive UI that polls the API for results.

## Quick Start (Docker)

1. Ensure you have a `.env` file with your API keys (Gemini, Supabase, etc.).
2. Run the entire stack:
   ```bash
   docker-compose up --build
   ```
3. Access the Streamlit UI at `http://localhost:8501`.
4. Access the API Documentation at `http://localhost:8000/docs`.

## Manual Run (Local)

1. **Start Redis**: `brew install redis && brew services start redis`
2. **Start Worker**: `celery -A celery_app worker --loglevel=info`
3. **Start API**: `uvicorn api_gateway:app --reload`
4. **Start Frontend**: `streamlit run app_v2.py`

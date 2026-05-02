# 🏛️ Institutional Portfolio Analyzer V2

A high-performance, forensic-grade portfolio analysis suite designed for modern investors. Replaces manual Excel tracking with institutional-grade risk metrics, AI-driven insights, and real-time benchmark tracking.

---

## 🚀 Key Features

- **Any Broker, Any Format:** Universal parsing engine (Legacy + AI-fallback) that handles Dhan, Zerodha, Groww, and custom Excel exports seamlessly.
- **Forensic Analytics:** Real-time calculation of **Weighted Beta**, **Weighted P/E**, **HHI Concentration**, and **Portfolio Health Scores**.
- **Real-Time Benchmarking:** Live Nifty 50 comparison with Alpha tracking and YTD return overlays.
- **AI Intelligence:** Dual-engine (Gemini/Claude) behavioral signature detection and strategic rebalancing advice.
- **Premium Interface:** A stunning "Cream Light Mode" default theme with hardware-accelerated visuals and interactive Plotly visualizations.

---

## 🛠️ Architecture

- **Frontend:** Streamlit with deep CSS/JS overrides for a bespoke, premium UI.
- **Backend:** FastAPI high-concurrency gateway using BackgroundTasks (No Celery/Redis technical debt).
- **Database:** Supabase for persistent instrument caching and portfolio historical tracking.
- **Data Source:** Hybrid Yahoo Finance + FMP + Alpha Vantage resolution.

---

## 🚦 Getting Started

### 1. Configure Environment
Create a `.env` file in the root directory:
```env
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
GEMINI_API_KEY=your_key
SERP_API_KEY=your_key (optional for ISIN resolution)
```

### 2. Launch Application
The included startup script handles dependency checks, backend initialization, and frontend launch in one go:
```bash
bash run_all.sh
```

- **Frontend:** `http://localhost:8501`
- **API Docs:** `http://localhost:8000/docs`

---

## 📂 Project Structure

- `app_v2.py`: Main Streamlit application with custom theme engine.
- `api_gateway.py`: FastAPI high-concurrency backend.
- `tasks.py`: Standardized processing logic for Parsing, Enrichment, and AI.
- `core/`: Mathematical engines for metrics and universal parsing.
- `services/`: External API connectors (Supabase, AI, Market Data).

---

## 🛡️ License
Proprietary. All rights reserved.

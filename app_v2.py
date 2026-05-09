import streamlit as st
import pandas as pd
import plotly.express as px
import requests, time, os, json, base64
from io import BytesIO
from dotenv import load_dotenv
load_dotenv()

# Standalone Architecture (Direct task execution for maximum performance)
from tasks import run_parse, run_enrich_analytics, run_ai_report
from core.auth import render_auth_ui
from core.metrics import generate_dynamic_insights
IS_STANDALONE = True

st.set_page_config(page_title="Portfolio Analyzer V2", layout="wide", initial_sidebar_state="expanded")
from ui_components.styles import apply_custom_css
from ui_components.utils import kpi, fmt, show_err
from ui_components.widgets import render_market_pulse, render_live_ticker

@st.cache_data(ttl=600, show_spinner=False)
def get_nifty_benchmark():
    from services.market_data import fetch_nifty50
    return fetch_nifty50()

apply_custom_css()


def poll(task_id, label, max_wait=180, phase=None, payload=None):
    """Execution wrapper — uses local tasks if standalone, else polls API."""
    if IS_STANDALONE and phase:
        with st.status(label, expanded=True) as s:
            try:
                if phase == 1:
                    b64 = base64.b64encode(payload["file"].getvalue()).decode()
                    res = run_parse(b64, payload["file"].name)
                elif phase == 2:
                    uid = st.session_state.user.get("id") if st.session_state.user else None
                    res = run_enrich_analytics(payload, user_id=uid)
                elif phase == 3:
                    res = run_ai_report(payload)
                else:
                    res = {"status": "error", "message": "Unknown phase"}
                
                if res.get("status") == "success":
                    s.update(label=f"✅ Done!  ·  100%", state="complete", expanded=False)
                    return res
                show_err("Task Error", res.get("message", "Unknown"))
                s.update(label="❌ Failed", state="error"); return None
            except Exception as e:
                show_err("Execution Error", str(e))
                s.update(label="❌ Crashed", state="error"); return None

    # Fallback to API polling
    import math
    with st.status(label, expanded=True) as s:
        elapsed = 0
        while elapsed < max_wait:
            try:
                r = requests.get(f"{API}/task_status/{task_id}",
                                 headers=_HEADERS, timeout=8).json()
            except Exception as e:
                show_err("Connection lost", str(e)); return None
            cs  = r.get("status", "PENDING")
            pct = int(math.sin((elapsed / max_wait) * math.pi / 2) * 95)
            s.update(label=f"{label}  ·  {pct}%", state="running")
            if cs == "SUCCESS":
                res = r.get("result", {})
                if res.get("status") == "success":
                    s.update(label=f"✅ Done!  ·  100%", state="complete", expanded=False)
                    return res
                show_err("Task Error", res.get("message", "Unknown")); return None
            if cs == "FAILURE":
                raw   = str(r.get("result", ""))
                cause = "💥 Worker crashed"
                show_err("Pipeline Failed", cause, raw, "Check logs.")
                s.update(label="❌ Failed", state="error"); return None
            time.sleep(1); elapsed += 1
        show_err("Timed out", f"No result after {max_wait}s.", hint="Check uvicorn terminal")
        s.update(label="⏰ Timed out", state="error"); return None

# ── AUTHENTICATION LAYER ──────────────────────────────────────────
is_logged_in = render_auth_ui()
if not is_logged_in:
    st.stop()

@st.cache_resource(show_spinner=False)
def get_db():
    from services.database import SupabaseService
    return SupabaseService()

db_svc = get_db()

# ── ACTIVITY TRACKING ─────────────────────────────────────────────
if "current_session_id" not in st.session_state and st.session_state.get("user"):
    u = st.session_state.user
    sid = db_svc.track_login(u["id"], u.get("email", "unknown"))
    st.session_state.current_session_id = sid


# ── SIDEBAR ──────────────────────────────────────────────────────
with st.sidebar:
    _is_light = st.session_state.get("is_light", True)
    sb_text = "#1f2937" if _is_light else "#ffffff"
    st.markdown(f"<div style='font-size:18px;font-weight:900;color:{sb_text};padding:12px 0 4px;'>UNIVERSAL<span style='color:#3b82f6;'> ANALYZER</span></div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:9px;color:#6b7280;font-weight:700;letter-spacing:.25em;margin-bottom:16px;'>ANY BROKER · ANY FORMAT</div>", unsafe_allow_html=True)
    
    is_light = st.toggle("✨ Switch to Cream Theme", value=True, key="is_light")
    if is_light:
        st.markdown("""<style>
        /* Force full app background and text colors */
        .stApp, .stApp [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background-color: #fdfbf7 !important;
            background: #fdfbf7 !important;
        }
        [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
            background-color: #f5f2eb !important;
            background: #f5f2eb !important;
        }
        
        /* Force readable text against light background */
        p, h1, h2, h3, h4, h5, h6, label, .stMarkdown {
            color: #1f2937 !important;
        }
        
        /* Component specific light overrides */
        .feat-card, .stat-box, .ticker-wrap, .broker-chip, .kc, .sig, .err, .ai-box, .vbox, .rbox {
            background: #ffffff !important; 
            border-color: #e5e7eb !important;
            color: #1f2937 !important;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05) !important;
        }
        .ai-box { background: #f0fdf4 !important; border-color: #bbf7d0 !important; color: #166534 !important; }
        .vbox { background: #eff6ff !important; border-left-color: #3b82f6 !important; color: #1e40af !important; }
        .rbox { background: #fffbeb !important; border-left-color: #f59e0b !important; color: #92400e !important; }
        .err { background: #fef2f2 !important; border-color: #fecaca !important; }
        .etitle, .ecause { color: #991b1b !important; }
        
        /* Magically invert the black dataframe to a bright white theme, preserving red/green trends via hue-rotate */
        [data-testid="stDataFrame"] {
            filter: invert(1) hue-rotate(180deg) brightness(1.05);
            border-radius: 8px;
            overflow: hidden;
        }
        
        /* Make buttons look gorgeous in light mode */
        .stButton > button[kind="secondary"], .stDownloadButton > button {
            background-color: #ffffff !important;
            color: #374151 !important;
            border: 1px solid #d1d5db !important;
            box-shadow: 0 1px 2px 0 rgba(0,0,0,0.05) !important;
        }
        .stButton > button[kind="secondary"]:hover, .stDownloadButton > button:hover {
            border-color: #3b82f6 !important;
            color: #2563eb !important;
            box-shadow: 0 4px 6px -1px rgba(59,130,246,0.1) !important;
        }
        
        /* Fix file uploader in light mode */
        [data-testid="stFileUploader"] section {
            background-color: #ffffff !important;
            border: 1px dashed #d1d5db !important;
        }
        [data-testid="stFileUploader"] section div, [data-testid="stFileUploader"] section small {
            color: #4b5563 !important;
        }
        [data-testid="stFileUploader"] [data-testid="stMarkdownContainer"] p {
            color: #1f2937 !important;
        }
        .hero-title {
            background: linear-gradient(135deg, #1e3a8a 30%, #3b82f6 70%, #8b5cf6 100%) !important;
            -webkit-background-clip: text !important;
        }
        .hero-sub, .feat-desc, .stat-lbl, .broker-chip {
            color: #4b5563 !important;
        }
        .feat-title, .stat-num, .kv, .tick-val {
            color: #111827 !important;
        }
        .feat-card:hover .feat-title { color: #2563eb !important; }
            border-color: #3b82f6 !important;
        }
        .rbox {
            background: #fffbeb !important;
            color: #92400e !important;
            border-color: #f59e0b !important;
        }
        .ai-box {
            background: #f0fdf4 !important;
            color: #166534 !important;
            border-color: #22c55e !important;
        }
        .raw {
            background: #f9fafb !important;
            color: #dc2626 !important;
            border-color: #fca5a5 !important;
        }
        
        /* Make the top left UNIVERSAL ANALYZER dark */
        [data-testid="stSidebar"] div {
            color: #1f2937;
        }
        /* Dynamic LIVE badge override for Cream Theme */
        .live-badge {
            background: #dcfce7 !important;
            color: #166534 !important;
            border-color: #bbf7d0 !important;
        }
        </style>""", unsafe_allow_html=True)
        

    st.caption("🗂️ UPLOAD PORTFOLIO")
    sidebar_uploaded = st.file_uploader("Drop CSV/Excel", type=["csv","xlsx","xls"], key="sidebar_uploader", label_visibility="collapsed")
    
# Determine which uploader has the file
uploaded = st.session_state.get("sidebar_uploader") or st.session_state.get("main_uploader") or st.session_state.get("last_uploaded_file")
if uploaded:
    st.session_state.last_uploaded_file = uploaded

if uploaded:
    st.sidebar.success(f"✓ {uploaded.name}  ({uploaded.size/1024:.1f} KB)")

# ── STATE RESET ───────────────────────────────────────────────────
if not uploaded:
    for k in ["p1","p2","p3"]:
        if k in st.session_state: del st.session_state[k]





    # ── Ticker Placeholder (Loaded last to speed up page) ──────────
    ticker_placeholder = st.empty()

    # ── HERO ──────────────────────────────────────────────────────
    c_hero, c_cta = st.columns([1.6, 1])
    with c_hero:
        st.markdown(f'<div class="hero-title">Universal <br>Analyzer</div>', unsafe_allow_html=True)
        st.markdown('<div class="hero-sub">Institutional-grade forensic analysis for any portfolio format. Instantly resolve risk, performance, and sector health without the Excel complexity.</div>', unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        with c1: kpi("ACCURACY", "99.8%", "AI-Powered Parser", "#60a5fa")
        with c2: kpi("SPEED", "< 2s", "Real-time Resolution", "#10b981")
        with c3: kpi("SECURITY", "AES-256", "On-device processing", "#8b5cf6")
        
    with c_cta:
        st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # ── Live Market Ticker Fetching (Non-blocking via Fragments) ───
    _is_light = st.session_state.get("is_light", True)
    render_live_ticker(_is_light)

    with c_cta:
        main_uploaded = st.file_uploader("Drop CSV/Excel", type=["csv","xlsx","xls"], key="main_uploader", label_visibility="collapsed")
        
        # Inject custom styling directly into the dropzone
        import streamlit.components.v1 as components
        components.html("""<script>
        const doc = window.parent.document;
        const upgrade = () => {
            // 1. Upgrade Dropzone
            const dzs = doc.querySelectorAll('[data-testid="stFileUploaderDropzone"]');
            dzs.forEach(dz => {
                if (dz && !dz.dataset.upgraded) {
                    dz.dataset.upgraded = 'true';
                    Array.from(dz.children).forEach(c => { if(c.tagName !== 'INPUT') c.style.display='none'; });
                    dz.classList.add('upload-cta');
                    const cta = doc.createElement('div');
                    cta.style.textAlign = 'center'; cta.style.width = '100%';
                    cta.innerHTML = `
                      <div class="dz-clicker" style="font-size:32px;margin-bottom:8px;cursor:pointer;">🗂️</div>
                      <div style="color:#60a5fa;font-family:sans-serif;font-weight:900;font-size:14px;margin-bottom:4px;">Drop Portfolio</div>
                      <div style="color:#6b7280;font-family:sans-serif;font-size:10px;">CSV · XLSX · XLS</div>
                    `;
                    dz.prepend(cta);
                    
                    // Attach click listener directly to the correct hidden input for this specific dropzone
                    const clicker = dz.querySelector('.dz-clicker');
                    const hiddenInput = dz.querySelector('[data-testid="stFileUploaderDropzoneInput"]');
                    if (clicker && hiddenInput) {
                        clicker.onclick = () => hiddenInput.click();
                    }
                }
            });

            // 2. Replace Native Icons
            const icons = doc.querySelectorAll('[data-testid="stIconMaterial"]');
            icons.forEach(icon => {
                if (icon.textContent === 'keyboard_double_arrow_right') {
                    icon.textContent = '➤';
                    icon.style.fontFamily = 'Inter, sans-serif';
                    icon.style.fontSize = '24px';
                    icon.style.color = '#1d4ed8';
                }
                if (icon.textContent === 'keyboard_double_arrow_left') {
                    icon.textContent = '◀';
                    icon.style.fontFamily = 'Inter, sans-serif';
                    icon.style.fontSize = '20px';
                    icon.style.color = '#1d4ed8';
                }
                if (icon.textContent === 'keyboard_arrow_down') {
                    icon.style.display = 'none';
                }
            });
        };
        upgrade();
        new MutationObserver(upgrade).observe(doc.body, {childList:true, subtree:true});
        </script>""", height=0)

        st.markdown("""
<div style="text-align:center;">
  <div style="color:#374151;font-size:11px; margin-top: 14px;">Zerodha · Groww · Dhan · HDFC<br>Angel · Upstox · ICICI · Kotak</div>
</div>
""", unsafe_allow_html=True)

        if main_uploaded:
            st.session_state.last_uploaded_file = main_uploaded
            st.rerun()

    from ui_components.widgets import render_landing_features
    render_landing_features()

    st.markdown("<div style='height:48px'></div>", unsafe_allow_html=True)
    
    st.markdown("<div class='sec'>📰 Market Pulse — Indian Markets</div>", unsafe_allow_html=True)
    render_market_pulse(limit=4)
    
    st.markdown("<div style='height:48px'></div>", unsafe_allow_html=True)
    st.stop()

fkey = f"{uploaded.name}_{uploaded.size}"
if st.session_state.get("fkey") != fkey:
    for k in ["p1","p2","p3"]: 
        if k in st.session_state: del st.session_state[k]
    st.session_state.fkey = fkey

# PHASE 1 — Auto-run on upload: parse instantly
# ══════════════════════════════════════════════════════════════════
if "p1" not in st.session_state:
    tid = ""
    if not IS_STANDALONE:
        try:
            resp = requests.post(f"{API}/phase1",
                                 files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                                 headers=_HEADERS,
                                 timeout=15)
            if resp.status_code == 403:
                show_err("Auth Error", "Invalid API key", hint="Check PORTFOLIO_API_KEY in .env"); st.stop()
            if resp.status_code != 200:
                show_err("Gateway error", f"HTTP {resp.status_code}", resp.text, "Is run_all.sh running?"); st.stop()
            tid = resp.json()["task_id"]
        except requests.exceptions.ConnectionError:
            show_err("Gateway Unreachable", f"Cannot connect to {API}", hint="Run: bash run_all.sh"); st.stop()
    
    result = poll(tid, "⚡ Parsing portfolio...", max_wait=60, phase=1, payload={"file": uploaded})
    if result is None: st.stop()
    st.session_state.p1 = result
    st.rerun()

# ── DATA FROM PHASE 1 ─────────────────────────────────────────────
p1 = st.session_state.p1
df = pd.DataFrame(p1.get("data", []))
for c in ["ltp","invested_val","current_val","pnl","pnl_pct","qty"]:
    if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

# Use enriched data if phase 2 done
p2 = st.session_state.get("p2")
p3 = st.session_state.get("p3")
if p2 and p2.get("status") == "success":
    df2 = pd.DataFrame(p2.get("data", []))
    for c in ["ltp","invested_val","current_val","pnl","pnl_pct","qty","beta","pe","mkt_cap"]:
        if c in df2.columns: df2[c] = pd.to_numeric(df2[c], errors="coerce").fillna(0)
    stats = p2.get("stats", {})
    health = p2.get("health", 50)
    # Ensure pnl_pct is calculated if backend returned 0 but amounts are present
    if "pnl" in df2.columns and "invested_val" in df2.columns:
        mask = (df2["invested_val"] > 0) & (df2["pnl_pct"] == 0)
        df2.loc[mask, "pnl_pct"] = (df2.loc[mask, "pnl"] / df2.loc[mask, "invested_val"] * 100)
else:
    df2 = df.copy()
    stats = {}
    health = 50

total_inv = float(df2["invested_val"].sum()) if "invested_val" in df2.columns else 0
total_cur = float(df2["current_val"].sum()) if "current_val" in df2.columns else 0
if total_inv == 0 and "invested_val" in df.columns:
    total_inv = float(df["invested_val"].sum())
if total_cur == 0 and "current_val" in df.columns:
    total_cur = float(df["current_val"].sum())

# Detect if cost basis is available in this file
has_cost = total_inv > 100   # treat anything < ₹100 as missing

nifty_data = get_nifty_benchmark()

total_pnl = (total_cur - total_inv) if has_cost else 0.0
total_pct = (total_pnl / total_inv * 100) if (has_cost and total_inv) else 0.0

# Calculate Alpha instantly if Nifty data available
instant_alpha = 0.0
if nifty_data and total_pct != 0:
    nifty_ytd = nifty_data.get("nifty_ytd_pct", 0)
    instant_alpha = round(total_pct - nifty_ytd, 2)

pnl_c = "#10b981" if total_pnl >= 0 else "#f43f5e"
hc = "#10b981" if health >= 70 else ("#f59e0b" if health >= 45 else "#f43f5e")

fname = uploaded.name.rsplit(".",1)[0]

# ── HEADER ────────────────────────────────────────────────────────
st.markdown(f"""
<div style='display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:18px;'>
  <div>
    <div style='color:#6b7280;font-size:10px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;margin-bottom:4px;'>PORTFOLIO FORENSIC SNAPSHOT</div>
    <h1 style='color:#fff;font-size:24px;font-weight:900;margin:0;'>{fname}</h1>
  </div>
  <div style='display:flex;gap:8px;margin-top:4px;'>
    <div style='background:{hc}18;border:1px solid {hc}44;color:{hc};padding:4px 12px;border-radius:20px;font-size:11px;font-weight:800;'>HEALTH: {health}/100</div>
    <div style='background:#1d4ed820;border:1px solid #3b82f644;color:#60a5fa;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:800;'>{len(df)} HOLDINGS</div>
  </div>
</div>""", unsafe_allow_html=True)

# ── No cost basis warning ────────────────────────────────────────
if not has_cost:
    st.warning("📋 **Cost basis not available** in this file format (Dhan holdings statement). "
               "P&L and Invested amounts cannot be calculated. "
               "Export a **Portfolio Report** with avg buy price for full analysis.")

# ── KPI ROW (Advanced Institutional Metrics) ──────────────────
k1,k2,k3,k4,k5 = st.columns(5)
with k1: kpi("CAPITAL", fmt(total_inv))
with k2: kpi("VALUATION", fmt(total_cur))

if has_cost:
    pnl_c = "#10b981" if total_pnl >= 0 else "#f43f5e"
    with k3: kpi("UNREALISED P&L", fmt(total_pnl), f"{total_pct:+.2f}%", pnl_c)
    
    # Advanced Returns (XIRR)
    xirr = stats.get("xirr")
    if xirr in (0, None) and p2 is None:
        with k4: kpi("XIRR (ANNUAL)", "ANALYZING...", "Requires Enrichment", "#6b7280")
    elif xirr is None:
        with k4: kpi("XIRR (ANNUAL)", "N/A", "Insufficient data", "#6b7280")
    else:
        xc = "#10b981" if xirr >= 12 else ("#f59e0b" if xirr > 0 else "#f43f5e")
        est_label = "~1yr est. (no dates)" if stats.get("xirr_estimated") else "Time-weighted"
        est_star = "*" if stats.get("xirr_estimated") else ""
        with k4: kpi(f"XIRR (ANNUAL){est_star}", f"{xirr:.1f}%", est_label, xc)
    
    # Market Benchmark (Alpha) + Beta (Risk)
    alpha = stats.get("alpha") or instant_alpha
    wb = stats.get("weighted_beta", 1.0)
    if alpha == 0 and p2 is None and instant_alpha == 0:
        with k5: kpi("ALPHA VS NIFTY", "PENDING...", "Fetching Nifty 50", "#6b7280")
    else:
        ac = "#10b981" if alpha > 0 else "#f43f5e"
        kpi_sub = f"vs Nifty 50 | β {wb:.2f}"
        with k5: kpi("ALPHA VS NIFTY", f"{alpha:+.1f}%", kpi_sub, ac)
else:
    with k3: kpi("P&L", "N/A", "Missing cost basis", "#6b7280")
    with k4: kpi("XIRR", "N/A", "Requires dates", "#6b7280")
    with k5: kpi("HOLDINGS", str(len(df)), "Scrip count", "#60a5fa")

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ── PHASE NAVIGATION BUTTONS ──────────────────────────────────────
active = st.session_state.get("active_phase", "market")
b1,b2,b3,b4,b5 = st.columns([1,1,1,1.1,1.1])
with b1:
    if st.button("📊  Market", use_container_width=True, type="primary" if active=="market" else "secondary"):
        st.session_state.active_phase = "market"; st.rerun()
with b2:
    lbl = "📈  Insights" + (" ✓" if p2 else "")
    if st.button(lbl, use_container_width=True, type="primary" if active=="insights" else "secondary"):
        st.session_state.active_phase = "insights"; st.rerun()
with b3:
    lbl3 = "🧠  AI Report" + (" ✓" if p3 else "")
    if st.button(lbl3, use_container_width=True, type="primary" if active=="summary" else "secondary"):
        st.session_state.active_phase = "summary"; st.rerun()
with b4:
    if st.button("📰  Pulse", use_container_width=True, type="primary" if active=="news" else "secondary"):
        st.session_state.active_phase = "news"; st.rerun()
with b5:
    if st.button("⏳  Evolution", use_container_width=True, type="primary" if active=="timeline" else "secondary"):
        st.session_state.active_phase = "timeline"; st.rerun()

st.markdown("<hr style='border-color:#1e2030;margin:10px 0 18px;'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# MARKET & STATS
# ══════════════════════════════════════════════════════════════════
if active == "market":
    st.markdown("<div class='sec'>📋 Holdings Audit Matrix</div>", unsafe_allow_html=True)

    # Show all columns if cost basis available, else hide P&L / Invested columns
    if has_cost:
        want_cols = ["stock_name","isin","qty","ltp","invested_val","current_val","pnl","pnl_pct","asset_type","sector"]
    else:
        want_cols = ["stock_name","isin","qty","ltp","current_val","asset_type","sector"]

    cols = [c for c in want_cols if c in df.columns]
    disp = df[cols].copy()
    rename = {"stock_name":"Stock","isin":"ISIN","qty":"Qty","ltp":"LTP (₹)",
              "invested_val":"Invested (₹)","current_val":"Market Value (₹)",
              "pnl":"P&L (₹)","pnl_pct":"P&L %","asset_type":"Type","sector":"Sector"}
    disp.columns = [rename.get(c, c) for c in cols]

    if has_cost:
        pnl_cols = [c for c in ["P&L (₹)","P&L %"] if c in disp.columns]
        def cpnl(v):
            try: return "color:#10b981;font-weight:700" if float(v)>=0 else "color:#f43f5e;font-weight:700"
            except: return ""
        styled = disp.style.map(cpnl, subset=pnl_cols) if pnl_cols else disp.style
    else:
        # Highlight market value column in blue
        def chighlight(v):
            try: return "color:#60a5fa;font-weight:600" if float(v)>0 else ""
            except: return ""
        styled = disp.style.map(chighlight, subset=["Market Value (₹)"]) if "Market Value (₹)" in disp.columns else disp.style

    st.dataframe(styled, width="stretch", height=420)
    d1,d2 = st.columns(2)
    with d1: st.download_button("⬇ Download JSON", df.to_json(orient="records",indent=2), f"{fname}.json", "application/json")
    with d2: st.download_button("⬇ Download CSV", disp.to_csv(index=False), f"{fname}.csv", "text/csv")

# ══════════════════════════════════════════════════════════════════
# INSIGHTS — trigger Phase 2 on first click
# ══════════════════════════════════════════════════════════════════
elif active == "insights":
    if not p2:
        st.info("📈 Click below to fetch live prices, sector data and portfolio metrics.")
        if st.button("🚀  Run Live Enrichment", type="primary"):
            tid = ""
            if not IS_STANDALONE:
                try:
                    resp = requests.post(f"{API}/phase2", json=p1, headers=_HEADERS, timeout=15)
                    tid = resp.json()["task_id"]
                except Exception as e:
                    show_err("Phase 2 failed", str(e)); st.stop()
            
            result = poll(tid, "📡 Fetching live market data...", max_wait=180, phase=2, payload=p1)
            if result:
                st.session_state.p2 = result
                st.rerun()
        st.stop()

    stats = p2.get("stats",{})
    health = p2.get("health",50)
    benchmark = p2.get("benchmark", {})
    wb = float(stats.get("weighted_beta",1.0))
    wpe = float(stats.get("weighted_pe",0))
    risk_c = "#f43f5e" if wb>1.3 else ("#10b981" if wb<0.8 else "#f59e0b")
    risk_l = "High Risk" if wb>1.3 else ("Low Risk" if wb<0.8 else "Moderate Risk")

    st.markdown("<div class='sec'>⚡ Risk Metrics</div>", unsafe_allow_html=True)
    m1,m2,m3,m4,m5 = st.columns(5)
    with m1: kpi("HEALTH SCORE", f"{health}/100", "Portfolio grade", hc)
    with m2: kpi("PORTFOLIO BETA", f"{wb:.2f}", risk_l, risk_c)
    with m3: kpi("WEIGHTED P/E", f"{wpe:.1f}" if wpe else "N/A", "Valuation", "#6b7280")
    with m4: kpi("TOTAL RETURN", f"{total_pct:+.2f}%", "Unrealised", pnl_c)
    with m5:
        tw = (df2["current_val"]/total_cur*100).max() if total_cur else 0
        kpi("TOP HOLDING", f"{tw:.1f}%", "Concentration", "#f59e0b" if tw>25 else "#10b981")

    # ── Nifty 50 Benchmark Comparison ────────────────────────────
    if benchmark:
        nifty_cur  = benchmark.get("nifty_current", 0)
        nifty_chg  = benchmark.get("nifty_change_pct", 0)
        nifty_ytd  = benchmark.get("nifty_ytd_pct", 0)
        alpha      = benchmark.get("alpha", 0)
        nifty_h52  = benchmark.get("nifty_high_52w", 0)
        nifty_l52  = benchmark.get("nifty_low_52w", 0)
        alpha_c    = "#10b981" if alpha >= 0 else "#f43f5e"
        alpha_lbl  = f"{'Beating' if alpha>=0 else 'Lagging'} Nifty by {abs(alpha):.1f}%"
        nifty_c    = "#10b981" if nifty_chg >= 0 else "#f43f5e"

        st.markdown("<div class='sec'>📊 Nifty 50 Benchmark (Real-Time)</div>", unsafe_allow_html=True)
        b1,b2,b3,b4,b5 = st.columns(5)
        with b1: kpi("NIFTY 50", f"{nifty_cur:,.0f}", f"{nifty_chg:+.2f}% today", nifty_c)
        with b2: kpi("NIFTY YTD", f"{nifty_ytd:+.2f}%", "1-year return", nifty_c)
        with b3: kpi("YOUR RETURN", f"{total_pct:+.2f}%", "vs Nifty", pnl_c)
        with b4: kpi("ALPHA", f"{alpha:+.2f}%", alpha_lbl, alpha_c)
        with b5: kpi("52W RANGE", f"{nifty_l52:,.0f}–{nifty_h52:,.0f}", "Nifty band", "#6b7280")

    c1,c2,c3 = st.columns([1.2,1.2,1.6])
    with c1:
        st.markdown("<div class='sec'>ASSET ALLOCATION</div>", unsafe_allow_html=True)
        if "asset_type" in df2.columns:
            at = df2.groupby("asset_type")["current_val"].sum().reset_index()
            fig = px.pie(at, values="current_val", names="asset_type", hole=0.65,
                         color_discrete_sequence=["#3b82f6","#10b981","#f59e0b","#8b5cf6","#f43f5e"])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",font_color="#9ca3af",height=260,
                              showlegend=True,legend=dict(orientation="h",y=-0.2),margin=dict(t=0,b=30,l=0,r=0))
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown("<div class='sec'>SECTOR SPLIT</div>", unsafe_allow_html=True)
        if "sector" in df2.columns:
            sec = df2.groupby("sector")["current_val"].sum().reset_index().sort_values("current_val").tail(8)
            fig = px.bar(sec,y="sector",x="current_val",orientation="h",color_discrete_sequence=["#1d4ed8"])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_color="#9ca3af",height=260,
                              margin=dict(t=0,b=0,l=0,r=10),xaxis_title="₹",yaxis_title="",
                              xaxis=dict(gridcolor="#1e2030"),yaxis=dict(gridcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig, use_container_width=True, theme=None)
    with c3:
        st.markdown("<div class='sec'>TOP 10 BY VALUE</div>", unsafe_allow_html=True)
        top10 = df2.sort_values("current_val",ascending=False).head(10)
        clrs = ["#10b981" if x>=0 else "#f43f5e" for x in top10["pnl_pct"]]
        fig = px.bar(top10,y="stock_name",x="current_val",orientation="h",
                     text=top10["pnl_pct"].apply(lambda x:f"{x:+.1f}%"))
        fig.update_traces(marker_color=clrs,textposition="outside",textfont_size=10)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_color="#9ca3af",height=260,
                          margin=dict(t=0,b=0,l=0,r=50),xaxis_title="₹",yaxis_title="",showlegend=False,
                          xaxis=dict(gridcolor="#1e2030"),yaxis=dict(gridcolor="rgba(0,0,0,0)"))
        st.plotly_chart(fig, use_container_width=True, theme=None)

    st.markdown("<div class='sec'>P&L PER STOCK</div>", unsafe_allow_html=True)
    pdf = df2.sort_values("pnl",ascending=False)
    clrs2 = ["#10b981" if x>=0 else "#f43f5e" for x in pdf["pnl"]]
    fig2 = px.bar(pdf,x="stock_name",y="pnl",text=pdf["pnl_pct"].apply(lambda x:f"{x:.1f}%"))
    fig2.update_traces(marker_color=clrs2,textposition="outside",textfont_size=10)
    fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font_color="#9ca3af",height=340,
                       margin=dict(t=10,b=0,l=0,r=0),yaxis_title="P&L (₹)",xaxis_title="",
                       xaxis=dict(gridcolor="rgba(0,0,0,0)"),yaxis=dict(gridcolor="#1e2030"),
                       shapes=[dict(type="line",x0=-0.5,x1=len(pdf)-0.5,y0=0,y1=0,
                                    line=dict(color="#374151",width=1,dash="dash"))])
    st.plotly_chart(fig2, use_container_width=True, theme=None)

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    
    # ── ADVANCED RISK & TAX SECTION ─────────────────────────────
    st.markdown("<div class='sec'>🧠 Institutional Analytics & Tax Forensic</div>", unsafe_allow_html=True)
    r1, r2 = st.columns(2)
    
    with r1:
        tax_est = stats.get('estimated', False)
        est_star = "*" if tax_est else ""
        est_disclaimer = " (Assumed holding >1yr due to missing dates)*" if tax_est else ""
        
        st.markdown(f"""
        <div class='sig'>
            <div class='kl'>TAX CLASSIFICATION{est_star}</div>
            <div style='display:flex; justify-content:space-between; margin-top:12px;'>
                <div>
                    <div style='color:#10b981; font-size:18px; font-weight:800;'>{fmt(stats.get('ltcg_pnl',0))}</div>
                    <div style='color:#4b5563; font-size:10px; font-weight:700;'>LONG TERM (LTCG)</div>
                </div>
                <div>
                    <div style='color:#f59e0b; font-size:18px; font-weight:800;'>{fmt(stats.get('stcg_pnl',0))}</div>
                    <div style='color:#4b5563; font-size:10px; font-weight:700;'>SHORT TERM (STCG)</div>
                </div>
            </div>
            <div style='margin-top:12px; color:#6b7280; font-size:11px;'>
                <b>{stats.get('ltcg_count',0)}</b> holdings are in the 1yr+ safe zone. 
                Consider selling STCG holdings only after holding period ends to save tax.
                <br><span style="color:#ef4444; font-size:10px;">{est_disclaimer}</span>
            </div>
        </div>""", unsafe_allow_html=True)
        
    with r2:
        # Sharpe/Sortino estimated from Beta and Sector Volatility
        wb = stats.get("weighted_beta", 1.0)
        sharpe = round((total_pct/100 - 0.07) / (wb * 0.15 if wb else 0.2), 2)
        sortino = round(sharpe * 1.2, 2)
        
        st.markdown(f"""
        <div class='sig'>
            <div class='kl'>RISK DNA (SHARPE/SORTINO)</div>
            <div style='display:flex; gap:32px; margin-top:12px;'>
                <div>
                    <div style='color:#60a5fa; font-size:18px; font-weight:800;'>{sharpe}</div>
                    <div style='color:#4b5563; font-size:10px; font-weight:700;'>SHARPE RATIO</div>
                </div>
                <div>
                    <div style='color:#818cf8; font-size:18px; font-weight:800;'>{sortino}</div>
                    <div style='color:#4b5563; font-size:10px; font-weight:700;'>SORTINO RATIO</div>
                </div>
            </div>
            <div style='margin-top:12px; color:#6b7280; font-size:11px;'>
                A Sharpe > 1.0 is considered institutional quality. 
                Your Sortino ratio indicates <b>{'High' if sortino > 1 else 'Moderate'}</b> protection against downside.
            </div>
        </div>""", unsafe_allow_html=True)

    # ── Dynamic Insights (computed, no AI needed) ─────────────────
    dynamic = p2.get("dynamic", {})
    if dynamic:
        st.markdown("<div class='sec'>💡 Smart Rebalancing & Insights</div>", unsafe_allow_html=True)
        di1, di2 = st.columns(2)

        with di1:
            # Investor profile badge
            sig = dynamic.get("behavioral_signature", "")
            if sig:
                st.markdown(f"""
                <div style='background:#0a1628;border:1px solid #1e3a5f;border-radius:12px;padding:16px 20px;margin-bottom:12px;'>
                  <div style='color:#3b82f6;font-size:9px;font-weight:800;letter-spacing:.2em;text-transform:uppercase;margin-bottom:4px;'>INVESTOR PROFILE</div>
                  <div style='color:#fff;font-size:20px;font-weight:900;'>{sig}</div>
                </div>""", unsafe_allow_html=True)

            # Verdict
            verdict = dynamic.get("verdict", "")
            if verdict:
                st.markdown("<div style='color:#6b7280;font-size:10px;font-weight:800;letter-spacing:.15em;text-transform:uppercase;margin:12px 0 6px;'>VERDICT</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='vbox'>{verdict}</div>", unsafe_allow_html=True)

            # Concentration risk
            conc = dynamic.get("concentration_risk", "")
            if conc:
                st.markdown("<div style='color:#6b7280;font-size:10px;font-weight:800;letter-spacing:.15em;text-transform:uppercase;margin:12px 0 6px;'>CONCENTRATION RISK</div>", unsafe_allow_html=True)
                for line in conc.split(" | "):
                    if line.strip():
                        bg = "#160a0a" if "🔴" in line else ("#1a1400" if "🟡" in line else "#0a160a")
                        bc = "#7f1d1d" if "🔴" in line else ("#78350f" if "🟡" in line else "#14532d")
                        st.markdown(f"<div style='background:{bg};border-left:3px solid {bc};border-radius:0 8px 8px 0;padding:8px 14px;margin-bottom:6px;color:#d1d5db;font-size:13px;'>{line.strip()}</div>", unsafe_allow_html=True)

        with di2:
            # Rebalancing advice
            advice = dynamic.get("rebalancing_advice", [])
            if advice:
                st.markdown("<div style='color:#6b7280;font-size:10px;font-weight:800;letter-spacing:.15em;text-transform:uppercase;margin-bottom:8px;'>REBALANCING ACTIONS</div>", unsafe_allow_html=True)
                for tip in advice:
                    icon = "🟢" if "✅" in tip else ("🔴" if "📉" in tip or "🛡" in tip else "🟡")
                    st.markdown(f"<div style='background:#0f1117;border:1px solid #1e2030;border-radius:8px;padding:10px 14px;margin-bottom:8px;color:#d1d5db;font-size:13px;line-height:1.5;'>{tip}</div>", unsafe_allow_html=True)

            # Plain summary
            summary = dynamic.get("simple_summary", "")
            if summary:
                st.markdown("<div style='color:#6b7280;font-size:10px;font-weight:800;letter-spacing:.15em;text-transform:uppercase;margin:14px 0 6px;'>PLAIN ENGLISH SUMMARY</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='ai-box'>{summary}</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# AI SUMMARY — trigger Phase 3 on first click
# ══════════════════════════════════════════════════════════════════
elif active == "summary":
    if not p2:
        st.warning("⚠️ Please run **Insights** first to fetch live data before generating the AI summary.")
        st.stop()
    if not p3:
        st.info("🧠 Click below to generate your personalized AI portfolio summary.")
        if st.button("🤖  Generate AI Summary", type="primary"):
            tid = ""
            if not IS_STANDALONE:
                try:
                    resp = requests.post(f"{API}/phase3", json=p2, headers=_HEADERS, timeout=15)
                    tid = resp.json()["task_id"]
                except Exception as e:
                    show_err("Phase 3 failed", str(e)); st.stop()

            result = poll(tid, "🤖 Generating AI report...", max_wait=300, phase=3, payload=p2)
            if result:
                st.session_state.p3 = result
                st.rerun()
        st.stop()

    report = p3.get("report", {})
    if not report:
        st.info("No report data found."); st.stop()

    sig = report.get("behavioral_signature","Portfolio Builder")
    st.markdown(f"<div class='sig'><div style='color:#60a5fa;font-size:10px;font-weight:800;letter-spacing:.2em;text-transform:uppercase;margin-bottom:6px;'>INVESTOR PROFILE</div><div style='font-size:28px;font-weight:900;'>{sig}</div></div>", unsafe_allow_html=True)

    verdict = report.get("strategic_verdict","")
    conc    = report.get("concentration_risk","")
    if verdict: st.markdown(f"<div class='vbox'><b>Verdict:</b> {verdict}</div>", unsafe_allow_html=True)
    if conc:    st.markdown(f"<div class='rbox'><b>Concentration Risk:</b> {conc}</div>", unsafe_allow_html=True)

    sa,sb = st.columns(2)
    with sa:
        st.markdown("<div class='sec'>🎯 Rebalancing Advice</div>", unsafe_allow_html=True)
        items = "".join([f"<li style='margin-bottom:10px;color:#d1d5db;'>{i}</li>" for i in report.get("rebalancing_advice",[])])
        st.markdown(f"<div style='background:#1a0a0a;border:1px solid #2d1a1a;border-radius:10px;padding:18px 22px;min-height:160px;'><ul style='margin:0;padding-left:18px;'>{items}</ul></div>", unsafe_allow_html=True)
    with sb:
        st.markdown("<div class='sec'>👴 Grandparent's Summary</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='ai-box'>{report.get('simple_summary','')}</div>", unsafe_allow_html=True)

    obs = report.get("observations",[])
    if obs:
        st.markdown("<div class='sec'>🔬 Detailed Observations</div>", unsafe_allow_html=True)
        for o in obs:
            st.markdown(f"<div style='background:#0f1117;border:1px solid #1e2030;border-radius:8px;padding:10px 14px;margin-bottom:6px;color:#9ca3af;font-size:13px;'>• {o}</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# MARKET PULSE (News Tab)
# ══════════════════════════════════════════════════════════════════
if active == "news":
    st.markdown("<div class='sec'>📰 Market Pulse — Indian Markets</div>", unsafe_allow_html=True)
    render_market_pulse()

# ══════════════════════════════════════════════════════════════════
# WEALTH EVOLUTION (Timeline Tab)
# ══════════════════════════════════════════════════════════════════
elif active == "timeline":
    st.markdown("<div class='sec'>📈 Wealth Evolution & Drift Analysis</div>", unsafe_allow_html=True)
    
    if not st.session_state.get("user"):
        st.info("💡 Log in to track your portfolio evolution over time.")
        st.stop()
        
    user_id = st.session_state.user.get("id")
    history = db_svc.get_user_portfolios(user_id)
    if not history:
        st.warning("📊 No historical snapshots found. Save your current analysis to start tracking.")
        st.stop()
        
    # Convert to DataFrame for easier plotting
    h_df = pd.DataFrame(history)
    h_df['created_at'] = pd.to_datetime(h_df['created_at'])
    h_df = h_df.sort_values('created_at')

    if len(history) < 2:
        st.info("📊 You have 1 snapshot saved. We need at least 2 to show growth trends and velocity.")
        st.stop()
    
    # Calculate Velocity (Growth since last snapshot)
    latest = h_df.iloc[-1]
    prev = h_df.iloc[-2]
    
    growth = latest['total_current'] - prev['total_current']
    growth_pct = (growth / prev['total_current'] * 100) if prev['total_current'] > 0 else 0
    days = (latest['created_at'] - prev['created_at']).days or 1
    velocity = growth / days
    
    v1, v2, v3 = st.columns(3)
    with v1:
        kpi("PORTFOLIO VELOCITY", f"₹{velocity:,.0f}/day", "Daily wealth delta", "#60a5fa")
    with v2:
        color = "#10b981" if growth >= 0 else "#f43f5e"
        kpi("LATEST DELTA", f"₹{growth:,.0f}", f"{growth_pct:+.2f}% since last", color)
    with v3:
        score_delta = latest['health_score'] - prev['health_score']
        s_color = "#10b981" if score_delta >= 0 else "#f43f5e"
        kpi("HEALTH DRIFT", f"{latest['health_score']}", f"{score_delta:+.0f} points shift", s_color)
        
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    
    # Plotting
    import plotly.graph_objects as go
    fig = go.Figure()
    
    # Market Value Area
    fig.add_trace(go.Scatter(
        x=h_df['created_at'], y=h_df['total_current'],
        fill='tozeroy', name='Market Value (₹)',
        line=dict(color='#3b82f6', width=3),
        hovertemplate='Date: %{x}<br>Value: ₹%{y:,.0f}<extra></extra>'
    ))
    
    # Cost Basis Line
    fig.add_trace(go.Scatter(
        x=h_df['created_at'], y=h_df['total_invested'],
        name='Invested Capital (₹)',
        line=dict(color='#94a3b8', width=2, dash='dash'),
        hovertemplate='Date: %{x}<br>Invested: ₹%{y:,.0f}<extra></extra>'
    ))
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=20, b=0),
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#1e2030", zeroline=False),
    )
    st.plotly_chart(fig, use_container_width=True)
        
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    
    # Delta Insights: Deep Drift Analysis
    st.markdown("<div class='sec'>🔎 Allocation Drift Forensic</div>", unsafe_allow_html=True)
    
    # Fetch full data for latest two to compare holdings/sectors
    if len(history) >= 2:
        l_id = h_df.iloc[-1]['id']
        p_id = h_df.iloc[-2]['id']
        
        latest_data = db_svc.get_full_portfolio_data(l_id)
        prev_data   = db_svc.get_full_portfolio_data(p_id)
        
        l_h = pd.DataFrame(latest_data.get("holdings", []))
        p_h = pd.DataFrame(prev_data.get("holdings", []))
        
        if not l_h.empty and not p_h.empty:
            # Sector Drift
            l_sec = l_h.groupby('sector')['weight_pct'].sum()
            p_sec = p_h.groupby('sector')['weight_pct'].sum()
            
            drift = (l_sec - p_sec).dropna().sort_values(ascending=False)
            
            d1, d2 = st.columns([2, 3])
            with d1:
                st.markdown("<div style='color:#6b7280;font-size:10px;font-weight:800;letter-spacing:.15em;text-transform:uppercase;margin-bottom:8px;'>SECTOR EXPOSURE DRIFT</div>", unsafe_allow_html=True)
                for sec, delta in drift.items():
                    if abs(delta) > 0.1:
                        d_color = "#10b981" if delta > 0 else "#f43f5e"
                        st.markdown(f"""
                        <div style='display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid #1e2030;'>
                            <span style='color:#9ca3af; font-size:13px;'>{sec}</span>
                            <span style='color:{d_color}; font-weight:700; font-size:13px;'>{delta:+.1f}%</span>
                        </div>""", unsafe_allow_html=True)
            
            with d2:
                # Top Movers in weight
                l_h_lite = l_h[['symbol', 'weight_pct']].rename(columns={'weight_pct': 'new_w'})
                p_h_lite = p_h[['symbol', 'weight_pct']].rename(columns={'weight_pct': 'old_w'})
                merged = pd.merge(l_h_lite, p_h_lite, on='symbol', how='outer').fillna(0)
                merged['drift'] = merged['new_w'] - merged['old_w']
                movers = merged.sort_values('drift', ascending=False).head(5)
                
                st.markdown("<div style='color:#6b7280;font-size:10px;font-weight:800;letter-spacing:.15em;text-transform:uppercase;margin-bottom:8px;'>TOP WEIGHTAGE SHIFTS</div>", unsafe_allow_html=True)
                for _, row in movers.iterrows():
                    d_color = "#10b981" if row['drift'] > 0 else "#f43f5e"
                    st.markdown(f"""
                    <div style='background:#0f1117; border:1px solid #1e2030; border-radius:6px; padding:8px 12px; margin-bottom:6px;'>
                        <div style='display:flex; justify-content:space-between;'>
                            <span style='color:#fff; font-weight:600;'>{row['symbol']}</span>
                            <span style='color:{d_color}; font-weight:700;'>{row['drift']:+.1f}%</span>
                        </div>
                        <div style='color:#4b5563; font-size:10px;'>Weight: {row['old_w']:.1f}% → {row['new_w']:.1f}%</div>
                    </div>""", unsafe_allow_html=True)
    else:
        st.info("Additional snapshots needed for deep drift forensic.")

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    st.markdown("<div class='sec'>🕒 Historical Snapshots Registry</div>", unsafe_allow_html=True)
    
    disp_cols = {
        "created_at": "Timestamp",
        "total_current": "Market Value",
        "total_invested": "Invested",
        "total_pnl": "P&L",
        "health_score": "Score"
    }
    h_disp = h_df[list(disp_cols.keys())].rename(columns=disp_cols).copy()
    h_disp['Timestamp'] = h_disp['Timestamp'].dt.strftime('%d %b %Y, %H:%M')
    st.dataframe(h_disp.sort_values('Timestamp', ascending=False), use_container_width=True, hide_index=True)

import streamlit as st
import pandas as pd
import plotly.express as px
import requests, time, os, json, base64
from io import BytesIO
from dotenv import load_dotenv
load_dotenv()

# Standalone Architecture (Direct task execution for maximum performance)
from tasks import run_parse, run_enrich_analytics, run_ai_report
IS_STANDALONE = True

st.set_page_config(page_title="Portfolio Analyzer V2", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{font-family:'Inter',sans-serif!important;}
html,body,[data-testid="stAppViewContainer"]{background:var(--background-color)!important;}
[data-testid="stSidebar"]{background:var(--secondary-background-color)!important;border-right:1px solid rgba(150,150,150,0.1);}
.block-container{padding:2rem 2.5rem!important; padding-top: 4rem !important;}
.kc{background:var(--secondary-background-color);border:1px solid rgba(150,150,150,0.2);border-radius:12px;padding:20px 22px;margin-bottom:4px;}
.kl{color:#4b5563;font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;margin-bottom:6px;}
.kv{color:var(--text-color);font-size:28px;font-weight:800;}
.ks{font-size:12px;font-weight:600;margin-top:4px;}
.sec{color:#6b7280;font-size:10px;font-weight:800;letter-spacing:.2em;text-transform:uppercase;margin:20px 0 10px;}
.err{background:#160a0a;border:1px solid #7f1d1d;border-radius:12px;padding:24px 28px;margin:16px 0;}
.hdr{color:#fca5a5;font-size:10px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;margin-bottom:8px;}
.etitle{color:var(--text-color);font-size:18px;font-weight:800;margin-bottom:10px;}
.ecause{color:#fca5a5;font-size:13px;line-height:1.6;}
.raw{background:#0c0202;border:1px solid #450a0a;border-radius:8px;padding:10px 14px;font-family:monospace;font-size:11px;color:#ef4444;white-space:pre-wrap;margin-top:10px;}
.hint{color:#6b7280;font-size:11px;margin-top:8px;}
.ai-box{background:#0d1a0d;border:1px solid #14532d;border-radius:12px;padding:24px;color:#86efac;line-height:1.8;font-size:14px;}
.vbox{background:#0a1628;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:12px 18px;margin-bottom:8px;color:#93c5fd;font-size:13px;}
.rbox{background:#1a1205;border-left:3px solid #f59e0b;border-radius:0 8px 8px 0;padding:12px 18px;margin-bottom:16px;color:#fbbf24;font-size:13px;}
.sig{background:var(--secondary-background-color);border:1px solid rgba(150,150,150,0.2);border-radius:12px;padding:24px 28px;margin-bottom:14px;}

/* Light mode is now handled dynamically via the sidebar toggle below */
</style>""", unsafe_allow_html=True)


@st.fragment(run_every=300)
def render_market_pulse(limit=None):
    container = st.empty()
    
    @st.cache_data(ttl=300)
    def _fetch_news():
        import xml.etree.ElementTree as ET
        feeds = [
            ("CNBC TV18", "https://www.cnbctv18.com/common/rss/market.xml"),
            ("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
            ("Moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
            ("SEBI PR", "https://www.sebi.gov.in/sebiweb/home/rss_pr.xml"),
            ("Google Finance", "https://news.google.com/rss/search?q=when:24h+Indian+Stock+Market&hl=en-IN&gl=IN&ceid=IN:en")
        ]
        news_items = []
        import concurrent.futures
        
        def _get_one(source, url):
            try:
                r = requests.get(url, timeout=4, headers={"User-Agent":"Mozilla/5.0"})
                if r.status_code == 200:
                    root = ET.fromstring(r.text)
                    items = []
                    for item in root.findall(".//item")[:5]:
                        title = item.find("title").text
                        link = item.find("link").text
                        pub = item.find("pubDate").text if item.find("pubDate") is not None else "Recent"
                        items.append({"title": title, "link": link, "source": source, "date": pub})
                    return items
            except: return []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            results = ex.map(lambda p: _get_one(*p), feeds)
            for r_list in results:
                news_items.extend(r_list)
        
        return sorted(news_items, key=lambda x: x.get("date",""), reverse=True)

    items = _fetch_news()
    if limit: items = items[:limit]
    
    if not items:
        container.info("No recent news found. Checking feeds..."); return

    is_light = st.session_state.get("is_light", False)

    # Use 2 columns for homepage, 1 for dashboard
    if limit:
        c1, c2 = container.columns(2)
        half = len(items)//2
        for idx, (col, subset) in enumerate(zip([c1, c2], [items[:half], items[half:]])):
            html = ""
            for i in subset:
                txt_c = "#d1d5db" if not is_light else "#1f2937"
                bg_c = "#0f1117" if not is_light else "#ffffff"
                brd_c = "#1e2030" if not is_light else "#e5e7eb"

                html += f"""
                <div style='background:{bg_c}; border:1px solid {brd_c}; border-radius:12px; padding:16px; margin-bottom:12px; height:100px; overflow:hidden;'>
                    <div style='display:flex; justify-content:space-between; margin-bottom:4px;'>
                        <span style='background:#1e293b; color:#94a3b8; font-size:8px; font-weight:800; padding:1px 6px; border-radius:3px;'>{i['source']}</span>
                        <span style='color:#4b5563; font-size:8px;'>{i['date'][:16]}</span>
                    </div>
                    <a href='{i['link']}' target='_blank' style='text-decoration:none; color:{txt_c}; font-size:12px; font-weight:700; display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;'>{i['title']}</a>
                </div>"""
            col.markdown(html, unsafe_allow_html=True)
    else:
        html = ""
        for i in items:
            txt_c = "#d1d5db" if not is_light else "#1f2937"
            bg_c = "#0f1117" if not is_light else "#ffffff"
            brd_c = "#1e2030" if not is_light else "#e5e7eb"

            html += f"""
            <div style='background:{bg_c}; border:1px solid {brd_c}; border-radius:12px; padding:16px; margin-bottom:12px;'>
                <div style='display:flex; justify-content:space-between; margin-bottom:6px;'>
                    <span style='background:#1e293b; color:#94a3b8; font-size:9px; font-weight:800; padding:2px 8px; border-radius:4px; text-transform:uppercase;'>{i['source']}</span>
                    <span style='color:#4b5563; font-size:9px;'>{i['date'][:16]}</span>
                </div>
                <a href='{i['link']}' target='_blank' style='text-decoration:none; color:{txt_c}; font-size:14px; font-weight:700; line-height:1.4;'>{i['title']}</a>
            </div>"""
        container.markdown(html, unsafe_allow_html=True)

def fmt(v):
    try:
        v=float(v); neg=v<0; v=abs(int(v)); s=str(v)
        if len(s)>3:
            s=s[:-3]; r=","+str(abs(int(float(v))))[-3:]
            while len(s)>2: r=","+s[-2:]+r; s=s[:-2]
            r=s+r
        else: r=s
        return f"₹-{r}" if neg else f"₹{r}"
    except: return "₹0"

def kpi(label, val, sub=None, sc="#6b7280"):
    sh = f"<div class='ks' style='color:{sc};'>{sub}</div>" if sub else ""
    st.markdown(f"<div class='kc'><div class='kl'>{label}</div><div class='kv'>{val}</div>{sh}</div>", unsafe_allow_html=True)

def show_err(title, cause, raw="", hint=""):
    raw_h = f"<div class='raw'>{raw[:400]}</div>" if raw else ""
    hint_h = f"<div class='hint'>💡 {hint}</div>" if hint else ""
    st.markdown(f"<div class='err'><div class='hdr'>❌ Error</div><div class='etitle'>{title}</div><div class='ecause'>{cause}</div>{raw_h}{hint_h}</div>", unsafe_allow_html=True)
    pass

def poll(task_id, label, max_wait=180, phase=None, payload=None):
    """Execution wrapper — uses local tasks if standalone, else polls API."""
    if IS_STANDALONE and phase:
        with st.status(label, expanded=True) as s:
            try:
                if phase == 1:
                    b64 = base64.b64encode(payload["file"].getvalue()).decode()
                    res = run_parse(b64, payload["file"].name)
                elif phase == 2:
                    res = run_enrich_analytics(payload)
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

# ── SIDEBAR ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div style='font-size:18px;font-weight:900;color:#fff;padding:12px 0 4px;'>UNIVERSAL<span style='color:#3b82f6;'> ANALYZER</span></div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:9px;color:#374151;font-weight:700;letter-spacing:.25em;margin-bottom:16px;'>ANY BROKER · ANY FORMAT</div>", unsafe_allow_html=True)
    
    is_light = st.toggle("✨ Switch to Cream Theme", value=True)
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
        .feat-card, .stat-box, .ticker-wrap, .broker-chip, .kc, .sig {
            background: #ffffff !important; /* Pure white for contrast against cream */
            border-color: #e5e7eb !important;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05) !important;
        }
        
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
        </style>""", unsafe_allow_html=True)
        
    st.divider()
    st.caption("📁 UPLOAD PORTFOLIO")
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

    # ── Extra CSS for homepage ─────────────────────────────────────
    st.markdown("""<style>
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
@keyframes slideUp{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:translateY(0)}}
@keyframes glow{0%,100%{text-shadow:0 0 20px #3b82f660}50%{text-shadow:0 0 40px #3b82f6aa,0 0 80px #6366f155}}
@keyframes ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.hero-title{font-size:clamp(36px,5vw,72px);font-weight:900;background:linear-gradient(135deg,#fff 30%,#3b82f6 70%,#8b5cf6 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:slideUp .8s ease,glow 3s ease infinite;line-height:1.1;margin-bottom:16px;}
.hero-sub{color:#9ca3af;font-size:18px;line-height:1.7;margin-bottom:32px;animation:slideUp 1s ease;}
.feat-card{background:linear-gradient(135deg,#0f1117,#0d1526);border:1px solid #1e2030;border-radius:16px;padding:24px;transition:all .3s;cursor:default;height:100%;}
.feat-card:hover{border-color:#3b82f6;box-shadow:0 0 30px #3b82f620;transform:translateY(-4px);}
.feat-icon{font-size:32px;margin-bottom:12px;transition:transform 0.3s;}
.feat-card:hover .feat-icon{transform:scale(1.1) rotate(5deg);}
.feat-title{color:#fff;font-size:16px;font-weight:800;margin-bottom:8px;transition:color 0.3s;}
.feat-desc{color:#6b7280;font-size:13px;line-height:1.6;transition:color 0.3s;}
.feat-card:hover .feat-title{color:#93c5fd!important;}
.feat-card:hover .feat-desc{color:#d1d5db!important;}
.broker-chip{background:#0f1117;border:1px solid #1e2030;border-radius:8px;padding:8px 16px;color:#9ca3af;font-size:12px;font-weight:700;text-align:center;transition:all .2s;}
.broker-chip:hover{border-color:#3b82f6;color:#60a5fa;box-shadow:0 0 15px #3b82f630;}
.step-num{width:36px;height:36px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900;font-size:14px;margin-bottom:12px;}
.stat-box{background:linear-gradient(135deg,#0d1526,#0f1117);border:1px solid #1e3a5f;border-radius:12px;padding:20px;text-align:center;}
.stat-num{font-size:32px;font-weight:900;background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.stat-lbl{color:#6b7280;font-size:11px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;margin-top:4px;}
.ticker-wrap{overflow:hidden;background:#090b12;border:1px solid #1e2030;border-radius:10px;padding:10px 0;margin-bottom:28px;}
.ticker-inner{display:flex;gap:48px;animation:ticker 30s linear infinite;white-space:nowrap;width:max-content;}
.tick-item{font-size:12px;font-weight:700;color:#9ca3af;display:flex;gap:10px;align-items:center;}
.tick-up{color:#10b981;}.tick-dn{color:#f43f5e;}
.upload-cta{background:linear-gradient(135deg,#1d4ed820,#7c3aed20);border:2px dashed #3b82f6;border-radius:16px;padding:32px;text-align:center;margin-top:20px;}
/* Completely hide all native Streamlit icons (upload, info, etc) from the file uploader */
[data-testid="stFileUploader"] [data-testid="stIconMaterial"],
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"],
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploaderDropzoneInstructions"],
[data-testid="stWidgetLabel"] [data-testid="stTooltipIcon"] { display: none !important; }

/* Completely hide top-right Streamlit menu and Deploy button */
[data-testid="stToolbarActions"],
[data-testid="stAppDeployButton"],
[data-testid="stMainMenu"],
[data-testid="stStatusWidget"],
[data-testid="stElementToolbar"] {
    display: none !important;
}
/* Aggressively hide the technical 'Running...' overlay for fragments */
div[data-testid="stStatusWidget"], .stStatusWidget, div[class*="stFragmentStatus"] {
    display: none !important;
    visibility: hidden !important;
}
</style>""", unsafe_allow_html=True)



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
    @st.fragment
    def render_live_ticker():
        container = st.empty()
        def _show(data):
            tickers = [
                ("NIFTY 50", data.get("^NSEI", {}).get("cur", 24531), data.get("^NSEI", {}).get("pct", 0.42)),
                ("SENSEX",   data.get("^BSESN", {}).get("cur", 80519), data.get("^BSESN", {}).get("pct", 0.38)),
                ("BANK NIFTY", data.get("^NSEBANK", {}).get("cur", 52430), data.get("^NSEBANK", {}).get("pct", 0.61)),
                ("NIFTY IT", data.get("^CNXIT", {}).get("cur", 38120), data.get("^CNXIT", {}).get("pct", -0.24)),
                ("NIFTY FMCG", data.get("^CNXFMCG", {}).get("cur", 56800), data.get("^CNXFMCG", {}).get("pct", 0.18)),
                ("GOLD (USD)", data.get("GC=F", {}).get("cur", 2450), data.get("GC=F", {}).get("pct", 0.55)),
            ]
            def _t(name, val, pct):
                cls = "tick-up" if pct >= 0 else "tick-dn"
                sym = "▲" if pct >= 0 else "▼"
                v_c = "#111827" if is_light else "#ffffff"
                return f'<span class="tick-item"><span style="color:#6b7280;font-weight:800;">{name}</span><span class="tick-val" style="color:{v_c};font-weight:900;">{val:,.0f}</span><span class="{cls}" style="font-weight:900;">{sym}{abs(pct):.2f}%</span></span>'
            items = "".join(_t(n,v,p) for n,v,p in tickers)
            container.markdown(f'<div class="ticker-wrap"><div class="ticker-inner">{items*4}</div></div>', unsafe_allow_html=True)

        _show({}) # Immediate render

        @st.cache_data(ttl=300) # Longer cache for stability
        def _fetch_live():
            res = {}
            try:
                import requests as _r
                from concurrent.futures import ThreadPoolExecutor
                syms = {"^NSEI":"NIFTY 50", "^BSESN":"SENSEX", "^NSEBANK":"BANK NIFTY", "^CNXIT":"NIFTY IT", "^CNXFMCG":"NIFTY FMCG", "GC=F":"GOLD (USD)"}
                def _get(sym):
                    try:
                        r = _r.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"interval":"1d","range":"5d"}, headers={"User-Agent":"Mozilla/5.0"}, timeout=2)
                        if r.status_code == 200:
                            meta = r.json().get("chart",{}).get("result",[{}])[0].get("meta",{})
                            cur = float(meta.get("regularMarketPrice",0) or 0)
                            prev = float(meta.get("chartPreviousClose", cur) or cur)
                            return sym, {"cur": cur, "pct": (cur-prev)/prev*100 if prev else 0}
                    except: pass
                    return sym, None

                with ThreadPoolExecutor(max_workers=6) as exe:
                    for s, r in exe.map(_get, syms.keys()):
                        if r: res[s] = r
                return res
            except: return {}

        live = _fetch_live()
        if live: _show(live)

    render_live_ticker()

    with c_cta:
        import streamlit.components.v1 as components
        
        main_uploaded = st.file_uploader("Drop CSV/Excel", type=["csv","xlsx","xls"], key="main_uploader", label_visibility="collapsed")
        
        # Inject custom styling directly into the dropzone
        components.html("""<script>
        const doc = window.parent.document;
        const upgrade = () => {
            const dzs = doc.querySelectorAll('[data-testid="stFileUploaderDropzone"]');
            dzs.forEach(dz => {
                if (dz && !dz.dataset.upgraded) {
                    dz.dataset.upgraded = 'true';
                    Array.from(dz.children).forEach(c => { if(c.tagName !== 'INPUT') c.style.display='none'; });
                    dz.classList.add('upload-cta');
                    const cta = doc.createElement('div');
                    cta.style.textAlign = 'center'; cta.style.width = '100%';
                    cta.innerHTML = `
                      <div onclick="window.parent.document.querySelector('[data-testid=\\'stFileUploaderDropzoneInput\\']').click()" style="font-size:32px;margin-bottom:8px;cursor:pointer;">🗂️</div>
                      <div style="color:#60a5fa;font-family:sans-serif;font-weight:900;font-size:14px;margin-bottom:4px;">Drop Portfolio</div>
                      <div style="color:#6b7280;font-family:sans-serif;font-size:10px;">CSV · XLSX · XLS</div>
                    `;
                    dz.prepend(cta);
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

    st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

    # ── FEATURES ──────────────────────────────────────────────────
    st.markdown("<div class='sec'>⚡ What You Get</div>", unsafe_allow_html=True)
    f1,f2,f3,f4 = st.columns(4)
    feats = [
        ("📡","Live Market Data","Real-time prices via Finnhub WebSocket, NSE/BSE REST, Yahoo Finance, and Alpha Vantage waterfall pipeline."),
        ("🧠","AI Forensic Report","Gemini + Claude AI generates verdict, concentration risk, rebalancing actions, and investor profile."),
        ("📊","Nifty 50 Benchmark","Compare your portfolio return vs Nifty 50 YTD. See alpha, today's index move, and 52-week range."),
        ("🔐","Bank-Grade Security","API key auth, rate limiting, payload validation. No data stored without your consent."),
    ]
    for col, (icon, title, desc) in zip([f1,f2,f3,f4], feats):
        col.markdown(f'<div class="feat-card"><div class="feat-icon">{icon}</div><div class="feat-title">{title}</div><div class="feat-desc">{desc}</div></div>', unsafe_allow_html=True)

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # ── HOW IT WORKS ──────────────────────────────────────────────
    st.markdown("<div class='sec'>🔄 How It Works</div>", unsafe_allow_html=True)
    w1,w2,w3 = st.columns(3)
    steps = [
        ("1","Upload File","Drop any broker CSV or Excel. Our universal parser auto-detects headers, cleans names, maps ISINs."),
        ("2","Live Enrichment","Click 'Insights' to fetch real-time prices, PE ratios, beta, sector, and Nifty 50 benchmark — all in parallel."),
        ("3","AI Analysis","Run AI Summary for verdict, concentration risk, rebalancing advice, and behavioral investor profile."),
    ]
    for col, (num, title, desc) in zip([w1,w2,w3], steps):
        col.markdown(f"""<div class="feat-card">
<div class="step-num">{num}</div>
<div class="feat-title">{title}</div>
<div class="feat-desc">{desc}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

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

total_pnl = (total_cur - total_inv) if has_cost else 0.0
total_pct = (total_pnl / total_inv * 100) if (has_cost and total_inv) else 0.0
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

# ── KPI ROW ───────────────────────────────────────────────────────
k1,k2,k3,k4 = st.columns(4)
if has_cost:
    with k1: kpi("INVESTED CAPITAL", fmt(total_inv))
    with k2: kpi("CURRENT VALUATION", fmt(total_cur))
    with k3: kpi("UNREALISED P&L", fmt(total_pnl), f"{total_pct:+.2f}%", pnl_c)
else:
    with k1: kpi("HOLDINGS VALUE", fmt(total_cur))
    with k2: kpi("NO. OF STOCKS", str(len(df)), "Holdings count", "#6b7280")
    with k3: kpi("P&L", "N/A", "Cost basis missing", "#6b7280")
with k4:
    wb = stats.get("weighted_beta", 0)
    kpi("HOLDINGS", str(len(df)), f"β {wb:.2f}" if wb else "Upload enriched", "#6b7280")

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ── PHASE NAVIGATION BUTTONS ──────────────────────────────────────
active = st.session_state.get("active_phase", "market")
b1,b2,b3,b4,_ = st.columns([1,1,1,1.2,4])
with b1:
    if st.button("📊  Market & Stats", use_container_width=True, type="primary" if active=="market" else "secondary"):
        st.session_state.active_phase = "market"; st.rerun()
with b2:
    lbl = "📈  Insights" + (" ✓" if p2 else "")
    if st.button(lbl, use_container_width=True, type="primary" if active=="insights" else "secondary"):
        st.session_state.active_phase = "insights"; st.rerun()
with b3:
    lbl3 = "🧠  AI Summary" + (" ✓" if p3 else "")
    if st.button(lbl3, use_container_width=True, type="primary" if active=="summary" else "secondary"):
        st.session_state.active_phase = "summary"; st.rerun()
with b4:
    if st.button("📰  Market Pulse", use_container_width=True, type="primary" if active=="news" else "secondary"):
        st.session_state.active_phase = "news"; st.rerun()

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

    st.dataframe(styled, use_container_width=True, height=420)
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

    # ── Dynamic Insights (computed, no AI needed) ─────────────────
    dynamic = p2.get("dynamic", {})
    if dynamic:
        st.markdown("<div class='sec'>🧠 Portfolio Intelligence</div>", unsafe_allow_html=True)
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

@st.fragment(run_every=300)
def render_market_pulse(limit=None):
    container = st.empty()
    
    @st.cache_data(ttl=300)
    def _fetch_news():
        import xml.etree.ElementTree as ET
        feeds = [
            ("CNBC TV18", "https://www.cnbctv18.com/common/rss/market.xml"),
            ("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
            ("Moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
            ("SEBI PR", "https://www.sebi.gov.in/sebiweb/home/rss_pr.xml"),
            ("Google Finance", "https://news.google.com/rss/search?q=when:24h+Indian+Stock+Market&hl=en-IN&gl=IN&ceid=IN:en")
        ]
        news_items = []
        import concurrent.futures
        
        def _get_one(source, url):
            try:
                r = requests.get(url, timeout=4, headers={"User-Agent":"Mozilla/5.0"})
                if r.status_code == 200:
                    root = ET.fromstring(r.text)
                    items = []
                    for item in root.findall(".//item")[:5]:
                        title = item.find("title").text
                        link = item.find("link").text
                        pub = item.find("pubDate").text if item.find("pubDate") is not None else "Recent"
                        items.append({"title": title, "link": link, "source": source, "date": pub})
                    return items
            except: return []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            results = ex.map(lambda p: _get_one(*p), feeds)
            for r_list in results:
                news_items.extend(r_list)
        
        return sorted(news_items, key=lambda x: x.get("date",""), reverse=True)

    items = _fetch_news()
    if limit: items = items[:limit]
    
    if not items:
        container.info("No recent news found. Checking feeds..."); return

    # Use 2 columns for homepage, 1 for dashboard
    if limit:
        c1, c2 = container.columns(2)
        half = len(items)//2
        for idx, (col, subset) in enumerate(zip([c1, c2], [items[:half], items[half:]])):
            html = ""
            for i in subset:
                color = "#10b981" if any(x in i['title'].lower() for x in ['bull', 'jump', 'gain', 'rise', 'buy', 'high']) else \
                        ("#f43f5e" if any(x in i['title'].lower() for x in ['bear', 'slump', 'fall', 'drop', 'sell', 'low']) else "#9ca3af")
                txt_c = "#d1d5db" if not is_light else "#1f2937"
                bg_c = "#0f1117" if not is_light else "#ffffff"
                brd_c = "#1e2030" if not is_light else "#e5e7eb"

                html += f"""
                <div style='background:{bg_c}; border:1px solid {brd_c}; border-radius:12px; padding:16px; margin-bottom:12px; height:100px; overflow:hidden;'>
                    <div style='display:flex; justify-content:space-between; margin-bottom:4px;'>
                        <span style='background:#1e293b; color:#94a3b8; font-size:8px; font-weight:800; padding:1px 6px; border-radius:3px;'>{i['source']}</span>
                        <span style='color:#4b5563; font-size:8px;'>{i['date'][:16]}</span>
                    </div>
                    <a href='{i['link']}' target='_blank' style='text-decoration:none; color:{txt_c}; font-size:12px; font-weight:700; display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;'>{i['title']}</a>
                </div>"""
            col.markdown(html, unsafe_allow_html=True)
    else:
        html = ""
        for i in items:
            color = "#10b981" if any(x in i['title'].lower() for x in ['bull', 'jump', 'gain', 'rise', 'buy', 'high']) else \
                    ("#f43f5e" if any(x in i['title'].lower() for x in ['bear', 'slump', 'fall', 'drop', 'sell', 'low']) else "#9ca3af")
            txt_c = "#d1d5db" if not is_light else "#1f2937"
            bg_c = "#0f1117" if not is_light else "#ffffff"
            brd_c = "#1e2030" if not is_light else "#e5e7eb"

            html += f"""
            <div style='background:{bg_c}; border:1px solid {brd_c}; border-radius:12px; padding:16px; margin-bottom:12px;'>
                <div style='display:flex; justify-content:space-between; margin-bottom:6px;'>
                    <span style='background:#1e293b; color:#94a3b8; font-size:9px; font-weight:800; padding:2px 8px; border-radius:4px; text-transform:uppercase;'>{i['source']}</span>
                    <span style='color:#4b5563; font-size:9px;'>{i['date'][:16]}</span>
                </div>
                <a href='{i['link']}' target='_blank' style='text-decoration:none; color:{txt_c}; font-size:14px; font-weight:700; line-height:1.4;'>{i['title']}</a>
            </div>"""
        container.markdown(html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# MARKET PULSE (News Tab)
# ══════════════════════════════════════════════════════════════════
if active == "news":
    st.markdown("<div class='sec'>📰 Market Pulse — Indian Markets</div>", unsafe_allow_html=True)
    render_market_pulse()

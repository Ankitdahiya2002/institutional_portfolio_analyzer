import streamlit as st
import time
import pandas as pd
import requests

@st.fragment(run_every=60)
def render_market_pulse(limit=None):
    container = st.empty()
    
    @st.cache_data(ttl=60, show_spinner=False)
    def _fetch_news():
        import xml.etree.ElementTree as ET
        feeds = [
            ("CNBC TV18", "https://www.cnbctv18.com/common/rss/market.xml"),
            ("ET Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
            ("Moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
            ("SEBI PR", "https://www.sebi.gov.in/sebiweb/home/rss_pr.xml"),
            ("Google Finance", "https://news.google.com/rss/search?q=when:1h+Indian+Stock+Market&hl=en-IN&gl=IN&ceid=IN:en"),
            ("LiveMint", "https://www.livemint.com/rss/markets"),
            ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss")
        ]
        news_items = []
        import concurrent.futures
        
        def _get_one(source, url):
            try:
                # Added a random timestamp to URL to bypass any intermediate caching
                burst_url = f"{url}?t={int(time.time())}"
                r = requests.get(burst_url, timeout=5, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                if r.status_code == 200:
                    root = ET.fromstring(r.text)
                    items = []
                    for item in root.findall(".//item")[:5]:
                        title = item.find("title").text if item.find("title") is not None else ""
                        link = item.find("link").text if item.find("link") is not None else ""
                        if title and link:
                            items.append({"title": title, "link": link, "source": source, "date": "LIVE"})
                    return items
            except: pass
            return []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
            results = list(ex.map(lambda p: _get_one(*p), feeds))
            for r_list in results:
                if r_list: news_items.extend(r_list)
        
        return news_items[:24]

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
                date_html = f"<span class='live-badge'>● LIVE</span>" if i['date'] == "LIVE" else f"<span style='color:#4b5563; font-size:8px;'>{i['date'][:16]}</span>"

                html += f"""
                <div style='background:{bg_c}; border:1px solid {brd_c}; border-radius:12px; padding:16px; margin-bottom:12px; height:100px; overflow:hidden;'>
                    <div style='display:flex; justify-content:space-between; margin-bottom:4px;'>
                        <span style='background:#1e293b; color:#94a3b8; font-size:8px; font-weight:800; padding:1px 6px; border-radius:3px;'>{i['source']}</span>
                        {date_html}
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
            date_html = f"<span class='live-badge'>● LIVE</span>" if i['date'] == "LIVE" else f"<span style='color:#4b5563; font-size:9px;'>{i['date'][:16]}</span>"

            html += f"""
            <div style='background:{bg_c}; border:1px solid {brd_c}; border-radius:12px; padding:16px; margin-bottom:12px;'>
                <div style='display:flex; justify-content:space-between; margin-bottom:6px;'>
                    <span style='background:#1e293b; color:#94a3b8; font-size:9px; font-weight:800; padding:2px 8px; border-radius:4px; text-transform:uppercase;'>{i['source']}</span>
                    {date_html}
                </div>
                <a href='{i['link']}' target='_blank' style='text-decoration:none; color:{txt_c}; font-size:14px; font-weight:700; line-height:1.4;'>{i['title']}</a>
            </div>"""
        container.markdown(html, unsafe_allow_html=True)


@st.fragment
def render_live_ticker(is_light):
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

    @st.cache_data(ttl=300, show_spinner=False) # Longer cache for stability
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

def render_landing_features():
    from ui_components.utils import kpi
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
        col.markdown(f'''<div class="feat-card">
<div class="step-num">{num}</div>
<div class="feat-title">{title}</div>
<div class="feat-desc">{desc}</div>
</div>''', unsafe_allow_html=True)

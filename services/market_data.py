"""
Hybrid Market Data Pipeline
============================
Tier 1 : Finnhub WebSocket  (real-time, <100ms)
Tier 2 : NSE / BSE REST     (Indian market, ~500ms)
Tier 3 : Yahoo Finance      (reliable, free, ~1s)
Tier 4 : Alpha Vantage      (indicators + price, ~2s)
Tier 5 : Finnhub REST       (final fallback)

Cache   : Thread-safe in-memory TTL dict (no Redis needed)
"""

import os, re, time, json, threading, warnings
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv()

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════
# TTL CACHE — replaces Redis, thread-safe
# ═══════════════════════════════════════════════════════════════════
class TTLCache:
    def __init__(self):
        self._store: dict = {}
        self._lock  = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._store.get(key)
            if entry and time.time() < entry["exp"]:
                return entry["val"]
            return None

    def set(self, key, val, ttl=300):
        with self._lock:
            self._store[key] = {"val": val, "exp": time.time() + ttl}

    def delete(self, key):
        with self._lock:
            self._store.pop(key, None)

    def cleanup(self):
        now = time.time()
        with self._lock:
            stale = [k for k, v in self._store.items() if now >= v["exp"]]
            for k in stale:
                del self._store[k]

_cache = TTLCache()

# Periodic cleanup thread
def _cache_cleaner():
    while True:
        time.sleep(600)
        _cache.cleanup()

threading.Thread(target=_cache_cleaner, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# TIER 1 — FINNHUB WEBSOCKET  (real-time push cache)
# ═══════════════════════════════════════════════════════════════════
class FinnhubWS:
    """
    Maintains a persistent WebSocket connection to Finnhub.
    Subscribed tickers get price updates pushed to TTLCache.
    All other tiers read from this cache first.
    """
    WS_URL = "wss://ws.finnhub.io"

    def __init__(self, key_provider):
        self.key_provider = key_provider
        self._ws         = None
        self._connected  = False
        self._subscribed = set()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        current_key = self.key_provider()
        if not current_key: return

        try:
            import websocket
            def on_message(ws, msg):
                data = json.loads(msg)
                if data.get("type") == "trade":
                    for trade in data.get("data", []):
                        sym = trade.get("s", "")
                        px  = trade.get("p", 0)
                        if sym and px:
                            _cache.set(f"ws:{sym}", {"price": float(px), "source": "FinnhubWS"}, ttl=30)

            def on_open(ws):
                self._connected = True
                print("[FinnhubWS] Connected")

            def on_error(ws, err):
                global _key_idx
                if "401" in str(err):
                    _key_idx += 1 # Rotate on auth error
                self._connected = False

            def on_close(ws, *_):
                self._connected = False
                time.sleep(15)
                self._run() # Retry with fresh key

            self._ws = websocket.WebSocketApp(
                f"{self.WS_URL}?token={current_key}",
                on_message=on_message, on_error=on_error,
                on_open=on_open, on_close=on_close
            )
            self._ws.run_forever()
        except Exception:
            time.sleep(15)
            self._run()

    def subscribe(self, symbols: list[str]):
        """Subscribe to a list of ticker symbols."""
        if not self._ws or not self._connected:
            return
        for sym in symbols:
            if sym not in self._subscribed:
                self._ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
                self._subscribed.add(sym)

    def get_price(self, symbol: str) -> float | None:
        cached = _cache.get(f"ws:{symbol}")
        return cached["price"] if cached else None


_FINNHUB_KEYS = [
    "d6gq57pr01qg85gvlda0",
    "d6gq57pr01qg85gvldag",
    "d7rhcapr01qgahvdl2sg",
    "d7rhcapr01qgahvdl2t0"
]
_key_idx = 0

def _get_fh_key():
    return _FINNHUB_KEYS[_key_idx % len(_FINNHUB_KEYS)]

_finnhub_ws = FinnhubWS(_get_fh_key)


# ═══════════════════════════════════════════════════════════════════
# TIER 2 — NSE / BSE REST  (Indian market)
# ═══════════════════════════════════════════════════════════════════
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
}
_NSE_SESSION = None

def _get_nse_session():
    global _NSE_SESSION
    if _NSE_SESSION is None:
        import requests
        s = requests.Session()
        try:
            s.get("https://www.nseindia.com", headers=_NSE_HEADERS, timeout=5)
        except Exception:
            pass
        _NSE_SESSION = s
    return _NSE_SESSION

def fetch_nse(symbol: str) -> dict | None:
    """Fetch live quote from NSE India."""
    cache_key = f"nse:{symbol}"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    clean = re.sub(r'\.(NS|BO)$', '', symbol.upper())
    try:
        import requests
        s   = _get_nse_session()
        url = f"https://www.nseindia.com/api/quote-equity?symbol={clean}"
        r   = s.get(url, headers=_NSE_HEADERS, timeout=10)
        if r.status_code == 200:
            d   = r.json()
            pd_ = d.get("priceInfo", {})
            ltp = float(pd_.get("lastPrice", 0) or 0)
            if ltp > 0:
                result = {
                    "price":  ltp,
                    "open":   float(pd_.get("open", 0) or 0),
                    "high":   float(pd_.get("intraDayHighLow", {}).get("max", 0) or 0),
                    "low":    float(pd_.get("intraDayHighLow", {}).get("min", 0) or 0),
                    "pct_chg": float(pd_.get("pChange", 0) or 0),
                    "volume": float(d.get("marketDeptOrderBook", {}).get("totalBuyQuantity", 0) or 0),
                    "source": "NSE",
                    "sector": d.get("metadata", {}).get("industry", "Unknown"),
                    "pe":     float(d.get("metadata", {}).get("pdSymbolPe", 0) or 0),
                }
                _cache.set(cache_key, result, ttl=60)
                return result
    except Exception as e:
        print(f"[NSE] {symbol}: {e}")
    return None


def fetch_bse(isin: str) -> dict | None:
    """Fetch live quote from BSE India using ISIN."""
    if not isin or len(isin) < 12:
        return None
    cache_key = f"bse:{isin}"
    cached = _cache.get(cache_key)
    if cached:
        return cached
    try:
        import requests
        url = f"https://api.bseindia.com/BseIndiaAPI/api/ComHeader/w?quotetype=EQ&scripcode=&isinno={isin}"
        r   = requests.get(url, timeout=10,
                           headers={"User-Agent": "Mozilla/5.0",
                                    "Referer": "https://www.bseindia.com"})
        if r.status_code == 200 and r.text.strip():
            try:
                d   = r.json()
                ltp = float(d.get("CurrRate", 0) or 0)
                if ltp > 0:
                    result = {
                        "price":   ltp,
                        "pct_chg": float(d.get("Chg_percent", 0) or 0),
                        "sector":  d.get("INDUSTRY", "Unknown"),
                        "pe":      float(d.get("PE", 0) or 0),
                        "source":  "BSE",
                    }
                    _cache.set(cache_key, result, ttl=60)
                    return result
            except:
                return None
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════
# TIER 3 — YAHOO FINANCE REST  (reliable fallback)
# ═══════════════════════════════════════════════════════════════════
def fetch_yahoo(symbol: str) -> dict | None:
    cache_key = f"yf:{symbol}"
    cached = _cache.get(cache_key)
    if cached:
        return cached
    try:
        import requests
        for base in ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]:
            r = requests.get(
                f"{base}/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "1d"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=5,
            )
            if r.status_code == 200:
                res_data = r.json()
                if not res_data.get("chart", {}).get("result"): continue
                meta = res_data["chart"]["result"][0]["meta"]
                ltp  = float(meta.get("regularMarketPrice") or meta.get("previousClose") or 0)
                if ltp > 0:
                    result = {
                        "price":    ltp,
                        "pe":       float(meta.get("trailingPE", 0) or 0),
                        "beta":     float(meta.get("beta", 1.0) or 1.0),
                        "mkt_cap":  float(meta.get("marketCap", 0) or 0),
                        "sector":   "Unknown",
                        "source":   "Yahoo",
                    }
                    # Try to get sector from quoteSummary if Unknown
                    meta_res = fetch_yahoo_metadata(symbol)
                    if meta_res.get("sector") != "Unknown":
                        result["sector"] = meta_res["sector"]
                    
                    _cache.set(cache_key, result, ttl=120)
                    return result
    except Exception as e:
        print(f"[Yahoo] {symbol}: {e}")
    return None

def fetch_yahoo_metadata(symbol: str) -> dict:
    """Fetch sector and industry from Yahoo Finance quoteSummary."""
    cache_key = f"yf_meta:{symbol}"
    cached = _cache.get(cache_key)
    if cached: return cached
    try:
        import requests
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=assetProfile"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if r.status_code == 200:
            res_data = r.json()
            profile = res_data.get("quoteSummary", {}).get("result", [{}])[0].get("assetProfile", {})
            res = {
                "sector": profile.get("sector", profile.get("industry", "Unknown")),
                "industry": profile.get("industry", "Unknown")
            }
            if res["sector"] != "Unknown":
                _cache.set(cache_key, res, ttl=86400)
            return res
    except: pass
    return {"sector": "Unknown", "industry": "Unknown"}


# ═══════════════════════════════════════════════════════════════════
# TIER 4 — ALPHA VANTAGE  (indicators + price)
# ═══════════════════════════════════════════════════════════════════
_AV_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")

def fetch_alpha_vantage(symbol: str) -> dict | None:
    if not _AV_KEY:
        return None
    cache_key = f"av:{symbol}"
    cached = _cache.get(cache_key)
    if cached:
        return cached
    try:
        import requests
        # Quote endpoint
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": _AV_KEY},
            timeout=8,
        )
        if r.status_code == 200:
            q   = r.json().get("Global Quote", {})
            ltp = float(q.get("05. price", 0) or 0)
            if ltp > 0:
                result = {
                    "price":    ltp,
                    "pct_chg":  float(q.get("10. change percent", "0%").strip("%") or 0),
                    "volume":   float(q.get("06. volume", 0) or 0),
                    "source":   "AlphaVantage",
                    "pe":       0.0,
                    "beta":     1.0,
                    "mkt_cap":  0.0,
                    "sector":   "Unknown",
                }
                _cache.set(cache_key, result, ttl=300)
                return result
    except Exception as e:
        print(f"[AlphaVantage] {symbol}: {e}")
    return None


def fetch_av_indicators(symbol: str) -> dict:
    """Fetch RSI + MACD from Alpha Vantage. Cached 1hr."""
    if not _AV_KEY:
        return {}
    cache_key = f"av_ind:{symbol}"
    cached = _cache.get(cache_key)
    if cached:
        return cached
    indicators = {}
    try:
        import requests
        for fn, key in [("RSI", "Technical Analysis: RSI"),
                        ("MACD", "Technical Analysis: MACD")]:
            r = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": fn, "symbol": symbol, "interval": "daily",
                        "time_period": 14, "series_type": "close", "apikey": _AV_KEY},
                timeout=8,
            )
            if r.status_code == 200:
                data = r.json().get(key, {})
                latest_date = max(data.keys()) if data else None
                if latest_date:
                    indicators[fn.lower()] = {
                        k: float(v) for k, v in data[latest_date].items()
                    }
        _cache.set(cache_key, indicators, ttl=3600)
    except Exception as e:
        print(f"[AV Indicators] {symbol}: {e}")
    return indicators


# ═══════════════════════════════════════════════════════════════════
# TIER 5 — FINNHUB REST  (final fallback)
# ═══════════════════════════════════════════════════════════════════
def fetch_finnhub(symbol: str) -> dict | None:
    if not _FINNHUB_KEYS:
        return None
    cache_key = f"fh:{symbol}"
    cached = _cache.get(cache_key)
    if cached:
        return cached
    def _do_fetch(sym, retry=True):
        try:
            import requests
            r = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": sym, "token": _get_fh_key()},
                timeout=5,
            )
            if r.status_code == 429 and retry:
                global _key_idx
                _key_idx += 1 # Rotate
                return _do_fetch(sym, retry=False) # Instant retry with new key
            
            if r.status_code == 200:
                d   = r.json()
                ltp = float(d.get("c", 0) or 0)
                if ltp > 0:
                    return {
                        "price":   ltp,
                        "open":    float(d.get("o", 0)),
                        "high":    float(d.get("h", 0)),
                        "low":     float(d.get("l", 0)),
                        "pct_chg": float(d.get("dp", 0)),
                        "source":  "Finnhub",
                        "pe":      0.0, "beta": 1.0, "mkt_cap": 0.0, "sector": "Unknown",
                    }
        except Exception:
            pass
        return None

    result = _do_fetch(symbol)
    if result:
        _cache.set(cache_key, result, ttl=60)
    return result


# ═══════════════════════════════════════════════════════════════════
# TICKER RESOLVER — symbol candidates from stock name
# ═══════════════════════════════════════════════════════════════════
NSE_OVERRIDES = {
    "SHILCHAR": "SHILCHAR.NS", "CAPLIN": "CAPLIPOINT.NS",
    "HDFC": "HDFCBANK.NS",     "SBI": "SBIN.NS",
    "RELIANCE": "RELIANCE.NS", "INFOSYS": "INFY.NS",
    "ICICI": "ICICIBANK.NS",   "WIPRO": "WIPRO.NS",
    "AXIS": "AXISBANK.NS",     "KOTAK": "KOTAKBANK.NS",
    "BAJAJ": "BAJFINANCE.NS",  "APOLLO": "APOLLOHOSP.NS",
}

def _candidates(stock_name: str, isin: str = "") -> list[str]:
    name  = re.sub(r'\s*-\s*(EQ|BE|N[0-9])\s*$', '', str(stock_name).upper()).strip()
    name  = re.sub(
        r'\s+(LIMITED|LTD|INDUSTRIES|TECHNOLOGIES|ENTERPRISE|SERVICES|SOLUTIONS|'
        r'CORPORATION|COMPANY|CHEMICALS|PHARMACEUTICALS|PHARMA|FINANCE|'
        r'FINANCIAL|BANK|TRADING|HOLDINGS|INTERNATIONAL)\s*$',
        '', name, flags=re.IGNORECASE).strip()
    words  = name.split()
    first  = words[0] if words else name
    first2 = ''.join(words[:2])[:12]

    out = []
    ov  = NSE_OVERRIDES.get(first)
    if ov:
        out += [ov, ov.replace(".NS", ".BO")]
    
    # Avoid generic one-word names that are rarely the actual ticker (e.g. TATA, STATE)
    if len(first) > 4 or ov:
        out += [f"{first2}.NS", f"{first2}.BO",
                f"{first}.NS",  f"{first}.BO"]
    
    out += [re.sub(r'[^A-Z0-9]', '', name)[:15] + ".NS"]

    seen, unique = set(), []
    for c in out:
        if c not in seen:
            seen.add(c); unique.append(c)
    return unique


# ═══════════════════════════════════════════════════════════════════
# WATERFALL FETCH — tries all tiers in order
# ═══════════════════════════════════════════════════════════════════
import streamlit as st

@st.cache_data(ttl=180, show_spinner=False)
def fetch_market_data(stock_name: str, isin: str = "",
                      ticker_hint: str = "") -> dict | None:
    """
    Waterfall: WS cache → NSE → BSE → Yahoo → AlphaVantage → Finnhub
    Returns unified dict with keys: price, pe, beta, mkt_cap, sector, source
    """
    cache_key = f"stock:{isin or stock_name}"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    syms = _candidates(stock_name, isin)
    if ticker_hint and ticker_hint not in syms:
        syms.insert(0, ticker_hint)

    # Subscribe to Finnhub WebSocket for all candidates
    _finnhub_ws.subscribe(syms)

    result = None

    # Tier 1: Finnhub WebSocket cache
    for sym in syms:
        px = _finnhub_ws.get_price(sym)
        if px:
            result = {"price": px, "pe": 0.0, "beta": 1.0,
                      "mkt_cap": 0.0, "sector": "Unknown", "source": "FinnhubWS"}
            break

    # Tier 2: NSE
    if not result:
        for sym in syms:
            result = fetch_nse(sym)
            if result: break

    # Tier 2b: BSE (ISIN-based)
    if not result and isin:
        result = fetch_bse(isin)

    # Tier 3: Yahoo Finance
    if not result:
        for sym in syms:
            result = fetch_yahoo(sym)
            if result: break

    # Tier 4: Alpha Vantage
    if not result:
        for sym in syms:
            result = fetch_alpha_vantage(sym)
            if result: break

    # Tier 5: Finnhub REST
    if not result:
        for sym in syms:
            result = fetch_finnhub(sym)
            if result: break

    if result:
        # Ensure all expected keys exist
        for k, default in [("pe", 0.0), ("beta", 1.0), ("mkt_cap", 0.0),
                            ("sector", "Unknown"), ("pct_chg", 0.0)]:
            result.setdefault(k, default)
        _cache.set(cache_key, result, ttl=180)
        print(f"[Market] {stock_name}: ₹{result['price']:.2f} via {result['source']}")
    return result


# ═══════════════════════════════════════════════════════════════════
# SCREENER.IN — sector fallback for Indian stocks
# ═══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_screener_sector(stock_name: str) -> str:
    """Scrape sector info from Screener.in with fallback candidates."""
    if not stock_name or len(stock_name) < 2: return "Unknown"
    cache_key = f"sec:{stock_name}"
    cached = _cache.get(cache_key)
    if cached: return cached

    import requests
    from bs4 import BeautifulSoup
    
    # Try different URL slugs
    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', stock_name).strip()
    candidates = [
        re.sub(r'\s+', '-', clean_name.lower()), # slug-style
        clean_name.split()[0].upper(),           # first word (often ticker)
        re.sub(r'\s+', '', clean_name).upper(),  # packed name
    ]
    
    # Remove duplicates
    seen = set()
    unique_candidates = [x for x in candidates if not (x in seen or seen.add(x))]

    for query in unique_candidates:
        try:
            url = f"https://www.screener.in/company/{query}/"
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                # Look for the sector link (usually a link containing /screens/)
                el = soup.find("a", {"href": re.compile(r"/screens/")})
                if el:
                    sector = el.text.strip()
                    _cache.set(cache_key, sector, ttl=86400)
                    return sector
        except Exception:
            continue
            
    return "Unknown"


# ═══════════════════════════════════════════════════════════════════
# MARKET DATA SERVICE — portfolio-level enrichment
# ═══════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════
# NIFTY 50 REAL-TIME BENCHMARK
# ═══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=60, show_spinner=False)
def fetch_nifty50() -> dict:
    """
    Fetch real-time Nifty 50 data from Yahoo Finance (^NSEI).
    Returns: current level, change%, YTD return%, 52w high/low.
    Cached for 60 seconds.
    """
    cache_key = "benchmark:nifty50"
    cached = _cache.get(cache_key)
    if cached:
        return cached

    try:
        import requests as _req
        for base in ["https://query1.finance.yahoo.com",
                     "https://query2.finance.yahoo.com"]:
            # Current quote
            r = _req.get(
                f"{base}/v8/finance/chart/%5ENSEI",
                params={"interval": "1d", "range": "1y"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=6,
            )
            if r.status_code != 200:
                continue
            data    = r.json()
            result_ = data.get("chart", {}).get("result", [])
            if not result_:
                continue
            meta    = result_[0].get("meta", {})
            closes  = result_[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])

            current = float(meta.get("regularMarketPrice") or meta.get("previousClose") or 0)
            prev    = float(meta.get("chartPreviousClose") or (closes[-2] if len(closes) >= 2 else current))
            ytd_start = float(closes[0]) if closes else current

            if current <= 0:
                continue

            change_pct  = ((current - prev) / prev * 100)   if prev    else 0
            ytd_pct     = ((current - ytd_start) / ytd_start * 100) if ytd_start else 0
            high_52w    = float(meta.get("fiftyTwoWeekHigh", 0) or 0)
            low_52w     = float(meta.get("fiftyTwoWeekLow",  0) or 0)

            result = {
                "nifty_current":    round(current, 2),
                "nifty_prev":       round(prev, 2),
                "nifty_change_pct": round(change_pct, 2),
                "nifty_ytd_pct":    round(ytd_pct, 2),
                "nifty_high_52w":   round(high_52w, 2),
                "nifty_low_52w":    round(low_52w, 2),
                "source":           "Yahoo ^NSEI",
            }
            _cache.set(cache_key, result, ttl=60)
            print(f"[Nifty50] {current:.0f} ({change_pct:+.2f}% today, {ytd_pct:+.2f}% YTD)")
            return result
    except Exception as e:
        print(f"[Nifty50] fetch error: {e}")

    # Fallback: NSE index API
    try:
        import requests as _req
        r = _req.get(
            "https://www.nseindia.com/api/allIndices",
            headers={"User-Agent": "Mozilla/5.0",
                     "Referer":    "https://www.nseindia.com"},
            timeout=5,
        )
        if r.status_code == 200:
            for idx in r.json().get("data", []):
                if idx.get("indexSymbol") == "NIFTY 50":
                    current    = float(idx.get("last", 0))
                    change_pct = float(idx.get("percentChange", 0))
                    result = {
                        "nifty_current":    current,
                        "nifty_prev":       float(idx.get("previousClose", current)),
                        "nifty_change_pct": change_pct,
                        "nifty_ytd_pct":    0.0,
                        "nifty_high_52w":   float(idx.get("yearHigh", 0)),
                        "nifty_low_52w":    float(idx.get("yearLow",  0)),
                        "source":           "NSE API",
                    }
                    _cache.set(cache_key, result, ttl=60)
                    return result
    except Exception as e:
        print(f"[Nifty50 NSE fallback] {e}")

    return {}


class MarketDataService:
    def __init__(self, fmp_keys=[], av_key=None):
        pass  # Keys now loaded from env via module-level constants

    def enrich_portfolio(self, df: pd.DataFrame) -> pd.DataFrame:
        """Enrich portfolio DataFrame using hybrid waterfall pipeline."""
        if df.empty:
            return df

        for col in ["ltp", "pe", "beta", "mkt_cap"]:
            if col not in df.columns:
                df[col] = 0.0
        if "sector" not in df.columns:
            df["sector"] = "Unknown"

        # Parallel fetch
        def _worker(args):
            idx, stock, isin, hint = args
            return idx, fetch_market_data(stock, isin, hint)

        tasks = [
            (idx, str(row.get("stock_name", row.get("symbol", ""))),
             str(row.get("isin", "")), str(row.get("_ticker_hint", "")))
            for idx, row in df.iterrows()
        ]

        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {ex.submit(_worker, t): t for t in tasks}
            for fut in as_completed(futures):
                idx, data = fut.result()
                if data and data.get("price", 0) > 0:
                    df.at[idx, "ltp"]     = data["price"]
                    df.at[idx, "pe"]      = data.get("pe", 0)
                    df.at[idx, "beta"]    = data.get("beta", 1.0)
                    df.at[idx, "mkt_cap"] = data.get("mkt_cap", 0)
                    if str(df.at[idx, "sector"]).strip() in ("", "Unknown"):
                        df.at[idx, "sector"] = data.get("sector", "Unknown")

        # Sector gap-fill via Screener.in and Yahoo Metadata
        unknown_mask = df["sector"].isin(["Unknown", "", None, "UNKNOWN"])
        if unknown_mask.any():
            with ThreadPoolExecutor(max_workers=10) as ex:
                def _sec_resolver(idx):
                    name = df.at[idx, "stock_name"]
                    hint = df.at[idx, "_ticker_hint"]
                    
                    # 1. Try Yahoo Metadata if we have a hint
                    if hint:
                        y_meta = fetch_yahoo_metadata(hint)
                        if y_meta["sector"] != "Unknown":
                            return idx, y_meta["sector"]
                    
                    # 2. Try Screener fallback
                    s_sector = fetch_screener_sector(name)
                    if s_sector != "Unknown":
                        return idx, s_sector
                    
                    return idx, "Unknown"

                futures = [ex.submit(_sec_resolver, i) for i in df.index[unknown_mask]]
                for fut in as_completed(futures):
                    idx, resolved_sector = fut.result()
                    if resolved_sector != "Unknown":
                        df.at[idx, "sector"] = resolved_sector

        # Recalculate P&L with live prices
        ltp = df["ltp"].astype(float)
        qty = (df["qty"] if "qty" in df.columns
               else df.get("quantity", pd.Series([0]*len(df), index=df.index))).astype(float)
        live = ltp > 0
        df.loc[live, "current_val"]   = (ltp * qty)[live]
        df["current_value"]            = df["current_val"]
        df["invested_amount"]          = df["invested_val"]
        df["pnl"]     = (df["current_val"] - df["invested_val"]).round(2)
        df["pnl_pct"] = (
            df["pnl"] / df["invested_val"].replace(0, float("nan")) * 100
        ).fillna(0).round(2)

        print(f"[Pipeline] Done — "
              f"LTP:{live.sum()}/{len(df)} | "
              f"Sector:{(df['sector']!='Unknown').sum()}/{len(df)}")
        return df

    def get_indicators(self, ticker: str) -> dict:
        """Fetch RSI + MACD from Alpha Vantage."""
        return fetch_av_indicators(ticker)

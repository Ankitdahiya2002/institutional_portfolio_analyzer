"""
Supabase REST API client for Portfolio V2.
Saves: portfolios, holdings (full data), benchmark comparison, AI reports, instruments.
"""
import os
import json
import requests
import pandas as pd
from datetime import datetime, timezone


class SupabaseService:
    def __init__(self, url: str = None, key: str = None):
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.key  = key or os.getenv("SUPABASE_KEY", "")
        self._ok  = bool(self.url and self.key and self.url.startswith("http"))

    @property
    def _headers(self):
        return {
            "apikey":        self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type":  "application/json",
            "Prefer":        "return=representation",
        }

    def is_configured(self) -> bool:
        return self._ok

    # ── Generic helpers ───────────────────────────────────────────
    def _insert(self, table: str, payload, upsert_on: str = None):
        if not self._ok:
            return None
        headers = dict(self._headers)
        if upsert_on:
            headers["Prefer"] = f"resolution=merge-duplicates,return=representation"
        try:
            r = requests.post(
                f"{self.url}/rest/v1/{table}",
                headers=headers,
                data=json.dumps(payload),
                timeout=12,
            )
            if r.status_code in (200, 201):
                data = r.json()
                return data if isinstance(data, list) else [data]
            print(f"[Supabase] INSERT {table}: {r.status_code} {r.text[:300]}")
            return None
        except Exception as e:
            print(f"[Supabase] network error ({table}): {e}")
            return None

    def _upsert(self, table: str, payload):
        return self._insert(table, payload, upsert_on=True)

    def _query(self, table: str, params: dict) -> list:
        if not self._ok:
            return []
        try:
            r = requests.get(
                f"{self.url}/rest/v1/{table}",
                headers=self._headers,
                params=params,
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[Supabase] query error ({table}): {e}")
        return []

    @staticmethod
    def _f(v) -> float:
        try: return round(float(v), 4) if pd.notna(v) else 0.0
        except: return 0.0

    @staticmethod
    def _i(v) -> int:
        try: return int(float(v)) if pd.notna(v) else 0
        except: return 0

    @staticmethod
    def _s(v, default="") -> str:
        return str(v) if v is not None else default

    # ═══════════════════════════════════════════════════════════════
    # PORTFOLIO
    # ═══════════════════════════════════════════════════════════════
    def save_portfolio(self, name: str, stats: dict, health_score,
                       benchmark: dict = None) -> dict | None:
        """
        Save or upsert portfolio summary row.
        Includes Nifty 50 benchmark comparison columns.
        """
        row = {
            "name":           name,
            "total_invested":  self._f(stats.get("total_invested", 0)),
            "total_current":   self._f(stats.get("total_current",  0)),
            "total_pnl":       self._f(stats.get("total_pnl",      0)),
            "total_pnl_pct":   self._f(stats.get("total_pnl_pct",  0)),
            "health_score":    self._i(health_score),
            "holdings_count":  self._i(stats.get("holdings_count", 0)),
            "weighted_beta":   self._f(stats.get("weighted_beta",  1.0)),
            "weighted_pe":     self._f(stats.get("weighted_pe",    0)),
            "hhi":             self._f(stats.get("hhi",            0)),
            "created_at":      datetime.now(timezone.utc).isoformat(),
        }

        # Nifty benchmark data
        if benchmark:
            row["nifty_level"]      = self._f(benchmark.get("nifty_current", 0))
            row["nifty_change_pct"] = self._f(benchmark.get("nifty_change_pct", 0))
            row["alpha"]            = self._f(benchmark.get("alpha", 0))
            row["nifty_ytd_pct"]    = self._f(benchmark.get("nifty_ytd_pct", 0))
            row["portfolio_ytd_pct"]= self._f(stats.get("total_pnl_pct", 0))

        result = self._insert("portfolios", row)
        return result[0] if result else None

    # ═══════════════════════════════════════════════════════════════
    # HOLDINGS — full data per stock
    # ═══════════════════════════════════════════════════════════════
    def save_holdings(self, portfolio_id, df_data: list):
        """
        Save complete per-stock data: price, P&L, sector, PE, beta,
        market cap, ISIN, asset type, data source, % of portfolio.
        """
        if not df_data:
            return

        df = pd.DataFrame(df_data)
        total_cur = self._f(df["current_val"].sum()) if "current_val" in df.columns else 1.0
        if total_cur <= 0:
            total_cur = 1.0

        rows = []
        for _, row in df.iterrows():
            cur_val = self._f(row.get("current_val", row.get("current_value", 0)))
            rows.append({
                "portfolio_id":   portfolio_id,
                # Identity
                "symbol":         self._s(row.get("stock_name", row.get("symbol", ""))),
                "isin":           self._s(row.get("isin", "")),
                "asset_type":     self._s(row.get("asset_type", "Equity")),
                "sector":         self._s(row.get("sector", "Unknown")),
                # Position
                "qty":            self._i(row.get("qty", row.get("quantity", 0))),
                "avg_cost":       self._f(
                    row.get("invested_val", row.get("invested_amount", 0)) /
                    max(self._i(row.get("qty", row.get("quantity", 1))), 1)
                ),
                # Pricing (live)
                "ltp":            self._f(row.get("ltp", 0)),
                "data_source":    self._s(row.get("_data_source", "Yahoo")),
                # Valuation
                "invested_val":   self._f(row.get("invested_val", row.get("invested_amount", 0))),
                "current_val":    cur_val,
                "pnl":            self._f(row.get("pnl", 0)),
                "pnl_pct":        self._f(row.get("pnl_pct", 0)),
                "weight_pct":     round(cur_val / total_cur * 100, 4),
                # Fundamentals
                "pe":             self._f(row.get("pe", 0)),
                "beta":           self._f(row.get("beta", 1.0)),
                "mkt_cap":        self._f(row.get("mkt_cap", 0)),
                # Meta
                "recorded_at":    datetime.now(timezone.utc).isoformat(),
            })

        # Batch insert in chunks of 100
        for i in range(0, len(rows), 100):
            self._insert("holdings", rows[i:i+100])
        print(f"[Supabase] Saved {len(rows)} holdings for portfolio {portfolio_id}")

    # ═══════════════════════════════════════════════════════════════
    # BENCHMARK SNAPSHOT — Nifty 50 data point
    # ═══════════════════════════════════════════════════════════════
    def save_benchmark_snapshot(self, portfolio_id, benchmark: dict):
        """Save Nifty 50 benchmark data alongside the portfolio."""
        if not benchmark:
            return
        row = {
            "portfolio_id":     portfolio_id,
            "index_name":       "NIFTY50",
            "current_level":    self._f(benchmark.get("nifty_current", 0)),
            "change_pct":       self._f(benchmark.get("nifty_change_pct", 0)),
            "ytd_return_pct":   self._f(benchmark.get("nifty_ytd_pct", 0)),
            "alpha":            self._f(benchmark.get("alpha", 0)),
            "portfolio_return":  self._f(benchmark.get("portfolio_pnl_pct", 0)),
            "recorded_at":      datetime.now(timezone.utc).isoformat(),
        }
        self._insert("benchmark_snapshots", row)

    # ═══════════════════════════════════════════════════════════════
    # AI REPORT
    # ═══════════════════════════════════════════════════════════════
    def save_ai_report(self, portfolio_id, report: dict, model: str = ""):
        if not report:
            return
        data = {
            "portfolio_id":        portfolio_id,
            "model":               model,
            "behavioral_signature": self._s(report.get("behavioral_signature", "")),
            "verdict":             self._s(report.get("verdict", "")),
            "concentration_risk":  self._s(report.get("concentration_risk", "")),
            "simple_summary":      self._s(report.get("simple_summary", "")),
            "rebalancing_advice":  json.dumps(report.get("rebalancing_advice", [])),
            "created_at":          datetime.now(timezone.utc).isoformat(),
        }
        self._insert("ai_reports", data)

    # ═══════════════════════════════════════════════════════════════
    # INSTRUMENTS CACHE
    # ═══════════════════════════════════════════════════════════════
    def resolve_instruments(self, stock_names: list) -> dict:
        if not self._ok or not stock_names:
            return {}
        try:
            names_filter = ",".join(f'"{n}"' for n in stock_names)
            rows = self._query("instruments", {
                "name":   f"in.({names_filter})",
                "select": "name,isin,sector,ticker",
            })
            return {
                row["name"]: {
                    "isin":   row.get("isin", ""),
                    "sector": row.get("sector", "Unknown"),
                    "ticker": row.get("ticker", ""),
                }
                for row in rows if row.get("name")
            }
        except Exception as e:
            print(f"[Supabase] resolve_instruments: {e}")
            return {}

    def save_instrument(self, name: str, isin: str = "",
                        sector: str = "Unknown", ticker: str = ""):
        if not self._ok or not name:
            return None
        payload = {"name": name, "isin": isin, "sector": sector, "ticker": ticker}
        try:
            r = requests.post(
                f"{self.url}/rest/v1/instruments",
                headers={**self._headers,
                         "Prefer": "resolution=merge-duplicates,return=representation"},
                data=json.dumps(payload),
                timeout=10,
            )
            if r.status_code in (200, 201):
                data = r.json()
                return data[0] if isinstance(data, list) else data
            print(f"[Supabase] save_instrument warning: {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"[Supabase] save_instrument error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# ISIN Resolver — Supabase cache → SerpAPI → store back
# ══════════════════════════════════════════════════════════════════
class ISINResolverService:
    ISIN_RE = __import__('re').compile(r'\bIN[A-Z0-9]{10}\b')

    def __init__(self):
        self.db       = SupabaseService()
        self.serp_key = os.getenv("SERP_API_KEY", "")
        self._local   = {}

    def resolve(self, stock_name: str) -> str:
        key = stock_name.strip().upper()
        if not key:
            return ''
        if key in self._local:
            return self._local[key]
        isin = self._from_supabase(key)
        if isin:
            self._local[key] = isin
            return isin
        isin = self._from_serp(key)
        if isin:
            self._local[key] = isin
            self._save_to_supabase(stock_name, isin)
        return isin or ''

    def resolve_batch(self, stock_names: list) -> dict:
        from concurrent.futures import ThreadPoolExecutor
        bulk    = self._bulk_from_supabase(stock_names)
        missing = [n for n in stock_names if not bulk.get(n.strip().upper())]
        results = dict(bulk)
        if missing and self.serp_key:
            with ThreadPoolExecutor(max_workers=5) as ex:
                results.update(dict(zip(missing, ex.map(self.resolve, missing))))
        return results

    def _from_supabase(self, name: str) -> str:
        rows = self.db._query("instruments", {
            "name": f"ilike.{name}", "select": "isin", "limit": "1"
        })
        return rows[0].get("isin", "") if rows else ""

    def _bulk_from_supabase(self, names: list) -> dict:
        if not self.db._ok or not names:
            return {}
        names_filter = ",".join(f'"{n.strip()}"' for n in names)
        rows = self.db._query("instruments", {
            "name": f"in.({names_filter})", "select": "name,isin"
        })
        return {row["name"].upper(): row["isin"] for row in rows if row.get("isin")}

    def _save_to_supabase(self, name: str, isin: str):
        self.db.save_instrument(name=name.strip(), isin=isin)

    def _from_serp(self, stock_name: str) -> str:
        if not self.serp_key:
            return ''
        try:
            r = requests.get(
                "https://serpapi.com/search",
                params={"q": f"{stock_name} ISIN India NSE BSE",
                        "api_key": self.serp_key, "num": 5, "engine": "google"},
                timeout=10,
            )
            if r.status_code == 200:
                data    = r.json()
                sources = []
                if data.get('answer_box', {}).get('answer'):
                    sources.append(data['answer_box']['answer'])
                for res in data.get('organic_results', []):
                    sources.append(res.get('snippet', ''))
                match = self.ISIN_RE.search(' '.join(sources))
                if match:
                    isin = match.group(0)
                    if len(isin) == 12:
                        return isin
        except Exception as e:
            print(f"[ISIN SerpAPI] {stock_name}: {e}")
        return ''

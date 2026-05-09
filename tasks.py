"""
Portfolio Analyzer — Pure Python Tasks (no Celery)
====================================================
Called directly by FastAPI background threads.
"""

import os
import base64
import pandas as pd
from io import StringIO, BytesIO
from dotenv import load_dotenv
load_dotenv()


# ═══════════════════════════════════════════════════════════════════
# PHASE 1 — PARSE
# ═══════════════════════════════════════════════════════════════════

def run_parse(file_content_b64: str, filename: str) -> dict:
    """Parse broker file into standardised records."""
    from core.parser import universal_smart_parse
    from services.ai_analyzer import AIAnalyzerService
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

    file_bytes = base64.b64decode(file_content_b64)

    # ── 1. Legacy parser (instant) ────────────────────────────────
    try:
        if filename.lower().endswith('.csv'):
            content_str = file_bytes.decode('utf-8', errors='replace')
            raw_df = pd.read_csv(StringIO(content_str), header=None, sep=None,
                                  engine='python', dtype=str, on_bad_lines='warn')
            df = universal_smart_parse(raw_df)
        else:
            xl  = pd.ExcelFile(BytesIO(file_bytes))
            df  = pd.DataFrame()
            for sheet in xl.sheet_names:
                try:
                    raw_df = xl.parse(sheet, header=None, dtype=str)
                    df = universal_smart_parse(raw_df)
                    if not df.empty:
                        break
                except Exception:
                    pass

        if not df.empty:
            print(f"[Phase1] Legacy parser: {len(df)} holdings in '{filename}'")
            return {"status": "success", "data": df.to_dict(orient='records'), "parser": "legacy"}

        print("[Phase1] Legacy parser returned empty — trying AI...")
    except Exception as e:
        print(f"[Phase1] Legacy error: {e}")

    # ── 2. AI parser fallback (30s hard cap) ─────────────────────
    try:
        ai = AIAnalyzerService(
            gemini_key=os.getenv("GEMINI_API_KEY_1") or os.getenv("GEMINI_API_KEY"),
            claude_key=os.getenv("CLAUDE_API_KEY"),
        )
        if ai.is_configured():
            if filename.lower().endswith('.csv'):
                file_text = file_bytes.decode('utf-8', errors='replace')
            else:
                xl = pd.ExcelFile(BytesIO(file_bytes))
                sheets_text = []
                for sheet in xl.sheet_names:
                    try:
                        raw_df = xl.parse(sheet, header=None, dtype=str)
                        sheets_text.append(raw_df.to_csv(index=False, header=False))
                    except Exception:
                        pass
                file_text = "\n".join(sheets_text)

            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(ai.parse_portfolio_file, file_text, filename)
                try:
                    ai_records = future.result(timeout=30)
                    if ai_records:
                        print(f"[Phase1] AI parser: {len(ai_records)} holdings")
                        return {"status": "success", "data": ai_records, "parser": "ai"}
                except FutureTimeout:
                    print("[Phase1] AI parser timed out after 30s")
    except Exception as e:
        print(f"[Phase1] AI error: {e}")

    return {"status": "error", "message": "Could not extract holdings from the uploaded file."}


# ═══════════════════════════════════════════════════════════════════
# PHASE 2 — ENRICH + ANALYTICS
# ═══════════════════════════════════════════════════════════════════

def run_enrich_analytics(parsed_data: dict, user_id: str = None) -> dict:
    """Enrich portfolio with live data + calculate metrics."""
    from services.market_data import MarketDataService
    from services.database import SupabaseService
    from core.metrics import calculate_portfolio_metrics, analyze_portfolio_health

    if parsed_data.get("status") != "success":
        return parsed_data

    df = pd.DataFrame(parsed_data["data"])

    # ── Ensure required columns ───────────────────────────────────
    for col in ['isin', 'sector', 'asset_type', '_ticker_hint']:
        if col not in df.columns:
            df[col] = '' if col in ('isin', '_ticker_hint') else 'Unknown'
    for col in ['ltp', 'qty', 'invested_val', 'current_val', 'pnl', 'pnl_pct']:
        if col not in df.columns:
            df[col] = 0.0
    df['isin'] = df['isin'].fillna('').astype(str)

    # ── 1. ISIN Resolution (Supabase Cache + AI/Web Search) ───────
    from services.database import ISINResolverService, SupabaseService
    db = SupabaseService(url=os.getenv("SUPABASE_URL"), key=os.getenv("SUPABASE_KEY"))
    resolver = ISINResolverService()
    
    missing_mask = (df['isin'].str.len() < 5)
    if missing_mask.any():
        to_resolve = df.loc[missing_mask, 'stock_name'].unique().tolist()
        resolved = resolver.resolve_batch(to_resolve)
        for name, isin in resolved.items():
            if isin:
                df.loc[df['stock_name'] == name, 'isin'] = isin
    
    print(f"[Phase2] ISIN resolution: {df['isin'].str.len().gt(5).sum()}/{len(df)} holdings identified")

    # ── 2. Live market data ───────────────────────────────────────
    mkt = MarketDataService(
        fmp_keys=[k for k in [os.getenv("FMP_KEY_1"), os.getenv("FMP_KEY_2")] if k],
        av_key=os.getenv("ALPHA_VANTAGE_KEY"),
    )
    try:
        df = mkt.enrich_portfolio(df)
    except Exception as e:
        print(f"[Phase2] Enrich error: {e}")

    # ── 3. Asset type detection ───────────────────────────────────
    ETF_KW    = ['BEES', 'ETF', 'NIFTYBEES', 'GOLDBEES', 'BANKBEES', 'JUNIORBEES',
                 'LIQUIDBEES', 'SILVERBEES', 'ITBEES', 'PSUBNKBEES', 'MAFANG']
    DEBT_KW   = ['LIQUIDFUND', 'OVERNIGHT', 'LIQUID', 'GILT', 'BOND']
    COMMOD_KW = ['GOLD', 'SILVER', 'COPPER', 'CRUDE', 'METAL', 'OIL']

    def _detect(row):
        name   = str(row.get('stock_name', '')).upper()
        sector = str(row.get('sector', '')).upper()
        if any(k in name for k in ETF_KW):      return 'ETF'
        if any(k in name for k in DEBT_KW):      return 'Debt'
        if any(k in name for k in COMMOD_KW):    return 'Commodity'
        if 'REAL ESTATE' in sector:              return 'Real Estate'
        if 'FINANCIAL' in sector or 'BANK' in sector: return 'Equity - Finance'
        return 'Equity'

    df['asset_type'] = df.apply(_detect, axis=1)

    # ── 4. Persist to Supabase ────────────────────────────────────
    if db.is_configured():
        for _, row in df[df['isin'].str.len() >= 12].iterrows():
            db.save_instrument(
                name=str(row['stock_name']), isin=str(row['isin']),
                sector=str(row.get('sector', 'Unknown')),
                ticker=str(row.get('_ticker_hint', '')),
            )

    # ── 5. Metrics + Performance + Tax + Benchmark ────────────────
    from core.metrics import (calculate_portfolio_metrics,
                              analyze_portfolio_health,
                              generate_dynamic_insights,
                              classify_taxes)
    from services.market_data import fetch_nifty50
    from concurrent.futures import ThreadPoolExecutor as _TPE

    # Run metrics + Nifty50 fetch in parallel
    with _TPE(max_workers=3) as ex:
        fut_stats   = ex.submit(calculate_portfolio_metrics, df)
        fut_nifty   = ex.submit(fetch_nifty50)
        fut_tax     = ex.submit(classify_taxes, df)
        
        stats       = fut_stats.result()
        benchmark   = fut_nifty.result()
        tax_info    = fut_tax.result()

    # Try Advanced Performance (XIRR + Sharpe/Sortino)
    try:
        from core.performance import calculate_xirr, calculate_risk_metrics
        xirr_result = calculate_xirr(df)
        if isinstance(xirr_result, dict):
            stats["xirr"]           = xirr_result["value"]
            stats["xirr_estimated"] = xirr_result["estimated"]
        else:
            stats["xirr"]           = xirr_result  # None → no data at all
            stats["xirr_estimated"] = False

        # Sharpe / Sortino from per-stock pnl_pct as a returns series
        if "pnl_pct" in df.columns:
            returns = df["pnl_pct"].dropna().astype(float) / 100
            risk = calculate_risk_metrics(returns)
            stats["sharpe"]  = risk.get("sharpe", 0.0)
            stats["sortino"] = risk.get("sortino", 0.0)
    except Exception as e:
        print(f"[Phase2] Performance metrics error: {e}")
        stats.setdefault("xirr", None)
        stats.setdefault("xirr_estimated", False)
        stats.setdefault("sharpe", 0.0)
        stats.setdefault("sortino", 0.0)

    # Ensure taxes are always added
    stats.update(tax_info)

    # Benchmark + Alpha
    if benchmark:
        pnl_pct  = stats.get("total_pnl_pct", 0)
        alpha    = round(pnl_pct - benchmark.get("nifty_ytd_pct", 0), 2)
        benchmark["alpha"]              = alpha
        benchmark["portfolio_pnl_pct"]  = pnl_pct
        stats["nifty_current"]          = benchmark.get("nifty_current", 0)
        stats["nifty_change_pct"]       = benchmark.get("nifty_change_pct", 0)
        stats["nifty_ytd_pct"]          = benchmark.get("nifty_ytd_pct", 0)
        stats["alpha"]                  = alpha

    health          = analyze_portfolio_health(stats)
    stats["health"] = health

    # Dynamic insights
    dynamic = generate_dynamic_insights(df, stats)

    # ── 6. Save everything to Supabase ────────────────────────────
    try:
        p_name = f"Portfolio_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}"
        res    = db.save_portfolio(p_name, stats, health, benchmark=benchmark, user_id=user_id)
        if res and "id" in res:
            p_id = res["id"]
            db.save_holdings(p_id, df.to_dict(orient="records"))
            if benchmark:
                db.save_benchmark_snapshot(p_id, benchmark)
            print(f"[Supabase] Phase2 saved: {p_name} (ID: {p_id})")
    except Exception as e:
        print(f"[Supabase] Phase2 save error: {e}")

    return {
        "status":    "success",
        "data":      df.to_dict(orient="records"),
        "stats":     stats,
        "health":    health,
        "benchmark": benchmark,
        "dynamic":   dynamic,
    }


# ═══════════════════════════════════════════════════════════════════
# PHASE 3 — AI REPORT
# ═══════════════════════════════════════════════════════════════════

def run_ai_report(analytics_data: dict, user_id: str = None) -> dict:
    """Generate AI forensic report + save to Supabase."""
    from services.ai_analyzer import AIAnalyzerService
    from services.database import SupabaseService

    if analytics_data.get("status") != "success":
        return analytics_data

    stats  = analytics_data["stats"]
    health = analytics_data.get("health", 50)
    data   = pd.DataFrame(analytics_data["data"])

    ai = AIAnalyzerService(
        gemini_key=os.getenv("GEMINI_API_KEY_1") or os.getenv("GEMINI_API_KEY"),
        claude_key=os.getenv("CLAUDE_API_KEY"),
    )

    # Start with dynamic (instant, always works)
    from core.metrics import generate_dynamic_insights
    dynamic = analytics_data.get("dynamic") or generate_dynamic_insights(data, stats)
    report  = dict(dynamic)  # base: dynamic insights

    # Try AI — merge if successful (AI enriches, not replaces)
    try:
        ai_report = ai.generate_portfolio_report(data, stats)
        if ai_report and isinstance(ai_report, dict):
            # AI output overrides only if non-empty
            for k in ['verdict', 'concentration_risk', 'rebalancing_advice',
                      'behavioral_signature', 'simple_summary']:
                if ai_report.get(k):
                    report[k] = ai_report[k]
            print("[Phase3] AI report merged with dynamic insights")
    except Exception as e:
        print(f"[Phase3] AI failed — using dynamic insights only: {e}")

    # Save AI report only (link to existing if possible)
    try:
        db = SupabaseService()
        if db.is_configured():
            # If we just saved in Phase 2, try to use that ID if passed in analytics_data
            p_id = analytics_data.get("portfolio_id")
            if not p_id:
                p_name = f"Portfolio_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}"
                res    = db.save_portfolio(p_name, stats, health, user_id=user_id)
                p_id   = res["id"] if res else None
            
            if p_id:
                db.save_ai_report(p_id, report, "Gemini/Claude")
                print(f"[Phase3] Saved report for ID: {p_id}")
    except Exception as e:
        print(f"[Phase3] Supabase save failed: {e}")

    return {
        "status": "success",
        "data":   analytics_data["data"],
        "stats":  stats,
        "health": health,
        "report": report,
    }

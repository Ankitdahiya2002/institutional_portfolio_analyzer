import pandas as pd
import numpy as np

def calculate_portfolio_metrics(df):
    """
    Calculates weighted portfolio metrics (Beta, PE, etc.).
    Returns a dictionary of summary statistics.
    """
    equity_df = df[df['asset_type'] == 'Equity'].copy() if 'asset_type' in df.columns else df.copy()
    total_invested = float(df['invested_val'].sum())
    total_current  = float(df['current_val'].sum())
    total_pnl      = total_current - total_invested
    total_pnl_pct  = (total_pnl / total_invested * 100) if total_invested != 0 else 0

    df = df.copy()
    df['weight'] = df['current_val'] / total_current if total_current != 0 else 0

    stats = {
        'total_invested':  total_invested,
        'total_current':   total_current,
        'total_pnl':       total_pnl,
        'total_pnl_pct':   total_pnl_pct,
        'holdings_count':  len(df),
    }

    if 'pe' in df.columns:
        valid_pe = df[df['pe'] > 0]
        if not valid_pe.empty:
            w = valid_pe['current_val'] / valid_pe['current_val'].sum()
            stats['weighted_pe'] = float((valid_pe['pe'] * w).sum())

    if 'beta' in df.columns:
        stats['weighted_beta'] = float((df['beta'] * df['weight']).sum())

    # Concentration risk: largest single holding %
    if total_current > 0:
        max_w = float(df['weight'].max()) * 100
        stats['max_single_weight'] = max_w
        # Herfindahl-Hirschman Index (sector concentration)
        if 'sector' in df.columns:
            sector_w = df.groupby('sector')['current_val'].sum() / total_current
            stats['hhi'] = float((sector_w ** 2).sum())   # 0=perfect, 1=monopoly

    return stats


def analyze_portfolio_health(stats):
    """Health score 0-100 based on diversification, risk, and returns."""
    score = 50

    n = stats['holdings_count']
    if n >= 15: score += 15
    elif n >= 10: score += 12
    elif n >= 5:  score += 8

    if 'weighted_beta' in stats:
        beta = stats['weighted_beta']
        if 0.7 <= beta <= 1.1: score += 15
        elif beta < 0.7:       score += 8
        else:                  score -= 5

    pnl = stats.get('total_pnl_pct', 0)
    if pnl > 20:    score += 20
    elif pnl > 10:  score += 15
    elif pnl > 0:   score += 10
    elif pnl < -20: score -= 15
    elif pnl < -10: score -= 8
    elif pnl < 0:   score -= 4

    # Penalise extreme concentration
    max_w = stats.get('max_single_weight', 0)
    if max_w > 30:   score -= 10
    elif max_w > 20: score -= 5

    hhi = stats.get('hhi', 0)
    if hhi < 0.10:   score += 5   # well-diversified sectors
    elif hhi > 0.25: score -= 8   # heavily concentrated

    return min(100, max(0, score))


# ═══════════════════════════════════════════════════════════════════
# REBALANCING ENGINE
# ═══════════════════════════════════════════════════════════════════

def calculate_rebalancing(df: pd.DataFrame, strategy: str = "equal_weight",
                           drift_threshold: float = 5.0) -> list:
    """
    Generate per-stock BUY / SELL / HOLD rebalancing actions.

    Strategies
    ----------
    equal_weight  : Each holding gets 1/N of portfolio value.
    risk_parity   : Weight inversely proportional to beta.
                    Lower beta → higher weight (less risk).
    sector_cap    : Equal weight but any sector capped at 30 %.
                    Excess redistributed to under-weight sectors.

    Parameters
    ----------
    drift_threshold : Minimum abs(current_wt - target_wt) % to generate action.
                      Below this → HOLD.  Default 5 %.

    Returns
    -------
    List of dicts, one per holding:
      stock_name, current_weight_pct, target_weight_pct, drift_pct,
      action, amount_inr, shares (estimated), reason
    """
    if df.empty:
        return []

    df = df.copy()
    total_val = float(df['current_val'].sum())
    if total_val <= 0:
        return []

    n = len(df)
    df['current_weight'] = df['current_val'].astype(float) / total_val

    # ── Compute target weights ─────────────────────────────────────
    if strategy == "equal_weight":
        df['target_weight'] = 1.0 / n

    elif strategy == "risk_parity":
        betas = df['beta'].astype(float).clip(lower=0.1) if 'beta' in df.columns \
                else pd.Series([1.0] * n, index=df.index)
        inv_beta = 1.0 / betas
        df['target_weight'] = inv_beta / inv_beta.sum()

    elif strategy == "sector_cap":
        cap = 0.30   # 30 % per sector max
        base_w = 1.0 / n
        df['target_weight'] = base_w

        if 'sector' in df.columns:
            sector_totals = df.groupby('sector')['target_weight'].transform('sum')
            over_mask = sector_totals > cap
            excess_total = (sector_totals[over_mask] - cap).sum()

            # Cap over-weight sectors
            df.loc[over_mask, 'target_weight'] = (
                cap / df.loc[over_mask].groupby('sector')['target_weight']
                        .transform('count')
            )
            # Redistribute excess to under-weight sectors
            n_under = (~over_mask).sum()
            if n_under > 0:
                df.loc[~over_mask, 'target_weight'] += excess_total / n_under
    else:
        df['target_weight'] = 1.0 / n   # fallback to equal

    # ── Compute drift and actions ─────────────────────────────────
    df['drift'] = (df['target_weight'] - df['current_weight']) * 100  # in %

    def _action(drift_pct):
        if abs(drift_pct) < drift_threshold: return 'HOLD'
        return 'BUY' if drift_pct > 0 else 'SELL'

    records = []
    for _, row in df.iterrows():
        drift_pct  = float(row['drift'])
        action     = _action(drift_pct)
        amount_inr = drift_pct / 100 * total_val          # ₹ to transact
        ltp        = float(row.get('ltp', 0))
        shares_est = round(abs(amount_inr) / ltp, 2) if ltp > 0 else None

        # Human-readable reason
        cw = float(row['current_weight']) * 100
        tw = float(row['target_weight'])  * 100
        if action == 'HOLD':
            reason = f"Within {drift_threshold}% tolerance — no action needed"
        elif action == 'BUY':
            reason = f"Under-weight ({cw:.1f}% → target {tw:.1f}%) — add ₹{abs(amount_inr):,.0f}"
        else:
            reason = f"Over-weight ({cw:.1f}% → target {tw:.1f}%) — trim ₹{abs(amount_inr):,.0f}"

        records.append({
            'stock_name':         str(row.get('stock_name', '')),
            'sector':             str(row.get('sector', 'Unknown')),
            'current_weight_pct': round(cw, 2),
            'target_weight_pct':  round(tw, 2),
            'drift_pct':          round(drift_pct, 2),
            'action':             action,
            'amount_inr':         round(amount_inr, 2),
            'shares_est':         shares_est,
            'reason':             reason,
        })

    # Sort: SELL first, then BUY, then HOLD
    order = {'SELL': 0, 'BUY': 1, 'HOLD': 2}
    records.sort(key=lambda r: order.get(r['action'], 3))
    return records


# ═══════════════════════════════════════════════════════════════════
# DYNAMIC INSIGHTS ENGINE
# ═══════════════════════════════════════════════════════════════════

def generate_dynamic_insights(df: pd.DataFrame, stats: dict) -> dict:
    """
    Compute verdict, concentration risk text, and rebalancing advice
    entirely from live portfolio data — no static text, no AI needed.

    Returns
    -------
    dict with keys:
        verdict            : str — overall portfolio verdict
        concentration_risk : str — specific concentration findings
        rebalancing_advice : list[str] — actionable bullet points
        behavioral_signature : str — investor profile label
        simple_summary     : str — plain-language summary
    """
    if df.empty or stats.get('total_current', 0) <= 0:
        return {
            "verdict": "Insufficient data to generate insights.",
            "concentration_risk": "Upload a portfolio with live prices.",
            "rebalancing_advice": [],
            "behavioral_signature": "Unknown",
            "simple_summary": "No data available.",
        }

    df = df.copy()
    total_inv   = float(stats.get('total_invested',  0))
    total_cur   = float(stats.get('total_current',   0))
    total_pnl   = float(stats.get('total_pnl',       0))
    pnl_pct     = float(stats.get('total_pnl_pct',   0))
    beta        = float(stats.get('weighted_beta',   1.0))
    pe          = float(stats.get('weighted_pe',     0))
    n           = int(stats.get('holdings_count',    len(df)))
    hhi         = float(stats.get('hhi',             0))
    max_w       = float(stats.get('max_single_weight', 0))
    health      = int(stats.get('health', 50))

    # ── 1. VERDICT ─────────────────────────────────────────────────
    verdict_parts = []

    # Return assessment
    if pnl_pct >= 30:
        verdict_parts.append(f"Outstanding returns of {pnl_pct:.1f}% — significantly outperforming broad market benchmarks.")
    elif pnl_pct >= 15:
        verdict_parts.append(f"Strong portfolio performance at {pnl_pct:.1f}% unrealised gain.")
    elif pnl_pct >= 5:
        verdict_parts.append(f"Moderate gains of {pnl_pct:.1f}% — broadly in line with market averages.")
    elif pnl_pct >= 0:
        verdict_parts.append(f"Marginal gains of {pnl_pct:.1f}% — portfolio is barely keeping pace with inflation.")
    elif pnl_pct >= -10:
        verdict_parts.append(f"Portfolio is underwater by {abs(pnl_pct):.1f}% — below cost basis.")
    else:
        verdict_parts.append(f"Significant drawdown of {abs(pnl_pct):.1f}% — portfolio requires urgent review.")

    # Risk assessment
    if beta >= 1.5:
        verdict_parts.append(f"Portfolio beta of {beta:.2f} indicates very high systematic risk — 50%+ more volatile than Nifty 50.")
    elif beta >= 1.2:
        verdict_parts.append(f"Above-average market risk (β={beta:.2f}) — portfolio amplifies market swings.")
    elif beta <= 0.7:
        verdict_parts.append(f"Defensive portfolio (β={beta:.2f}) — lower volatility than the broader market.")
    else:
        verdict_parts.append(f"Moderate market sensitivity (β={beta:.2f}) — moves broadly in line with Nifty 50.")

    # Valuation
    if pe > 0:
        if pe > 40:
            verdict_parts.append(f"Weighted P/E of {pe:.1f}x signals aggressive growth bets — premium valuation warrants caution.")
        elif pe > 25:
            verdict_parts.append(f"Portfolio trades at {pe:.1f}x earnings — growth-oriented but not overextended.")
        elif pe > 0:
            verdict_parts.append(f"Attractive valuation at {pe:.1f}x P/E — potential value opportunity.")

    verdict = " ".join(verdict_parts)

    # ── 2. CONCENTRATION RISK ──────────────────────────────────────
    conc_parts = []

    # Single stock concentration
    if max_w > 0 and 'current_val' in df.columns:
        top_stock = df.loc[df['current_val'].idxmax(), 'stock_name']
        top_pct   = max_w
        if top_pct > 30:
            conc_parts.append(f"🔴 CRITICAL: {top_stock} alone represents {top_pct:.1f}% of portfolio — catastrophic risk if this stock falls.")
        elif top_pct > 20:
            conc_parts.append(f"🟡 WARNING: {top_stock} is {top_pct:.1f}% of portfolio — single-stock risk elevated.")
        else:
            conc_parts.append(f"✅ Top holding {top_stock} at {top_pct:.1f}% — within acceptable limits.")

    # Sector concentration (HHI)
    if 'sector' in df.columns and total_cur > 0:
        sector_weights = (
            df.groupby('sector')['current_val'].sum() / total_cur * 100
        ).sort_values(ascending=False)

        top_sector  = sector_weights.index[0]
        top_sec_pct = sector_weights.iloc[0]

        if hhi > 0.30:
            conc_parts.append(
                f"🔴 Extreme sector concentration (HHI={hhi:.2f}): {top_sector} dominates at {top_sec_pct:.1f}% — no diversification benefit."
            )
        elif hhi > 0.18:
            conc_parts.append(
                f"🟡 Moderate sector concentration: {top_sector} at {top_sec_pct:.1f}% of portfolio."
            )
        else:
            sectors_above_10 = (sector_weights > 10).sum()
            conc_parts.append(
                f"✅ Well-diversified across {len(sector_weights)} sectors — no single sector above {top_sec_pct:.0f}%."
            )

        # Over-concentrated sectors (>35%)
        over_sectors = sector_weights[sector_weights > 35]
        for sec, pct in over_sectors.items():
            conc_parts.append(f"   ↳ {sec}: {pct:.1f}% — consider trimming to below 30%.")

    # Holdings count
    if n < 5:
        conc_parts.append(f"🔴 Only {n} holdings — dangerously undiversified. Target minimum 10–15 stocks.")
    elif n < 10:
        conc_parts.append(f"🟡 {n} holdings — moderate diversification. Consider expanding to 15+ for better risk spread.")
    else:
        conc_parts.append(f"✅ {n} holdings provide reasonable diversification.")

    concentration_risk = " | ".join(conc_parts)

    # ── 3. REBALANCING ADVICE ──────────────────────────────────────
    advice = []

    # Winners / losers
    if 'pnl_pct' in df.columns and 'stock_name' in df.columns:
        df_valid = df[df['ltp'] > 0] if 'ltp' in df.columns else df
        if not df_valid.empty:
            top_winners = df_valid.nlargest(3, 'pnl_pct')[['stock_name', 'pnl_pct']]
            top_losers  = df_valid.nsmallest(3, 'pnl_pct')[['stock_name', 'pnl_pct']]

            winner_str = ", ".join(
                f"{r['stock_name']} (+{r['pnl_pct']:.1f}%)"
                for _, r in top_winners.iterrows() if r['pnl_pct'] > 0
            )
            loser_str  = ", ".join(
                f"{r['stock_name']} ({r['pnl_pct']:.1f}%)"
                for _, r in top_losers.iterrows() if r['pnl_pct'] < 0
            )

            if winner_str:
                advice.append(f"📈 Top performers: {winner_str} — consider booking partial profits if these exceed 35% of portfolio.")
            if loser_str:
                advice.append(f"📉 Underperformers: {loser_str} — evaluate fundamentals; cut if thesis is broken.")

    # Beta-based advice
    if beta > 1.3:
        advice.append(f"⚖️ High beta ({beta:.2f}) — reduce cyclical/momentum stocks; add defensive sectors (FMCG, Pharma, IT services) to dampen volatility.")
    elif beta < 0.7:
        advice.append(f"⚖️ Low beta ({beta:.2f}) — portfolio is overly defensive. Consider adding quality growth names for better upside capture.")

    # Sector rebalancing
    if 'sector' in df.columns and total_cur > 0:
        sw = df.groupby('sector')['current_val'].sum() / total_cur * 100
        for sec, pct in sw.items():
            if pct > 35:
                advice.append(f"🏭 {sec} sector is {pct:.0f}% of portfolio — trim by ₹{(pct-30)/100*total_cur:,.0f} to cap at 30%.")

    # Concentration fix
    if max_w > 25:
        top_stock = df.loc[df['current_val'].idxmax(), 'stock_name']
        advice.append(f"🎯 Reduce {top_stock} from {max_w:.1f}% → below 20% — sell approximately ₹{(max_w-20)/100*total_cur:,.0f}.")

    # Diversification
    if n < 10:
        advice.append(f"➕ Add {10-n} more quality stocks to reach minimum 10-holding diversification threshold.")

    # Return-based
    if pnl_pct > 40:
        advice.append("💰 Portfolio up 40%+ — consider booking 20–25% profits and deploying into undervalued sectors.")
    elif pnl_pct < -15:
        advice.append("🛡️ Portfolio down significantly — avoid averaging down without fundamental conviction. Set strict stop-losses.")

    if not advice:
        advice.append("✅ Portfolio is well-balanced. Maintain current allocation and review quarterly.")

    # ── 4. BEHAVIORAL SIGNATURE ────────────────────────────────────
    if beta >= 1.4 and pnl_pct > 15:
        sig = "Aggressive Growth Investor"
    elif beta >= 1.4 and pnl_pct < 0:
        sig = "High-Risk, Distressed Speculator"
    elif beta < 0.8 and pnl_pct > 10:
        sig = "Conservative Compounder"
    elif beta < 0.8 and pnl_pct < 0:
        sig = "Defensive Wealth Preserver"
    elif hhi > 0.25:
        sig = "Concentrated Conviction Investor"
    elif n >= 20 and hhi < 0.12:
        sig = "Diversified Index-Hugger"
    elif pe > 35:
        sig = "Growth & Quality Seeker"
    elif pe > 0 and pe < 15:
        sig = "Deep Value Hunter"
    else:
        sig = "Balanced Moderate Investor"

    # ── 5. SIMPLE SUMMARY (plain English) ─────────────────────────
    pnl_word    = "gained" if total_pnl >= 0 else "lost"
    pnl_abs     = abs(total_pnl)
    risk_word   = "high-risk" if beta > 1.2 else ("low-risk" if beta < 0.8 else "moderate-risk")
    health_word = "excellent" if health >= 75 else ("good" if health >= 60 else ("average" if health >= 45 else "poor"))

    simple_summary = (
        f"Your portfolio of {n} stocks has {pnl_word} ₹{pnl_abs:,.0f} ({pnl_pct:+.1f}%) "
        f"on an investment of ₹{total_inv:,.0f}. "
        f"It is a {risk_word} portfolio (β={beta:.2f}) with {health_word} overall health ({health}/100). "
    )
    if 'sector' in df.columns:
        top_sec = df.groupby('sector')['current_val'].sum().idxmax()
        simple_summary += f"Your largest sector exposure is {top_sec}. "
    if advice:
        simple_summary += f"Key action: {advice[0]}"

    return {
        "verdict":              verdict,
        "concentration_risk":   concentration_risk,
        "rebalancing_advice":   advice,
        "behavioral_signature": sig,
        "simple_summary":       simple_summary,
    }

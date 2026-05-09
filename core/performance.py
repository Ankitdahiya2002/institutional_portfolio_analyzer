import pandas as pd
import numpy as np
from datetime import datetime, date
from scipy.optimize import newton

def xnpv(rate, cashflows):
    """Calculates the Net Present Value for a series of irregular cash flows."""
    return sum([cf / (1 + rate) ** ((t - cashflows[0][0]).days / 365.0) for t, cf in cashflows])

def calculate_xirr(df):
    """
    Calculates the XIRR of the portfolio.
    Requires 'invested_val' and 'current_val'.
    If 'buy_date' is absent, estimates using a default 1-year holding period.
    Returns a dict: {"value": float, "estimated": bool} or None on hard failure.
    """
    if df.empty:
        return None

    try:
        df = df.copy()
        estimated = False

        if 'buy_date' not in df.columns or df['buy_date'].isna().all():
            # No date info — assume 1-year holding period as a conservative estimate
            df['buy_date'] = pd.Timestamp.now() - pd.DateOffset(years=1)
            estimated = True
        else:
            df['buy_date'] = pd.to_datetime(df['buy_date'], errors='coerce')
            # Fill rows where date is NaT with 1-year-ago
            df['buy_date'] = df['buy_date'].fillna(pd.Timestamp.now() - pd.DateOffset(years=1))
            if df['buy_date'].isna().all():
                estimated = True

        cashflows = []
        df_valid = df[df['invested_val'].astype(float) > 0]
        if not df_valid.empty:
            dates = df_valid['buy_date']
            vals  = -df_valid['invested_val'].astype(float)
            cashflows.extend(list(zip(dates, vals)))

        total_current = float(df['current_val'].sum())
        if total_current > 0:
            cashflows.append((pd.Timestamp.now(), total_current))

        if not cashflows or len(cashflows) < 2:
            return None

        # Sort by date (required for XNPV)
        cashflows.sort(key=lambda x: x[0])

        xirr_val = round(newton(lambda r: xnpv(r, cashflows), 0.1) * 100, 2)
        return {"value": xirr_val, "estimated": estimated}
    except Exception as e:
        print(f"[XIRR] Solver failed: {e}")
        return None

def calculate_risk_metrics(returns_series, risk_free_rate=0.07):
    """
    Calculates Sharpe and Sortino ratios.
    returns_series: Annualized returns or daily returns.
    """
    if returns_series is None or len(returns_series) < 2:
        return {"sharpe": 0.0, "sortino": 0.0}
    
    avg_return = returns_series.mean()
    std_dev = returns_series.std()
    
    # Sharpe Ratio
    sharpe = (avg_return - risk_free_rate/252) / std_dev if std_dev > 0 else 0
    
    # Sortino Ratio (Downside deviation)
    downside_returns = returns_series[returns_series < 0]
    downside_std = downside_returns.std() if len(downside_returns) > 1 else std_dev
    sortino = (avg_return - risk_free_rate/252) / downside_std if downside_std > 0 else 0
    
    return {
        "sharpe": round(float(sharpe * np.sqrt(252)), 2),
        "sortino": round(float(sortino * np.sqrt(252)), 2)
    }


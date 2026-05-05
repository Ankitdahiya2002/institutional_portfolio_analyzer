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
    Requires 'buy_date', 'invested_val', and 'current_val'.
    """
    if 'buy_date' not in df.columns or df.empty:
        return 0.0
    
    try:
        # 1. Prepare cash flows
        # Investment is negative outflow
        cashflows = []
        df_valid = df[df['invested_val'].astype(float) > 0]
        if not df_valid.empty:
            dates = pd.to_datetime(df_valid['buy_date'])
            vals = -df_valid['invested_val'].astype(float)
            cashflows.extend(list(zip(dates, vals)))
        
        # Current value is positive inflow (if we sold today)
        total_current = df['current_val'].sum()
        if total_current > 0:
            cashflows.append((pd.to_datetime(datetime.now()), float(total_current)))
            
        if not cashflows or len(cashflows) < 2:
            return 0.0

        # 2. Solve for rate
        return newton(lambda r: xnpv(r, cashflows), 0.1) * 100
    except:
        return 0.0

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

def classify_taxes(df):
    """
    Classifies holdings into STCG and LTCG.
    Equity: > 1 year = LTCG
    """
    if 'buy_date' not in df.columns or df.empty:
        return {"ltcg_val": 0, "stcg_val": 0}
    
    df = df.copy()
    df['buy_date'] = pd.to_datetime(df['buy_date'], errors='coerce')
    today = pd.to_datetime(datetime.now())
    
    # Default to 365 days for Equity
    df['is_long_term'] = (today - df['buy_date']).dt.days > 365
    
    ltcg = df[df['is_long_term']]['pnl'].sum() if 'pnl' in df.columns else 0
    stcg = df[~df['is_long_term']]['pnl'].sum() if 'pnl' in df.columns else 0
    
    return {
        "ltcg_pnl": float(ltcg),
        "stcg_pnl": float(stcg),
        "ltcg_count": int(df['is_long_term'].sum()),
        "stcg_count": int((~df['is_long_term']).sum())
    }

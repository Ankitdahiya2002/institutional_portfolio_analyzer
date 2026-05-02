from typing import List, Optional
from pydantic import BaseModel, Field

class PortfolioItem(BaseModel):
    """The standardized internal representation of a single portfolio holding."""
    stock_name: str = Field(..., alias="stock_name")
    isin: Optional[str] = Field(None, alias="isin")
    quantity: float = Field(0.0, alias="quantity")
    avg_price: float = Field(0.0, alias="avg_price")
    invested_val: float = Field(0.0, alias="invested_val")
    asset_type: str = Field("Equity", alias="asset_type")
    
    # Enrichment Fields (Filled in Step 2)
    ltp: float = Field(0.0, alias="ltp")
    current_val: float = Field(0.0, alias="current_val")
    pnl: float = Field(0.0, alias="pnl")
    pnl_pct: float = Field(0.0, alias="pnl_pct")
    sector: str = Field("Unknown", alias="sector")
    ticker: Optional[str] = Field(None, alias="ticker")

class UniversalPortfolio(BaseModel):
    """The complete portfolio container."""
    items: List[PortfolioItem]
    total_invested: float = 0.0
    total_current: float = 0.0
    total_pnl: float = 0.0
    health_score: int = 0

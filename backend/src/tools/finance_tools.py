"""Finance/market data fetching tools - Yahoo Finance (unofficial) and Alpha Vantage."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx


@dataclass
class StockQuote:
    """A stock quote."""

    symbol: str
    name: str
    price: float
    change: float
    change_percent: float
    previous_close: float
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    volume: Optional[int] = None
    market_cap: Optional[float] = None


@dataclass
class MarketIndex:
    """A market index."""

    symbol: str
    name: str
    value: float
    change: float
    change_percent: float


@dataclass
class MarketSummary:
    """Overall market summary."""

    indices: list[MarketIndex]
    movers_up: list[StockQuote]
    movers_down: list[StockQuote]
    market_status: str  # pre_market, open, after_hours, closed
    as_of: datetime


# Major indices to track
MAJOR_INDICES = [
    ("^GSPC", "S&P 500"),
    ("^DJI", "Dow Jones"),
    ("^IXIC", "NASDAQ"),
    ("^RUT", "Russell 2000"),
    ("^VIX", "VIX"),
]

# Yahoo Finance API (unofficial - requires browser-like headers)
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"

# Browser-like headers for Yahoo Finance
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}


async def fetch_yahoo_quotes(symbols: list[str]) -> list[dict]:
    """Fetch quotes from Yahoo Finance API."""
    if not symbols:
        return []

    try:
        async with httpx.AsyncClient(timeout=30.0, headers=YAHOO_HEADERS) as client:
            response = await client.get(
                YAHOO_QUOTE_URL,
                params={"symbols": ",".join(symbols)},
            )
            response.raise_for_status()
            data = response.json()

        return data.get("quoteResponse", {}).get("result", [])

    except httpx.HTTPStatusError as e:
        # Yahoo Finance may require authentication - gracefully fail
        print(f"Yahoo Finance API unavailable (HTTP {e.response.status_code}): using fallback data")
        return []
    except Exception as e:
        print(f"Error fetching Yahoo Finance quotes: {e}")
        return []


async def get_market_indices() -> list[MarketIndex]:
    """Fetch major market indices."""
    symbols = [s[0] for s in MAJOR_INDICES]
    quotes = await fetch_yahoo_quotes(symbols)

    indices = []
    symbol_names = dict(MAJOR_INDICES)

    for quote in quotes:
        symbol = quote.get("symbol", "")
        indices.append(
            MarketIndex(
                symbol=symbol,
                name=symbol_names.get(symbol, quote.get("shortName", symbol)),
                value=quote.get("regularMarketPrice", 0),
                change=quote.get("regularMarketChange", 0),
                change_percent=quote.get("regularMarketChangePercent", 0),
            )
        )

    return indices


async def get_stock_quotes(symbols: list[str]) -> list[StockQuote]:
    """Fetch quotes for specific stocks."""
    quotes = await fetch_yahoo_quotes(symbols)

    results = []
    for quote in quotes:
        results.append(
            StockQuote(
                symbol=quote.get("symbol", ""),
                name=quote.get("shortName", quote.get("longName", "")),
                price=quote.get("regularMarketPrice", 0),
                change=quote.get("regularMarketChange", 0),
                change_percent=quote.get("regularMarketChangePercent", 0),
                previous_close=quote.get("regularMarketPreviousClose", 0),
                day_high=quote.get("regularMarketDayHigh"),
                day_low=quote.get("regularMarketDayLow"),
                volume=quote.get("regularMarketVolume"),
                market_cap=quote.get("marketCap"),
            )
        )

    return results


async def get_market_movers() -> tuple[list[StockQuote], list[StockQuote]]:
    """Get top gainers and losers.

    Returns:
        Tuple of (gainers, losers)
    """
    # Yahoo Finance screener endpoints (may require adjustment)
    # For now, use a list of commonly watched stocks
    watched_stocks = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
        "JPM", "V", "JNJ", "UNH", "HD", "PG", "MA", "DIS",
        "NFLX", "PYPL", "INTC", "AMD", "CRM",
    ]

    quotes = await get_stock_quotes(watched_stocks)

    # Sort by change percent
    sorted_quotes = sorted(quotes, key=lambda q: q.change_percent, reverse=True)

    gainers = [q for q in sorted_quotes if q.change_percent > 0][:5]
    losers = [q for q in sorted_quotes if q.change_percent < 0][-5:][::-1]

    return gainers, losers


async def get_market_summary() -> MarketSummary:
    """Get complete market summary."""
    indices = await get_market_indices()
    gainers, losers = await get_market_movers()

    # Determine market status based on time (simplified)
    now = datetime.now()
    hour = now.hour

    if hour < 9 or (hour == 9 and now.minute < 30):
        market_status = "pre_market"
    elif hour < 16:
        market_status = "open"
    elif hour < 20:
        market_status = "after_hours"
    else:
        market_status = "closed"

    # Weekend check
    if now.weekday() >= 5:
        market_status = "closed"

    return MarketSummary(
        indices=indices,
        movers_up=gainers,
        movers_down=losers,
        market_status=market_status,
        as_of=now,
    )


def format_change(value: float) -> str:
    """Format a change value with +/- sign."""
    if value > 0:
        return f"+{value:.2f}"
    return f"{value:.2f}"


def format_change_percent(value: float) -> str:
    """Format a percentage change with +/- sign."""
    if value > 0:
        return f"+{value:.2f}%"
    return f"{value:.2f}%"


def format_market_for_agent(summary: MarketSummary) -> str:
    """Format market data for the Claude agent."""
    lines = ["# Market Summary\n"]

    # Market status
    status_text = {
        "pre_market": "Pre-Market Trading",
        "open": "Markets Open",
        "after_hours": "After-Hours Trading",
        "closed": "Markets Closed",
    }
    lines.append(f"**Status:** {status_text.get(summary.market_status, 'Unknown')}")
    lines.append(f"**As of:** {summary.as_of.strftime('%I:%M %p %Z')}\n")

    # Major indices
    lines.append("## Major Indices\n")
    for index in summary.indices:
        direction = "🟢" if index.change >= 0 else "🔴"
        lines.append(
            f"- **{index.name}** ({index.symbol}): {index.value:,.2f} "
            f"{direction} {format_change(index.change)} ({format_change_percent(index.change_percent)})"
        )
    lines.append("")

    # Top movers
    if summary.movers_up:
        lines.append("## Top Gainers\n")
        for stock in summary.movers_up:
            lines.append(
                f"- **{stock.symbol}** ({stock.name}): ${stock.price:.2f} "
                f"🟢 {format_change_percent(stock.change_percent)}"
            )
        lines.append("")

    if summary.movers_down:
        lines.append("## Biggest Decliners\n")
        for stock in summary.movers_down:
            lines.append(
                f"- **{stock.symbol}** ({stock.name}): ${stock.price:.2f} "
                f"🔴 {format_change_percent(stock.change_percent)}"
            )
        lines.append("")

    return "\n".join(lines)

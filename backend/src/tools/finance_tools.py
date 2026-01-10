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
    data_time: Optional[datetime] = None  # When this price data is from


@dataclass
class MarketSummary:
    """Overall market summary."""

    indices: list[MarketIndex]
    movers_up: list[StockQuote]
    movers_down: list[StockQuote]
    market_status: str  # pre_market, open, after_hours, closed
    as_of: datetime
    data_date: Optional[datetime] = None  # Trading date of the data


# Major indices to track
MAJOR_INDICES = [
    ("^GSPC", "S&P 500"),
    ("^DJI", "Dow Jones"),
    ("^IXIC", "NASDAQ"),
    ("^RUT", "Russell 2000"),
    ("^VIX", "VIX"),
]

# Yahoo Finance Chart API (v8) - works without authentication
YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart"

# Browser-like headers for Yahoo Finance
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


async def fetch_yahoo_chart(symbol: str) -> dict | None:
    """Fetch chart data from Yahoo Finance v8 API for a single symbol."""
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=YAHOO_HEADERS) as client:
            response = await client.get(
                f"{YAHOO_CHART_URL}/{symbol}",
                params={"interval": "1d", "range": "1d"},
            )
            response.raise_for_status()
            data = response.json()

        result = data.get("chart", {}).get("result")
        if result and len(result) > 0:
            return result[0].get("meta", {})
        return None

    except Exception as e:
        print(f"Error fetching Yahoo Finance chart for {symbol}: {e}")
        return None


async def fetch_yahoo_quotes(symbols: list[str]) -> list[dict]:
    """Fetch quotes from Yahoo Finance Chart API (v8) for multiple symbols."""
    if not symbols:
        return []

    import asyncio

    async def fetch_single(symbol: str) -> dict | None:
        meta = await fetch_yahoo_chart(symbol)
        if meta:
            # Get the actual market data timestamp
            market_time = meta.get("regularMarketTime")
            data_time = datetime.fromtimestamp(market_time) if market_time else None
            return {
                "symbol": meta.get("symbol", symbol),
                "shortName": meta.get("shortName", ""),
                "longName": meta.get("longName", ""),
                "regularMarketPrice": meta.get("regularMarketPrice", 0),
                "regularMarketPreviousClose": meta.get("chartPreviousClose", 0),
                "regularMarketChange": meta.get("regularMarketPrice", 0) - meta.get("chartPreviousClose", 0),
                "regularMarketChangePercent": (
                    ((meta.get("regularMarketPrice", 0) - meta.get("chartPreviousClose", 0))
                     / meta.get("chartPreviousClose", 1)) * 100
                    if meta.get("chartPreviousClose", 0) != 0 else 0
                ),
                "regularMarketDayHigh": meta.get("regularMarketDayHigh"),
                "regularMarketDayLow": meta.get("regularMarketDayLow"),
                "regularMarketVolume": meta.get("regularMarketVolume"),
                "marketCap": meta.get("marketCap"),
                "dataTime": data_time,
            }
        return None

    results = await asyncio.gather(*[fetch_single(s) for s in symbols])
    return [r for r in results if r is not None]


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
                data_time=quote.get("dataTime"),
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


async def get_market_movers(
    movers_limit: Optional[int] = None,
) -> tuple[list[StockQuote], list[StockQuote]]:
    """Get top gainers and losers.

    Args:
        movers_limit: If set, return top N gainers and top N losers.
                      None = default (5 each). "Most important" = largest absolute change.

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

    # Sort by absolute change percent for "most important" movers
    sorted_by_abs_change = sorted(quotes, key=lambda q: abs(q.change_percent), reverse=True)

    # Separate gainers and losers, preserving "most important" order
    gainers = [q for q in sorted_by_abs_change if q.change_percent > 0]
    losers = [q for q in sorted_by_abs_change if q.change_percent < 0]

    # Apply limit
    limit = movers_limit if movers_limit is not None else 5
    gainers = gainers[:limit]
    losers = losers[:limit]

    return gainers, losers


async def get_market_summary(
    movers_limit: Optional[int] = None,
    user_timezone: str = None,
) -> MarketSummary:
    """Get complete market summary.

    Args:
        movers_limit: If set, limit gainers/losers to N each. None = default (5 each).
        user_timezone: IANA timezone string for user's local time context
    """
    from zoneinfo import ZoneInfo

    indices = await get_market_indices()
    gainers, losers = await get_market_movers(movers_limit=movers_limit)

    # Get the data date from the first index with a timestamp
    data_date = None
    for idx in indices:
        if idx.data_time:
            data_date = idx.data_time
            break

    # Determine market status based on Eastern Time (NYSE trading hours)
    # Markets operate 9:30 AM - 4:00 PM ET regardless of user's timezone
    try:
        et_tz = ZoneInfo("America/New_York")
    except Exception:
        et_tz = ZoneInfo("UTC")
    now_et = datetime.now(et_tz)
    hour = now_et.hour

    if hour < 9 or (hour == 9 and now_et.minute < 30):
        market_status = "pre_market"
    elif hour < 16:
        market_status = "open"
    elif hour < 20:
        market_status = "after_hours"
    else:
        market_status = "closed"

    # Weekend check (also in ET)
    if now_et.weekday() >= 5:
        market_status = "closed"

    return MarketSummary(
        indices=indices,
        movers_up=gainers,
        movers_down=losers,
        market_status=market_status,
        as_of=now_et,
        data_date=data_date,
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


def format_market_for_agent(summary: MarketSummary, user_timezone: str = None) -> str:
    """Format market data for the Claude agent.

    Args:
        summary: MarketSummary object with market data
        user_timezone: IANA timezone string for date comparison
    """
    from src.utils.timezone import get_user_today

    lines = ["# Market Summary\n"]

    # Market status
    status_text = {
        "pre_market": "Pre-Market Trading",
        "open": "Markets Open",
        "after_hours": "After-Hours Trading",
        "closed": "Markets Closed",
    }
    lines.append(f"**Market Status:** {status_text.get(summary.market_status, 'Unknown')}")

    # Show trading date context
    if summary.data_date:
        trading_date = summary.data_date.strftime('%A, %B %d, %Y')
        trading_time = summary.data_date.strftime('%I:%M %p ET')
        today = get_user_today(user_timezone)
        data_day = summary.data_date.date()

        if data_day == today:
            date_context = f"Today ({trading_date})"
        elif (today - data_day).days == 1:
            date_context = f"Yesterday ({trading_date})"
        else:
            date_context = trading_date

        lines.append(f"**Trading Date:** {date_context}")
        lines.append(f"**Prices as of:** {trading_time}")
    else:
        lines.append(f"**Fetched at:** {summary.as_of.strftime('%I:%M %p')}")

    lines.append("")

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

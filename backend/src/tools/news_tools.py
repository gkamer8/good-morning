"""News data fetching tools - RSS feeds and NewsAPI integration."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import feedparser
import httpx

from src.config import get_settings


@dataclass
class NewsArticle:
    """A news article."""

    title: str
    summary: str
    source: str
    url: str
    published: Optional[datetime] = None
    category: Optional[str] = None
    author: Optional[str] = None


# User-Agent header to avoid 403 errors from some RSS servers
USER_AGENT = "MorningDrive/1.0 (Personal News Aggregator)"

# RSS Feed URLs for major news sources
RSS_FEEDS = {
    # General News
    "bbc": {
        "world": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "technology": "http://feeds.bbci.co.uk/news/technology/rss.xml",
        "business": "http://feeds.bbci.co.uk/news/business/rss.xml",
        "top": "http://feeds.bbci.co.uk/news/rss.xml",
        "science": "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "health": "http://feeds.bbci.co.uk/news/health/rss.xml",
        "entertainment": "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    },
    "npr": {
        "top": "https://feeds.npr.org/1001/rss.xml",
        "world": "https://feeds.npr.org/1004/rss.xml",
        "technology": "https://feeds.npr.org/1019/rss.xml",
        "business": "https://feeds.npr.org/1006/rss.xml",
        "science": "https://feeds.npr.org/1007/rss.xml",
        "health": "https://feeds.npr.org/1128/rss.xml",
    },
    "nyt": {
        "top": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "world": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "technology": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "business": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "science": "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
        "health": "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
    },
    # Note: Reuters RSS feeds are no longer publicly available
    "techcrunch": {
        "technology": "https://techcrunch.com/feed/",
        "top": "https://techcrunch.com/feed/",
    },
    "hackernews": {
        "technology": "https://hnrss.org/frontpage",
        "top": "https://hnrss.org/frontpage",
    },
    "arstechnica": {
        "technology": "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "science": "https://feeds.arstechnica.com/arstechnica/science",
        "top": "https://feeds.arstechnica.com/arstechnica/index",
    },
}


async def fetch_rss_feed(url: str, source: str, category: str) -> list[NewsArticle]:
    """Fetch and parse an RSS feed."""
    try:
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

        feed = feedparser.parse(response.text)
        articles = []

        for entry in feed.entries[:10]:  # Limit to 10 per feed
            # Parse published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])

            # Get summary, handling different RSS formats
            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
            elif hasattr(entry, "description"):
                summary = entry.description

            # Strip HTML tags from summary (basic)
            import re
            summary = re.sub(r"<[^>]+>", "", summary)
            summary = summary[:500]  # Limit length

            articles.append(
                NewsArticle(
                    title=entry.get("title", ""),
                    summary=summary,
                    source=source,
                    url=entry.get("link", ""),
                    published=published,
                    category=category,
                    author=entry.get("author"),
                )
            )

        return articles

    except Exception as e:
        print(f"Error fetching RSS feed {url}: {e}")
        return []


async def fetch_news_from_rss(
    sources: list[str],
    topics: list[str],
    limit_per_source: int = 5,
) -> list[NewsArticle]:
    """Fetch news from multiple RSS sources and topics."""
    tasks = []

    for source in sources:
        if source not in RSS_FEEDS:
            continue

        source_feeds = RSS_FEEDS[source]
        for topic in topics:
            if topic in source_feeds:
                tasks.append(fetch_rss_feed(source_feeds[topic], source, topic))
            elif "top" in source_feeds:
                # Fall back to top news if specific topic not available
                tasks.append(fetch_rss_feed(source_feeds["top"], source, "top"))

    # Fetch all feeds concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten and deduplicate
    all_articles = []
    seen_titles = set()

    for result in results:
        if isinstance(result, list):
            for article in result:
                if article.title not in seen_titles:
                    seen_titles.add(article.title)
                    all_articles.append(article)

    # Sort by published date (most recent first)
    all_articles.sort(
        key=lambda a: a.published or datetime.min,
        reverse=True,
    )

    return all_articles[:limit_per_source * len(sources)]


async def fetch_news_from_newsapi(
    topics: list[str],
    limit: int = 10,
) -> list[NewsArticle]:
    """Fetch news from NewsAPI (requires API key)."""
    settings = get_settings()
    if not settings.news_api_key:
        return []

    articles = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for topic in topics:
            try:
                response = await client.get(
                    "https://newsapi.org/v2/top-headlines",
                    params={
                        "apiKey": settings.news_api_key,
                        "category": topic,
                        "language": "en",
                        "pageSize": limit,
                    },
                )
                response.raise_for_status()
                data = response.json()

                for item in data.get("articles", []):
                    published = None
                    if item.get("publishedAt"):
                        try:
                            published = datetime.fromisoformat(
                                item["publishedAt"].replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass

                    articles.append(
                        NewsArticle(
                            title=item.get("title", ""),
                            summary=item.get("description", ""),
                            source=item.get("source", {}).get("name", "NewsAPI"),
                            url=item.get("url", ""),
                            published=published,
                            category=topic,
                            author=item.get("author"),
                        )
                    )

            except Exception as e:
                print(f"Error fetching from NewsAPI for {topic}: {e}")

    return articles


async def get_top_news(
    sources: list[str] = ["bbc", "npr", "nyt"],
    topics: list[str] = ["top", "world", "technology", "business"],
    limit: int = 15,
) -> list[NewsArticle]:
    """Get top news stories from configured sources.

    This is the main entry point for the news agent.
    """
    # Fetch from RSS (always available)
    rss_articles = await fetch_news_from_rss(sources, topics, limit_per_source=5)

    # Optionally supplement with NewsAPI
    newsapi_articles = await fetch_news_from_newsapi(topics, limit=5)

    # Combine and deduplicate
    all_articles = rss_articles + newsapi_articles
    seen_titles = set()
    unique_articles = []

    for article in all_articles:
        # Normalize title for deduplication
        title_key = article.title.lower().strip()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)

    # Sort by recency and return top articles
    unique_articles.sort(
        key=lambda a: a.published or datetime.min,
        reverse=True,
    )

    return unique_articles[:limit]


def format_news_for_agent(articles: list[NewsArticle]) -> str:
    """Format news articles for the Claude agent."""
    if not articles:
        return "No news articles available."

    lines = ["# Top News Stories\n"]

    for i, article in enumerate(articles, 1):
        lines.append(f"## {i}. {article.title}")
        lines.append(f"**Source:** {article.source} | **Category:** {article.category or 'General'}")
        if article.published:
            lines.append(f"**Published:** {article.published.strftime('%B %d, %Y at %I:%M %p')}")
        lines.append(f"\n{article.summary}\n")
        lines.append("---\n")

    return "\n".join(lines)

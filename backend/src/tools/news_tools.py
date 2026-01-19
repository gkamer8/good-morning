"""News data fetching tools - RSS feeds and NewsAPI integration."""

import asyncio
import re
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

# Mapping from NewsAPI source names to normalized keys (matching RSS_FEEDS keys)
# This ensures per-source limiting works correctly across both sources
NEWSAPI_SOURCE_MAPPING = {
    "bbc news": "bbc",
    "bbc": "bbc",
    "bbc.com": "bbc",
    "npr": "npr",
    "npr news": "npr",
    "the new york times": "nyt",
    "new york times": "nyt",
    "nytimes": "nyt",
    "nyt": "nyt",
    "techcrunch": "techcrunch",
    "ars technica": "arstechnica",
    "hacker news": "hackernews",
}


def normalize_source_name(source: str) -> str:
    """Normalize source name to a canonical key for per-source limiting."""
    source_lower = source.lower().strip()
    return NEWSAPI_SOURCE_MAPPING.get(source_lower, source_lower)


# Valid NewsAPI categories - NewsAPI only accepts these specific values
# See: https://newsapi.org/docs/endpoints/top-headlines
NEWSAPI_VALID_CATEGORIES = {"business", "entertainment", "general", "health", "science", "sports", "technology"}

# Mapping from our topic names to NewsAPI categories
NEWSAPI_TOPIC_MAPPING = {
    "top": "general",
    "world": "general",  # NewsAPI doesn't have a world category
    "business": "business",
    "technology": "technology",
    "science": "science",
    "health": "health",
    "entertainment": "entertainment",
    "sports": "sports",
}


def get_newsapi_category(topic: str) -> Optional[str]:
    """Map our topic name to a valid NewsAPI category, or None if invalid."""
    topic_lower = topic.lower().strip()
    # First check our mapping
    if topic_lower in NEWSAPI_TOPIC_MAPPING:
        return NEWSAPI_TOPIC_MAPPING[topic_lower]
    # If it's already a valid category, use it directly
    if topic_lower in NEWSAPI_VALID_CATEGORIES:
        return topic_lower
    # Invalid topic for NewsAPI
    return None

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


async def fetch_rss_feed(url: str, source: str, category: str) -> tuple[list[NewsArticle], Optional[NewsFetchError]]:
    """Fetch and parse an RSS feed.

    Returns:
        Tuple of (articles, error) where error is None on success.
    """
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

        return articles, None

    except Exception as e:
        error_msg = str(e)
        print(f"Error fetching RSS feed {url}: {error_msg}")
        return [], NewsFetchError(source=source, category=category, error_message=error_msg)


async def fetch_news_from_rss(
    sources: list[str],
    topics: list[str],
    limit_per_source: int = 5,
) -> tuple[list[NewsArticle], list[NewsFetchError]]:
    """Fetch news from multiple RSS sources and topics.

    Returns:
        Tuple of (articles, errors) where errors is a list of any feed failures.
    """
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

    # Flatten and deduplicate, collecting errors
    all_articles = []
    all_errors = []
    seen_titles = set()

    for result in results:
        if isinstance(result, Exception):
            # asyncio.gather returned an exception (shouldn't happen with our error handling)
            all_errors.append(NewsFetchError(
                source="unknown",
                category="unknown",
                error_message=str(result)
            ))
        elif isinstance(result, tuple):
            articles, error = result
            if error:
                all_errors.append(error)
            for article in articles:
                if article.title not in seen_titles:
                    seen_titles.add(article.title)
                    all_articles.append(article)

    # Sort by published date (most recent first)
    all_articles.sort(
        key=lambda a: a.published or datetime.min,
        reverse=True,
    )

    return all_articles[:limit_per_source * len(sources)], all_errors


async def fetch_news_from_newsapi(
    topics: list[str],
    limit: int = 10,
) -> tuple[list[NewsArticle], list[NewsFetchError]]:
    """Fetch news from NewsAPI (requires API key).

    Returns:
        Tuple of (articles, errors) where errors is a list of any API failures.
    """
    settings = get_settings()
    if not settings.news_api_key:
        return [], []

    articles = []
    errors = []
    # Track which categories we've already fetched to avoid duplicates
    # (e.g., both "top" and "world" map to "general")
    fetched_categories = set()

    async with httpx.AsyncClient(timeout=30.0) as client:
        for topic in topics:
            # Map our topic to a valid NewsAPI category
            category = get_newsapi_category(topic)
            if category is None:
                print(f"Skipping NewsAPI fetch for invalid category: {topic}")
                continue

            # Skip if we've already fetched this category
            if category in fetched_categories:
                continue
            fetched_categories.add(category)

            try:
                response = await client.get(
                    "https://newsapi.org/v2/top-headlines",
                    params={
                        "apiKey": settings.news_api_key,
                        "category": category,
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
                            category=topic,  # Keep original topic for display
                            author=item.get("author"),
                        )
                    )

            except Exception as e:
                error_msg = str(e)
                print(f"Error fetching from NewsAPI for {topic} (category={category}): {error_msg}")
                errors.append(NewsFetchError(source="newsapi", category=topic, error_message=error_msg))

    return articles, errors


async def get_top_news(
    sources: list[str] = ["bbc", "npr", "nyt"],
    topics: list[str] = ["top", "world", "technology", "business"],
    limit: int = 15,
    stories_per_source: Optional[int] = None,
) -> NewsFetchResult:
    """Get top news stories from configured sources.

    This is the main entry point for the news agent.

    Args:
        sources: News sources to fetch from
        topics: Topics/categories to include
        limit: Total limit on articles returned
        stories_per_source: If set, limit to N stories per source (most recent first, no repeats)

    Returns:
        NewsFetchResult containing articles and any errors that occurred during fetching.
    """
    all_errors = []

    # Fetch from RSS (always available)
    rss_articles, rss_errors = await fetch_news_from_rss(sources, topics, limit_per_source=5)
    all_errors.extend(rss_errors)

    # Optionally supplement with NewsAPI
    newsapi_articles, newsapi_errors = await fetch_news_from_newsapi(topics, limit=5)
    all_errors.extend(newsapi_errors)

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

    # Sort by recency (most recent = most important for news)
    unique_articles.sort(
        key=lambda a: a.published or datetime.min,
        reverse=True,
    )

    # If stories_per_source is set, limit to N stories per source
    if stories_per_source is not None:
        source_counts: dict[str, int] = {}
        filtered_articles = []
        for article in unique_articles:
            # Use normalized source name to handle NewsAPI vs RSS differences
            # (e.g., "BBC News" and "bbc" should be treated as the same source)
            source_key = normalize_source_name(article.source)
            if source_counts.get(source_key, 0) < stories_per_source:
                filtered_articles.append(article)
                source_counts[source_key] = source_counts.get(source_key, 0) + 1
        unique_articles = filtered_articles

    return NewsFetchResult(
        articles=unique_articles[:limit],
        errors=all_errors,
    )


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


import os
import requests

from datetime import datetime, timezone
from dotenv import load_dotenv

from database.db import get_connection, create_table


# Load API key
load_dotenv()

API_KEY = os.getenv("GNEWS_API_KEY")

BASE_URL = "https://gnews.io/api/v4"

MAX_ARTICLES = 10


# Each category has its own collection configuration
CATEGORIES = {

    "International": {
        "endpoint": "top-headlines",
        "params": {
            "category": "world"
        }
    },

    "National": {
        "endpoint": "top-headlines",
        "params": {
            "category": "nation",
            "country": "in"
        }
    },

    "Kerala": {
        "endpoint": "search",
        "params": {
            "q": '"Kerala" AND (government OR politics OR infrastructure OR policy)',
            "country": "in"
        }
    },

    "Local": {
        "endpoint": "search",
        "params": {
            "q": '"Thrissur" OR "Irinjalakuda" OR "Kochi" OR "Kozhikode" OR "Kannur" OR "Palakkad"',
            "country": "in"
        }
    },

    "Sports": {
        "endpoint": "top-headlines",
        "params": {
            "category": "sports",
            "country": "in"
        }
    },

    "Business": {
        "endpoint": "top-headlines",
        "params": {
            "category": "business",
            "country": "in"
        }
    },

    "Technology": {
        "endpoint": "top-headlines",
        "params": {
            "category": "technology",
            "country": "in"
        }
    },

    "Science": {
        "endpoint": "top-headlines",
        "params": {
            "category": "science",
            "country": "in"
        }
    },

    "Education": {
        "endpoint": "search",
        "params": {
            "q": 'India AND (education OR university OR examination OR admission)',
            "country": "in"
        }
    },

    "Culture & Entertainment": {
        "endpoint": "search",
        "params": {
            "q": '(India OR Kerala) AND (culture OR festival OR cinema OR art OR heritage)',
            "country": "in"
        }
    }

}


def fetch_news(category, config):

    endpoint = config["endpoint"]

    params = config["params"].copy()

    params["lang"] = "en"
    params["max"] = MAX_ARTICLES

    headers = {
        "X-Api-Key": API_KEY
    }

    url = f"{BASE_URL}/{endpoint}"

    try:

        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        articles = data.get("articles", [])

        print(
            f"{category}: "
            f"{len(articles)} articles fetched"
        )

        return articles

    except requests.exceptions.RequestException as error:

        print(f"Error fetching {category}: {error}")

        return []


def save_articles(articles, category):

    conn = get_connection()

    saved = 0

    for article in articles:

        source = article.get("source") or {}

        title = article.get("title")
        url = article.get("url")

        if not title or not url:
            continue

        cursor = conn.execute("""

            INSERT OR IGNORE INTO articles

            (
                title,
                description,
                source,
                url,
                published_at,
                category,
                fetched_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?)

        """, (

            title,
            article.get("description"),
            source.get("name"),
            url,
            article.get("publishedAt"),
            category,
            datetime.now(timezone.utc).isoformat()

        ))

        if cursor.rowcount > 0:
            saved += 1

    conn.commit()
    conn.close()

    return saved


def collect_news():

    if not API_KEY:
        raise ValueError(
            "GNEWS_API_KEY is missing in .env"
        )

    create_table()

    total_fetched = 0
    total_saved = 0

    print("\n========== DAILY SCOPE ==========")
    print("Starting news collection...\n")

    for category, config in CATEGORIES.items():

        print(f"\nCollecting: {category}")

        articles = fetch_news(category, config)

        saved = save_articles(articles, category)

        total_fetched += len(articles)
        total_saved += saved

        print(f"New articles saved: {saved}")

    print("\n========== COLLECTION SUMMARY ==========")

    print(f"Categories processed: {len(CATEGORIES)}")

    print(f"Total articles fetched: {total_fetched}")

    print(f"New unique URLs saved: {total_saved}")

    print("\nNews collection completed!")


if __name__ == "__main__":

    collect_news()

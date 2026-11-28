
from datetime import datetime, timezone

from database.db import (
    get_connection,
    create_table,
    parse_date
)


# Maximum points for each criterion
MAX_IMPORTANCE = 25
MAX_RELEVANCE = 25
MAX_CREDIBILITY = 20
MAX_RECENCY = 15
MAX_COVERAGE = 15


# Initial keyword groups for importance assessment
IMPORTANCE_KEYWORDS = {

    "critical": [
        "disaster",
        "earthquake",
        "flood",
        "cyclone",
        "war",
        "terrorist attack",
        "emergency",
        "major accident",
        "pandemic"
    ],

    "high": [
        "election",
        "government policy",
        "supreme court",
        "high court",
        "budget",
        "economic crisis",
        "resignation",
        "rescue operation",
        "major breakthrough",
        "international agreement"
    ],

    "medium": [
        "infrastructure",
        "development",
        "education policy",
        "investment",
        "technology",
        "research",
        "championship",
        "unemployment",
        "price hike",
        "protest"
    ]

}


def calculate_importance(title, descriptions):

    text = (title + " " + descriptions).lower()

    if any(word in text for word in IMPORTANCE_KEYWORDS["critical"]):
        return 25

    if any(word in text for word in IMPORTANCE_KEYWORDS["high"]):
        return 20

    if any(word in text for word in IMPORTANCE_KEYWORDS["medium"]):
        return 15

    return 8


def calculate_relevance(title, descriptions, categories):

    text = (title + " " + descriptions).lower()

    categories = set(categories)

    # Direct Kerala coverage
    if categories.intersection({"Kerala", "Local"}):
        return 25

    if "kerala" in text:
        return 25

    # National Indian coverage
    if "National" in categories or "india" in text:
        return 22

    # International news with no direct Indian connection
    if "International" in categories:
        return 12

    # Other categories
    return 15


def calculate_credibility(sources, conn):

    if not sources:
        return 10

    scores = []

    for source in sources:

        row = conn.execute("""
            SELECT credibility_score
            FROM sources
            WHERE LOWER(source_name) = LOWER(?)
        """, (source,)).fetchone()

        if row is None:

            # Unknown publishers receive a neutral score
            credibility = 50

            conn.execute("""
                INSERT OR IGNORE INTO sources
                (source_name, credibility_score)
                VALUES (?, ?)
            """, (source, credibility))

        else:

            credibility = row["credibility_score"]

        scores.append(credibility)

    average_score = sum(scores) / len(scores)

    # Convert 0-100 credibility to 0-20 points
    return round((average_score / 100) * MAX_CREDIBILITY, 2)


def calculate_recency(dates):

    valid_dates = [
        date for date in dates if date is not None
    ]

    if not valid_dates:
        return 0

    # Use the newest publication date in the event
    latest_date = max(valid_dates)

    now = datetime.now(timezone.utc)

    age_hours = max(
        0,
        (now - latest_date).total_seconds() / 3600
    )

    if age_hours <= 3:
        return 15

    elif age_hours <= 6:
        return 12

    elif age_hours <= 12:
        return 9

    elif age_hours <= 24:
        return 6

    elif age_hours <= 48:
        return 3

    return 0


def calculate_coverage(sources):

    # Count distinct publishers
    count = len(set(sources))

    if count >= 5:
        return 15

    elif count == 4:
        return 12

    elif count == 3:
        return 9

    elif count == 2:
        return 6

    elif count == 1:
        return 3

    return 0


def rank_events():

    create_table()

    conn = get_connection()

    # Fetch all events
    events = conn.execute("""
        SELECT *
        FROM events
    """).fetchall()

    ranked_events = []

    for event in events:

        # Fetch all articles belonging to this event
        articles = conn.execute("""
            SELECT
                title,
                description,
                source,
                category,
                published_at,
                fetched_at
            FROM articles
            WHERE event_id = ?
        """, (event["id"],)).fetchall()

        if not articles:
            continue

        # Combine article information
        titles = [
            article["title"] or ""
            for article in articles
        ]

        descriptions = [
            article["description"] or ""
            for article in articles
        ]

        sources = list(set(
            article["source"]
            for article in articles
            if article["source"]
        ))

        categories = [
            article["category"]
            for article in articles
            if article["category"]
        ]

        dates = []

        for article in articles:

            date = (
                parse_date(article["published_at"])
                or parse_date(article["fetched_at"])
            )

            if date:
                dates.append(date)

        # Use the canonical event title and all descriptions
        title = event["canonical_title"]

        combined_descriptions = " ".join(
            descriptions + titles
        )

        # Calculate all five criteria
        importance = calculate_importance(
            title,
            combined_descriptions
        )

        relevance = calculate_relevance(
            title,
            combined_descriptions,
            categories
        )

        credibility = calculate_credibility(
            sources,
            conn
        )

        recency = calculate_recency(dates)

        coverage = calculate_coverage(sources)

        # Calculate total score
        total_score = round(
            importance
            + relevance
            + credibility
            + recency
            + coverage,
            2
        )

        # Save scores in the events table
        conn.execute("""
            UPDATE events
            SET
                importance_score = ?,
                relevance_score = ?,
                credibility_score = ?,
                recency_score = ?,
                coverage_score = ?,
                ranking_score = ?
            WHERE id = ?
        """, (
            importance,
            relevance,
            credibility,
            recency,
            coverage,
            total_score,
            event["id"]
        ))

        ranked_events.append({
            "id": event["id"],
            "title": title,
            "importance": importance,
            "relevance": relevance,
            "credibility": credibility,
            "recency": recency,
            "coverage": coverage,
            "total": total_score
        })

    conn.commit()
    conn.close()

    # Sort events by their final score
    ranked_events.sort(
        key=lambda event: event["total"],
        reverse=True
    )

    print("\n========== DAILY SCOPE RANKINGS ==========")

    for position, event in enumerate(ranked_events, start=1):

        print(f"\nRank: {position}")
        print(f"Event ID: {event['id']}")
        print(f"Title: {event['title']}")

        print(
            f"Importance: {event['importance']}/25"
        )

        print(
            f"Relevance: {event['relevance']}/25"
        )

        print(
            f"Credibility: {event['credibility']}/20"
        )

        print(
            f"Recency: {event['recency']}/15"
        )

        print(
            f"Coverage: {event['coverage']}/15"
        )

        print(
            f"FINAL SCORE: {event['total']}/100"
        )

    print("\n========== RANKING COMPLETED ==========")

    print(f"Events ranked: {len(ranked_events)}")


if __name__ == "__main__":

    rank_events()


from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from database.db import (
    get_connection,
    create_table,
    parse_date
)


# Selection settings
MAX_EVENTS_PER_CATEGORY = 10
MIN_EVENTS_PER_CATEGORY = 7
MIN_RANKING_SCORE = 40

REPORT_TIMEZONE = ZoneInfo("Asia/Kolkata")
CATEGORIES = [
    "International",
    "National",
    "Kerala",
    "Local",
    "Sports",
    "Business",
    "Technology",
    "Science",
    "Education",
    "Culture & Entertainment"
]


def get_report_window():

    now = datetime.now(REPORT_TIMEZONE)

    # Find the most recent completed 7 AM reporting boundary
    report_end = now.replace(
        hour=7,
        minute=0,
        second=0,
        microsecond=0
    )

    if now < report_end:
        report_end -= timedelta(days=1)

    report_start = report_end - timedelta(days=1)

    return (
        report_start.astimezone(timezone.utc),
        report_end.astimezone(timezone.utc),
        report_end.date().isoformat()
    )


def get_category_events(conn, start_time, end_time):

    articles = conn.execute("""
        SELECT
            id,
            event_id,
            category,
            published_at,
            fetched_at
        FROM articles
        WHERE event_id IS NOT NULL
    """).fetchall()

    category_event_ids = {
        category: set()
        for category in CATEGORIES
    }

    for article in articles:

        category = article["category"]
        event_id = article["event_id"]

        if category not in category_event_ids:
            continue

        # Use publication time for report-window filtering
        article_date = parse_date(article["published_at"])

        if article_date is None:
            continue

        if start_time <= article_date < end_time:
            category_event_ids[category].add(event_id)

    return category_event_ids


def select_news():

    create_table()

    conn = get_connection()

    start_time, end_time, report_date = get_report_window()

    print("\n========== DAILY SCOPE SELECTION ==========")

    print(f"Report date: {report_date}")
    print(f"Window starts: {start_time}")
    print(f"Window ends: {end_time}")

    category_event_ids = get_category_events(
        conn,
        start_time,
        end_time
    )

    # Remove an earlier selection for the same report date.
    # This makes rerunning selection safe.
    conn.execute("""
        DELETE FROM selected_news
        WHERE report_date = ?
    """, (report_date,))

    total_selected = 0

    for category in CATEGORIES:

        print(f"\n========== {category} ==========")

        event_ids = category_event_ids[category]

        if not event_ids:

            print("No events found in this reporting period.")
            continue

        placeholders = ",".join(
            "?" for _ in event_ids
        )

        query = f"""
            SELECT
                id,
                canonical_title,
                ranking_score
            FROM events
            WHERE id IN ({placeholders})
              AND ranking_score >= ?
            ORDER BY ranking_score DESC, id ASC
            LIMIT ?
        """

        selected_events = conn.execute(
            query,
            (*event_ids, MIN_RANKING_SCORE, MAX_EVENTS_PER_CATEGORY)
        ).fetchall()

        if not selected_events:

            print("No events met the minimum ranking score.")
            continue

        # Select up to 10; do not fill with weak stories
        for position, event in enumerate(
            selected_events,
            start=1
        ):

            conn.execute("""
                INSERT INTO selected_news (
                    report_date,
                    category,
                    event_id,
                    rank,
                    ranking_score,
                    selected_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                report_date,
                category,
                event["id"],
                position,
                event["ranking_score"],
                datetime.now(timezone.utc).isoformat()
            ))

            total_selected += 1

            print(f"\nRank: {position}")
            print(f"Event ID: {event['id']}")
            print(f"Title: {event['canonical_title']}")
            print(f"Score: {event['ranking_score']}/100")

        count = len(selected_events)

        print(f"\nSelected {count} events.")

        if count < MIN_EVENTS_PER_CATEGORY:

            print(
                "Note: Fewer than 7 qualifying events were "
                "available. No low-quality stories were added."
            )

    conn.commit()
    conn.close()

    print("\n========== SELECTION COMPLETED ==========")
    print(f"Total events selected: {total_selected}")


if __name__ == "__main__":

    select_news()

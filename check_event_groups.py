
from database.db import get_connection

conn = get_connection()

events = conn.execute("""
    SELECT
        e.id,
        e.canonical_title,
        COUNT(a.id) AS article_count
    FROM events e
    LEFT JOIN articles a ON e.id = a.event_id
    GROUP BY e.id
    ORDER BY article_count DESC, e.id
""").fetchall()

print("\n========== ALL EVENT GROUPS ==========")

for event in events:
    print("\n" + "-" * 80)
    print(f"Event ID: {event['id']}")
    print(f"Article count: {event['article_count']}")
    print(f"Canonical: {event['canonical_title']}")

    articles = conn.execute("""
        SELECT title, source, category
        FROM articles
        WHERE event_id = ?
    """, (event["id"],)).fetchall()

    for article in articles:
        print(
            f"  [{article['category']}] "
            f"{article['source']}: {article['title']}"
        )

conn.close()

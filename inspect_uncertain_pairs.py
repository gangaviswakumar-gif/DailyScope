
from database.db import get_connection

PAIRS = [
    (66, 48, "Real Madrid vs PSV"),
    (32, 7, "Kerala Congress dispute"),
    (12, 11, "Apple products"),
    (36, 96, "Tariff developments")
]

conn = get_connection()

try:
    for event1, event2, name in PAIRS:
        print("\n" + "=" * 80)
        print(name)
        print("=" * 80)

        for event_id in (event1, event2):
            print(f"\nEVENT {event_id}")

            articles = conn.execute("""
                SELECT id, title, description, source, published_at
                FROM articles
                WHERE event_id = ?
            """, (event_id,)).fetchall()

            for article in articles:
                print("\nArticle ID:", article["id"])
                print("Source:", article["source"])
                print("Title:", article["title"])
                print("Published:", article["published_at"])
                print("Description:", article["description"])

finally:
    conn.close()

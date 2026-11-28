
from database.db import get_connection

conn = get_connection()

print("\n========== ARTICLE CATEGORY COUNTS ==========\n")

rows = conn.execute("""
    SELECT category, COUNT(*) AS total
    FROM articles
    GROUP BY category
    ORDER BY category
""").fetchall()

for row in rows:
    print(f"{row['category']}: {row['total']}")


print("\n========== ARTICLES IN REPORTING WINDOW ==========\n")

rows = conn.execute("""
    SELECT category, COUNT(*) AS total
    FROM articles
    WHERE published_at >= '2026-11-24T01:30:00+00:00'
    AND published_at < '2026-11-25T01:30:00+00:00'
    GROUP BY category
    ORDER BY category
""").fetchall()

for row in rows:
    print(f"{row['category']}: {row['total']}")


print("\n========== INTERNATIONAL ARTICLES ==========\n")

rows = conn.execute("""
    SELECT
        id,
        title,
        source,
        published_at,
        event_id
    FROM articles
    WHERE category = 'International'
    ORDER BY published_at DESC
    LIMIT 10
""").fetchall()

for row in rows:
    print(dict(row))


print("\n========== SAMPLE REPORT ARTICLE DETAILS ==========\n")

row = conn.execute("""
    SELECT
        a.title,
        a.description,
        a.source,
        a.url
    FROM reports r
    JOIN articles a
        ON a.event_id = r.event_id
    WHERE r.report_date = '2026-11-25'
    AND r.category = 'Business'
    LIMIT 5
""").fetchall()

for article in row:
    print(dict(article))
    print("-" * 60)

conn.close()

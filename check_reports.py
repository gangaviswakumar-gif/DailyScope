
from database.db import get_connection

conn = get_connection()

print("\n========== DAILY SCOPE REPORT CHECK ==========\n")

# Count reports by category
rows = conn.execute("""
    SELECT category, COUNT(*) AS total
    FROM reports
    GROUP BY category
    ORDER BY category
""").fetchall()

print("REPORT COUNTS:")

for row in rows:
    print(f"{row['category']}: {row['total']}")

# Check International selection
international = conn.execute("""
    SELECT COUNT(*) AS total
    FROM selected_news
    WHERE report_date = '2026-11-25'
    AND category = 'International'
""").fetchone()

print("\nINTERNATIONAL SELECTION:")
print("Selected events:", international["total"])

# Check a sample report
sample = conn.execute("""
    SELECT *
    FROM reports
    WHERE report_date = '2026-11-25'
    LIMIT 1
""").fetchone()

if sample:
    print("\nSAMPLE GENERATED REPORT:")
    print("Title:", sample["title"])
    print("\nSummary:", sample["summary"])
    print("\nBackground:", sample["background"])
    print("\nImpact:", sample["impact"])
    print("\nSources:", sample["sources_json"])

conn.close()

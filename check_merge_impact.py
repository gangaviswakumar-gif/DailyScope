
from database.db import get_connection

EVENT_GROUPS = {
    "Palakkad": [2, 99],
    "Delhi cafe": [39, 82],
    "Sooryavanshi": [72, 33],
    "Shenzhou 24": [90, 104],
    "India-Cyprus": [14, 13],
    "Apple": [12, 11],
    "US tariffs": [36, 96]
}

conn = get_connection()

try:
    for name, event_ids in EVENT_GROUPS.items():
        placeholders = ",".join("?" for _ in event_ids)

        print("\n" + "=" * 65)
        print(name, "- Event IDs:", event_ids)
        print("=" * 65)

        selected = conn.execute(f"""
            SELECT event_id, report_date, category, rank
            FROM selected_news
            WHERE event_id IN ({placeholders})
            ORDER BY report_date, category
        """, event_ids).fetchall()

        reports = conn.execute(f"""
            SELECT event_id, report_date, category, title
            FROM reports
            WHERE event_id IN ({placeholders})
            ORDER BY report_date, category
        """, event_ids).fetchall()

        print("\nSelected news references:", len(selected))
        for row in selected:
            print(dict(row))

        print("\nGenerated report references:", len(reports))
        for row in reports:
            print(dict(row))

finally:
    conn.close()

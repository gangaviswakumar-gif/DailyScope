
from database.db import get_connection, calculate_similarity
from rapidfuzz import fuzz

SUSPECT_PAIRS = [
    (2, 99, "Palakkad school shooting"),
    (39, 82, "Delhi cafe incident"),
    (72, 33, "Sooryavanshi double century"),
    (90, 104, "China Shenzhou 24 launch")
]


def check_pair(conn, event1, event2, description):
    print("\n" + "=" * 75)
    print(f"CHECKING: {description}")
    print(f"Event IDs: {event1} and {event2}")
    print("=" * 75)

    articles1 = conn.execute("""
        SELECT id, title, description, source, published_at, event_id
        FROM articles
        WHERE event_id = ?
    """, (event1,)).fetchall()

    articles2 = conn.execute("""
        SELECT id, title, description, source, published_at, event_id
        FROM articles
        WHERE event_id = ?
    """, (event2,)).fetchall()

    if not articles1 or not articles2:
        print("One or both event groups were not found.")
        return

    for a in articles1:
        for b in articles2:
            title_score = max(
                fuzz.WRatio(a["title"] or "", b["title"] or ""),
                fuzz.token_set_ratio(a["title"] or "", b["title"] or "")
            )

            final_score = calculate_similarity(a, b)

            print("\n--- Article 1 ---")
            print("ID:", a["id"])
            print("Source:", a["source"])
            print("Title:", a["title"])
            print("Published:", a["published_at"])
            print("Description:", a["description"])

            print("\n--- Article 2 ---")
            print("ID:", b["id"])
            print("Source:", b["source"])
            print("Title:", b["title"])
            print("Published:", b["published_at"])
            print("Description:", b["description"])

            print("\n--- Similarity Results ---")
            print(f"Headline similarity: {title_score:.2f}")
            print(f"Final matching score: {final_score:.2f}")

            if final_score >= 82:
                print("Result: STRONG DUPLICATE CANDIDATE")
            elif final_score > 0:
                print("Result: POSSIBLE MATCH - REVIEW")
            else:
                print("Result: NOT MATCHED BY CURRENT LOGIC")


def main():
    conn = get_connection()

    try:
        for event1, event2, description in SUSPECT_PAIRS:
            check_pair(conn, event1, event2, description)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

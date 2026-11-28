from database.db import (
    get_connection,
    build_idf,
    is_same_event
)


# These are regression tests based on the event groups already inspected.
# True means the two groups should describe the same exact development.
# False means they should remain separate events.
REGRESSION_TESTS = [
    (2, 99, "Palakkad school shooting", True),
    (39, 82, "Delhi cafe incident", True),
    (72, 33, "Sooryavanshi 204", True),
    (90, 104, "Shenzhou 24 launch", True),
    (14, 13, "India-Cyprus education MoU", True),

    (66, 48, "Real Madrid lineup vs match result", False),
    (32, 7, "Different Kerala Congress developments", False),
    (31, 60, "Waqf Board vs shipwreck", False),
]


def load_group(conn, event_id):
    return conn.execute("""
        SELECT id, title, description, source, published_at,
               fetched_at, event_id, category
        FROM articles
        WHERE event_id = ?
    """, (event_id,)).fetchall()


def compare_groups(group1, group2):
    best_result = None
    best_match = False

    for article1 in group1:
        for article2 in group2:
            idf = build_idf([article1, article2])
            matched, result = is_same_event(article1, article2, idf)

            if best_result is None or result["score"] > best_result["score"]:
                best_result = result
                best_match = matched

    return best_match, best_result


def main():
    conn = get_connection()
    passed = 0
    total = 0

    try:
        for event1, event2, label, expected in REGRESSION_TESTS:
            total += 1

            group1 = load_group(conn, event1)
            group2 = load_group(conn, event2)

            print("\n" + "=" * 72)
            print(label)
            print(f"Event groups: {event1} and {event2}")

            if not group1 or not group2:
                print("SKIPPED: One or both event groups were not found.")
                continue

            matched, result = compare_groups(group1, group2)

            print("Expected:", "MATCH" if expected else "SEPARATE")
            print("Actual:  ", "MATCH" if matched else "SEPARATE")
            print(f"Score: {result['score']:.2f}")
            print(f"Weighted overlap: {result['weighted_overlap']:.2%}")
            print(f"Headline overlap: {result['title_overlap']:.2%}")
            print("Shared headline anchors:", result["shared_title_anchors"])
            print("Shared anchors:", result["shared_anchors"])
            print("Development conflict:", result["development_conflict"])

            if matched == expected:
                print("TEST: PASS")
                passed += 1
            else:
                print("TEST: FAIL")

        print("\n" + "=" * 72)
        print(f"Regression tests passed: {passed}/{total}")
        print("This test only reads the database. It does not modify records.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()

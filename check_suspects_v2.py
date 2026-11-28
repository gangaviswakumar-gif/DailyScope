
import re
from database.db import get_connection
from rapidfuzz import fuzz

PAIRS = [
    (2, 99, "Palakkad school incident"),
    (39, 82, "Delhi cafe incident"),
    (72, 33, "Sooryavanshi double century"),
    (90, 104, "Shenzhou 24 launch")
]

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on",
    "at", "to", "for", "of", "by", "with", "from",
    "after", "before", "as", "is", "are", "was", "were",
    "be", "has", "have", "had", "will", "would", "could",
    "should", "its", "their", "his", "her", "this", "that",
    "these", "those", "over", "under", "into", "about",
    "said", "says", "according", "reported", "reports",
    "news", "latest", "today"
}


def words(text):
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in tokens if len(w) > 2 and w not in STOPWORDS}


def analyse(a, b):
    title1 = a["title"] or ""
    title2 = b["title"] or ""

    desc1 = a["description"] or ""
    desc2 = b["description"] or ""

    combined1 = title1 + " " + desc1
    combined2 = title2 + " " + desc2

    title_score = fuzz.token_set_ratio(title1, title2)
    description_score = fuzz.token_set_ratio(desc1, desc2)
    combined_score = fuzz.token_set_ratio(combined1, combined2)

    w1 = words(combined1)
    w2 = words(combined2)

    common = w1.intersection(w2)
    overlap = len(common) / max(1, min(len(w1), len(w2)))

    print("\nArticle 1:", title1)
    print("Article 2:", title2)

    print(f"\nHeadline similarity: {title_score:.2f}")
    print(f"Description similarity: {description_score:.2f}")
    print(f"Combined similarity: {combined_score:.2f}")
    print(f"Shared-word overlap: {overlap:.2f}")

    print("Shared meaningful words:", sorted(common))


def main():
    conn = get_connection()

    try:
        for event1, event2, name in PAIRS:
            print("\n" + "=" * 75)
            print(name)
            print("=" * 75)

            articles1 = conn.execute(
                "SELECT * FROM articles WHERE event_id = ?",
                (event1,)
            ).fetchall()

            articles2 = conn.execute(
                "SELECT * FROM articles WHERE event_id = ?",
                (event2,)
            ).fetchall()

            for a in articles1:
                for b in articles2:
                    analyse(a, b)

    finally:
        conn.close()


if __name__ == "__main__":
    main()

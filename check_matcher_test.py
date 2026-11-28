
import math
from itertools import combinations
from database.db import get_connection, parse_date
from rapidfuzz import fuzz

TIME_WINDOW_HOURS = 48
MIN_CANDIDATE_SCORE = 40

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on",
    "at", "to", "for", "of", "by", "with", "from",
    "after", "before", "as", "is", "are", "was", "were",
    "be", "has", "have", "had", "will", "would", "could",
    "should", "its", "their", "his", "her", "this", "that",
    "these", "those", "over", "under", "into", "about",
    "said", "says", "according", "reported", "reports",
    "news", "latest", "today", "who", "what", "when",
    "where", "which", "while", "also", "than", "then",
    "been", "being", "their", "they", "them", "there",
    "here", "more", "most", "some", "such", "could",
    "would", "should", "will", "may", "might", "can"
}


def get_words(text):
    import re

    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())

    return {
        word for word in tokens
        if len(word) > 2 and word not in STOPWORDS
    }


def build_idf(articles):
    document_frequency = {}

    for article in articles:
        text = (article["title"] or "") + " " + (
            article["description"] or ""
        )

        for word in get_words(text):
            document_frequency[word] = (
                document_frequency.get(word, 0) + 1
            )

    total_documents = max(len(articles), 1)

    return {
        word: math.log(
            (total_documents + 1) / (frequency + 1)
        ) + 1
        for word, frequency in document_frequency.items()
    }


def weighted_overlap(words1, words2, idf):
    if not words1 or not words2:
        return 0

    shared = words1.intersection(words2)

    shared_weight = sum(idf.get(word, 1) for word in shared)

    total1 = sum(idf.get(word, 1) for word in words1)
    total2 = sum(idf.get(word, 1) for word in words2)

    denominator = min(total1, total2)

    if denominator == 0:
        return 0

    return shared_weight / denominator


def calculate_score(a, b, idf):
    title1 = a["title"] or ""
    title2 = b["title"] or ""

    desc1 = a["description"] or ""
    desc2 = b["description"] or ""

    combined1 = title1 + " " + desc1
    combined2 = title2 + " " + desc2

    title_score = fuzz.token_set_ratio(title1, title2)

    combined_score = fuzz.token_set_ratio(
        combined1, combined2
    )

    words1 = get_words(combined1)
    words2 = get_words(combined2)

    overlap = weighted_overlap(words1, words2, idf)

    # Weighted score out of 100
    final_score = (
        overlap * 50
        + combined_score * 0.30
        + title_score * 0.20
    )

    return {
        "final": final_score,
        "title": title_score,
        "combined": combined_score,
        "overlap": overlap * 100,
        "shared": sorted(words1.intersection(words2))
    }


def get_article_date(article):
    return (
        parse_date(article["published_at"])
        or parse_date(article["fetched_at"])
    )


def main():
    conn = get_connection()

    try:
        articles = conn.execute("""
            SELECT id, title, description, source,
                   published_at, fetched_at, event_id
            FROM articles
            WHERE event_id IS NOT NULL
        """).fetchall()

        print("Articles loaded:", len(articles))

        idf = build_idf(articles)

        # Keep only the strongest match for each pair of event groups.
        best_matches = {}

        for a, b in combinations(articles, 2):

            # Articles already in the same event are not candidates.
            if a["event_id"] == b["event_id"]:
                continue

            date1 = get_article_date(a)
            date2 = get_article_date(b)

            if date1 is None or date2 is None:
                continue

            difference = abs(
                (date1 - date2).total_seconds()
            )

            if difference > TIME_WINDOW_HOURS * 3600:
                continue

            result = calculate_score(a, b, idf)

            event_pair = tuple(sorted((
                a["event_id"],
                b["event_id"]
            )))

            if (
                event_pair not in best_matches
                or result["final"] >
                best_matches[event_pair]["result"]["final"]
            ):
                best_matches[event_pair] = {
                    "article1": a,
                    "article2": b,
                    "result": result
                }

        candidates = [
            match for match in best_matches.values()
            if match["result"]["final"] >= MIN_CANDIDATE_SCORE
        ]

        candidates.sort(
            key=lambda x: x["result"]["final"],
            reverse=True
        )

        print("\n========== POSSIBLE DUPLICATE EVENTS ==========")
        print("Candidate event pairs:", len(candidates))

        for index, match in enumerate(candidates[:40], start=1):
            a = match["article1"]
            b = match["article2"]
            r = match["result"]

            print("\n" + "=" * 75)
            print(f"CANDIDATE {index}")
            print(f"Event IDs: {a['event_id']} and {b['event_id']}")

            print(f"\nScore: {r['final']:.2f}/100")
            print(f"Headline similarity: {r['title']:.2f}")
            print(f"Combined similarity: {r['combined']:.2f}")
            print(f"Weighted keyword overlap: {r['overlap']:.2f}%")

            print("\nArticle 1:")
            print("ID:", a["id"])
            print("Source:", a["source"])
            print("Title:", a["title"])

            print("\nArticle 2:")
            print("ID:", b["id"])
            print("Source:", b["source"])
            print("Title:", b["title"])

            print("\nShared keywords:", ", ".join(r["shared"]))

        if not candidates:
            print("No candidates found above the threshold.")

        if len(candidates) > 40:
            print("\nOnly the top 40 candidates are displayed.")

        print("\n========== TEST COMPLETE ==========")
        print("No database records were modified.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()

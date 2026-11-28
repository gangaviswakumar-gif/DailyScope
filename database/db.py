import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from rapidfuzz import fuzz


DB_NAME = "dailyscope.db"
TIME_WINDOW_HOURS = 48

# Conservative matching thresholds. These are combined with safeguards below;
# a score by itself never causes an event match.
MIN_MATCH_SCORE = 40.0
MIN_WEIGHTED_OVERLAP = 0.28
MIN_COMBINED_SIMILARITY = 45.0
MIN_SHARED_ANCHORS = 1
AMBIGUOUS_SCORE_GAP = 5.0


STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "by", "with", "from", "after", "before", "as",
    "is", "are", "was", "were", "be", "has", "have", "had", "will",
    "would", "could", "should", "its", "their", "his", "her", "this",
    "that", "these", "those", "over", "under", "into", "about",
    "report", "reports", "today", "latest", "news", "says", "said",
    "according", "reported", "reportedly", "who", "what", "when",
    "where", "which", "while", "also", "than", "then", "been",
    "being", "they", "them", "there", "here", "more", "most",
    "some", "such", "could", "would", "should", "will", "may",
    "might", "can", "your", "best", "source", "quality", "read",
    "click", "here", "discover", "google", "preferred", "updated",
    "update", "updates", "pti", "nov", "tuesday", "wednesday",
    "monday", "thursday", "friday", "saturday", "sunday",
    "new", "state", "government",
    "govt", "official", "officials", "people", "person", "country",
    "city", "district", "area", "region", "national", "international",
    "situation", "issue", "issues", "amid", "following", "including",
    "among", "said", "says", "told", "made", "make", "makes",
    "one", "two", "three", "first", "second", "another", "many",
    "much", "year", "years", "day", "days", "time", "times",
    "according", "statement", "statements", "newsroom"
}

# Broad terms that should not, by themselves, prove that two articles
# describe the same event.
NON_ANCHOR_WORDS = STOPWORDS | {
    "school", "student", "students", "woman", "women", "man", "men",
    "court", "high", "police", "officer", "officers", "minister",
    "chief", "minister", "party", "leader", "leaders", "company",
    "companies", "market", "markets", "business", "world", "national",
    "international", "match", "team", "teams", "play", "player",
    "players", "sports", "technology", "science", "education",
    "culture", "entertainment", "launch", "announced", "announcement"
}

BOILERPLATE_PATTERNS = [
    r"your best source for .*?fan perspective",
    r"all rights reserved",
    r"subscribe to .*?newsletter",
    r"click here to read more",
    r"read more at .*",
]

# Separate developments in the same broad subject must not be merged.
PRE_EVENT_TERMS = {
    "lineup", "lineups", "predicted", "preview", "pre-match",
    "starting", "squad", "selection", "team-news"
}
POST_EVENT_TERMS = {
    "reaction", "result", "results", "won", "wins", "beat",
    "defeated", "victory", "loss", "lost", "score", "scored"
}

# These action groups help distinguish separate political developments.
POLITICAL_ACTION_GROUPS = {
    "support": {
        "backs", "backed", "supports", "supported", "endorses",
        "endorsed", "praises", "praised"
    },
    "accusation": {
        "targets", "targeted", "accuses", "accused", "criticises",
        "criticizes", "criticised", "criticized", "slams", "slammed"
    },
    "demand": {
        "demands", "demanded", "seeks", "sought", "urges", "urged"
    },
    "resignation": {
        "resigns", "resigned", "quits", "quit", "steps"
    },
}


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_table():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            importance_score REAL DEFAULT 0,
            relevance_score REAL DEFAULT 0,
            credibility_score REAL DEFAULT 0,
            recency_score REAL DEFAULT 0,
            coverage_score REAL DEFAULT 0,
            ranking_score REAL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            source TEXT,
            url TEXT UNIQUE,
            published_at TEXT,
            category TEXT,
            fetched_at TEXT,
            event_id INTEGER,
            FOREIGN KEY (event_id) REFERENCES events(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS selected_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            category TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            ranking_score REAL NOT NULL,
            selected_at TEXT NOT NULL,
            UNIQUE(report_date, category, event_id),
            FOREIGN KEY (event_id) REFERENCES events(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            category TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            background TEXT NOT NULL,
            impact TEXT NOT NULL,
            sources_json TEXT NOT NULL,
            model_name TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            UNIQUE(report_date, category, event_id),
            FOREIGN KEY (event_id) REFERENCES events(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            source_name TEXT PRIMARY KEY,
            credibility_score REAL NOT NULL DEFAULT 50
        )
    """)

    article_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(articles)").fetchall()
    }

    if "event_id" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN event_id INTEGER")

    event_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(events)").fetchall()
    }

    ranking_columns = {
        "importance_score": "REAL DEFAULT 0",
        "relevance_score": "REAL DEFAULT 0",
        "credibility_score": "REAL DEFAULT 0",
        "recency_score": "REAL DEFAULT 0",
        "coverage_score": "REAL DEFAULT 0",
        "ranking_score": "REAL DEFAULT 0"
    }

    for column, data_type in ranking_columns.items():
        if column not in event_columns:
            conn.execute(
                f"ALTER TABLE events ADD COLUMN {column} {data_type}"
            )

    conn.commit()
    conn.close()


def parse_date(date_string):
    if not date_string:
        return None

    try:
        value = date_string.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError, AttributeError):
        return None


def clean_text(text):
    """Remove known publisher boilerplate and normalize article text."""
    if not text:
        return ""

    cleaned = text.lower()

    for pattern in BOILERPLATE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    # Remove common publisher/footer fragments.
    cleaned = re.sub(
        r"\b(?:discover more|google preferred source|preferred source|"
        r"follow us|read more|click here|subscribe now)\b",
        " ",
        cleaned
    )

    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s'-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def get_meaningful_words(text):
    cleaned = clean_text(text)
    tokens = re.findall(r"[a-z0-9]+", cleaned)

    return {
        token for token in tokens
        if len(token) > 2 and token not in STOPWORDS
    }


def get_anchor_words(words):
    return {
        word for word in words
        if word not in NON_ANCHOR_WORDS
        and not word.isdigit()
    }


def article_text(article):
    title = clean_text(article["title"] or "")
    description = clean_text(article["description"] or "")
    return (title + " " + description).strip()


def build_idf(articles):
    """Give rare, event-specific words more weight than common words."""
    document_frequency = defaultdict(int)

    for article in articles:
        words = get_meaningful_words(article_text(article))
        for word in words:
            document_frequency[word] += 1

    total = max(len(articles), 1)

    return {
        word: math.log((total + 1) / (count + 1)) + 1
        for word, count in document_frequency.items()
    }


def weighted_overlap(words1, words2, idf):
    if not words1 or not words2:
        return 0.0

    shared = words1.intersection(words2)
    shared_weight = sum(idf.get(word, 1.0) for word in shared)

    weight1 = sum(idf.get(word, 1.0) for word in words1)
    weight2 = sum(idf.get(word, 1.0) for word in words2)

    denominator = min(weight1, weight2)

    if denominator == 0:
        return 0.0

    return shared_weight / denominator


def get_political_action_group(article):
    title_words = get_meaningful_words(article["title"] or "")

    for group, terms in POLITICAL_ACTION_GROUPS.items():
        if title_words.intersection(terms):
            return group

    return None


def has_development_conflict(article1, article2):
    """
    Return True when headlines clearly describe different stages/actions
    rather than two reports of the same development.
    """
    title1 = get_meaningful_words(article1["title"] or "")
    title2 = get_meaningful_words(article2["title"] or "")

    pre1 = bool(title1.intersection(PRE_EVENT_TERMS))
    pre2 = bool(title2.intersection(PRE_EVENT_TERMS))
    post1 = bool(title1.intersection(POST_EVENT_TERMS))
    post2 = bool(title2.intersection(POST_EVENT_TERMS))

    if (pre1 and post2) or (pre2 and post1):
        return True

    action1 = get_political_action_group(article1)
    action2 = get_political_action_group(article2)

    if action1 and action2 and action1 != action2:
        return True

    return False


def calculate_similarity(article, candidate, idf=None):
    """
    Return explainable similarity measurements.

    A high score alone is not enough: the caller also checks anchor words,
    overlap, time and development conflicts.
    """
    title1 = clean_text(article["title"] or "")
    title2 = clean_text(candidate["title"] or "")

    text1 = article_text(article)
    text2 = article_text(candidate)

    title_score = fuzz.token_set_ratio(title1, title2)
    combined_score = fuzz.token_set_ratio(text1, text2)

    words1 = get_meaningful_words(text1)
    words2 = get_meaningful_words(text2)
    title_words1 = get_meaningful_words(title1)
    title_words2 = get_meaningful_words(title2)

    if idf is None:
        all_words = words1.union(words2)
        idf = {word: 1.0 for word in all_words}

    # Keep headline evidence separate so long descriptions cannot dilute it.
    overlap = weighted_overlap(words1, words2, idf)
    title_overlap = weighted_overlap(title_words1, title_words2, idf)

    shared = words1.intersection(words2)
    shared_anchors = get_anchor_words(shared)
    shared_title_words = title_words1.intersection(title_words2)
    shared_title_anchors = get_anchor_words(shared_title_words)

    final_score = (
        title_score * 0.35
        + title_overlap * 100 * 0.35
        + combined_score * 0.15
        + overlap * 100 * 0.15
    )

    return {
        "score": final_score,
        "title_score": title_score,
        "title_overlap": title_overlap,
        "combined_score": combined_score,
        "weighted_overlap": overlap,
        "shared_words": sorted(shared),
        "shared_anchors": sorted(shared_anchors),
        "shared_title_words": sorted(shared_title_words),
        "shared_title_anchors": sorted(shared_title_anchors),
        "development_conflict": has_development_conflict(
            article, candidate
        )
    }


def is_same_event(article, candidate, idf=None):
    """Apply conservative matching rules, not just a score threshold."""
    result = calculate_similarity(article, candidate, idf)

    if result["development_conflict"]:
        return False, result

    # Very similar titles still need meaningful shared event details.
    standard_match = (
        result["score"] >= MIN_MATCH_SCORE
        and result["weighted_overlap"] >= MIN_WEIGHTED_OVERLAP
        and result["combined_score"] >= MIN_COMBINED_SIMILARITY
        and len(result["shared_anchors"]) >= MIN_SHARED_ANCHORS
    )

    # Headline-led path catches paraphrased reports whose descriptions differ.
    headline_match = (
        result["title_score"] >= 45
        and result["title_overlap"] >= 0.30
        and len(result["shared_title_anchors"]) >= 1
        and result["score"] >= 40
    )

    if standard_match or headline_match:
        return True, result

    return False, result


def get_article_datetime(article):
    return (
        parse_date(article["published_at"])
        or parse_date(article["fetched_at"])
    )


def _find_matching_event(conn, article):
    """Find the best existing event without merging existing event groups."""
    current_date = (
        get_article_datetime(article)
        or datetime.now(timezone.utc)
    )

    cutoff = current_date - timedelta(hours=TIME_WINDOW_HOURS)
    upper_bound = current_date + timedelta(hours=TIME_WINDOW_HOURS)

    candidates = conn.execute("""
        SELECT id, title, description, source, published_at,
               fetched_at, event_id, category
        FROM articles
        WHERE event_id IS NOT NULL
    """).fetchall()

    recent_candidates = []

    for candidate in candidates:
        candidate_date = get_article_datetime(candidate)

        if candidate_date is None:
            continue

        if cutoff <= candidate_date <= upper_bound:
            recent_candidates.append(candidate)

    if not recent_candidates:
        return None

    idf = build_idf([article] + recent_candidates)

    # Keep the best article-level evidence for each existing event.
    event_matches = {}

    for candidate in recent_candidates:
        if candidate["event_id"] is None:
            continue

        matched, result = is_same_event(article, candidate, idf)

        if not matched:
            continue

        event_id = candidate["event_id"]

        if (
            event_id not in event_matches
            or result["score"] > event_matches[event_id]["score"]
        ):
            event_matches[event_id] = {
                "event_id": event_id,
                "score": result["score"],
                "article_id": candidate["id"],
                "result": result
            }

    if not event_matches:
        return None

    ranked = sorted(
        event_matches.values(),
        key=lambda item: item["score"],
        reverse=True
    )

    # If two different event groups are nearly equally plausible,
    # do not guess. Create a separate event for manual review later.
    if (
        len(ranked) > 1
        and ranked[0]["score"] - ranked[1]["score"] < AMBIGUOUS_SCORE_GAP
    ):
        print(
            "Ambiguous event match for article",
            article["id"],
            "- creating a new event instead."
        )
        return None

    return ranked[0]["event_id"]


def _assign_event(conn, article_id):
    article = conn.execute("""
        SELECT id, title, description, source, published_at,
               fetched_at, event_id, category
        FROM articles
        WHERE id = ?
    """, (article_id,)).fetchone()

    if article is None:
        return None

    # Existing assignments are not silently changed.
    if article["event_id"] is not None:
        return article["event_id"]

    matched_event_id = _find_matching_event(conn, article)

    if matched_event_id is not None:
        event_id = matched_event_id
    else:
        cursor = conn.execute("""
            INSERT INTO events (canonical_title, created_at)
            VALUES (?, ?)
        """, (
            article["title"],
            datetime.now(timezone.utc).isoformat()
        ))
        event_id = cursor.lastrowid

    conn.execute("""
        UPDATE articles
        SET event_id = ?
        WHERE id = ?
    """, (event_id, article_id))

    return event_id


def assign_event(article_id):
    """Assign one unassigned article to an existing or new event."""
    conn = get_connection()

    try:
        with conn:
            event_id = _assign_event(conn, article_id)
        return event_id
    finally:
        conn.close()


def assign_missing_events():
    """
    Assign all unassigned articles in chronological order.

    One connection and one transaction are used for the batch.
    """
    conn = get_connection()

    try:
        with conn:
            rows = conn.execute("""
                SELECT id
                FROM articles
                WHERE event_id IS NULL
                ORDER BY
                    COALESCE(published_at, fetched_at),
                    id
            """).fetchall()

            processed = 0

            for row in rows:
                _assign_event(conn, row["id"])
                processed += 1

        print(f"Unassigned articles processed: {processed}")

    finally:
        conn.close()


if __name__ == "__main__":
    create_table()
    print("Database tables and ranking columns ready!")

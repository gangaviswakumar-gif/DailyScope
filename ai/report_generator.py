
import os
import json
import sys

from datetime import datetime, timezone

from dotenv import load_dotenv
from google import genai

from database.db import (
    get_connection,
    create_table
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = "gemini-3.5-flash-lite"

MAX_ARTICLES_PER_EVENT = 5


if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")


client = genai.Client(api_key=API_KEY)


CATEGORIES = [
    "International",
    "National",
    "Kerala",
    "Local",
    "Sports",
    "Business",
    "Technology",
    "Science",
    "Education",
    "Culture & Entertainment"
]


# --------------------------------------------------
# JSON RESPONSE STRUCTURE
# --------------------------------------------------

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "reports": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "integer"
                    },
                    "title": {
                        "type": "string"
                    },
                    "summary": {
                        "type": "string"
                    },
                    "background": {
                        "type": "string"
                    },
                    "impact": {
                        "type": "string"
                    }
                },
                "required": [
                    "event_id",
                    "title",
                    "summary",
                    "background",
                    "impact"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": ["reports"],
    "additionalProperties": False
}


# --------------------------------------------------
# GET REPORT DATE
# --------------------------------------------------

def get_latest_report_date(conn):

    row = conn.execute("""
        SELECT MAX(report_date) AS report_date
        FROM selected_news
    """).fetchone()

    if row is None or row["report_date"] is None:
        return None

    return row["report_date"]


# --------------------------------------------------
# GET SELECTED EVENTS AND ARTICLES
# --------------------------------------------------

def get_category_events(conn, report_date, category):

    selected_events = conn.execute("""
        SELECT
            sn.event_id,
            sn.rank,
            e.canonical_title,
            e.ranking_score
        FROM selected_news sn
        JOIN events e
            ON sn.event_id = e.id
        WHERE sn.report_date = ?
        AND sn.category = ?
        ORDER BY sn.rank
    """, (report_date, category)).fetchall()

    results = []

    for event in selected_events:

        articles = conn.execute("""
            SELECT
                title,
                description,
                source,
                url,
                published_at
            FROM articles
            WHERE event_id = ?
            ORDER BY published_at DESC
        """, (event["event_id"],)).fetchall()

        article_list = []

        for article in articles:

            article_list.append({
                "title": article["title"],
                "description": (
                    (article["description"] or "")[:1500]
                ),
                "source": article["source"],
                "published_at": article["published_at"]
            })

        if not article_list:
            continue

        # Keep all original source links for storage.
        sources = [
            {
                "source": article["source"],
                "url": article["url"],
                "published_at": article["published_at"]
            }
            for article in articles
            if article["url"]
        ]

        results.append({
            "event_id": event["event_id"],
            "canonical_title": event["canonical_title"],
            "ranking_score": event["ranking_score"],
            "articles": article_list[:MAX_ARTICLES_PER_EVENT],
            "sources": sources
        })

    return results


# --------------------------------------------------
# GENERATE CATEGORY REPORTS
# --------------------------------------------------

def generate_category_reports(conn, report_date, category):

    events = get_category_events(
        conn,
        report_date,
        category
    )

    if not events:
        print(f"No articles found for {category}.")
        return 0

    # Skip events that already have generated reports.
    missing_events = []

    for event in events:

        existing = conn.execute("""
            SELECT id
            FROM reports
            WHERE report_date = ?
            AND category = ?
            AND event_id = ?
        """, (
            report_date,
            category,
            event["event_id"]
        )).fetchone()

        if existing is None:
            missing_events.append(event)

    if not missing_events:
        print(f"Reports already exist for {category}. Skipping.")
        return 0

    # Prepare news information for Gemini.
    news_input = []

    for event in missing_events:

        news_input.append({
            "event_id": event["event_id"],
            "headline": event["canonical_title"],
            "articles": event["articles"]
        })

    prompt = f"""
You are the professional news editor of DailyScope.

Generate detailed, factual news reports for the following
selected {category} news events.

REPORT DATE: {report_date}
CATEGORY: {category}

NEWS DATA:
{json.dumps(news_input, ensure_ascii=False, indent=2)}

For EACH event:

1. Return the exact event_id provided.
2. Write a clear and informative headline.
3. Write a factual summary explaining what happened.
4. Explain the background using the supplied information.
5. Explain the impact, distinguishing confirmed facts
   from possible future consequences.

IMPORTANT RULES:

- Use only the information supplied in the articles.
- Do not invent names, dates, statistics or quotations.
- Do not introduce unsupported background information.
- If information is insufficient, say so clearly.
- Do not combine separate events.
- Return every supplied event exactly once.
- Keep the report informative and readable.
"""

    print(
        f"\nGenerating {len(missing_events)} reports "
        f"for {category}..."
    )

    response = client.interactions.create(
        model=MODEL_NAME,
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": RESPONSE_SCHEMA
        }
    )

    generated_data = json.loads(response.output_text)

    generated_reports = generated_data.get("reports", [])

    # Only accept IDs that were actually sent to Gemini.
    allowed_ids = {
        event["event_id"]: event
        for event in missing_events
    }

    saved_count = 0
    seen_ids = set()

    for report in generated_reports:

        event_id = report.get("event_id")

        if event_id not in allowed_ids or event_id in seen_ids:
            continue

        seen_ids.add(event_id)

        event = allowed_ids[event_id]

        conn.execute("""
            INSERT OR IGNORE INTO reports (
                report_date,
                category,
                event_id,
                title,
                summary,
                background,
                impact,
                sources_json,
                model_name,
                generated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_date,
            category,
            event_id,
            report["title"],
            report["summary"],
            report["background"],
            report["impact"],
            json.dumps(
                event["sources"],
                ensure_ascii=False
            ),
            MODEL_NAME,
            datetime.now(timezone.utc).isoformat()
        ))

        if conn.execute("SELECT changes()").fetchone()[0]:
            saved_count += 1

    conn.commit()

    missing_ids = set(allowed_ids) - seen_ids

    if missing_ids:
        print(
            f"Warning: Gemini did not return "
            f"{len(missing_ids)} expected events."
        )

    print(f"Saved {saved_count} reports for {category}.")

    return saved_count


# --------------------------------------------------
# MAIN FUNCTION
# --------------------------------------------------

def generate_reports(report_date=None):

    create_table()

    conn = get_connection()

    try:

        if report_date is None:
            report_date = get_latest_report_date(conn)

        if report_date is None:
            print("No selected news found. Run selection.py first.")
            return

        print("\n========== DAILY SCOPE AI REPORT GENERATION ==========")
        print(f"Report date: {report_date}")
        print(f"Model: {MODEL_NAME}")

        total_saved = 0

        for category in CATEGORIES:

            try:

                saved = generate_category_reports(
                    conn,
                    report_date,
                    category
                )

                total_saved += saved

            except Exception as error:

                conn.rollback()

                print(
                    f"Error generating {category} reports: {error}"
                )

        print("\n========== GENERATION COMPLETE ==========")
        print(f"Total new reports saved: {total_saved}")

    finally:
        conn.close()


if __name__ == "__main__":

    selected_date = (
        sys.argv[1] if len(sys.argv) > 1 else None
    )

    generate_reports(selected_date)

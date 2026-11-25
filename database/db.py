
import sqlite3

DB_NAME = "dailyscope.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def create_table():

    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            source TEXT,
            url TEXT UNIQUE,
            published_at TEXT,
            category TEXT,
            fetched_at TEXT
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_table()
    print("Database created successfully!")

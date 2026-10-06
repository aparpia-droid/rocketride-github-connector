import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
  repository   TEXT    NOT NULL,
  issue_number INTEGER NOT NULL,
  title        TEXT    NOT NULL,
  url          TEXT    NOT NULL,
  PRIMARY KEY (repository, issue_number)
);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn


def get_existing(conn, repo):
    """Return {issue_number: (title, url)} for rows already saved for repo."""
    rows = conn.execute(
        "SELECT issue_number, title, url FROM issues WHERE repository = ?", (repo,)
    )
    return {number: (title, url) for number, title, url in rows}


def upsert_issue(conn, repo, number, title, url):
    conn.execute(
        """
        INSERT INTO issues (repository, issue_number, title, url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(repository, issue_number)
        DO UPDATE SET title = excluded.title, url = excluded.url
        """,
        (repo, number, title, url),
    )


def list_issues(conn, repo):
    rows = conn.execute(
        "SELECT issue_number, title, url FROM issues "
        "WHERE repository = ? ORDER BY issue_number DESC",
        (repo,),
    )
    return [{"number": n, "title": t, "url": u} for n, t, u in rows]

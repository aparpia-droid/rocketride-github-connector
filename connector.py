import re

import database
import github_client

# owner: letters, digits, hyphens. name: letters, digits, dot, underscore, hyphen.
REPO_PATTERN = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+")


def _failure(repo, error):
    return {
        "success": False,
        "repository": repo,
        "error": {"code": error.code, "message": error.message},
    }


def _is_valid_repo(repo):
    if not isinstance(repo, str) or not REPO_PATTERN.fullmatch(repo):
        return False
    return repo.split("/")[1] not in (".", "..")


def _invalid_repo_failure(repo):
    return _failure(
        repo if isinstance(repo, str) else None,
        github_client.GitHubError("INVALID_REPO", "Repository must look like owner/name"),
    )


def import_issues(repo, db_path, fetch=github_client.default_fetch):
    if not _is_valid_repo(repo):
        return _invalid_repo_failure(repo)
    repo = repo.lower()
    try:
        items = github_client.fetch_open_issues(repo, fetch=fetch)
    except github_client.GitHubError as e:
        return _failure(repo, e)

    inserted = updated = unchanged = skipped = 0
    conn = database.connect(db_path)
    with conn:  # one transaction: commits on success, rolls back on error
        existing = database.get_existing(conn, repo)
        for item in items:
            if "pull_request" in item:
                skipped += 1
                continue
            number, title, url = item["number"], item["title"], item["html_url"]
            if number not in existing:
                inserted += 1
            elif existing[number] != (title, url):
                updated += 1
            else:
                unchanged += 1
            database.upsert_issue(conn, repo, number, title, url)
    conn.close()

    return {
        "success": True,
        "repository": repo,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "skipped_pull_requests": skipped,
    }


def read_issues(repo, db_path):
    if not _is_valid_repo(repo):
        return _invalid_repo_failure(repo)
    repo = repo.lower()
    conn = database.connect(db_path)
    issues = database.list_issues(conn, repo)
    conn.close()
    return {"success": True, "repository": repo, "count": len(issues), "issues": issues}

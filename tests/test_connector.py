import json
from pathlib import Path

from connector import import_issues, read_issues

FIXTURE = Path(__file__).parent / "fixtures" / "issues_page.json"
REPO = "facebook/react"


def load_page():
    return json.loads(FIXTURE.read_text())


def count_real_issues():
    return sum(1 for i in load_page() if "pull_request" not in i)


def fake_fetch_ok(url):
    # Same shape as the real fetch: (status_code, headers, body_text)
    return 200, {}, FIXTURE.read_text()


def fake_fetch_500(url):
    return 500, {}, '{"message": "Server Error"}'


def test_import_then_read(tmp_path):
    db = str(tmp_path / "issues.db")
    result = import_issues(REPO, db, fetch=fake_fetch_ok)

    assert result["success"] is True
    assert result["repository"] == "facebook/react"
    assert result["inserted"] == count_real_issues()

    read = read_issues(REPO, db)
    assert read["success"] is True
    assert read["count"] == count_real_issues()
    first = read["issues"][0]
    assert set(first) == {"number", "title", "url"}


def test_import_twice_creates_no_duplicates(tmp_path):
    db = str(tmp_path / "issues.db")
    import_issues(REPO, db, fetch=fake_fetch_ok)
    second = import_issues(REPO, db, fetch=fake_fetch_ok)

    assert second["inserted"] == 0
    assert second["unchanged"] == count_real_issues()
    assert read_issues(REPO, db)["count"] == count_real_issues()


def test_api_failure_returns_useful_error(tmp_path):
    db = str(tmp_path / "issues.db")
    result = import_issues(REPO, db, fetch=fake_fetch_500)

    assert result["success"] is False
    assert result["repository"] == "facebook/react"
    assert result["error"]["code"] == "API_ERROR"
    assert result["error"]["message"]


def test_pull_requests_are_excluded(tmp_path):
    db = str(tmp_path / "issues.db")
    page = load_page()
    pr_numbers = {i["number"] for i in page if "pull_request" in i}
    assert pr_numbers, "fixture must contain at least one PR"

    result = import_issues(REPO, db, fetch=fake_fetch_ok)
    assert result["skipped_pull_requests"] == len(pr_numbers)

    saved = {i["number"] for i in read_issues(REPO, db)["issues"]}
    assert saved.isdisjoint(pr_numbers)


def fetch_must_not_be_called(url):
    raise AssertionError("fetch should not be called")


def test_invalid_repo_rejected_before_any_request(tmp_path):
    db = str(tmp_path / "issues.db")
    bad_names = ["react", "a/b/c", "", "/react", "facebook/", "face book/react",
                 "facebook/react;DROP TABLE issues", "../etc/passwd", "a/..", None]
    for bad in bad_names:
        result = import_issues(bad, db, fetch=fetch_must_not_be_called)
        assert result["success"] is False, bad
        assert result["error"]["code"] == "INVALID_REPO", bad
        assert result["error"]["message"]


def make_fetch(status, headers=None, body="{}"):
    return lambda url: (status, headers or {}, body)


def test_404_maps_to_not_found(tmp_path):
    db = str(tmp_path / "issues.db")
    result = import_issues("nobody/nothing", db, fetch=make_fetch(404, body='{"message": "Not Found"}'))
    assert result["success"] is False
    assert result["error"]["code"] == "NOT_FOUND"


def test_rate_limit_maps_to_rate_limited(tmp_path):
    db = str(tmp_path / "issues.db")
    exhausted = {"x-ratelimit-remaining": "0"}
    for fetch in (make_fetch(403, exhausted), make_fetch(429)):
        result = import_issues(REPO, db, fetch=fetch)
        assert result["success"] is False
        assert result["error"]["code"] == "RATE_LIMITED"


def test_403_with_requests_left_is_not_rate_limited(tmp_path):
    db = str(tmp_path / "issues.db")
    result = import_issues(REPO, db, fetch=make_fetch(403, {"x-ratelimit-remaining": "12"}))
    assert result["error"]["code"] == "API_ERROR"


def test_header_names_are_case_insensitive(tmp_path):
    db = str(tmp_path / "issues.db")
    result = import_issues(REPO, db, fetch=make_fetch(403, {"X-RateLimit-Remaining": "0"}))
    assert result["error"]["code"] == "RATE_LIMITED"


def test_network_failure_maps_to_network_error(tmp_path):
    import requests

    db = str(tmp_path / "issues.db")

    def timeout(url):
        raise requests.exceptions.Timeout("timed out")

    def refused(url):
        raise ConnectionError("connection refused")

    for fetch in (timeout, refused):
        result = import_issues(REPO, db, fetch=fetch)
        assert result["success"] is False
        assert result["error"]["code"] == "NETWORK_ERROR"


def test_malformed_response_maps_to_bad_response(tmp_path):
    db = str(tmp_path / "issues.db")
    bodies = ["this is not json", "", '{"message": "an object, not a list"}', "null"]
    for body in bodies:
        result = import_issues(REPO, db, fetch=make_fetch(200, body=body))
        assert result["success"] is False, body
        assert result["error"]["code"] == "BAD_RESPONSE", body


def one_issue_page(number, title):
    page = [{"number": number, "title": title, "html_url": f"https://github.com/x/y/issues/{number}"}]
    return make_fetch(200, body=json.dumps(page))


def test_title_change_on_reimport_is_updated(tmp_path):
    db = str(tmp_path / "issues.db")
    import_issues("a/b", db, fetch=one_issue_page(1, "old title"))
    result = import_issues("a/b", db, fetch=one_issue_page(1, "new title"))
    assert result["updated"] == 1 and result["inserted"] == 0
    assert read_issues("a/b", db)["issues"][0]["title"] == "new title"


def test_same_issue_number_in_two_repos_does_not_collide(tmp_path):
    db = str(tmp_path / "issues.db")
    import_issues("a/one", db, fetch=one_issue_page(1, "from one"))
    import_issues("a/two", db, fetch=one_issue_page(1, "from two"))
    assert read_issues("a/one", db)["issues"][0]["title"] == "from one"
    assert read_issues("a/two", db)["issues"][0]["title"] == "from two"


def test_repo_names_are_case_insensitive(tmp_path):
    db = str(tmp_path / "issues.db")
    import_issues("Facebook/React", db, fetch=fake_fetch_ok)
    again = import_issues("facebook/react", db, fetch=fake_fetch_ok)
    assert again["inserted"] == 0
    assert read_issues("FACEBOOK/REACT", db)["count"] == count_real_issues()


def test_read_never_calls_fetch(tmp_path, monkeypatch):
    import github_client

    db = str(tmp_path / "issues.db")
    import_issues(REPO, db, fetch=fake_fetch_ok)
    monkeypatch.setattr(github_client, "default_fetch", fetch_must_not_be_called)
    monkeypatch.setattr(github_client, "fetch_open_issues", fetch_must_not_be_called)
    assert read_issues(REPO, db)["count"] == count_real_issues()


def test_data_persists_in_the_database_file(tmp_path):
    import sqlite3

    db = str(tmp_path / "issues.db")
    import_issues(REPO, db, fetch=fake_fetch_ok)
    conn = sqlite3.connect(db)  # a brand new connection, like a restarted program
    (rows,) = conn.execute("SELECT COUNT(*) FROM issues").fetchone()
    conn.close()
    assert rows == count_real_issues()


def test_read_with_invalid_repo_returns_error(tmp_path):
    result = read_issues("not a repo", str(tmp_path / "issues.db"))
    assert result["success"] is False
    assert result["error"]["code"] == "INVALID_REPO"


def test_403_with_retry_after_is_rate_limited(tmp_path):
    # GitHub docs: a secondary rate limit is a 403 or 429 with a retry-after header,
    # and x-ratelimit-remaining may still be above 0.
    db = str(tmp_path / "issues.db")
    headers = {"retry-after": "60", "x-ratelimit-remaining": "40"}
    result = import_issues(REPO, db, fetch=make_fetch(403, headers))
    assert result["error"]["code"] == "RATE_LIMITED"


def test_malformed_issue_items_map_to_bad_response_and_write_nothing(tmp_path):
    db = str(tmp_path / "issues.db")
    good = {"number": 1, "title": "ok", "html_url": "https://github.com/a/b/issues/1"}
    bad_pages = [
        [1, 2],                                        # items are not objects
        [None],
        [good, {"number": 9}],                         # missing title and html_url
        [{"number": 3, "title": None, "html_url": "u"}],  # null title
    ]
    for page in bad_pages:
        result = import_issues("a/b", db, fetch=make_fetch(200, body=json.dumps(page)))
        assert result["success"] is False, page
        assert result["error"]["code"] == "BAD_RESPONSE", page
    assert read_issues("a/b", db)["count"] == 0  # nothing partially saved

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

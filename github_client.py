import json

import requests


class GitHubError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def default_fetch(url):
    """Real HTTP call. Returns (status_code, headers, body_text)."""
    resp = requests.get(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "rr-connector"},
        timeout=10,
    )
    return resp.status_code, dict(resp.headers), resp.text


def fetch_open_issues(repo, fetch=default_fetch):
    """Fetch ONE page of open issues. Returns the parsed JSON list."""
    url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page=30"
    status, headers, body = fetch(url)
    if status != 200:
        raise GitHubError("API_ERROR", f"GitHub returned HTTP {status}")
    return json.loads(body)

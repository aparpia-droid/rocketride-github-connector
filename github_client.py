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
    try:
        status, headers, body = fetch(url)
    except OSError as e:
        # requests exceptions, ConnectionError and TimeoutError are all OSError subclasses
        raise GitHubError("NETWORK_ERROR", f"Could not reach GitHub: {e}")
    headers = {k.lower(): v for k, v in headers.items()}
    out_of_requests = headers.get("x-ratelimit-remaining") == "0"
    told_to_wait = "retry-after" in headers  # GitHub's secondary rate limit signal
    if status == 429 or (status == 403 and (out_of_requests or told_to_wait)):
        raise GitHubError("RATE_LIMITED", "GitHub rate limit reached, try again later")
    if status == 404:
        raise GitHubError("NOT_FOUND", f"Repository {repo} was not found on GitHub")
    if status != 200:
        raise GitHubError("API_ERROR", f"GitHub returned HTTP {status}")
    try:
        issues = json.loads(body)
    except ValueError:
        raise GitHubError("BAD_RESPONSE", "GitHub returned a response that is not valid JSON")
    if not isinstance(issues, list):
        raise GitHubError("BAD_RESPONSE", "GitHub returned JSON that is not a list of issues")
    for item in issues:
        # Pull requests are skipped later, so only real issues need the three fields.
        if not isinstance(item, dict):
            raise GitHubError("BAD_RESPONSE", "GitHub returned a list item that is not an object")
        if "pull_request" in item:
            continue
        if not (
            isinstance(item.get("number"), int)
            and isinstance(item.get("title"), str)
            and isinstance(item.get("html_url"), str)
        ):
            raise GitHubError("BAD_RESPONSE", "GitHub returned an issue missing number, title or html_url")
    return issues

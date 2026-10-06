# GitHub Issue Snapshot Connector

Imports the open issues of a public GitHub repository into a local SQLite file, and reads them back later without calling GitHub.

- `import_issues(repo, db_path)` fetches one page of open issues, drops pull requests, and saves repository, issue number, title and URL.
- `read_issues(repo, db_path)` returns the saved issues from SQLite only. It never makes a network call.
- Importing the same repo again updates existing rows. It never creates duplicates.
- Both functions return the same JSON-compatible envelope, and a thin CLI wraps them.

## Prerequisites

- Python 3 (developed and tested on 3.12)
- Internet access for `import` only. No GitHub token or account is needed.

## Setup

```bash
git clone https://github.com/aparpia-droid/rocketride-github-connector.git
cd rocketride-github-connector
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python cli.py import facebook/react
python cli.py read facebook/react
```

Database path, in order of priority: `--db PATH`, then the `RR_DB_PATH` environment variable, then `./issues.db`.

```bash
python cli.py import facebook/react --db /tmp/issues.db
RR_DB_PATH=/tmp/issues.db python cli.py read facebook/react
```

The CLI prints JSON and exits with 0 on success or 1 on failure.

It can also be used as a library:

```python
from connector import import_issues, read_issues

import_issues("facebook/react", "issues.db")
read_issues("facebook/react", "issues.db")
```

## Test

```bash
python -m pytest
```

All tests run without network access. They use a real GitHub response saved in `tests/fixtures/issues_page.json` (captured from `facebook/react`, 22 pull requests and 8 issues) and an injected fetch function.

## Example output

Real runs against the live API (the first import was into an empty database):

```
$ python cli.py import facebook/react
{
  "success": true,
  "repository": "facebook/react",
  "inserted": 8,
  "updated": 0,
  "unchanged": 0,
  "skipped_pull_requests": 22
}

$ python cli.py import facebook/react        # second run, same data
{
  "success": true,
  "repository": "facebook/react",
  "inserted": 0,
  "updated": 0,
  "unchanged": 8,
  "skipped_pull_requests": 22
}

$ python cli.py read facebook/react          # separate process, reads the file
{
  "success": true,
  "repository": "facebook/react",
  "count": 8,
  "issues": [
    {
      "number": 37762,
      "title": "Bug: \"Cannot commit the same tree as before\" ...",
      "url": "https://github.com/react/react/issues/37762"
    },
    ...
  ]
}

$ python cli.py import facebook/this-repo-does-not-exist-xyz
{
  "success": false,
  "repository": "facebook/this-repo-does-not-exist-xyz",
  "error": {
    "code": "NOT_FOUND",
    "message": "Repository facebook/this-repo-does-not-exist-xyz was not found on GitHub"
  }
}
```

These outputs are a point-in-time snapshot of `facebook/react`. The counts and titles will differ when you run the connector later, because they depend on what is open at that moment.

Error codes: `INVALID_REPO`, `NOT_FOUND`, `RATE_LIMITED`, `NETWORK_ERROR`, `API_ERROR`, `BAD_RESPONSE`. See [Architecture.MD](Architecture.MD) for when each one is returned. An unwritable `--db` path is deliberately not one of them: I chose to keep the contract at six codes, so it surfaces as the underlying OS error (explained in the Architecture error-handling section).

## Known limits

- One page only: `per_page=30`. Pull requests share that page, so fewer than 30 issues may be saved.
- Imports never delete rows. With one page there is no way to tell a closed issue from one that is just not on page 1.
- Without a token GitHub allows about 60 requests per hour per IP.
- `read` on a path with no file creates an empty database file.
- Two imports running at the same time into one file are not handled.

## AI and tools used

- **ChatGPT** for architecture and scope decisions throughout: what not to build (no UI, no pagination, no retries, no extra abstractions), the module split, and pushing back on scope creep. Most of the design judgment came out of that back and forth.
- **Claude Code (Claude Sonnet 5.5)** for the implementation, the test-first workflow and debugging, one step at a time, with a failing test committed before each fix. I reviewed each step and answered design questions before moving on.
- **Cursor cloud agents** for independent verification. They re-ran the `facebook/react` request against the live API and confirmed the 301, found where it redirects (see below), reviewed all four modules, ran the test suite separately, and flagged agent tooling files that should not be committed to this repo. No Cursor output is in the repository.
- **GitHub REST API docs and `curl`** to check real API behavior (redirects, status codes, rate limit headers) instead of trusting memory.

`AI_LOG.md` records what the AI got wrong and what a test or the real API corrected.

## One problem solved with AI, and how I checked it

**Rate limit detection.** I needed to tell "you are rate limited" apart from other errors. The first version (from the PRD and from Claude) treated a response as rate limited if it was a 429, or a 403 with `x-ratelimit-remaining: 0`. The tests passed, and the live API did not contradict it, because I could not trigger a limit on purpose.

During the review pass I questioned that assumption and checked GitHub's official rate limit documentation instead of trusting either of us. It says a secondary rate limit is also a 403 or 429, signalled by a `retry-after` header, and `x-ratelimit-remaining` may still be above zero. Under the first rule that response would have been reported as a generic `API_ERROR`, which is misleading because the caller should wait and retry.

I added a failing test for a 403 with `retry-after` and `remaining: 40`, then changed the classifier so a 403 with `retry-after` is `RATE_LIMITED`. A separate test keeps a plain 403 as `API_ERROR`, so access errors are not mislabeled.

A smaller finding came from the first real capture: my first `curl` for `facebook/react` returned HTTP 301 "Moved Permanently" and I almost saved that message as the fixture. Counting the items caught it. GitHub redirects to a numeric repository ID endpoint (`api.github.com/repositories/10270250/issues`), and the issue URLs in the response show a different owner (`react/react`) than the `facebook/react` I typed. That is why rows are keyed by the name the user supplied and not by GitHub's URLs. The `requests` library follows the redirect, which I confirmed against the live API.

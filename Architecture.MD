# Architecture

## Interface

Two plain functions, both returning JSON-compatible dicts.

```python
import_issues(repo, db_path, fetch=default_fetch) -> dict
read_issues(repo, db_path) -> dict
```

Success:

```json
{"success": true, "repository": "facebook/react", "inserted": 8, "updated": 0, "unchanged": 0, "skipped_pull_requests": 22}
{"success": true, "repository": "facebook/react", "count": 8, "issues": [{"number": 1, "title": "...", "url": "..."}]}
```

Failure (same shape for every error):

```json
{"success": false, "repository": "facebook/react", "error": {"code": "NOT_FOUND", "message": "..."}}
```

CLI: `python cli.py import|read owner/name [--db PATH]`. Prints the dict as JSON. Exit code 0 on success, 1 on failure.

## Components

| File | Responsibility |
|---|---|
| `connector.py` | Validates the repo name, normalizes it, runs the import inside one transaction, counts results, builds the envelope |
| `github_client.py` | Builds the URL, calls the injected `fetch`, maps HTTP and network failures to error codes, validates the response shape |
| `database.py` | Creates the schema and runs the parameterized SQL (existing rows, upsert, list) |
| `cli.py` | Parses arguments, picks the DB path, calls the connector, prints JSON |

`github_client.py` and `database.py` do not know about each other. Only `connector.py` uses both.

## Data flow

```
import:
  CLI/caller --> connector.import_issues
                   |-- validate repo (regex), lowercase
                   |-- github_client.fetch_open_issues --> fetch(url) --> GitHub (1 page)
                   |        |-- map status/network/JSON problems to error codes
                   |        '-- check the whole page before returning it
                   |-- BEGIN
                   |-- database.get_existing (rows for this repo)
                   |-- for each non-PR issue: count inserted/updated/unchanged, upsert
                   '-- COMMIT --> result dict

read:
  CLI/caller --> connector.read_issues --> database.list_issues --> SQLite file
                 (no import of fetch on this path, no network)
```

## Schema

```sql
CREATE TABLE IF NOT EXISTS issues (
  repository   TEXT    NOT NULL,
  issue_number INTEGER NOT NULL,
  title        TEXT    NOT NULL,
  url          TEXT    NOT NULL,
  PRIMARY KEY (repository, issue_number)
);
```

Upsert: `INSERT ... ON CONFLICT(repository, issue_number) DO UPDATE SET title, url`. Counts come from comparing the page with the existing rows before writing.

## Configuration

Database path: `--db` flag, then `RR_DB_PATH`, then `./issues.db`. The library functions take the path as an argument. The request timeout is 10 seconds.

## Error handling

Checked in this order inside `github_client.py`, after the repo name check in `connector.py`:

| Code | When |
|---|---|
| `INVALID_REPO` | Name is not `owner/name` (letters, digits, `-` in the owner; letters, digits, `.`, `_`, `-` in the name; `.` and `..` rejected). No request is made. |
| `NETWORK_ERROR` | `fetch` raises an `OSError` (includes `requests` timeouts and connection errors) |
| `RATE_LIMITED` | 429, or 403 with `x-ratelimit-remaining: 0`, or 403 with `retry-after` (secondary limit) |
| `NOT_FOUND` | 404 |
| `API_ERROR` | Any other non-200, including 5xx and a 403 that is not a rate limit |
| `BAD_RESPONSE` | Body is not JSON, is not a list, or an issue is missing `number`, `title` or `html_url` |

Only `OSError` is caught around the fetch, so a bug in this code is not reported as a network problem.

**Where the contract stops.** The error envelope describes outcomes of the connector's own operations: bad input, and anything GitHub does. An unwritable database path is an environment misconfiguration, not a connector outcome, so it surfaces as the underlying OS error (`sqlite3.OperationalError: unable to open database file`) rather than being flattened into JSON. This is why there are six error codes and not seven. I made that call deliberately.

## Design decisions and tradeoffs

- **D1 Lowercase repo names.** GitHub names are case-insensitive, so `Facebook/React` and `facebook/react` are one key. The key is the name the user typed, not GitHub's: a request for `facebook/react` is redirected to `/repositories/10270250/issues`, and the stored URLs show a different owner (`react/react`).
- **D2 Composite primary key.** Issue numbers are only unique inside one repository.
- **D3 Imports never delete.** One page cannot tell a closed issue from one that is not on page 1, so deleting would lose data. Cost: closed issues stay in the database.
- **D4 Injected fetch.** `fetch(url)` returns `(status_code, headers, body_text)`. Tests pass a fake that serves a real saved response, so no network and no mocking library.
- **D5 Parameterized SQL.** The repo name is validated by regex and never put into SQL text.
- **D6 Counts in the result.** `inserted`, `updated`, `unchanged` and `skipped_pull_requests` make a repeated import visibly idempotent.
- **D7 Three modules.** HTTP, storage and orchestration are separate so each can be tested alone.
- **One transaction per import, and the page is checked first.** A bad page is rejected before the database is touched, and any failure during writes rolls back. An import is all or nothing.
- **Whole-page validation is deliberately small.** It checks only the three fields we store, and only for non-PR items.

## Future directions

Not built: pagination (follow the `Link` header to read every page and allow safe deletion of closed issues), and an MCP wrapper that exposes `import_issues` and `read_issues` as tools.

# AI_LOG

Running notes of what the AI got wrong or right, and what real checks corrected. Only real events go here.

## Decisions and assumptions (PRD gaps, decided explicitly)
- RocketRide_Student_Challenge.docx was not available at the start. The PRD is the spec until it is checked against the brief.
- Only a 403 with x-ratelimit-remaining: 0 maps to RATE_LIMITED, plus 429. Other 403, 401, 410, 422 map to API_ERROR.
- A 200 response that is valid JSON but not a list maps to BAD_RESPONSE.
- An import runs in one transaction, so a failed import writes nothing.
- The response "repository" field is the normalized (lowercase) name, matching what is stored.
- Repo regex: owner is letters, digits, hyphens; name is letters, digits, ".", "_", "-"; names "." and ".." are rejected.

## Step 1: scaffold
- No corrections. Repo layout from PRD section 7, pushed to origin/main. gh was already logged in, so no deploy key was needed.

## Step 2: fixture capture
- Wrong: my first curl for facebook/react returned HTTP 301 and a 227 byte "Moved Permanently" body, not issues. I almost saved that as the fixture. Caught by counting items (3 keys, not a list).
- Real API behavior: the repo moved, so GitHub redirects /repos/facebook/react to /repositories/10270250. curl needs -L. requests follows redirects on GET by default, so the connector should work, but this must be tested live in step 6.
- Real API behavior: issue html_url values say github.com/react/react/issues/N even though we asked for facebook/react. We store the URL GitHub gives, and key rows by the repo name the user typed (lowercased). Worth mentioning in Architecture.MD.
- Fixture: facebook/react, 30 items, 22 pull requests, 8 issues, all with number/title/html_url. 160 KB of public data, no secrets, no edits made.

## Step 3: failing tests first
- Wrote 4 tests (import then read, import twice, API failure, PR exclusion) against the real fixture. They fail at collection: ImportError, cannot import name import_issues from connector. That is the expected reason, since connector.py is a stub.
- Decision: the injected fetch is fetch(url) -> (status_code, headers, body_text) and raises on network failure. Tests fix this contract before any implementation exists.
- Pasted Cursor output described the repo as empty with a Cursor temp remote. That was stale; this repo already had the scaffold and fixture on GitHub. Declined its extra handoff files for now, since they are outside the PRD layout.

## Step 4: naive implementation
- Changed the tests (at the user's request) to compute the expected count from the fixture instead of hardcoding 8. Reason: a recaptured fixture would break a hardcoded number.
- First naive version passes all 4 tests. Known gaps left on purpose, to be driven by failing tests in step 5: no repo validation, only HTTP status != 200 maps to API_ERROR (404 and rate limit are not distinguished yet), a network exception or bad JSON would crash instead of returning an error envelope.
- No real corrections yet; nothing in the naive version has been tested against the live API.

## Step 5: error mapping and extra tests
- Each of INVALID_REPO, NOT_FOUND, RATE_LIMITED, NETWORK_ERROR, BAD_RESPONSE was added as a failing test commit followed by a fix commit.
- Test that passed before any fix: 403 with requests left stays API_ERROR (naive code already did that). It is a guard, not a failing-first test. The same is true of title update, repo collision, case-insensitivity, read-without-network and persistence: they passed on the naive code, so I checked them by mutation instead.
- Mutation checks (temporary edits, then restored): upsert DO NOTHING failed the title-update test; removing lowercasing failed the case test; removing repository from the primary key failed 8 tests, but with a sqlite OperationalError (ON CONFLICT target no longer matches), not a clean assertion. So the collision test is not what catches that one by itself.
- Real miss found by a test: read_issues did not validate the repo (I only validated in import_issues). A junk name or None would have been lowercased or crashed. Fixed by sharing the check.
- Design note: all of requests' exceptions, ConnectionError and TimeoutError are OSError subclasses, so one except OSError covers NETWORK_ERROR.
- Header names are lowercased before checking x-ratelimit-remaining, because HTTP/2 sends them lowercase and a test can pass any case.

## Step 6: CLI and live run
- CLI tests (JSON output, exit codes, --db > RR_DB_PATH > ./issues.db) written first, failed with AttributeError (no cli.main), then cli.py made them pass. 20 tests total.
- Live run against api.github.com for facebook/react: inserted 8, skipped_pull_requests 22. Same numbers as the fixture, which is expected because it was captured minutes earlier, not a coincidence to rely on.
- The 301 redirect from step 2 was handled by requests with no extra code, as predicted. Checked live, not assumed.
- Second import (typed as Facebook/React): inserted 0, unchanged 8; sqlite row count stayed 8, so case normalization and idempotency both hold against the real API.
- Each CLI call was a separate process, so the read after import proves data comes from the SQLite file.
- Real error cases: nonexistent repo gives NOT_FOUND (exit 1), not-a-repo gives INVALID_REPO (exit 1).
- Not done on purpose: RR_LIVE=1 smoke test (optional in PRD).

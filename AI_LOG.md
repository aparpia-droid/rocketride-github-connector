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

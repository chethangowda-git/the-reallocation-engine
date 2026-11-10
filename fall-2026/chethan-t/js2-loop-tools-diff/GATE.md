# GATE.md — Job-Search Agent 2

Author: Chethan Gowda GT
Written: 2026-11-10 (before any code changes by Claude Code)

## Boards

| Company | ATS | Board name | API endpoint |
|---|---|---|---|
| ATLAS SP | Greenhouse | `atlassp` | `https://boards-api.greenhouse.io/v1/boards/atlassp/jobs` |
| HubSpot | Greenhouse | `hubspotjobs` | `https://boards-api.greenhouse.io/v1/boards/hubspotjobs/jobs` |
| Analytic Partners | Lever | `analyticpartners` | `https://api.lever.co/v0/postings/analyticpartners?mode=json` |
| Deliberate failure | Greenhouse | `atlassp-doesnotexist` | `https://boards-api.greenhouse.io/v1/boards/atlassp-doesnotexist/jobs` |

Note: the deliberate-failure board is included in the demo run, so that run is expected to end `incomplete`, not `finished`.

---

## 1. Exits

Every run ends with exactly one status. A loop that stops is not a loop that succeeded.

| Status | When it happens | What it reports |
|---|---|---|
| **finished** | Every board was fetched successfully and filtered. | New matching jobs per board (by job ID, compared with last run's set). |
| **incomplete** | At least one board failed after its allowed retries; the others succeeded. | Results for the boards that succeeded; for each failed board: what failed and why. A failed board is never reported as "0 jobs." |
| **budget-exhausted** | A budget (boards, requests, or time) ran out before all boards were checked. | Which boards were done, which were skipped, and which budget ran out. |
| **error** | Something broke for the whole run (bad config, can't read/save state, repeated action). | The error and its reason. Results only for boards completed before the error, clearly marked. |

New jobs are found by comparing the **full set of job IDs** with last run's saved set, not by checking only the last job.

---

## 2. Budgets

| Budget | Limit per run |
|---|---|
| Boards | 4 |
| Requests | 8 (1 + 1 retry per board) |
| Time | 60 seconds per run |
| Per request | 10 second timeout |

If the board list grows past 4, the run stops with `budget-exhausted` rather than checking more.

**Who may change budgets:** only Chethan, by editing this file with a dated note explaining the decision.

---

## 3. Repeat rule

- **Same action:** fetching the same board again in one run, beyond its allowed retry.
- **On repeat:** stop the run with status `error` ("loop repeated an action"). Report which boards were done and which were not.
- **Duplicate jobs:** if the same job ID appears twice, keep one and log that a duplicate was dropped.

---

## 4. Error policy

| Case | Retry? | Why | Action | Run status |
|---|---|---|---|---|
| Timeout / 5xx | Once | May be temporary on the server side. | If it fails again, record the error type and status code. | incomplete |
| 404 not found | No | Retrying won't fix a wrong board name. | Escalate to Chethan, who fixes the board name by hand. The agent never edits board names or URLs itself. | incomplete |
| Empty response | No | 0 jobs may mean a wrong URL or broken response, not a truly empty board. | Flag as suspicious; never report as "no new jobs." Escalate to Chethan. | incomplete |

**Every failure report includes:**
- what failed (board, URL, status code or error)
- a likely reason
- a manual check: the exact URL or `curl` command to confirm it by hand

---

## 5. Permission policy

**Hosts (allow-list):**
- `boards-api.greenhouse.io`
- `api.lever.co`

Every other host is blocked.

**Folders:**

| Folder | Read | Write |
|---|---|---|
| `config/` (board list, filters) | ✅ | Needs Chethan's approval |
| `state/` (last run's job IDs) | ✅ | ✅ (deleting needs approval) |
| `jobs/` (results, traces, raw responses) | ✅ | ✅ |
| Anything else | ❌ | ❌ |

**Blocked paths:** `..` escapes, look-alike folders (e.g. `jobs-evil/`), and symlinks pointing outside the allowed folders.

**Never:** apply to jobs, send email, send messages, log in, send any POST request, or use credentials. The agent only reads with GET.

The policy is enforced in code, not in a prompt.

---

## 6. Wrong versions (tests must catch these)

| # | Wrong version | Test |
|---|---|---|
| 1 | Empty board reported as "no new jobs" with status `finished`. | Fake an empty response; expect `incomplete` and an escalation. |
| 2 | Filter too strict — a matching job is dropped (e.g. "Sr. Software Engineer" missed). | Feed sample titles with known expected matches. |
| 3 | Stale data reported as fresh — last run's saved jobs shown when this run's fetch failed. | Fail the fetch; output must mark the board failed, not show old jobs. |
| 4 | Claims it ran but didn't — status `finished` though a board was never fetched. | Every board must have a logged observation with timestamp and status code. |
| 5 | Failed board wipes saved state — next run shows every job as "new." | Fail a board; `state/` must stay unchanged for that board. |
| 6 | Path check by prefix — `startswith("jobs")` allows `jobs-evil/`. | Boundary test. |
| 7 | Retrying a 404 — wastes budget. | A 404 board must get exactly 1 request. |

# Sources

## Executive summary

**What this is.** Everything this agent was built from or relied on: the contract, the code it
started from, the job-board APIs it calls, and the tools used to write it.

**Why read it.** To check where each piece came from and how far each source was trusted.

**What it found.** One contract (Chethan's), one starting script (copied unchanged), two public
job-board APIs, the Python standard library and pytest, and Claude Code as the drafting tool.
The two API references were not opened while building; the field names the code uses were
instead confirmed against the real responses saved on 2026-11-10.

---

| Source | What it is | How it was used |
|---|---|---|
| `GATE.md` (this folder; Chethan, commit `dd20bf6`) | the contract: boards, exits, budgets, repeat rule, error policy, permissions, wrong versions | the specification for every test and every module |
| Reallocation Engine — greenhouse-watch skill, `.claude/skills/greenhouse-watch/scripts/greenhouse_watch.py` | the starting point (one-board Greenhouse watcher) | copied **unchanged** to `agent/greenhouse_watch.py`; its `fetch_board` ideas (no-redirect handler, fixed User-Agent, host allow-list) reused in `agent/fetch.py` and `agent/policy.py` |
| Reallocation Engine — ATS providers, `scripts/ats/providers/greenhouse.mjs`, `lever.mjs`, `ashby.mjs`, `_http.mjs` | the repo's JavaScript ATS fetchers | read during the initial inspection to compare endpoints, allow-lists and error handling; no code copied |
| Greenhouse Job Board API — <https://developers.greenhouse.io/job-board.html> | public, unauthenticated board API: `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` | endpoint used for `atlassp`, `hubspotjobs`, `atlassp-doesnotexist`; fields used: `jobs[].id`, `title`, `absolute_url`, `location.name` |
| Lever Postings API — <https://github.com/lever/postings-api> | public postings API: `GET https://api.lever.co/v0/postings/{site}?mode=json` | endpoint used for `analyticpartners`; fields used: `id`, `text`, `hostedUrl`, `categories.location` |
| Python standard library — <https://docs.python.org/3/library/> | `urllib.request` (`HTTPRedirectHandler`, `build_opener`), `urllib.parse`, `json`, `os.path.realpath`, `pathlib`, `shlex`, `runpy` | the whole implementation; no third-party runtime packages |
| pytest 8.4.2 — <https://docs.pytest.org/> | test runner | `tests/` (fixtures, `monkeypatch`, `parametrize`, `tmp_path`) |
| Claude Code (Claude Opus 5.5, Anthropic) | AI coding assistant | drafted tests, code and these documents under Chethan's direction; see the driver's-seat table in `README.md` |

**How far the API references were trusted.** The two API pages were not opened during this
session; the endpoint shapes and field names above come from prior knowledge. They were then
confirmed against the real saved responses in `jobs/raw/` (2026-11-10 runs): every field the
code reads is present in both the Greenhouse and the Lever responses.

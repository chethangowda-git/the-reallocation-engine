# Job-Search Agent 2 — a bounded loop over job boards

## Executive summary

**What this is.** A small program that checks four company job boards once, compares each
board's job list with what it saw last time, and reports any new software-engineering jobs.
It is built to stop safely: it has fixed limits on how many boards, requests and seconds it
may use, it never treats an empty or failed answer as "no new jobs", and it may only talk to
two approved job-board hosts and write inside three folders.

**Why read it.** It says how to run it from a fresh copy, what happened when it ran against
the real boards, what was checked and how, what was *not* checked, and who decided what.

**What it found.** Both real runs ended "incomplete" — as intended, because one of the four
boards is a deliberately wrong address that answers "not found". The other three boards
answered normally. 128 automated tests pass. Chethan signed off on 2026-11-10 (end of the
sign-off section).

---

## Language and toolchain

- **Python 3.10 or newer** (the timeout handling relies on `socket.timeout` being
  `TimeoutError`, which is true from 3.10). Developed and tested on **Python 3.13.9**.
- **pytest 8.4.2** for the tests. Everything else is the Python standard library — the real
  fetcher uses `urllib.request`; there are no other dependencies.

## Where it started

From the Reallocation Engine's **greenhouse-watch** skill
(`.claude/skills/greenhouse-watch/`). Its script `greenhouse_watch.py` is copied **unchanged**
into `agent/greenhouse_watch.py` as the starting point; two ideas from its `fetch_board`
(a no-redirect handler and a fixed User-Agent) were reused. All new code is in `agent/`:

| File | What it does |
|---|---|
| `GATE.md` | the contract — exits, budgets, repeat rule, error policy, permissions, wrong versions (written by Chethan first) |
| `agent/policy.py` | the permission policy, enforced in code |
| `agent/loop.py` | the bounded multi-board loop |
| `agent/fetch.py` | the real HTTP fetcher (GET only, no redirects, 10 s timeout) |
| `agent/run.py` | `python -m agent.run` — loads the boards, runs the loop, saves traces |
| `demo/finished_wrong.py` | offline demo: a naive loop's clean-looking wrong answer, and the check that catches it |
| `config/boards.json` | the four boards from GATE.md |
| `tests/` | 128 tests, all offline |

## Commands, from a fresh clone

```bash
git clone https://github.com/chethangowda-git/the-reallocation-engine.git
cd the-reallocation-engine
git checkout js2-chethan-t
cd fall-2026/chethan-t/js2-loop-tools-diff

python3 -m venv .venv && source .venv/bin/activate     # optional; .venv/ is gitignored
python -m pip install pytest

python -m pytest -q                 # expect: 128 passed — offline, no network
python -m demo.finished_wrong       # offline demo; exit code 0 means the wrong answer was caught
python -m agent.run                 # REAL network: GETs the 4 boards in config/boards.json
echo $?                             # expect 1 (incomplete) — the deliberate 404 board
```

Notes: the branch must be pushed for `git checkout js2-chethan-t` to work from a fresh clone
(it is local-only at the time of writing). `python -m agent.run` writes to `state/` and
`jobs/` in this folder. Because the saved `state/` from the runs below is committed, a fresh
run compares against 2026-11-10's job lists (boards show `ok`, not `baseline`).

Exit codes: `0` finished · `1` incomplete · `2` budget-exhausted · `3` error.

## What ran against the real boards

Chethan ran `python -m agent.run` twice on 2026-11-10. Both traces are in `jobs/traces/`,
raw responses in `jobs/raw/`, saved job IDs in `state/`.

| Run (UTC) | Trace | Exit | Status | atlassp | hubspotjobs | analyticpartners | atlassp-doesnotexist |
|---|---|---|---|---|---|---|---|
| 21:37:20 | `jobs/traces/20261110T213720Z.json` | 1 | incomplete | baseline, HTTP 200 | baseline, HTTP 200 | baseline, HTTP 200 | failed, HTTP 404, escalated |
| 21:37:22 | `jobs/traces/20261110T213722Z.json` | 1 | incomplete | ok, 0 new | ok, 0 new | ok, 0 new | failed, HTTP 404, escalated |

Each board used 1 request in each run. The real boards listed 2, 122 and 21 jobs, the same
IDs in both runs. As GATE.md predicts, the deliberate-failure board makes each run
`incomplete`, not `finished`.

---

## Sign-off

### Checked

Properties, each with the tests that check it (all pass: `python -m pytest -q` → 128 passed):

| Property | Tests |
|---|---|
| Every run ends with exactly one status, mapped to an exit code | `test_all_boards_ok_is_finished`, `test_exit_code_matches_run_status[…]`, `test_python_m_agent_run_exits_with_the_run_code` |
| An empty response is never "no new jobs" | `test_empty_response_is_incomplete_never_no_new_jobs[…]`, `test_failed_board_is_absent_from_new_jobs[…]`, `test_independent_check_flags_the_mismatch`, `test_independent_check_flags_mismatch_against_the_committed_real_raw` |
| A 404 gets exactly one request and is escalated | `test_404_is_incomplete_other_boards_checked_and_single_request` |
| Timeout / 5xx: one retry, then fail | `test_timeout_or_5xx_retried_once_then_incomplete[…]`, `test_timeout_then_successful_retry_is_finished` |
| Budgets stop the run (4 boards, 8 requests, 60 s) | `test_five_boards_over_board_budget_is_budget_exhausted`, `test_more_than_8_requests_is_budget_exhausted`, `test_run_over_60_seconds_is_budget_exhausted` |
| Repeat rule and duplicate job IDs | `test_same_board_fetched_twice_beyond_retry_is_error`, `test_duplicate_job_ids_kept_once` |
| A failed board never changes its state or shows old jobs | `test_failed_board_leaves_its_saved_state_unchanged[…]`, `test_failed_board_does_not_report_last_runs_jobs` |
| First run is a baseline; a job seen before is never new again | `test_first_run_without_state_is_baseline_never_zero_new_jobs`, `test_job_seen_earlier_then_removed_then_reposted_is_not_new` |
| Every board attempted is logged with time and status code | `test_every_board_has_observation_with_timestamp_and_status_code` |
| Title filter (decision #6, whole-word "sde") | `test_sr_software_engineer_matches_title_filter`, `test_title_filter_matches_each_term[…]`, `test_title_filter_rejects_non_engineering_titles[…]`, `test_sde_matches_only_as_whole_word[…]` |
| Permissions enforced in code (hosts, folders, GET only, every write) | all of `tests/test_policy.py`, plus `test_blocked_host_is_never_fetched`, `test_fetcher_checks_host_itself_and_never_opens[…]`, `test_every_write_goes_through_check_write` — see `PERMISSIONS.md` |
| Fetcher: no redirects, timeout passed through and raised, empty body → None | `test_3xx_is_returned_as_is_and_never_followed[…]`, `test_no_redirect_handler_refuses_to_follow`, `test_default_opener_uses_no_redirect_handler`, `test_timeout_is_passed_through_to_the_opener`, `test_timeouts_raise_timeout_error[…]`, `test_other_transport_error_is_not_a_timeout`, `test_200_empty_body_is_none` |
| Run outputs: raw per board, never overwritten, bad config → exit 3 | `test_raw_responses_saved_per_requested_board`, `test_two_runs_in_the_same_second_do_not_overwrite`, `test_unreadable_config_exits_3_without_fetching[…]` |

### How

- **Tests were drafted by Claude (Claude Code, Claude Opus 5.5) from Chethan's `GATE.md`,
  and reviewed by Chethan** before any implementation; they were committed failing first
  (`5f20161`, `7019e49`, `861812c`). Chethan made the open decisions they encode: the title
  filter terms (#6), first-run baseline (#9), `[]` vs absent, whole-word "sde", the stricter
  delete rule, and "a job seen in any earlier run is not new".
- **Checks Chethan ran in Chethan's own terminal:**
  - `python -m pytest -q` on the loop → 81 passed; planted bug (the `check_host` call
    commented out) → 1 failed, 80 passed (`test_blocked_host_is_never_fetched`); restored →
    81 passed.
  - The reposted-job fix: with the fix → 128 passed; fix reverted → 1 failed, 127 passed
    (`test_job_seen_earlier_then_removed_then_reposted_is_not_new`, `assert ['123'] == []`);
    restored → 128 passed.
  - The two real runs of `python -m agent.run` (table above).
- **Checks Claude ran** (labelled so they are not mistaken for Chethan's): mutation checks in
  a scratch copy — 6 planted bugs in `loop.py` and 7 in `fetch.py`/`run.py`, all caught; the
  grep for `startswith`/`requests`/`urllib`; re-running each test commit from a clean
  `git archive` extract; a scan of the real-run files for emails, phone numbers and named
  contacts (none found).

### Not checked

1. **HTTP 429 (rate limited).** Handled as a failure with no retry and escalated; never tested,
   never seen live.
2. **A real redirect.** Only the no-redirect handler and a simulated 3xx are tested; no live
   board has ever answered with a redirect.
3. **The 60-second budget stopping a retry.** The time budget is tested between boards only;
   running out between a first attempt and its retry is untested.
4. **Bad board entries and corrupt state.** An unknown ATS, an unsafe board name, a bad budget
   value, or a corrupt / unreadable state file all end the run with `error` in code — none is
   tested. (An unreadable or non-list `config/boards.json` *is* tested.)
5. **A job reposted under a new ID** is reported as new; nothing tests or prevents it.
6. **The title filter against real titles.** It is tested only on hand-picked titles; it has
   not been compared with the real titles in `jobs/raw/`, so missed or wrong matches on real
   boards are unknown. (Both real runs reported 0 new jobs, which says nothing about the filter.)

### Not claiming

- It does **not** apply to jobs, judge fit, rank roles, or contact anyone.
- It does **not** run on a schedule — each run is one manual `python -m agent.run`.
- It covers **Greenhouse and Lever only**; no Workday or Amazon boards (or any other ATS).

### Signed

Signed: Chethan Gowda GT, 2026-11-10

---

## Driver's seat — loop and review

| Step | What Claude did | What Chethan did | Why it stays Chethan's | Evidence |
|---|---|---|---|---|
| Contract | committed it unchanged | wrote `GATE.md` before any code | the exits, budgets and error policy are Chethan's rules | `dd20bf6` |
| Tests before code | drafted the failing tests and stubs | reviewed them; decided #6, #9, `[]` vs absent, whole-word "sde" | the tests encode Chethan's decisions, not Claude's guesses | `5f20161` |
| Permission policy | wrote `policy.py` and the boundary tests | accepted it; chose the stricter delete rule (GATE.md note) | what the agent may touch is Chethan's call | `eb74932`, `f48d945` |
| Test sandbox | found that the tests could not pass with the policy obeyed; proposed the fix | chose the fixture fix and the added blocked-host test | Claude stopped instead of bypassing the policy; Chethan chose | `2ca2945` |
| The loop | wrote `loop.py`; reported untested extras | ran pytest, planted the `check_host` bug, restored, then accepted | acceptance came from Chethan's own test of the tests | `204b425` |
| Fetcher and run command | wrote failing tests first, then `fetch.py` / `run.py` | accepted; ran the two real runs | real network use was Chethan's, by hand | `7019e49`, `709fdb6`, `c35b116` |
| Wrong-answer demo | wrote the naive loop, the independent check and tests | specified what the demo must show | the independent check is the human-side verifier | `d3ca801` |
| Reposted-job review | wrote the three-run failing test, the one-line fix and `REVIEW.md` | made the GATE.md decision; ran fail/pass in own terminal; wrote the ACCEPT | the defect definition and the acceptance are Chethan's | `861812c`, `6585d42` |

"""Loop behaviour tests — written BEFORE the implementation. Contract: ../GATE.md.

One test per required item. Each docstring names the GATE.md section it enforces.
All network access goes through the injected FakeFetcher (see conftest.py).
"""

import json
from datetime import datetime

import pytest

from agent import loop
from conftest import (ANALYTIC, ATLAS, BUDGET, HUBSPOT, MISSING, OK_GH, OK_LEVER,
                      FakeClock, FakeFetcher, err_for, gh_board, gh_body, obs_for, seed_state)


def test_all_boards_ok_is_finished(state_dir):
    """GATE 1 Exits: every board fetched and filtered -> finished."""
    fetch = FakeFetcher({ATLAS["url"]: [OK_GH], HUBSPOT["url"]: [OK_GH], ANALYTIC["url"]: [OK_LEVER]})

    report = loop.run([ATLAS, HUBSPOT, ANALYTIC], fetch, BUDGET, state_dir)

    assert report["status"] == "finished"
    assert report["errors"] == []
    assert sorted(fetch.calls) == sorted([ATLAS["url"], HUBSPOT["url"], ANALYTIC["url"]])


def test_404_is_incomplete_other_boards_checked_and_single_request(state_dir):
    """GATE 4 Error policy: 404 -> no retry, escalate; GATE 6 wrong version #7."""
    fetch = FakeFetcher({
        ATLAS["url"]: [OK_GH],
        MISSING["url"]: [(404, {"status": 404, "error": "Job not found"})],
        ANALYTIC["url"]: [OK_LEVER],
    })

    report = loop.run([ATLAS, MISSING, ANALYTIC], fetch, BUDGET, state_dir)

    assert report["status"] == "incomplete"
    # the boards on either side of the 404 were still checked
    assert fetch.count(ATLAS["url"]) == 1
    assert fetch.count(ANALYTIC["url"]) == 1
    # the 404 board got exactly one request — no retry
    assert fetch.count(MISSING["url"]) == 1
    assert obs_for(report, MISSING["name"])["request_count"] == 1
    # failure report: what failed, why, how to check by hand, escalated
    err = err_for(report, MISSING["name"])
    assert err["status_code"] == 404
    assert err["reason"]
    assert MISSING["url"] in err["manual_check"]
    assert err["escalate"] is True
    assert MISSING["name"] not in report["new_jobs"]


@pytest.mark.parametrize("failure", [TimeoutError("read timed out"), (500, None), (503, None)],
                         ids=["timeout", "http-500", "http-503"])
def test_timeout_or_5xx_retried_once_then_incomplete(state_dir, failure):
    """GATE 4 Error policy: timeout / 5xx -> retry once (2 requests), then fail."""
    fetch = FakeFetcher({ATLAS["url"]: [failure], HUBSPOT["url"]: [OK_GH]})

    report = loop.run([ATLAS, HUBSPOT], fetch, BUDGET, state_dir)

    assert report["status"] == "incomplete"
    assert fetch.count(ATLAS["url"]) == 2
    assert obs_for(report, ATLAS["name"])["request_count"] == 2
    err = err_for(report, ATLAS["name"])
    assert err["error"]
    assert ATLAS["name"] not in report["new_jobs"]


@pytest.mark.parametrize("board, body", [
    (ATLAS, {"jobs": []}),   # Greenhouse board with zero jobs
    (ATLAS, {}),             # Greenhouse response without a jobs list
    (ATLAS, None),           # empty body
    (ANALYTIC, []),          # Lever board with zero postings
], ids=["gh-zero-jobs", "gh-no-jobs-key", "empty-body", "lever-zero-postings"])
def test_empty_response_is_incomplete_never_no_new_jobs(state_dir, board, body):
    """GATE 4 Error policy: empty -> suspicious, escalate, no retry; GATE 6 wrong version #1."""
    seed_state(state_dir, board["name"], [])  # a naive loop would now report "0 new jobs"
    fetch = FakeFetcher({board["url"]: [(200, body)], HUBSPOT["url"]: [OK_GH]})

    report = loop.run([board, HUBSPOT], fetch, BUDGET, state_dir)

    assert report["status"] == "incomplete"
    # never reported as "no new jobs": the board is absent, not an empty list
    assert board["name"] not in report["new_jobs"]
    err = err_for(report, board["name"])
    assert err["escalate"] is True
    assert fetch.count(board["url"]) == 1  # empty is not retried


def test_five_boards_over_board_budget_is_budget_exhausted(state_dir):
    """GATE 2 Budgets: more than 4 boards -> budget-exhausted, never check more than 4."""
    fifth = gh_board("fifthboard")
    boards = [ATLAS, HUBSPOT, ANALYTIC, gh_board("fourthboard"), fifth]
    fetch = FakeFetcher({b["url"]: [OK_LEVER if b["ats"] == "lever" else OK_GH] for b in boards})

    report = loop.run(boards, fetch, BUDGET, state_dir)

    assert report["status"] == "budget-exhausted"
    assert len(set(fetch.calls)) <= 4
    assert fifth["url"] not in fetch.calls
    budget_errs = [e for e in report["errors"] if e.get("budget") == "boards"]
    assert budget_errs, "report must say which budget ran out"
    assert fifth["name"] in budget_errs[0]["skipped"]


def test_more_than_8_requests_is_budget_exhausted(state_dir):
    """GATE 2 Budgets: requests capped at 8.

    The board budget is raised to 5 for this test only, so that the REQUEST budget is
    the one that runs out: 5 failing boards x (1 + 1 retry) = 10 requests wanted > 8.
    """
    boards = [gh_board(f"board{i}") for i in range(5)]
    fetch = FakeFetcher({b["url"]: [(500, None)] for b in boards})

    report = loop.run(boards, fetch, {**BUDGET, "boards": 5}, state_dir)

    assert report["status"] == "budget-exhausted"
    assert len(fetch.calls) <= 8
    assert any(e.get("budget") == "requests" for e in report["errors"])


def test_same_board_fetched_twice_beyond_retry_is_error(state_dir):
    """GATE 3 Repeat rule: fetching the same board again beyond its retry -> error."""
    fetch = FakeFetcher({ATLAS["url"]: [OK_GH], HUBSPOT["url"]: [OK_GH]})

    report = loop.run([ATLAS, HUBSPOT, ATLAS], fetch, BUDGET, state_dir)

    assert report["status"] == "error"
    assert fetch.count(ATLAS["url"]) == 1  # the repeat is caught before it is sent
    assert any("repeated" in str(e.get("error", "")).lower() for e in report["errors"])


def test_duplicate_job_ids_kept_once(state_dir):
    """GATE 3 Repeat rule: the same job ID twice -> keep one."""
    seed_state(state_dir, ATLAS["name"], [])
    body = gh_body([(7, "Software Engineer"), (7, "Software Engineer"), (8, "Software Engineer II")])
    fetch = FakeFetcher({ATLAS["url"]: [(200, body)]})

    report = loop.run([ATLAS], fetch, BUDGET, state_dir)

    ids = sorted(str(j["id"]) for j in report["new_jobs"][ATLAS["name"]])
    assert ids == ["7", "8"]


@pytest.mark.parametrize("failure", [(500, None), (404, None), (200, {"jobs": []}), TimeoutError("t")],
                         ids=["http-500", "http-404", "empty", "timeout"])
def test_failed_board_leaves_its_saved_state_unchanged(state_dir, failure):
    """GATE 6 wrong version #5: a failed board must not wipe or rewrite its state."""
    path = seed_state(state_dir, ATLAS["name"], ["1", "2", "3"])
    before = path.read_bytes()
    fetch = FakeFetcher({ATLAS["url"]: [failure], HUBSPOT["url"]: [OK_GH]})

    loop.run([ATLAS, HUBSPOT], fetch, BUDGET, state_dir)

    assert path.read_bytes() == before


def test_failed_board_does_not_report_last_runs_jobs(state_dir):
    """GATE 6 wrong version #3: stale data must never be shown as this run's result."""
    seed_state(state_dir, ATLAS["name"], ["101", "102"])
    seed_state(state_dir, HUBSPOT["name"], [])
    fetch = FakeFetcher({
        ATLAS["url"]: [TimeoutError("read timed out")],
        HUBSPOT["url"]: [(200, gh_body([(201, "Software Engineer")]))],
    })

    report = loop.run([ATLAS, HUBSPOT], fetch, BUDGET, state_dir)

    assert ATLAS["name"] not in report["new_jobs"]
    reported = {str(j["id"]) for jobs in report["new_jobs"].values() for j in jobs}
    assert not reported & {"101", "102"}
    assert obs_for(report, ATLAS["name"])["status_code"] != 200


def test_every_board_has_observation_with_timestamp_and_status_code(state_dir):
    """GATE 6 wrong version #4: no board may be claimed without a logged observation."""
    fetch = FakeFetcher({
        ATLAS["url"]: [OK_GH],
        MISSING["url"]: [(404, None)],
        HUBSPOT["url"]: [(500, None)],
    })

    report = loop.run([ATLAS, MISSING, HUBSPOT], fetch, BUDGET, state_dir)

    obs = report["observations"]
    assert len(obs) == 3  # exactly one per board, retries included in request_count
    for o in obs:
        datetime.fromisoformat(o["timestamp"])  # raises if not ISO 8601
        assert isinstance(o["status_code"], int)
        assert o["request_count"] >= 1
    assert {o["board"]: o["status_code"] for o in obs} == {
        ATLAS["name"]: 200, MISSING["name"]: 404, HUBSPOT["name"]: 500}


# ------------------------------------------------------------------ title filter
# Decision #6 (Chethan, 2026-11-10): a title matches if it contains, case-insensitively,
# any of these terms. Account Executive and Recruiting Coordinator must be rejected.
MATCHING_TITLES = [
    "Software Engineer",
    "Sr. Software Engineer",
    "SENIOR SOFTWARE ENGINEER, PLATFORM",   # case-insensitive
    "Software Developer",
    "SDE II",
    "sde i (new grad)",                     # case-insensitive
    "Frontend Engineer",
    "Front-End Developer",
    "Full Stack Engineer",
    "Full-Stack Developer",
    "UI Engineer",
    "Web Developer",
]
REJECTED_TITLES = ["Account Executive", "Recruiting Coordinator"]


def _reported_titles(state_dir, titles):
    """One Greenhouse board, previous state seeded empty, so every match is a new job."""
    seed_state(state_dir, ATLAS["name"], [])
    fetch = FakeFetcher({ATLAS["url"]: [(200, gh_body(list(enumerate(titles, start=1))))]})
    report = loop.run([ATLAS], fetch, BUDGET, state_dir)
    return {j["title"] for j in report["new_jobs"].get(ATLAS["name"], [])}


def test_sr_software_engineer_matches_title_filter(state_dir):
    """GATE 6 wrong version #2: the filter must not be too strict."""
    titles = _reported_titles(state_dir, ["Sr. Software Engineer", "Account Executive"])
    assert "Sr. Software Engineer" in titles
    assert "Account Executive" not in titles


@pytest.mark.parametrize("title", MATCHING_TITLES)
def test_title_filter_matches_each_term(state_dir, title):
    """Decision #6: every listed term matches, case-insensitively."""
    assert _reported_titles(state_dir, [title]) == {title}


@pytest.mark.parametrize("title", REJECTED_TITLES)
def test_title_filter_rejects_non_engineering_titles(state_dir, title):
    """Decision #6: a filter that lets everything through must fail here."""
    assert _reported_titles(state_dir, [title]) == set()


@pytest.mark.parametrize("title, expected", [
    ("SDE II", True),
    ("Misdemeanor Court Clerk", False),   # "mi-SDE-meanor": sde inside another word
], ids=["SDE-II-matches", "sde-inside-word-rejected"])
def test_sde_matches_only_as_whole_word(state_dir, title, expected):
    """Call 3 (Chethan, 2026-11-10): "sde" matches only as a whole word."""
    assert (title in _reported_titles(state_dir, [title])) is expected


# ------------------------------------------------------------------ reposted jobs (GATE 6 change)
def test_job_seen_earlier_then_removed_then_reposted_is_not_new(state_dir):
    """GATE 6 change (Chethan, 2026-11-10): a job ID seen in any earlier run is not new,
    even if it was removed and reposted. Three runs on one board:
      run 1: job 123 appears          -> new: [123]
      run 2: 123 removed, 456 appears -> new: [456]
      run 3: 123 reposted (same ID)   -> new: []   (123 was seen in run 1)
    """
    seed_state(state_dir, ATLAS["name"], [])  # not a first run, so run 1 reports new jobs

    def one_run(jobs):
        fetch = FakeFetcher({ATLAS["url"]: [(200, gh_body(jobs))]})
        report = loop.run([ATLAS], fetch, BUDGET, state_dir)
        assert report["status"] == "finished"
        return sorted(str(j["id"]) for j in report["new_jobs"][ATLAS["name"]])

    assert one_run([(123, "Software Engineer")]) == ["123"]
    assert one_run([(456, "Software Engineer II")]) == ["456"]
    assert one_run([(123, "Software Engineer"), (456, "Software Engineer II")]) == []


# ------------------------------------------------------------------ policy enforced by the loop
def test_blocked_host_is_never_fetched(state_dir):
    """GATE 5 Permission policy: the loop calls policy.check_host before every fetch,
    so a board on a host outside the allow-list is never requested."""
    evil = {"name": "evilboard", "ats": "greenhouse", "url": "https://evil.com/v1/boards/atlassp/jobs"}
    fetch = FakeFetcher({evil["url"]: [OK_GH], HUBSPOT["url"]: [OK_GH]})

    report = loop.run([evil, HUBSPOT], fetch, BUDGET, state_dir)

    assert evil["url"] not in fetch.calls
    assert obs_for(report, evil["name"])["status"] == "failed"
    assert fetch.count(HUBSPOT["url"]) == 1   # the allowed board is still checked
    assert report["status"] == "incomplete"


# ------------------------------------------------------------------ new_jobs shape (call 2)
def test_ok_board_with_no_matching_titles_reports_empty_list(state_dir):
    """Call 2 (Chethan, 2026-11-10): an "ok" board with nothing matching -> new_jobs = []."""
    seed_state(state_dir, ATLAS["name"], [])
    body = gh_body([(1, "Account Executive"), (2, "Recruiting Coordinator")])
    fetch = FakeFetcher({ATLAS["url"]: [(200, body)]})

    report = loop.run([ATLAS], fetch, BUDGET, state_dir)

    assert obs_for(report, ATLAS["name"])["status"] == "ok"
    assert report["new_jobs"][ATLAS["name"]] == []   # present, and empty
    assert report["status"] == "finished"


@pytest.mark.parametrize("failure", [(404, None), (500, None), TimeoutError("t"), (200, {"jobs": []})],
                         ids=["http-404", "http-500", "timeout", "empty"])
def test_failed_board_is_absent_from_new_jobs(state_dir, failure):
    """Call 2 (Chethan, 2026-11-10): a failed board is ABSENT from new_jobs, never []."""
    seed_state(state_dir, ATLAS["name"], [])
    seed_state(state_dir, HUBSPOT["name"], [])  # so HUBSPOT is an "ok" board, not a baseline
    fetch = FakeFetcher({ATLAS["url"]: [failure], HUBSPOT["url"]: [OK_GH]})

    report = loop.run([ATLAS, HUBSPOT], fetch, BUDGET, state_dir)

    assert obs_for(report, ATLAS["name"])["status"] == "failed"
    assert ATLAS["name"] not in report["new_jobs"]
    assert HUBSPOT["name"] in report["new_jobs"]   # the ok board is still reported


# ------------------------------------------------------------------ added 2026-11-10
def test_first_run_without_state_is_baseline_never_zero_new_jobs(state_dir):
    """Decision #9 (Chethan, 2026-11-10): no saved state -> record ALL job IDs as the
    baseline, mark the board "baseline", and never report it as "0 new jobs"."""
    assert not (state_dir / f"{ATLAS['name']}.json").exists()
    body = gh_body([(1, "Software Engineer"), (2, "Account Executive"), (3, "Frontend Engineer")])
    fetch = FakeFetcher({ATLAS["url"]: [(200, body)]})

    report = loop.run([ATLAS], fetch, BUDGET, state_dir)

    assert obs_for(report, ATLAS["name"])["status"] == "baseline"
    # not reported as new jobs, and not as an empty list either
    assert ATLAS["name"] not in report["new_jobs"]
    # ALL IDs saved — including the title the filter rejects — so the next run diffs the full set
    saved = json.loads((state_dir / f"{ATLAS['name']}.json").read_text(encoding="utf-8"))
    assert sorted(saved["seen_ids"]) == ["1", "2", "3"]
    # the board was fetched successfully, so the run itself still ends "finished"
    assert report["status"] == "finished"


def test_timeout_then_successful_retry_is_finished(state_dir):
    """GATE 4 Error policy: a timeout gets one retry; if the retry works, the board succeeds."""
    seed_state(state_dir, ATLAS["name"], [])
    fetch = FakeFetcher({ATLAS["url"]: [TimeoutError("read timed out"),
                                        (200, gh_body([(9, "Software Engineer")]))]})

    report = loop.run([ATLAS], fetch, BUDGET, state_dir)

    assert report["status"] == "finished"
    assert fetch.count(ATLAS["url"]) == 2
    obs = obs_for(report, ATLAS["name"])
    assert obs["request_count"] == 2
    assert obs["status_code"] == 200
    assert [str(j["id"]) for j in report["new_jobs"][ATLAS["name"]]] == ["9"]


def test_run_over_60_seconds_is_budget_exhausted(state_dir):
    """GATE 2 Budgets: 60 seconds per run. Fake clock — no real sleeping.

    Each request "takes" 25 s: the clock reads 25, 50, 75 after boards 1-3, so the
    time budget is gone before board 4 and board 4 must never be fetched.
    """
    clock = FakeClock()
    boards = [ATLAS, HUBSPOT, gh_board("thirdboard"), gh_board("fourthboard")]
    fetch = FakeFetcher({b["url"]: [OK_GH] for b in boards}, on_call=lambda url: clock.advance(25))

    report = loop.run(boards, fetch, BUDGET, state_dir, clock=clock)

    assert report["status"] == "budget-exhausted"
    assert boards[3]["url"] not in fetch.calls
    assert len(fetch.calls) <= 3
    time_errs = [e for e in report["errors"] if e.get("budget") == "seconds"]
    assert time_errs, "report must say the time budget ran out"
    assert boards[3]["name"] in time_errs[0]["skipped"]

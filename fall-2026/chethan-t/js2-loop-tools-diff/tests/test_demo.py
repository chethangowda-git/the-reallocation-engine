"""Tests for demo/finished_wrong.py — the independent check must catch the naive loop's
clean-looking wrong answer. Offline: fake fetcher + files on disk only."""

import json

from demo import finished_wrong as demo
from conftest import ATLAS, gh_body


def write_raw(raw_dir, board, body, run_at="2026-11-10T21:37:22+00:00", stamp="20261110T213722Z"):
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{board}-{stamp}.json"
    path.write_text(json.dumps({"board": board, "url": "https://x", "run_at": run_at,
                                "attempts": [{"fetched_at": run_at, "status_code": 200, "body": body}]}),
                    encoding="utf-8")
    return path


def test_naive_loop_reports_finished_zero_on_empty():
    """The wrong version: empty response -> "finished", 0 jobs, no errors."""
    report = demo.naive_run([ATLAS], demo.empty_fetch)
    assert report["status"] == "finished"
    assert report["errors"] == []
    assert report["new_jobs"][ATLAS["name"]] == []
    assert demo.claims_from_naive(report) == {ATLAS["name"]: 0}


def test_independent_check_flags_the_mismatch(tmp_path):
    """The naive loop claims 0 jobs; the last real response had 3 -> flagged."""
    raw_dir = tmp_path / "raw"
    write_raw(raw_dir, ATLAS["name"], gh_body([(1, "a"), (2, "b"), (3, "c")]))
    naive = demo.naive_run([ATLAS], demo.empty_fetch)

    mismatches = demo.independent_check(demo.claims_from_naive(naive), raw_dir)

    assert len(mismatches) == 1
    m = mismatches[0]
    assert (m["board"], m["reported"], m["real"]) == (ATLAS["name"], 0, 3)
    assert "MISMATCH" in m["verdict"]


def test_independent_check_is_quiet_when_counts_agree(tmp_path):
    """Not an always-on alarm: a claim that matches the real response is not flagged."""
    raw_dir = tmp_path / "raw"
    write_raw(raw_dir, ATLAS["name"], gh_body([(1, "a"), (2, "b")]))
    assert demo.independent_check({ATLAS["name"]: 2}, raw_dir) == []


def test_independent_check_uses_the_latest_real_response(tmp_path):
    raw_dir = tmp_path / "raw"
    write_raw(raw_dir, ATLAS["name"], gh_body([(1, "a")]), run_at="2026-11-09T10:00:00+00:00",
              stamp="20261109T100000Z")
    write_raw(raw_dir, ATLAS["name"], gh_body([(1, "a"), (2, "b")]))
    assert demo.independent_check({ATLAS["name"]: 1}, raw_dir)[0]["real"] == 2


def test_latest_raw_ignores_lookalike_board_names(tmp_path):
    """Regression: "atlassp-*" must not pick up "atlassp-doesnotexist-*" (found on real data)."""
    raw_dir = tmp_path / "raw"
    write_raw(raw_dir, "atlassp", gh_body([(1, "a")]), run_at="2026-11-10T21:37:20+00:00",
              stamp="20261110T213720Z")
    write_raw(raw_dir, "atlassp-doesnotexist", {"status": 404}, run_at="2026-11-10T21:37:59+00:00",
              stamp="20261110T213759Z")
    assert demo.latest_raw(raw_dir, "atlassp").name == "atlassp-20261110T213720Z.json"


def test_independent_check_flags_mismatch_against_the_committed_real_raw():
    """Uses jobs/raw/ from the real run (committed): a naive 0 disagrees with the real count."""
    raw_dir = demo.ROOT / "jobs" / "raw"
    real = demo.real_job_count(demo.latest_raw(raw_dir, "atlassp"))
    assert real > 0, "the saved real atlassp response should list at least one job"
    mismatches = demo.independent_check({"atlassp": 0}, raw_dir)
    assert [(m["reported"], m["real"]) for m in mismatches] == [(0, real)]


def test_real_loop_on_the_same_empty_input_is_incomplete_and_escalated():
    report = demo.real_run_on_empty(ATLAS)
    assert report["status"] == "incomplete"
    assert ATLAS["name"] not in report["new_jobs"]
    assert report["errors"][0]["escalate"] is True


def test_demo_does_not_leave_policy_root_changed():
    before = demo.policy.ROOT
    demo.real_run_on_empty(ATLAS)
    assert demo.policy.ROOT == before

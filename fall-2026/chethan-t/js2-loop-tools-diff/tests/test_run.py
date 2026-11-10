"""`python -m agent.run` tests — written BEFORE the implementation. Contract: ../GATE.md.

Offline: every test runs inside a throwaway agent root (policy.ROOT -> tmp_path) with
a FakeFetcher; the one test of the default fetcher patches agent.fetch.http_fetch.
"""

import json
import os
import runpy
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent import fetch as fetch_mod
from agent import policy, run
from conftest import (ATLAS, HUBSPOT, MISSING, OK_GH, FakeFetcher, gh_board, gh_body, seed_state)

FIXED_NOW = datetime(2026, 11, 10, 15, 30, 0, tzinfo=timezone.utc)
TS = "20261110T153000Z"

GATE_BOARDS = [  # GATE.md "Boards" table, in order
    ("atlassp", "greenhouse", "https://boards-api.greenhouse.io/v1/boards/atlassp/jobs"),
    ("hubspotjobs", "greenhouse", "https://boards-api.greenhouse.io/v1/boards/hubspotjobs/jobs"),
    ("analyticpartners", "lever", "https://api.lever.co/v0/postings/analyticpartners?mode=json"),
    ("atlassp-doesnotexist", "greenhouse", "https://boards-api.greenhouse.io/v1/boards/atlassp-doesnotexist/jobs"),
]


# ------------------------------------------------------------------ helpers
@pytest.fixture
def agent_root(tmp_path, monkeypatch):
    """A throwaway agent root: policy.ROOT points here; config/ exists, state/ and jobs/ do not."""
    monkeypatch.setattr(policy, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    return tmp_path


def write_boards(root, boards):
    (root / "config" / "boards.json").write_text(json.dumps(boards), encoding="utf-8")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def files_under(root, *skip):
    return sorted(p for p in root.rglob("*") if p.is_file() and p not in skip)


# ------------------------------------------------------------------ the real config

def test_config_has_the_four_gate_boards():
    """GATE.md "Boards": config/boards.json holds exactly the four boards, in order."""
    path = Path(__file__).resolve().parent.parent / "config" / "boards.json"
    boards = load(path)
    assert [(b["name"], b["ats"], b["url"]) for b in boards] == GATE_BOARDS


# ------------------------------------------------------------------ exit codes

def test_baseline_run_exits_0_and_saves_trace_and_raw(agent_root):
    """First run (no state): every board is a baseline, the run is "finished" -> exit 0."""
    write_boards(agent_root, [ATLAS, HUBSPOT])
    fetch = FakeFetcher({ATLAS["url"]: [OK_GH], HUBSPOT["url"]: [OK_GH]})

    code = run.main([], fetch=fetch, now=lambda: FIXED_NOW)

    assert code == 0
    trace = load(agent_root / "jobs" / "traces" / f"{TS}.json")
    assert trace["exit_code"] == 0
    assert trace["report"]["status"] == "finished"
    assert {o["status"] for o in trace["report"]["observations"]} == {"baseline"}
    assert (agent_root / "jobs" / "raw" / f"atlassp-{TS}.json").is_file()
    assert (agent_root / "jobs" / "raw" / f"hubspotjobs-{TS}.json").is_file()


def test_finished_run_with_saved_state_exits_0(agent_root):
    write_boards(agent_root, [ATLAS])
    seed_state(agent_root / "state", ATLAS["name"], [])
    fetch = FakeFetcher({ATLAS["url"]: [OK_GH]})

    assert run.main([], fetch=fetch, now=lambda: FIXED_NOW) == 0
    assert load(agent_root / "jobs" / "traces" / f"{TS}.json")["report"]["observations"][0]["status"] == "ok"


@pytest.mark.parametrize("boards, routes, expected_status, expected_code", [
    ([ATLAS, MISSING], {ATLAS["url"]: [OK_GH], MISSING["url"]: [(404, None)]}, "incomplete", 1),
    ([gh_board(f"b{i}") for i in range(5)],
     {gh_board(f"b{i}")["url"]: [OK_GH] for i in range(5)}, "budget-exhausted", 2),
    ([ATLAS, HUBSPOT, ATLAS], {ATLAS["url"]: [OK_GH], HUBSPOT["url"]: [OK_GH]}, "error", 3),
], ids=["incomplete-1", "budget-exhausted-2", "error-3"])
def test_exit_code_matches_run_status(agent_root, boards, routes, expected_status, expected_code):
    write_boards(agent_root, boards)

    code = run.main([], fetch=FakeFetcher(routes), now=lambda: FIXED_NOW)

    assert code == expected_code
    trace = load(agent_root / "jobs" / "traces" / f"{TS}.json")
    assert trace["report"]["status"] == expected_status
    assert trace["exit_code"] == expected_code


@pytest.mark.parametrize("content", [None, "{not json", json.dumps({"boards": "nope"})],
                         ids=["missing-file", "invalid-json", "not-a-list"])
def test_unreadable_config_exits_3_without_fetching(agent_root, content):
    if content is not None:
        (agent_root / "config" / "boards.json").write_text(content, encoding="utf-8")
    fetch = FakeFetcher({})

    assert run.main([], fetch=fetch, now=lambda: FIXED_NOW) == 3
    assert fetch.calls == []


# ------------------------------------------------------------------ raw responses

def test_raw_responses_saved_per_requested_board(agent_root):
    """One raw file per board that was actually requested; every attempt recorded."""
    evil = {"name": "evilboard", "ats": "greenhouse", "url": "https://evil.com/v1/boards/x/jobs"}
    write_boards(agent_root, [ATLAS, MISSING, HUBSPOT, evil])
    fetch = FakeFetcher({
        ATLAS["url"]: [(200, gh_body([(1, "Software Engineer")]))],
        MISSING["url"]: [(404, {"status": 404, "error": "Job not found"})],
        HUBSPOT["url"]: [TimeoutError("read timed out"), OK_GH],
        evil["url"]: [OK_GH],
    })

    run.main([], fetch=fetch, now=lambda: FIXED_NOW)

    raw_dir = agent_root / "jobs" / "raw"
    atlas = load(raw_dir / f"atlassp-{TS}.json")
    assert atlas["board"] == "atlassp" and atlas["url"] == ATLAS["url"]
    assert [a["status_code"] for a in atlas["attempts"]] == [200]
    assert atlas["attempts"][0]["body"] == gh_body([(1, "Software Engineer")])

    missing = load(raw_dir / f"atlassp-doesnotexist-{TS}.json")
    assert [a["status_code"] for a in missing["attempts"]] == [404]

    hub = load(raw_dir / f"hubspotjobs-{TS}.json")
    assert len(hub["attempts"]) == 2
    assert "TimeoutError" in hub["attempts"][0]["error"]
    assert hub["attempts"][1]["status_code"] == 200

    # the blocked board was never requested, so it has no raw file
    assert not list(raw_dir.glob("evilboard-*"))


# ------------------------------------------------------------------ policy on every write (GATE 5)

def test_every_write_goes_through_check_write(agent_root, monkeypatch):
    write_boards(agent_root, [ATLAS, HUBSPOT])
    checked = set()
    real_check_write = policy.check_write

    def spy(path, approved=False):
        checked.add(os.path.realpath(path))
        return real_check_write(path, approved)

    monkeypatch.setattr(policy, "check_write", spy)
    fetch = FakeFetcher({ATLAS["url"]: [OK_GH], HUBSPOT["url"]: [OK_GH]})

    run.main([], fetch=fetch, now=lambda: FIXED_NOW)

    config_file = agent_root / "config" / "boards.json"
    written = [p for p in agent_root.rglob("*") if p != config_file and p != agent_root / "config"]
    assert written, "the run should have written state, a trace and raw files"
    unchecked = [str(p) for p in written if os.path.realpath(p) not in checked]
    assert unchecked == [], f"written without policy.check_write: {unchecked}"


def test_blocked_jobs_write_exits_3_and_writes_nothing_there(agent_root, monkeypatch):
    write_boards(agent_root, [ATLAS])
    jobs = os.path.realpath(agent_root / "jobs")
    real_check_write = policy.check_write

    def block_jobs(path, approved=False):
        p = os.path.realpath(path)
        if p == jobs or p.startswith(jobs + os.sep):  # test-side fence, not the policy under test
            raise PermissionError(f"blocked for this test: {p}")
        return real_check_write(path, approved)

    monkeypatch.setattr(policy, "check_write", block_jobs)

    code = run.main([], fetch=FakeFetcher({ATLAS["url"]: [OK_GH]}), now=lambda: FIXED_NOW)

    assert code == 3
    assert not (agent_root / "jobs").exists() or files_under(agent_root / "jobs") == []


# ------------------------------------------------------------------ no overwrite

def test_two_runs_in_the_same_second_do_not_overwrite(agent_root):
    write_boards(agent_root, [ATLAS])
    for _ in range(2):
        run.main([], fetch=FakeFetcher({ATLAS["url"]: [OK_GH]}), now=lambda: FIXED_NOW)

    traces = sorted(p.name for p in (agent_root / "jobs" / "traces").iterdir())
    raws = sorted(p.name for p in (agent_root / "jobs" / "raw").iterdir())
    assert traces == [f"{TS}-2.json", f"{TS}.json"]
    assert raws == [f"atlassp-{TS}-2.json", f"atlassp-{TS}.json"]


# ------------------------------------------------------------------ wiring

def test_default_fetcher_is_http_fetch(agent_root, monkeypatch):
    """main() with no fetch argument uses agent.fetch.http_fetch (patched here — no network)."""
    write_boards(agent_root, [ATLAS])
    fake = FakeFetcher({ATLAS["url"]: [OK_GH]})
    monkeypatch.setattr(fetch_mod, "http_fetch", fake)

    assert run.main([], now=lambda: FIXED_NOW) == 0
    assert fake.calls == [ATLAS["url"]]


@pytest.mark.filterwarnings("ignore::RuntimeWarning")  # runpy re-executing an imported module
def test_python_m_agent_run_exits_with_the_run_code(agent_root, monkeypatch):
    """`python -m agent.run` = runpy with __name__ == "__main__"; exit code comes from main()."""
    write_boards(agent_root, [ATLAS, MISSING])
    monkeypatch.setattr(fetch_mod, "http_fetch",
                        FakeFetcher({ATLAS["url"]: [OK_GH], MISSING["url"]: [(404, None)]}))
    monkeypatch.setattr(sys, "argv", ["agent.run"])

    with pytest.raises(SystemExit) as info:
        runpy.run_module("agent.run", run_name="__main__")

    assert info.value.code == 1  # incomplete

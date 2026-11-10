"""Shared test helpers for Job-Search Agent 2. Contract: ../GATE.md.

Offline by construction: the loop gets an injected FakeFetcher, and an autouse
fixture makes any real socket connection fail the test.
"""

import json
import socket
import sys
from pathlib import Path

import pytest

# Make `agent` importable (this folder has dashes in its name, so it is not a package).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# GATE.md section 2 — the budgets, verbatim.
BUDGET = {"boards": 4, "requests": 8, "seconds": 60, "request_timeout": 10}


# ------------------------------------------------------------------ boards (GATE.md "Boards")
def gh_board(slug):
    return {"name": slug, "ats": "greenhouse",
            "url": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"}


def lever_board(slug):
    return {"name": slug, "ats": "lever",
            "url": f"https://api.lever.co/v0/postings/{slug}?mode=json"}


ATLAS = gh_board("atlassp")
HUBSPOT = gh_board("hubspotjobs")
ANALYTIC = lever_board("analyticpartners")
MISSING = gh_board("atlassp-doesnotexist")  # the deliberate-failure board


# ------------------------------------------------------------------ response bodies
def gh_body(jobs):
    """Greenhouse boards-api shape. jobs: [(id, title), ...]."""
    return {"jobs": [{"id": jid, "title": title,
                      "absolute_url": f"https://job-boards.greenhouse.io/x/jobs/{jid}",
                      "location": {"name": "Boston, MA"}} for jid, title in jobs]}


def lever_body(jobs):
    """Lever postings-api shape (a bare list). jobs: [(id, title), ...]."""
    return [{"id": str(jid), "text": title,
             "hostedUrl": f"https://jobs.lever.co/x/{jid}",
             "categories": {"location": "Boston, MA"}} for jid, title in jobs]


OK_GH = (200, gh_body([(1, "Software Engineer")]))
OK_LEVER = (200, lever_body([("a1", "Software Engineer")]))


# ------------------------------------------------------------------ fake fetcher
class FakeFetcher:
    """Injected in place of the network. routes: url -> list of responses.

    A response is (status_code, body) or an Exception instance to raise.
    The last response for a URL repeats if the loop asks again.
    Every call is recorded in .calls (URLs, in order).
    on_call, if given, runs before each response (e.g. to advance a FakeClock).
    """

    def __init__(self, routes, on_call=None):
        self.routes = {url: list(responses) for url, responses in routes.items()}
        self.calls = []
        self.on_call = on_call

    def __call__(self, url, *, timeout=None):
        self.calls.append(url)
        if self.on_call:
            self.on_call(url)
        if url not in self.routes:
            raise AssertionError(f"loop fetched an unexpected URL: {url}")
        responses = self.routes[url]
        resp = responses.pop(0) if len(responses) > 1 else responses[0]
        if isinstance(resp, BaseException):
            raise resp
        return resp

    def count(self, url):
        return self.calls.count(url)


class FakeClock:
    """A monotonic clock the test controls. No real sleeping."""

    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# ------------------------------------------------------------------ state helpers
def seed_state(state_dir, board_name, seen_ids):
    """Write <state_dir>/<board>.json as if a previous run had saved it."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{board_name}.json"
    path.write_text(json.dumps({"seen_ids": [str(i) for i in seen_ids]}), encoding="utf-8")
    return path


def obs_for(report, board_name):
    matches = [o for o in report["observations"] if o["board"] == board_name]
    assert len(matches) == 1, f"expected exactly one observation for {board_name}, got {matches}"
    return matches[0]


def err_for(report, board_name):
    matches = [e for e in report["errors"] if e.get("board") == board_name]
    assert matches, f"expected an error entry for {board_name}, got {report['errors']}"
    return matches[0]


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """tmp_path stands in for the agent root, so tmp_path/state is the agent's state/
    folder and the loop's policy checks (check_read / check_write) apply to it."""
    from agent import policy
    monkeypatch.setattr(policy, "ROOT", tmp_path)
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real connection attempt fails the test."""
    def refuse(*args, **kwargs):
        raise AssertionError("test tried to use the real network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

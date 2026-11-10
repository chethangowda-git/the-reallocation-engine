"""The agent loop — INTERFACE STUB ONLY. No implementation yet (tests come first).

Contract: ../GATE.md. The tests in ../tests/test_loop.py define the expected behaviour.

run(boards, fetch, budget, state_dir, *, clock=None) -> report

boards     list of dicts: {"name": str, "ats": "greenhouse" | "lever", "url": str}
fetch      callable fetch(url, *, timeout) -> (status_code: int, body)
           - body is the parsed JSON (dict for Greenhouse, list for Lever) or None
           - raises TimeoutError when the request times out
           The loop never does network I/O itself; the fetcher is injected.
budget     dict: {"boards": int, "requests": int, "seconds": float, "request_timeout": float}
           GATE.md defaults: boards 4, requests 8, seconds 60, request_timeout 10
state_dir  folder holding one file per board: <state_dir>/<board name>.json
           with {"seen_ids": [<job id as str>, ...]}
           No file for a board = its first run: record ALL job IDs as the baseline,
           mark that board "baseline", and never report it as "0 new jobs".
clock      optional zero-arg callable returning seconds (monotonic); used for the
           "seconds" budget. Defaults to time.monotonic. Tests inject a fake clock.

Title filter (fixed default): a title matches if it contains, case-insensitively, any of
  software engineer, software developer, sde, frontend, front-end, full stack,
  full-stack, ui engineer, web developer
  "sde" matches only as a whole word ("SDE II" yes; "Misdemeanor" no).

report     dict:
  status        "finished" | "incomplete" | "budget-exhausted" | "error"
  observations  list, one per board attempted:
                {"board", "status" ("ok" | "baseline" | "failed"), "timestamp" (ISO 8601),
                 "status_code" (int or None), "request_count"}
  new_jobs      dict: board name -> list of {"id", "title", "url"}.
                An "ok" board with no matching new jobs -> [] (a real "0 new jobs").
                A "failed" or "baseline" board is ABSENT (never an empty list).
  errors        list of dicts; a board failure carries
                {"board", "url", "status_code", "error", "reason", "manual_check", "escalate"};
                a budget stop carries {"budget": "boards" | "requests" | "seconds", "skipped": [...]}
"""

DEFAULT_BUDGET = {"boards": 4, "requests": 8, "seconds": 60, "request_timeout": 10}


def run(boards, fetch, budget, state_dir, *, clock=None):
    raise NotImplementedError("agent.loop.run — not implemented yet (tests first)")

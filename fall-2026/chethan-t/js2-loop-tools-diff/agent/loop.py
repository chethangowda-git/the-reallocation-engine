"""The agent loop. Contract: ../GATE.md sections 1-4 and 6. Tests: ../tests/test_loop.py.

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
                 "status_code" (int or None), "request_count", "notes" (list of str)}
  new_jobs      dict: board name -> list of {"id", "title", "url"}.
                An "ok" board with no matching new jobs -> [] (a real "0 new jobs").
                A "failed" or "baseline" board is ABSENT (never an empty list).
  errors        list of dicts; a board failure carries
                {"board", "url", "status_code", "error", "reason", "manual_check", "escalate"};
                a budget stop carries {"budget": "boards" | "requests" | "seconds", "skipped": [...]}

Policy (GATE.md section 5) is enforced through agent.policy, never bypassed:
  policy.check_host + check_method("GET") before EVERY fetch (retries included),
  policy.check_read before reading a state file, policy.check_write before EVERY file write.
A failed board never touches its state file and never appears in new_jobs.
"""

import json
import os
import re
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path

from . import policy

DEFAULT_BUDGET = {"boards": 4, "requests": 8, "seconds": 60, "request_timeout": 10}

ATS_KINDS = ("greenhouse", "lever")
MAX_ATTEMPTS = 2  # GATE.md section 4: one request + one retry, for timeout / 5xx only
BOARD_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")  # also a safe state file name

# Decision #6 + call 3 (Chethan, 2026-11-10).
TITLE_TERMS = ("software engineer", "software developer", "frontend", "front-end",
               "full stack", "full-stack", "ui engineer", "web developer")
SDE_WORD = re.compile(r"\bsde\b", re.IGNORECASE)


def title_matches(title):
    """Decision #6: any term as a case-insensitive substring; "sde" as a whole word only."""
    t = (title or "").lower()
    return any(term in t for term in TITLE_TERMS) or bool(SDE_WORD.search(t))


class _Stop(Exception):
    """Ends the whole run with `status`; `entry` goes into report["errors"]."""

    def __init__(self, status, entry):
        super().__init__(entry.get("error", status))
        self.status = status
        self.entry = entry


# ------------------------------------------------------------------ run
def run(boards, fetch, budget, state_dir, *, clock=None):
    clock = clock or time.monotonic
    start = clock()
    report = {"status": None, "observations": [], "new_jobs": {}, "errors": []}

    try:
        budget = _check_config(boards, fetch, budget)
    except ValueError as e:
        report["errors"].append({"error": f"bad config: {e}",
                                 "reason": "the board list or budget does not match GATE.md",
                                 "escalate": True})
        report["status"] = "error"
        return report

    state_dir = Path(state_dir)
    ctx = {"requests": 0, "clock": clock, "start": start, "budget": budget}
    done, seen_names, seen_urls = [], set(), set()
    any_failed = False

    try:
        for i, board in enumerate(boards):
            rest = [b["name"] for b in boards[i:]]
            # GATE.md section 2: budgets are checked before a board is started.
            if i >= budget["boards"]:
                raise _Stop("budget-exhausted", _budget_entry("boards", budget, done, rest))
            if ctx["requests"] >= budget["requests"]:
                raise _Stop("budget-exhausted", _budget_entry("requests", budget, done, rest))
            if clock() - start >= budget["seconds"]:
                raise _Stop("budget-exhausted", _budget_entry("seconds", budget, done, rest))
            # GATE.md section 3: fetching the same board again in one run -> error.
            if board["name"] in seen_names or board["url"] in seen_urls:
                raise _Stop("error", {
                    "board": board["name"], "url": board["url"],
                    "error": f"loop repeated an action: board {board['name']!r} was already fetched in this run",
                    "reason": "GATE.md section 3 repeat rule — the board list or the loop repeats a board",
                    "escalate": True, "done": list(done), "not_done": rest,
                })
            seen_names.add(board["name"])
            seen_urls.add(board["url"])

            ok = _check_board(board, fetch, state_dir, ctx, report, done, rest[1:])
            done.append(board["name"])
            any_failed = any_failed or not ok
    except _Stop as stop:
        report["errors"].append(stop.entry)
        report["status"] = stop.status
        return report

    report["status"] = "incomplete" if any_failed else "finished"
    return report


# ------------------------------------------------------------------ one board
def _check_board(board, fetch, state_dir, ctx, report, done, rest_after):
    """Fetch, classify, diff, and save one board. Returns True on success, False on a
    board failure. Raises _Stop for run-level stops (budget, state I/O)."""
    name, url = board["name"], board["url"]
    state_path = state_dir / f"{name}.json"
    seen = _load_state(state_path, name)  # None = no saved state yet (baseline)

    code, body, attempts, failure, stop_budget = _fetch_with_retry(board, fetch, ctx)

    if failure is None:
        if not isinstance(code, int):
            failure = _failure(board, None, f"fetcher returned a non-integer status code: {code!r}",
                               "fetcher bug or broken response", escalate=True)
        elif code == 404:
            failure = _failure(board, 404, "HTTP 404 not found",
                               "board name is probably wrong (renamed or removed); retrying won't fix it",
                               escalate=True)
        elif not 200 <= code <= 299:
            failure = _failure(board, code, f"HTTP {code}",
                               "unexpected status; not a case GATE.md retries", escalate=True)

    jobs, notes = None, []
    if failure is None:
        jobs = _normalize(board, body)
        if not jobs:
            what = "no job list in the response" if jobs is None else "0 jobs in the response"
            failure = _failure(board, code, f"empty response: {what}",
                               "may be a wrong URL or a broken response, not a truly empty board",
                               escalate=True)

    if failure is not None:
        _observe(report, name, "failed", code, attempts, notes)
        report["errors"].append(failure)
        if stop_budget:
            raise _Stop("budget-exhausted", _budget_entry(stop_budget, ctx["budget"], done + [name], rest_after))
        return False

    jobs, dropped = _dedupe(jobs)
    if dropped:
        notes.append(f"duplicate job IDs dropped (kept first): {', '.join(dropped)}")
    ids_now = {j["id"] for j in jobs}

    if seen is None:
        _save_state(state_dir, state_path, ids_now, name, done, rest_after, report, code, attempts, notes)
        notes.append(f"baseline: recorded {len(ids_now)} job IDs; nothing reported as new on a first run")
        _observe(report, name, "baseline", code, attempts, notes)
        return True

    new = [j for j in jobs if j["id"] not in seen and title_matches(j["title"])]
    # GATE.md section 6 change (2026-11-10): an ID seen in ANY earlier run is never new again,
    # so the saved set keeps every ID ever seen, not only the IDs on the board right now.
    _save_state(state_dir, state_path, seen | ids_now, name, done, rest_after, report, code, attempts, notes)
    report["new_jobs"][name] = new
    _observe(report, name, "ok", code, attempts, notes)
    return True


def _fetch_with_retry(board, fetch, ctx):
    """GATE.md section 4. Returns (status_code, body, attempts, failure_entry, stop_budget)."""
    url, budget = board["url"], ctx["budget"]
    attempts, code, body = 0, None, None
    while True:
        # GATE.md section 5: policy is checked before EVERY request, retries included.
        try:
            policy.check_host(url)
            policy.check_method("GET")
        except PermissionError as e:
            return None, None, attempts, _failure(
                board, None, f"blocked by policy: {e}",
                "URL is outside GATE.md section 5 (host allow-list / HTTPS / GET only)",
                escalate=True), None

        attempts += 1
        ctx["requests"] += 1
        try:
            code, body = fetch(url, timeout=budget["request_timeout"])
            transient = isinstance(code, int) and 500 <= code <= 599
            what = f"HTTP {code}"
        except TimeoutError as e:
            code, body, transient = None, None, True
            what = f"timeout after {budget['request_timeout']}s ({e})"
        except Exception as e:  # anything else from the transport: fail, do not retry
            return None, None, attempts, _failure(
                board, None, f"fetch raised {type(e).__name__}: {e}",
                "transport error that GATE.md does not retry", escalate=True), None

        if not transient:
            return code, body, attempts, None, None
        if attempts >= MAX_ATTEMPTS:
            return code, body, attempts, _failure(
                board, code, f"{what} after {attempts} attempts",
                "server-side problem or slow server; may be temporary", escalate=False), None

        # A retry is wanted — only if the budgets allow it.
        if ctx["requests"] >= budget["requests"]:
            return code, body, attempts, _failure(
                board, code, f"{what}; retry not sent: request budget exhausted",
                "may be temporary; not retried because the request budget ran out",
                escalate=False), "requests"
        if ctx["clock"]() - ctx["start"] >= budget["seconds"]:
            return code, body, attempts, _failure(
                board, code, f"{what}; retry not sent: time budget exhausted",
                "may be temporary; not retried because the time budget ran out",
                escalate=False), "seconds"


# ------------------------------------------------------------------ responses
def _normalize(board, body):
    """Map an ATS response to [{"id", "title", "url"}]. None = no job list at all."""
    if board["ats"] == "greenhouse":
        raw = body.get("jobs") if isinstance(body, dict) else None
        id_key, title_key, url_key = "id", "title", "absolute_url"
    else:  # lever
        raw = body
        id_key, title_key, url_key = "id", "text", "hostedUrl"
    if not isinstance(raw, list):
        return None
    jobs = []
    for j in raw:
        if isinstance(j, dict) and j.get(id_key) is not None:
            jobs.append({"id": str(j[id_key]), "title": str(j.get(title_key) or ""),
                         "url": str(j.get(url_key) or "")})
    return jobs


def _dedupe(jobs):
    """GATE.md section 3: the same job ID twice -> keep the first, log the drop."""
    kept, seen, dropped = [], set(), []
    for j in jobs:
        if j["id"] in seen:
            dropped.append(j["id"])
            continue
        seen.add(j["id"])
        kept.append(j)
    return kept, dropped


# ------------------------------------------------------------------ state (policy-checked I/O)
def _load_state(path, name):
    """Return the saved set of job IDs, or None if this board has no state yet.
    Unreadable or malformed state stops the run with "error" (never a silent re-baseline)."""
    try:
        policy.check_read(path)
    except PermissionError as e:
        raise _Stop("error", _state_error(name, f"can't read state: {e}", path))
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise _Stop("error", _state_error(name, f"can't read state: {e}", path))
    ids = data.get("seen_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        raise _Stop("error", _state_error(name, "state file has no seen_ids list", path))
    return {str(i) for i in ids}


def _save_state(state_dir, path, ids, name, done, rest_after, report, code, attempts, notes):
    """Write <state_dir>/<name>.json atomically (temp file + os.replace).
    Every write — the folder, the temp file, the final file — is policy-checked first."""
    try:
        if not state_dir.exists():
            policy.check_write(state_dir)
            state_dir.mkdir()
        tmp = path.with_name(path.name + ".tmp")
        policy.check_write(tmp)
        policy.check_write(path)
        tmp.write_text(json.dumps({"seen_ids": sorted(ids)}, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:  # PermissionError from policy is an OSError too
        _observe(report, name, "failed", code, attempts, notes + [f"state not saved: {e}"])
        entry = _state_error(name, f"can't save state: {e}", path)
        entry.update({"done": list(done), "not_done": [name] + list(rest_after)})
        raise _Stop("error", entry)


# ------------------------------------------------------------------ report pieces
def _observe(report, name, status, code, attempts, notes):
    """GATE.md section 6 #4: every board attempted gets a logged observation."""
    report["observations"].append({
        "board": name,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status_code": code,
        "request_count": attempts,
        "notes": list(notes),
    })


def _failure(board, code, error, reason, *, escalate):
    """GATE.md section 4: what failed, a likely reason, and a manual check."""
    return {
        "board": board["name"],
        "url": board["url"],
        "status_code": code,
        "error": error,
        "reason": reason,
        "manual_check": f"curl -sS -i {shlex.quote(board['url'])}",
        "escalate": escalate,
    }


def _state_error(name, error, path):
    return {"board": name, "error": error, "reason": "GATE.md section 1: can't read/save state -> error",
            "manual_check": f"cat {shlex.quote(str(path))}", "escalate": True}


def _budget_entry(which, budget, done, skipped):
    return {"budget": which, "limit": budget[which],
            "error": f"{which} budget exhausted (limit {budget[which]})",
            "done": list(done), "skipped": list(skipped)}


# ------------------------------------------------------------------ config
def _check_config(boards, fetch, budget):
    """GATE.md section 1: bad config -> error. Returns the budget with GATE defaults filled in."""
    if not callable(fetch):
        raise ValueError("fetch must be callable")
    b = {**DEFAULT_BUDGET, **(budget or {})}
    for key in DEFAULT_BUDGET:
        v = b[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise ValueError(f"budget {key!r} must be a positive number, got {v!r}")
    if not isinstance(boards, list) or not boards:
        raise ValueError("board list must be a non-empty list")
    for i, board in enumerate(boards):
        if not isinstance(board, dict):
            raise ValueError(f"board #{i} is not a dict")
        name = board.get("name")
        if not isinstance(name, str) or not BOARD_NAME_RE.fullmatch(name):
            raise ValueError(f"board #{i} has an unsafe or missing name: {name!r}")
        if board.get("ats") not in ATS_KINDS:
            raise ValueError(f"board {name!r}: ats must be one of {ATS_KINDS}, got {board.get('ats')!r}")
        if not isinstance(board.get("url"), str):
            raise ValueError(f"board {name!r}: url must be a string")
    return b

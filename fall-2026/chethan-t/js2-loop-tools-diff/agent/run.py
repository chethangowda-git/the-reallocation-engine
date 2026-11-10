"""`python -m agent.run` — check the GATE.md job boards once. Contract: ../GATE.md.
Tests: ../tests/test_run.py.

main(argv=None, *, fetch=None, now=None) -> exit code
  - root = policy.ROOT (the folder holding config/, state/, jobs/)
  - loads <root>/config/boards.json (a list of {"name", "ats", "url", ...})
  - calls loop.run(boards, fetch, loop.DEFAULT_BUDGET, <root>/state)
      fetch defaults to agent.fetch.http_fetch (looked up at call time)
  - saves the report to       <root>/jobs/traces/<timestamp>.json
      as {"run_at", "exit_code", "boards_file", "raw_files", "report"}
  - saves each board's raw responses to <root>/jobs/raw/<board>-<timestamp>.json
      as {"board", "url", "run_at", "attempts": [{"fetched_at", "status_code", "body"} |
                                                 {"fetched_at", "error"}]}
      (only boards that were actually requested get a raw file)
  - <timestamp> is UTC, YYYYMMDDTHHMMSSZ; a second run in the same second never
    overwrites — it gets a -2, -3, ... suffix
  - every write (folders and files) goes through policy.check_write
  - exit code: 0 finished (incl. baseline boards), 1 incomplete, 2 budget-exhausted, 3 error
      (unreadable config, or a trace/raw file that can't be saved, is 3)
  - now: optional zero-arg callable returning an aware UTC datetime (tests fix it)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import fetch as fetch_mod
from . import loop, policy

EXIT_CODES = {"finished": 0, "incomplete": 1, "budget-exhausted": 2, "error": 3}
BOARDS_FILE = Path("config") / "boards.json"


def main(argv=None, *, fetch=None, now=None):
    argparse.ArgumentParser(
        prog="python -m agent.run",
        description="Check the job boards in config/boards.json once, per GATE.md. "
                    "Exit code: 0 finished, 1 incomplete, 2 budget-exhausted, 3 error.",
    ).parse_args(argv)

    now = now or (lambda: datetime.now(timezone.utc))
    started = now()
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    run_at = started.isoformat(timespec="seconds")
    root = Path(os.path.realpath(policy.ROOT))
    real_fetch = fetch or fetch_mod.http_fetch  # looked up now, so tests can patch it

    raw_calls = {}  # url -> [attempt records], filled by the recording wrapper
    try:
        boards = _load_boards(root / BOARDS_FILE)
    except (OSError, ValueError) as e:  # PermissionError from policy is an OSError
        boards = []
        report = {"status": "error", "observations": [], "new_jobs": {}, "errors": [{
            "error": f"can't load {BOARDS_FILE}: {e}",
            "reason": "GATE.md section 1: bad config -> error",
            "manual_check": f"python -m json.tool {BOARDS_FILE}",
            "escalate": True,
        }]}
    else:
        report = loop.run(boards, _recorder(real_fetch, raw_calls, now),
                          loop.DEFAULT_BUDGET, root / "state")

    code = EXIT_CODES.get(report["status"], 3)
    try:
        raw_files = _save_raw(root, boards, raw_calls, stamp, run_at)
        trace_path = _save_json(root / "jobs" / "traces", stamp, {
            "run_at": run_at,
            "exit_code": code,
            "boards_file": str(BOARDS_FILE),
            "raw_files": raw_files,
            "report": report,
        })
    except OSError as e:
        print(f"ERROR: could not save run outputs under jobs/: {e}", file=sys.stderr)
        _print_summary(report, 3, None, run_at)
        return 3

    _print_summary(report, code, trace_path.relative_to(root), run_at)
    return code


# ------------------------------------------------------------------ config
def _load_boards(path):
    policy.check_read(path)
    boards = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(boards, list):
        raise ValueError("expected a JSON list of boards")
    return boards  # each board's fields are validated by loop.run (bad config -> error)


# ------------------------------------------------------------------ raw responses
def _recorder(real_fetch, raw_calls, now):
    """Wrap the fetcher so every attempt (response or exception) is kept for jobs/raw/."""
    def recording_fetch(url, *, timeout):
        record = {"fetched_at": now().isoformat(timespec="seconds")}
        try:
            code, body = real_fetch(url, timeout=timeout)
        except Exception as e:
            record["error"] = f"{type(e).__name__}: {e}"
            raw_calls.setdefault(url, []).append(record)
            raise
        record.update({"status_code": code, "body": body})
        raw_calls.setdefault(url, []).append(record)
        return code, body
    return recording_fetch


def _save_raw(root, boards, raw_calls, stamp, run_at):
    written, done_urls = [], set()
    for board in boards:
        url = board.get("url") if isinstance(board, dict) else None
        if url not in raw_calls or url in done_urls:
            continue  # never requested (blocked, skipped by a budget) or already saved
        done_urls.add(url)
        path = _save_json(root / "jobs" / "raw", f"{board['name']}-{stamp}", {
            "board": board["name"], "url": url, "run_at": run_at, "attempts": raw_calls[url],
        })
        written.append(str(path.relative_to(root)))
    return written


# ------------------------------------------------------------------ policy-checked writes
def _ensure_dir(path):
    """Create `path` and any missing parents one level at a time, each policy-checked."""
    missing = []
    p = path
    while not p.exists():
        missing.append(p)
        p = p.parent
    for d in reversed(missing):
        policy.check_write(d)
        d.mkdir()


def _save_json(folder, stem, obj):
    """Write obj to folder/<stem>.json, or <stem>-2.json, -3, ... — never overwrite."""
    _ensure_dir(folder)
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    n = 1
    while True:
        path = folder / (f"{stem}.json" if n == 1 else f"{stem}-{n}.json")
        if not path.exists():
            policy.check_write(path)
            try:
                with open(path, "x", encoding="utf-8") as f:  # "x": fails rather than overwrite
                    f.write(text)
                return path
            except FileExistsError:
                pass  # created between the check and the open — try the next suffix
        n += 1


# ------------------------------------------------------------------ human summary
def _print_summary(report, code, trace_path, run_at):
    print(f"JS2 run {run_at} — status: {report['status']} (exit {code})")
    for o in report["observations"]:
        sc = f"HTTP {o['status_code']}" if o["status_code"] is not None else "no response"
        new = report["new_jobs"].get(o["board"])
        tail = f"{len(new)} new matching job(s)" if new is not None else ""
        print(f"  {o['board']:<24} {o['status']:<9} {sc:<12} {o['request_count']} request(s)  {tail}")
    for e in report["errors"]:
        who = e.get("board") or e.get("budget", "run")
        print(f"  ! {who}: {e.get('error')}")
        if e.get("reason"):
            print(f"      why:   {e['reason']}")
        if e.get("manual_check"):
            print(f"      check: {e['manual_check']}")
        if e.get("escalate"):
            print("      -> escalate to Chethan")
    if trace_path:
        print(f"  trace: {trace_path}")


if __name__ == "__main__":
    sys.exit(main())

"""Finished-wrong-answer demo — offline. GATE.md section 6, wrong version #1.

    python -m demo.finished_wrong        (from the js2-loop-tools-diff folder)

A board that answers HTTP 200 with {"jobs": []} looks like "no new jobs". It may just
as well be a broken response or a wrong URL. This demo shows three things:

  1. NAIVE loop (defined here only — agent/loop.py is not changed): treats the empty
     response as success and ends "finished, 0 new jobs". Clean, and wrong.
  2. INDEPENDENT check: does not trust the agent's report. It reads the board's last
     saved REAL response from jobs/raw/ (written by an earlier real run), counts the
     jobs itself, and flags the mismatch with what the agent claimed.
  3. REAL loop.run on the same empty input: ends "incomplete", board escalated.

No network: every response comes from a fake fetcher or from files already on disk.
"""

import json
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

if __package__ in (None, ""):  # allow `python demo/finished_wrong.py` as well as `-m`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import loop, policy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BOARD_NAME = "atlassp"
EMPTY = (200, {"jobs": []})


def empty_fetch(url, *, timeout):
    """Fake fetcher: every board answers HTTP 200 with an empty job list."""
    return EMPTY


# ------------------------------------------------------------------ 1. the naive loop
def naive_run(boards, fetch):
    """A NAIVE loop — the wrong version GATE.md section 6 #1 warns about.
    It trusts any HTTP 200 and counts whatever jobs came back, so an empty
    response becomes a clean-looking "finished, 0 new jobs"."""
    report = {"status": "finished", "observations": [], "new_jobs": {}, "errors": []}
    for board in boards:
        code, body = fetch(board["url"], timeout=10)
        jobs = body.get("jobs", []) if isinstance(body, dict) else (body or [])
        report["observations"].append({"board": board["name"], "status": "ok",
                                       "status_code": code, "jobs_seen": len(jobs)})
        report["new_jobs"][board["name"]] = []  # nothing new — because nothing was seen
    return report


# ------------------------------------------------------------------ 2. the independent check
def latest_raw(raw_dir, board_name):
    """The most recent saved raw response for a board (by its recorded run_at).

    Matched exactly — `<board>-<YYYYMMDDTHHMMSSZ>[-n].json` AND the file's own "board"
    field — never by prefix: "atlassp-*" would also match "atlassp-doesnotexist-...".
    """
    name_re = re.compile(rf"{re.escape(board_name)}-\d{{8}}T\d{{6}}Z(?:-\d+)?\.json")
    files = []
    for p in Path(raw_dir).glob("*.json"):
        if name_re.fullmatch(p.name):
            raw = json.loads(p.read_text(encoding="utf-8"))
            if raw.get("board") == board_name:
                files.append((raw["run_at"], p.name, p))
    if not files:
        raise FileNotFoundError(f"no saved raw response for {board_name!r} in {raw_dir}")
    return max(files)[2]


def real_job_count(raw_path):
    """Count the jobs in a saved raw response, with this check's OWN parser —
    nothing from agent/loop.py is reused, so a bug there cannot hide here."""
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    ok = [a for a in raw["attempts"] if a.get("status_code") == 200 and "body" in a]
    if not ok:
        raise ValueError(f"{raw_path} has no successful (HTTP 200) attempt to count")
    body = ok[-1]["body"]
    if isinstance(body, dict) and isinstance(body.get("jobs"), list):  # Greenhouse
        return len(body["jobs"])
    if isinstance(body, list):  # Lever
        return len(body)
    raise ValueError(f"{raw_path}: unrecognised response shape")


def independent_check(claims, raw_dir):
    """claims: {board: job count the agent says it saw}. Returns one entry per board
    whose claim disagrees with the last real saved response; [] means no disagreement.
    Any difference is flagged — the check reports, a human decides (it does not "fix")."""
    mismatches = []
    for board, claimed in claims.items():
        path = latest_raw(raw_dir, board)
        real = real_job_count(path)
        if claimed != real:
            mismatches.append({
                "board": board, "reported": claimed, "real": real,
                "raw_file": str(path), "run_at": json.loads(path.read_text(encoding="utf-8"))["run_at"],
                "verdict": "MISMATCH — do not trust this run's answer for this board; check by hand",
            })
    return mismatches


def claims_from_naive(report):
    return {o["board"]: o["jobs_seen"] for o in report["observations"]}


# ------------------------------------------------------------------ 3. the real loop
@contextmanager
def throwaway_agent_root():
    """Run the real loop in a temporary agent root so the demo can never touch the
    real state/ folder. policy.ROOT is restored afterwards."""
    saved = policy.ROOT
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "state").mkdir()
        policy.ROOT = root
        try:
            yield root
        finally:
            policy.ROOT = saved


def real_run_on_empty(board):
    with throwaway_agent_root() as root:
        return loop.run([board], empty_fetch, loop.DEFAULT_BUDGET, root / "state")


# ------------------------------------------------------------------ demo
def load_board(name=BOARD_NAME):
    boards = json.loads((ROOT / "config" / "boards.json").read_text(encoding="utf-8"))
    return next(b for b in boards if b["name"] == name)


def main():
    board = load_board()
    raw_dir = ROOT / "jobs" / "raw"
    line = "=" * 78

    print(line)
    print(f'1. NAIVE loop (demo-only variant) — board {board["name"]!r} answers HTTP 200 {{"jobs": []}}')
    print(line)
    naive = naive_run([board], empty_fetch)
    o = naive["observations"][0]
    print(f'   status: {naive["status"]}')
    print(f'   {o["board"]}: HTTP {o["status_code"]}, {o["jobs_seen"]} jobs seen, '
          f'{len(naive["new_jobs"][o["board"]])} new jobs')
    print(f'   errors: {naive["errors"] or "none"}')
    print("   -> Clean-looking and WRONG: an empty response was reported as \"no new jobs\".")

    print()
    print(line)
    print("2. INDEPENDENT check — reads the last REAL saved response, not the agent's report")
    print(line)
    mismatches = independent_check(claims_from_naive(naive), raw_dir)
    path = latest_raw(raw_dir, board["name"])
    print(f"   source: {path.relative_to(ROOT)}")
    print(f'   agent reported {o["jobs_seen"]} jobs on {board["name"]!r}; '
          f"the last real response had {real_job_count(path)}")
    if mismatches:
        for m in mismatches:
            print(f'   FLAG {m["board"]}: reported {m["reported"]} vs real {m["real"]} '
                  f'(real response from {m["run_at"]})')
            print(f'        {m["verdict"]}')
            print(f"        manual check: curl -sS -i '{board['url']}'")
    else:
        print("   no disagreement found")

    print()
    print(line)
    print("3. REAL loop.run on the same empty input")
    print(line)
    real = real_run_on_empty(board)
    ro = real["observations"][0]
    err = real["errors"][0]
    print(f'   status: {real["status"]}')
    print(f'   {ro["board"]}: {ro["status"]} (HTTP {ro["status_code"]}, {ro["request_count"]} request); '
          f'in new_jobs: {"yes" if ro["board"] in real["new_jobs"] else "no (absent, never [])"}')
    print(f'   error: {err["error"]}')
    print(f'   why:   {err["reason"]}')
    print(f'   escalate: {err["escalate"]}   manual check: {err["manual_check"]}')

    caught = bool(mismatches) and real["status"] == "incomplete" and err["escalate"] is True
    print()
    print("RESULT:", "the wrong answer was caught twice — by the independent check and by the real loop"
          if caught else "DEMO FAILED: the wrong answer was not caught")
    return 0 if caught else 1


if __name__ == "__main__":
    sys.exit(main())

"""`python -m agent.run` — INTERFACE STUB ONLY. No implementation yet (tests come first).

Contract: ../GATE.md. Tests: ../tests/test_run.py.

main(argv=None, *, fetch=None, now=None) -> exit code
  - root = policy.ROOT (the folder holding config/, state/, jobs/)
  - loads <root>/config/boards.json (a list of {"name", "ats", "url", ...})
  - calls loop.run(boards, fetch, loop.DEFAULT_BUDGET, <root>/state)
      fetch defaults to agent.fetch.http_fetch (looked up at call time)
  - saves the report to       <root>/jobs/traces/<timestamp>.json
      as {"run_at", "exit_code", "boards_file", "report"}
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

import sys

EXIT_CODES = {"finished": 0, "incomplete": 1, "budget-exhausted": 2, "error": 3}


def main(argv=None, *, fetch=None, now=None):
    raise NotImplementedError("agent.run.main — not implemented yet")


if __name__ == "__main__":
    sys.exit(main())

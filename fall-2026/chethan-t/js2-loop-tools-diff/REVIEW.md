# REVIEW — reposted jobs no longer reported as new (`agent/loop.py`, uncommitted patch)

## Executive summary

**What this is.** A review of one small change to the job-board loop. Before it, a job that
was taken down and later put back up under the same ID was announced as a "new job" again.
Chethan decided that this is wrong: a job seen in any earlier run is not new. This document
reviews the fix.

**Why read it.** It shows that the wrong behaviour was first demonstrated by a test that
failed, that the test was committed before the fix, what the loop now does differently, what
else the fix touches, and one case that still slips through.

**What it found.** The new test failed on the old code for exactly the reported reason (the
reposted job came back as new) and passes on the fixed code; nothing else in the suite
changed. The fix is one line. It has two side effects no test covers: the saved list of jobs
now only grows, and jobs forgotten by the old code before the fix stay forgotten. A job
reposted under a *new* ID is still reported as new. The decision is Chethan's (section 5).

**Who wrote what.** Every section is tagged:
- **[Claude wrote]** — drafted by Claude Code from git history and this session's output.
- **[Claude ran]** — commands Claude ran, with the output seen.
- **[Chethan ran]** — commands Chethan ran in Chethan's own terminal, output as Chethan pasted it.
- **[Chethan decides]** — left for Chethan; Claude does not fill it in.

(The earlier review of the whole loop, commit `204b425`, is kept as `REVIEW-204b425.md`.)

---

## Review record

| | |
|---|---|
| Change under review | uncommitted patch to `agent/loop.py` (3 insertions, 1 deletion) |
| Decision it implements | `GATE.md` section 6, change dated 2026-11-10 (Chethan): "A job ID seen in any earlier run is not new, even if it was removed and reposted." |
| Test before patch | `861812c` — "JS2: failing test for reposted-job defect" (2026-11-10 17:22:48 −0500; `GATE.md` + `tests/test_loop.py` only) |
| Code it changes | `204b425` (the loop), which saved only the job IDs on the board at each run |
| Branch | `js2-chethan-t`, local, not pushed |
| Drafted | 2026-11-10, by Claude Code (Claude Opus 5.5) |

---

## 1. Defect reproduced, test before patch — [Claude wrote] [Claude ran]

**The defect.** After each successful check, the loop saved only the IDs on the board *at
that moment*. A job removed in one run was dropped from the saved list, so when it came back
(same ID) it was reported as new.

**The test** (`test_job_seen_earlier_then_removed_then_reposted_is_not_new`, committed in
`861812c`, before any fix) runs one board three times:

| Run | Board shows | Must report as new |
|---|---|---|
| 1 | job 123 | 123 |
| 2 | job 456 (123 removed) | 456 |
| 3 | jobs 123 and 456 (123 reposted) | nothing — 123 was seen in run 1 |

**Failing before the patch.** Re-run for this review on a clean `git archive` extract of
`861812c` (not the working tree):

```
tests/test_loop.py:270: AssertionError: assert ['123'] == []
1 failed, 127 passed
```

Runs 1 and 2 passed; run 3 reported the reposted job 123 as new — the defect, and only the
defect. Every other test still passed.

**Passing after the patch.** Full suite on the working tree with the patch: `128 passed`.

## 2. The diff, read as behaviour — [Claude wrote]

The loop now **remembers every job ID it has ever seen on a board**, not just the ones on
the board today. Each successful run adds today's IDs to what was already remembered; nothing
is forgotten. So a job that disappears and comes back is recognised and not announced again.

Unchanged: the first run of a board still records everything as a baseline and reports
nothing; a failed board still leaves its saved list untouched; which jobs count as "new" in a
run is still decided against the saved list *before* the run.

```diff
     new = [j for j in jobs if j["id"] not in seen and title_matches(j["title"])]
-    _save_state(state_dir, state_path, ids_now, name, done, rest_after, report, code, attempts, notes)
+    # GATE.md section 6 change (2026-11-10): an ID seen in ANY earlier run is never new again,
+    # so the saved set keeps every ID ever seen, not only the IDs on the board right now.
+    _save_state(state_dir, state_path, seen | ids_now, name, done, rest_after, report, code, attempts, notes)
```

## 3. Scope — [Claude wrote]

**Stayed in scope.** The patch changes one call in the loop's success path (`agent/loop.py`
only). It does not touch the baseline path, the failure path, budgets, retries, the policy,
the fetcher, the run command or any test.

**Side effects not covered by any test:**

1. **The saved list only grows.** Every ID ever seen on a board is kept forever; nothing
   prunes it. Today's boards are small (the real `state/hubspotjobs.json` is under 2 KB), but
   nothing caps it.
2. **What the old code forgot stays forgotten.** State files written before this patch hold
   only the IDs that were on the board at that run. An ID that had already disappeared before
   the patch is not in them, so if it is reposted it will still be reported as new once. (The
   committed `state/` files come from two runs 2 seconds apart with identical boards, so in
   this repository nothing was lost — but the code cannot know that.) The IDs could be
   recovered from `jobs/raw/`; the patch does not try.
3. **A closed-and-reopened job is now silent.** If a company genuinely closes a role and
   reopens it under the same ID, it is no longer announced. That is the behaviour Chethan's
   GATE.md decision asks for.

## 4. Commands run

### Run by Claude — [Claude ran]

| Ran | Saw | Expected |
|---|---|---|
| `pytest tests/test_loop.py -k reposted` (before patch, working tree) | `1 failed` — `assert ['123'] == []` | a failure on run 3 |
| `pytest tests` (before patch) | `1 failed, 127 passed` | only the new test fails |
| same, on a clean `git archive 861812c` extract | `1 failed, 127 passed`, same assertion | same |
| `git diff agent/loop.py` (after patch) | 3 insertions, 1 deletion, one call changed | a minimal patch |
| `pytest tests` (after patch) | `128 passed` | all pass |

### Run by Chethan, in Chethan's own terminal — [Chethan ran]

| Ran | Saw | Expected |
|---|---|---|
| 1. `python -m pytest -q` (fix in place) | `128 passed in 0.14s` | 128 passed |
| 2. `python -m pytest -q` (fix reverted) | `1 failed, 127 passed in 0.15s`<br>`FAILED tests/test_loop.py::test_job_seen_earlier_then_removed_then_reposted_is_not_new`<br>`AssertionError: assert ['123'] == []` | 1 failed — `test_job_seen_earlier_then_removed_then_reposted_is_not_new` |
| 3. `python -m pytest -q` (fix restored) | `128 passed in 0.14s` | 128 passed |

## 5. Decision — [Chethan decides]

ACCEPT. The fix is one line and only touches loop.py. In my own terminal, the reposted-job
test failed without the fix and passed with it. I accept that the saved ID list only grows.

— Chethan, 2026-11-10

## 6. A case the tests would still miss — [Claude wrote]

**A job reposted under a new ID is still reported as new.** The rule is keyed on the job ID.
Many companies close a posting and publish the same role again as a fresh posting with a new
ID — same title, same team, same location. To the loop that is a different job, so it is
announced as new, and no test covers it: every test identifies jobs only by ID.

Catching it would need a second identity for a job (for example company + normalised title +
location). That would also merge genuinely different openings with the same title, so it is
a judgment for Chethan and a GATE.md change, not a quiet fix.

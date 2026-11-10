# FRICTIONAL.md — Job-Search Agent 2

Honest log: what I tried, what Claude flagged, what I accepted or changed.
Entries written by Chethan.

| # | What I tried | What Claude flagged | What I accepted / changed |
|---|---|---|---|
| 1 | **Boards:** Red Sox, Suno, Fidelity (Workday) and Amazon (own system). | — | Rejected Red Sox/Suno; dropped Fidelity (Workday) and Amazon (own system), since neither has a public ATS API. Final: ATLAS SP and HubSpot (Greenhouse), Analytic Partners (Lever). |
| 2 | **Exit rule:** my first idea was "stop when the last job matches the last run." | Ordering, multiple new jobs, removals, and empty boards. | Switched to comparing full ID sets with four exits. |
| 3 | **Budget:** I started with 1 request per board and 10 minutes. | 10 minutes would never be tested. | Changed to 1 retry (8 requests), 60 s per run, and 10 s per request. |
| 4 | **Error policy:** I wanted the agent to fix URLs and retry. | Claude flagged it. | Now it only escalates to me. |
| 5 | **Permissions:** "the folder where it runs" and "required host". | — | Too vague. Narrowed to config/state/jobs and an exact host allow-list. |
| 6 | **Starting point:** the Python skill vs the JS providers. | Empty→[] bug, no Lever allow-list. | Chose the Python skill over the JS providers. |
| 7 | **Repo confusion:** Claude created fall-2026/chethan-t in the Reallocation Engine fork. | — | We had to clarify build repo vs submission repo. |
| 8 | **Commit caution:** — | Claude Code stopped before committing GATE.md during a read-only step. | — |
| 9 | **Tests:** Claude drafted them from GATE. | — | I reviewed and decided the title list, the baseline status, whole-word "sde", and "ok = [] vs failed = absent". |
| 10 | **Policy extras:** — | 12 policy tests were written after the code, so they never failed first. | — |
| 11 | **Sandbox conflict:** — | Claude stopped instead of editing tests. | We added a test proving the loop actually calls check_host. |
| 12 | **Planted bug:** my first planted-bug run showed 81 passed (probably an unsaved file). | — | The re-run failed correctly. |
| 13 | **Bad check:** my grep falsely flagged the "requests" budget key. | — | — |
| 14 | **zsh:** pasted # comments broke commands. | — | — |
| 15 | **Look-alike file bug:** — | The demo's atlassp-* matched atlassp-doesnotexist, caught by real data. | — |
| 16 | **Review packet switch:** — | A stub isn't a defect. | Switched to the reposted-job defect and amended GATE. |
| 17 | **Attribution fix:** — | — | Claude Code at first credited my terminal runs to itself in REVIEW.md, and I corrected it. |
| 18 | **Delete rule:** — | Delete rule was stricter than GATE. | I amended GATE with a dated note. |

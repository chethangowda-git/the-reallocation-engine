# Permissions — what the agent may and may not touch

## Executive summary

**What this is.** The agent's permission rules and the evidence that they hold: every rule
has a test that tries to cross it, and this page records what each test expected and what
actually happened.

**Why read it.** The agent talks to the internet and writes files. This is the one place that
says exactly where it may go, what it may write, and how that was checked.

**What it found.** All 47 permission tests pass. The agent can reach only two job-board
hosts, over HTTPS, with GET requests; it can read only its config, state and job folders and
write only to state and jobs (config needs Chethan's approval; every delete needs approval).
Tricks such as `..`, look-alike folder names and symlinks are blocked.

---

## The policy (GATE.md section 5, enforced in `agent/policy.py`)

**Hosts (allow-list):** `boards-api.greenhouse.io`, `api.lever.co`. Everything else is
blocked. Also blocked: plain `http://`, credentials in the URL, any port other than 443,
malformed URLs.

**Methods:** GET only (case-insensitive). POST and everything else are blocked.

**Folders** (paths resolved with `os.path.realpath` first, then compared as whole path
components — never by prefix):

| Folder | Read | Write | Delete |
|---|---|---|---|
| `config/` | ✅ | needs Chethan's approval | needs approval |
| `state/` | ✅ | ✅ | needs approval |
| `jobs/` | ✅ | ✅ | needs approval |
| anything else | ❌ | ❌ | ❌ |

"Approval" means `approved=True` exactly — `approved="yes"` does not count. The delete rule
for `config/` and `jobs/` is Chethan's 2026-11-10 change to GATE.md section 5.

**Where it is enforced:** `policy.check_host` + `check_method("GET")` before every request
(in the loop, retries included, and again inside the fetcher); `check_read` before reading
state or config; `check_write` before every file or folder the loop or run command writes.

## Boundary tests

Run on 2026-11-10 (Claude, Claude Code session), from this folder:

```
python -m pytest tests/test_policy.py <the 11 wiring tests below> -v
47 passed in 0.05s
```

### Hosts and methods — `tests/test_policy.py`

| Case | Expected | Actual | Test |
|---|---|---|---|
| `https://boards-api.greenhouse.io/…` | allowed | allowed — PASSED | `test_host_greenhouse_boards_api_allowed` |
| `https://api.lever.co/…` | allowed | allowed — PASSED | `test_host_lever_api_allowed` |
| `https://api.ashbyhq.com/…` | blocked | PermissionError — PASSED | `test_host_ashby_blocked` |
| `https://evil.com/…` | blocked | PermissionError — PASSED | `test_host_evil_com_blocked` |
| `https://boards-api.greenhouse.io.evil.com/…` (look-alike) | blocked | PermissionError — PASSED | `test_host_lookalike_suffix_blocked` |
| `http://boards-api.greenhouse.io/…` | blocked | PermissionError — PASSED | `test_plain_http_blocked_even_for_allowed_host` |
| `https://user:pass@…` and `https://token@…` | blocked | PermissionError — PASSED (2 cases) | `test_credentials_in_url_blocked[user-and-password]`, `[token-only]` |
| port `:8443` | blocked | PermissionError — PASSED | `test_non_standard_port_blocked` |
| explicit port `:443` | allowed | allowed — PASSED | `test_explicit_port_443_allowed` |
| port 99999, port `abc`, no scheme, `not a url`, empty | blocked | PermissionError — PASSED (5 cases) | `test_malformed_url_blocked[…]` |
| `POST` | blocked | PermissionError — PASSED | `test_post_blocked` |
| `GET` | allowed | allowed — PASSED | `test_get_allowed` |
| `get` (lowercase) | allowed | allowed — PASSED | `test_lowercase_get_allowed` |

### Paths — `tests/test_policy.py`

| Case | Expected | Actual | Test |
|---|---|---|---|
| read `jobs/../secret` | blocked | PermissionError — PASSED | `test_dotdot_escape_from_jobs_blocked` |
| read `jobs-evil/x` | blocked | PermissionError — PASSED | `test_lookalike_folder_jobs_evil_read_blocked` |
| write `jobs-evil/x` | blocked | PermissionError — PASSED | `test_lookalike_folder_jobs_evil_write_blocked` |
| read `jobs/link/secret.txt`, `jobs/link` → outside folder | blocked | PermissionError — PASSED | `test_symlink_inside_jobs_pointing_outside_blocked` |
| read `outside/secret.txt` | blocked | PermissionError — PASSED | `test_read_outside_allowed_folders_blocked` |
| read `config/boards.json` | allowed | allowed — PASSED | `test_read_config_allowed` |
| write `config/boards.json` | needs approval | blocked without, allowed with `approved=True` — PASSED | `test_write_config_needs_approval` |
| write `config/…` with `approved="yes"` | needs approval | PermissionError — PASSED | `test_write_config_approved_yes_string_does_not_count` |
| write `jobs/report-….json` | allowed | allowed — PASSED | `test_write_jobs_allowed` |
| write `state/atlassp.json` | allowed | allowed — PASSED | `test_write_state_allowed` |
| delete `state/atlassp.json` | needs approval | blocked without, allowed with `approved=True` — PASSED | `test_delete_in_state_needs_approval` |
| delete in `state/` with `approved="yes"` | needs approval | PermissionError — PASSED | `test_delete_state_approved_yes_string_does_not_count` |
| delete in `jobs/`, in `config/` | needs approval | blocked without, allowed with — PASSED (2 cases) | `test_delete_in_jobs_or_config_needs_approval[jobs]`, `[config]` |
| delete `outside/…`, `secret`, `jobs-evil/x`, `jobs/../secret` | blocked, even with approval | PermissionError — PASSED (4 cases) | `test_delete_outside_allowed_folders_blocked[…]` |

### The policy is actually called — wiring tests

| Case | Expected | Actual | Test |
|---|---|---|---|
| a board on `https://evil.com/…` in the loop | never requested; board failed; run incomplete | not requested — PASSED | `tests/test_loop.py::test_blocked_host_is_never_fetched` |
| fetcher called directly with evil host / `http://` / Ashby | PermissionError before any request | no request made — PASSED (3 cases) | `tests/test_fetch.py::test_fetcher_checks_host_itself_and_never_opens[…]` |
| fetcher with the method check refusing | PermissionError before any request | no request made — PASSED | `tests/test_fetch.py::test_fetcher_checks_method_itself` |
| a redirect (301 / 302 / 307 / 308) | returned as-is, never followed | one request only — PASSED (4 cases) | `tests/test_fetch.py::test_3xx_is_returned_as_is_and_never_followed[…]` |
| every file and folder a run creates | passed through `check_write` | none unchecked — PASSED | `tests/test_run.py::test_every_write_goes_through_check_write` |
| writes to `jobs/` refused | run exits 3, nothing written there | exit 3, `jobs/` empty — PASSED | `tests/test_run.py::test_blocked_jobs_write_exits_3_and_writes_nothing_there` |

Planted-bug evidence that the wiring test bites: with the loop's `check_host` call commented
out, `test_blocked_host_is_never_fetched` failed (1 failed, 80 passed) in Chethan's own
terminal; restored → 81 passed.

## Not covered

- A real redirect from a live server (only simulated 3xx responses).
- Policy behaviour on a case-insensitive filesystem with differently-cased folder names
  (`JOBS/`): it is blocked (the name is not `jobs`), but no test shows it.
- Time-of-check / time-of-use races between a policy check and the write it guards.

"""Permission-policy boundary tests — written BEFORE the implementation. Contract: ../GATE.md section 5.

Every check returns None when allowed and raises PermissionError when blocked.
"Needs approval" = blocked with approved=False, allowed with approved=True.
Paths are relative to policy.ROOT, which each test points at a throwaway folder.
"""

import pytest

from agent import policy


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A fake agent root with the three allowed folders, a look-alike, and an outside folder."""
    r = tmp_path.resolve()
    for d in ("config", "state", "jobs", "jobs-evil", "outside"):
        (r / d).mkdir()
    (r / "config" / "boards.json").write_text("[]", encoding="utf-8")
    (r / "state" / "atlassp.json").write_text('{"seen_ids": []}', encoding="utf-8")
    (r / "jobs-evil" / "x").write_text("look-alike", encoding="utf-8")
    (r / "outside" / "secret.txt").write_text("secret", encoding="utf-8")
    (r / "secret").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(policy, "ROOT", r)
    return r


# ================================================================== hosts

# EXPECTED: allowed
def test_host_greenhouse_boards_api_allowed():
    policy.check_host("https://boards-api.greenhouse.io/v1/boards/atlassp/jobs")


# EXPECTED: allowed
def test_host_lever_api_allowed():
    policy.check_host("https://api.lever.co/v0/postings/analyticpartners?mode=json")


# EXPECTED: blocked
def test_host_ashby_blocked():
    with pytest.raises(PermissionError):
        policy.check_host("https://api.ashbyhq.com/posting-api/job-board/acme")


# EXPECTED: blocked
def test_host_evil_com_blocked():
    with pytest.raises(PermissionError):
        policy.check_host("https://evil.com/v1/boards/atlassp/jobs")


# EXPECTED: blocked
def test_host_lookalike_suffix_blocked():
    with pytest.raises(PermissionError):
        policy.check_host("https://boards-api.greenhouse.io.evil.com/v1/boards/atlassp/jobs")


# EXPECTED: blocked
def test_plain_http_blocked_even_for_allowed_host():
    with pytest.raises(PermissionError):
        policy.check_host("http://boards-api.greenhouse.io/v1/boards/atlassp/jobs")


# ================================================================== paths — escapes

# EXPECTED: blocked
def test_dotdot_escape_from_jobs_blocked(root):
    with pytest.raises(PermissionError):
        policy.check_read("jobs/../secret")


# EXPECTED: blocked
def test_lookalike_folder_jobs_evil_read_blocked(root):
    with pytest.raises(PermissionError):
        policy.check_read("jobs-evil/x")


# EXPECTED: blocked
def test_lookalike_folder_jobs_evil_write_blocked(root):
    with pytest.raises(PermissionError):
        policy.check_write("jobs-evil/x")


# EXPECTED: blocked
def test_symlink_inside_jobs_pointing_outside_blocked(root):
    (root / "jobs" / "link").symlink_to(root / "outside", target_is_directory=True)
    with pytest.raises(PermissionError):
        policy.check_read("jobs/link/secret.txt")


# EXPECTED: blocked
def test_read_outside_allowed_folders_blocked(root):
    with pytest.raises(PermissionError):
        policy.check_read("outside/secret.txt")


# ================================================================== paths — folder rules

# EXPECTED: allowed
def test_read_config_allowed(root):
    policy.check_read("config/boards.json")


# EXPECTED: needs approval
def test_write_config_needs_approval(root):
    with pytest.raises(PermissionError):
        policy.check_write("config/boards.json")
    policy.check_write("config/boards.json", approved=True)


# EXPECTED: allowed
def test_write_jobs_allowed(root):
    policy.check_write("jobs/report-2026-11-10.json")


# EXPECTED: allowed
def test_write_state_allowed(root):
    policy.check_write("state/atlassp.json")


# EXPECTED: needs approval
def test_delete_in_state_needs_approval(root):
    with pytest.raises(PermissionError):
        policy.check_delete("state/atlassp.json")
    policy.check_delete("state/atlassp.json", approved=True)


# ================================================================== HTTP methods

# EXPECTED: blocked
def test_post_blocked():
    with pytest.raises(PermissionError):
        policy.check_method("POST")


# EXPECTED: allowed
def test_get_allowed():
    policy.check_method("GET")

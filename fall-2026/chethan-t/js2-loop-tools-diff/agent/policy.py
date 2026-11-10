"""Permission policy — INTERFACE STUB ONLY. No implementation yet (tests come first).

Contract: ../GATE.md section 5. The tests in ../tests/test_policy.py define the expected
behaviour. Every check returns None when allowed and raises PermissionError when blocked
(or when approval is required and not given).

Relative paths are resolved against ROOT (the folder holding config/, state/, jobs/).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check_host(url):
    """HTTPS + host in the allow-list (boards-api.greenhouse.io, api.lever.co)."""
    raise NotImplementedError("agent.policy.check_host — not implemented yet")


def check_read(path):
    """Read allowed only inside config/, state/, jobs/ (after resolving .. and symlinks)."""
    raise NotImplementedError("agent.policy.check_read — not implemented yet")


def check_write(path, approved=False):
    """Write: jobs/ and state/ allowed; config/ only with approved=True; elsewhere blocked."""
    raise NotImplementedError("agent.policy.check_write — not implemented yet")


def check_delete(path, approved=False):
    """Delete in state/ only with approved=True (GATE.md section 5)."""
    raise NotImplementedError("agent.policy.check_delete — not implemented yet")


def check_method(method):
    """Only GET is allowed."""
    raise NotImplementedError("agent.policy.check_method — not implemented yet")

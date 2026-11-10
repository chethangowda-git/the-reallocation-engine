"""Permission policy. Contract: ../GATE.md section 5. Tests: ../tests/test_policy.py.

Every check returns None when allowed and raises PermissionError when blocked
(or when approval is required and not given). The policy is enforced here, in
code — not in a prompt.

Relative paths are resolved against ROOT (the folder holding config/, state/, jobs/).
Paths are resolved with os.path.realpath BEFORE any check, so `..` escapes and
symlinks pointing outside are caught, and the allowed folder is compared as a
whole path component, so look-alikes such as `jobs-evil/` never match `jobs`.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent

# GATE.md section 5 — hosts (allow-list). Every other host is blocked.
ALLOWED_HOSTS = frozenset({"boards-api.greenhouse.io", "api.lever.co"})

# GATE.md section 5 — the agent only reads with GET.
ALLOWED_METHODS = frozenset({"GET"})

# GATE.md section 5 — folders.
READ_FOLDERS = frozenset({"config", "state", "jobs"})
WRITE_FOLDERS = frozenset({"state", "jobs"})            # write freely
WRITE_WITH_APPROVAL = frozenset({"config"})             # write only with approval
DELETE_WITH_APPROVAL = frozenset({"config", "state", "jobs"})  # every delete needs approval


# ------------------------------------------------------------------ hosts
def check_host(url):
    """HTTPS + host in the allow-list (boards-api.greenhouse.io, api.lever.co)."""
    if not isinstance(url, str):
        raise PermissionError(f"blocked: URL must be a string, got {type(url).__name__}")
    try:
        parts = urlsplit(url)
        port = parts.port  # raises ValueError on a malformed port
    except ValueError as e:
        raise PermissionError(f"blocked: malformed URL {url!r} ({e})") from None
    if parts.scheme != "https":
        raise PermissionError(f"blocked: URL must use https, got {parts.scheme or 'no scheme'!r}: {url}")
    if parts.username is not None or parts.password is not None:
        raise PermissionError(f"blocked: credentials in URL are never allowed: {url}")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise PermissionError(f"blocked: host {host!r} not in allow-list {sorted(ALLOWED_HOSTS)}")
    if port not in (None, 443):
        raise PermissionError(f"blocked: non-standard port {port} for {host}")


# ------------------------------------------------------------------ methods
def check_method(method):
    """Only GET is allowed."""
    if not isinstance(method, str) or method.strip().upper() not in ALLOWED_METHODS:
        raise PermissionError(f"blocked: HTTP method {method!r} — the agent only reads with GET")


# ------------------------------------------------------------------ paths
def _top_folder(path):
    """Resolve `path` (realpath: follows .. and symlinks) and return the first path
    component below ROOT. Raises PermissionError if it resolves outside ROOT or to ROOT itself."""
    root = os.path.realpath(ROOT)
    raw = os.fspath(path)
    full = raw if os.path.isabs(raw) else os.path.join(root, raw)
    resolved = os.path.realpath(full)
    if os.path.commonpath([root, resolved]) != root:
        raise PermissionError(f"blocked: {raw!r} resolves outside the agent root ({resolved})")
    rel = os.path.relpath(resolved, root)
    if rel == os.curdir:
        raise PermissionError(f"blocked: {raw!r} is the agent root itself, not an allowed folder")
    return rel.split(os.sep)[0], resolved


def check_read(path):
    """Read allowed only inside config/, state/, jobs/ (after resolving .. and symlinks)."""
    folder, resolved = _top_folder(path)
    if folder not in READ_FOLDERS:
        raise PermissionError(f"blocked: read of {resolved} — {folder!r} is not one of {sorted(READ_FOLDERS)}")


def check_write(path, approved=False):
    """Write: jobs/ and state/ allowed; config/ only with approved=True; elsewhere blocked."""
    folder, resolved = _top_folder(path)
    if folder in WRITE_FOLDERS:
        return
    if folder in WRITE_WITH_APPROVAL:
        if approved is True:
            return
        raise PermissionError(f"needs approval: write to {resolved} — {folder}/ changes need Chethan's approval")
    raise PermissionError(f"blocked: write to {resolved} — {folder!r} is not a writable folder")


def check_delete(path, approved=False):
    """Delete in state/ only with approved=True (GATE.md section 5).

    GATE.md names deletion only for state/; this policy is stricter and requires
    approval for any delete inside the allowed folders, and blocks it everywhere else.
    """
    folder, resolved = _top_folder(path)
    if folder not in DELETE_WITH_APPROVAL:
        raise PermissionError(f"blocked: delete of {resolved} — {folder!r} is outside the allowed folders")
    if approved is not True:
        raise PermissionError(f"needs approval: delete of {resolved} needs Chethan's approval")

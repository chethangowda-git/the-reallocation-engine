"""Real HTTP fetcher. Contract: ../GATE.md sections 4-5. Tests: ../tests/test_fetch.py.

http_fetch(url, *, timeout, opener=None) -> (status_code: int, body)
  - calls policy.check_host(url) and policy.check_method("GET") itself, before any I/O
  - sends one GET; never follows redirects: a 3xx comes back as (3xx, body)
  - 2xx and HTTP errors (4xx/5xx) both return (status_code, body):
      body = parsed JSON, or None for an empty body
  - a 2xx whose body is not valid JSON raises ValueError
  - a timeout (while connecting or reading) raises TimeoutError
  - other transport errors raise OSError (not TimeoutError, so the loop won't retry them)
  - `timeout` is passed straight to opener.open(request, timeout=timeout)
  - `opener` is injectable for tests; default is build_opener() (urllib, NoRedirect)

Ideas reused from greenhouse_watch.py's fetch_board (that file is not modified):
a NoRedirect handler so a redirect can never leave the allow-list, and a fixed User-Agent.
"""

import json
import urllib.error
import urllib.request

from . import policy

USER_AGENT = "reallocation-engine js2-agent (read-only, GET)"
MAX_BYTES = 10 * 1024 * 1024  # a job board response larger than 10 MB is treated as broken


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect: redirect_request returns None, so urllib raises
    HTTPError with the 3xx status instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_opener():
    """urllib opener whose redirect handler is NoRedirect (replaces the default one)."""
    return urllib.request.build_opener(NoRedirect)


def http_fetch(url, *, timeout, opener=None):
    # GATE.md section 5: the fetcher enforces policy itself too (defence in depth —
    # the loop checks first, but this function must be safe to call on its own).
    policy.check_host(url)
    policy.check_method("GET")

    opener = opener or build_opener()
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = resp.getcode()
            raw = _read_capped(resp)
    except urllib.error.HTTPError as e:
        # 3xx (refused redirect), 4xx, 5xx: return the status so the loop applies GATE.md section 4.
        try:
            body = _parse(_read_capped(e))
        except ValueError:
            body = None  # an error page that is not JSON carries no usable body
        finally:
            e.close()
        return e.code, body
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):  # socket.timeout is TimeoutError on 3.10+
            raise TimeoutError(f"timed out after {timeout}s: {url}") from e
        raise  # DNS failure, refused connection, TLS error: an OSError, never retried
    return status, _parse(raw)


def _read_capped(resp):
    raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"response larger than {MAX_BYTES} bytes")
    return raw


def _parse(raw):
    """JSON body -> object; empty body -> None; anything else -> ValueError."""
    text = raw.decode("utf-8")  # UnicodeDecodeError is a ValueError
    if not text.strip():
        return None
    return json.loads(text)  # JSONDecodeError is a ValueError

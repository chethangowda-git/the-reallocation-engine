"""Real HTTP fetcher — INTERFACE STUB ONLY. No implementation yet (tests come first).

Contract: ../GATE.md sections 4-5. Tests: ../tests/test_fetch.py.

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
"""

import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect: redirect_request returns None, so urllib raises
    HTTPError with the 3xx status instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise NotImplementedError("agent.fetch.NoRedirect.redirect_request — not implemented yet")


def build_opener():
    raise NotImplementedError("agent.fetch.build_opener — not implemented yet")


def http_fetch(url, *, timeout, opener=None):
    raise NotImplementedError("agent.fetch.http_fetch — not implemented yet")

"""Real-fetcher tests — written BEFORE the implementation. Contract: ../GATE.md sections 4-5.

Offline: every test injects a FakeOpener in place of urllib's opener, and the
autouse no_network fixture (conftest.py) fails any real socket use.
"""

import io
import json
import urllib.error
import urllib.request
from email.message import Message

import pytest

from agent import fetch, policy

GH_URL = "https://boards-api.greenhouse.io/v1/boards/atlassp/jobs"
LEVER_URL = "https://api.lever.co/v0/postings/analyticpartners?mode=json"


# ------------------------------------------------------------------ fakes
class FakeResponse:
    def __init__(self, status, body=b"", read_error=None):
        self.status = status
        self._body = body
        self._read_error = read_error
        self.headers = Message()

    def getcode(self):
        return self.status

    def read(self, *args):
        if self._read_error:
            raise self._read_error
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Stands in for urllib's opener. `result` is a FakeResponse or an exception to raise."""

    def __init__(self, result):
        self.result = result
        self.calls = []  # (request, timeout)

    def open(self, req, timeout=None):
        self.calls.append((req, timeout))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def http_error(code, body=b""):
    return urllib.error.HTTPError(GH_URL, code, f"HTTP {code}", Message(), io.BytesIO(body))


def ok_json(obj, status=200):
    return FakeResponse(status, json.dumps(obj).encode("utf-8"))


# ------------------------------------------------------------------ success / body handling

def test_200_json_body_is_parsed():
    opener = FakeOpener(ok_json({"jobs": [{"id": 1, "title": "Software Engineer"}]}))
    assert fetch.http_fetch(GH_URL, timeout=10, opener=opener) == (
        200, {"jobs": [{"id": 1, "title": "Software Engineer"}]})


def test_lever_list_body_is_parsed():
    opener = FakeOpener(ok_json([{"id": "a1", "text": "Software Engineer"}]))
    assert fetch.http_fetch(LEVER_URL, timeout=10, opener=opener) == (
        200, [{"id": "a1", "text": "Software Engineer"}])


def test_200_empty_body_is_none():
    """GATE 4: an empty response is returned as None so the loop can flag it, never as []."""
    assert fetch.http_fetch(GH_URL, timeout=10, opener=FakeOpener(FakeResponse(200, b""))) == (200, None)


def test_200_invalid_json_raises_value_error():
    with pytest.raises(ValueError):
        fetch.http_fetch(GH_URL, timeout=10, opener=FakeOpener(FakeResponse(200, b"<html>oops</html>")))


# ------------------------------------------------------------------ HTTP errors returned, not raised

def test_404_is_returned_with_its_body():
    opener = FakeOpener(http_error(404, b'{"status":404,"error":"Job not found"}'))
    assert fetch.http_fetch(GH_URL, timeout=10, opener=opener) == (
        404, {"status": 404, "error": "Job not found"})


@pytest.mark.parametrize("code", [500, 503])
def test_5xx_is_returned_so_the_loop_can_retry(code):
    assert fetch.http_fetch(GH_URL, timeout=10, opener=FakeOpener(http_error(code, b"Service Unavailable"))) == (
        code, None)


# ------------------------------------------------------------------ redirects (GATE 5: never leave the allow-list)

@pytest.mark.parametrize("code", [301, 302, 307, 308])
def test_3xx_is_returned_as_is_and_never_followed(code):
    opener = FakeOpener(http_error(code))
    assert fetch.http_fetch(GH_URL, timeout=10, opener=opener) == (code, None)
    assert len(opener.calls) == 1  # exactly one request — the redirect target was never requested


def test_no_redirect_handler_refuses_to_follow():
    req = urllib.request.Request(GH_URL)
    assert fetch.NoRedirect().redirect_request(req, None, 302, "Found", Message(), "https://evil.com/") is None


def test_default_opener_uses_no_redirect_handler():
    opener = fetch.build_opener()
    assert any(isinstance(h, fetch.NoRedirect) for h in opener.handlers)


# ------------------------------------------------------------------ timeouts (GATE 2 + 4)

def test_timeout_is_passed_through_to_the_opener():
    opener = FakeOpener(ok_json({"jobs": []}))
    fetch.http_fetch(GH_URL, timeout=10, opener=opener)
    assert opener.calls[0][1] == 10


@pytest.mark.parametrize("result", [
    TimeoutError("timed out"),                                  # timeout while connecting
    urllib.error.URLError(TimeoutError("timed out")),           # urllib wraps connect timeouts
    FakeResponse(200, read_error=TimeoutError("read timed out")),  # timeout while reading the body
], ids=["connect-timeout", "urlerror-wrapped-timeout", "read-timeout"])
def test_timeouts_raise_timeout_error(result):
    with pytest.raises(TimeoutError):
        fetch.http_fetch(GH_URL, timeout=10, opener=FakeOpener(result))


def test_other_transport_error_is_not_a_timeout():
    """A DNS failure must not look like a timeout, or the loop would retry it."""
    with pytest.raises(OSError) as info:
        fetch.http_fetch(GH_URL, timeout=10,
                         opener=FakeOpener(urllib.error.URLError("nodename nor servname provided")))
    assert not isinstance(info.value, TimeoutError)


# ------------------------------------------------------------------ policy inside the fetcher (GATE 5)

@pytest.mark.parametrize("url", [
    "https://evil.com/v1/boards/atlassp/jobs",
    "http://boards-api.greenhouse.io/v1/boards/atlassp/jobs",
    "https://api.ashbyhq.com/posting-api/job-board/acme",
], ids=["evil-host", "plain-http", "ashby-not-allowed"])
def test_fetcher_checks_host_itself_and_never_opens(url):
    opener = FakeOpener(ok_json({"jobs": []}))
    with pytest.raises(PermissionError):
        fetch.http_fetch(url, timeout=10, opener=opener)
    assert opener.calls == []


def test_fetcher_checks_method_itself(monkeypatch):
    def refuse(method):
        raise PermissionError(f"blocked {method}")
    monkeypatch.setattr(policy, "check_method", refuse)
    opener = FakeOpener(ok_json({"jobs": []}))
    with pytest.raises(PermissionError):
        fetch.http_fetch(GH_URL, timeout=10, opener=opener)
    assert opener.calls == []


def test_request_is_a_plain_get_with_no_body():
    opener = FakeOpener(ok_json({"jobs": []}))
    fetch.http_fetch(GH_URL, timeout=10, opener=opener)
    req = opener.calls[0][0]
    assert req.full_url == GH_URL
    assert req.get_method() == "GET"
    assert req.data is None
    assert req.get_header("User-agent")

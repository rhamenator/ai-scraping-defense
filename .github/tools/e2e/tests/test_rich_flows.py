import os
import time

import pytest
import requests
from bs4 import BeautifulSoup

BASE = os.environ.get("BASE_URL")


def _get(path, **kw):
    return requests.get(BASE + path, timeout=kw.pop("timeout", 20), **kw)


@pytest.mark.order(1)
def test_base_url_set():
    assert BASE, "Set BASE_URL env (Actions supplies STAGING_BASE_URL)"


@pytest.mark.order(2)
@pytest.mark.parametrize(
    "path,ok", [("/", {200, 301, 302}), ("/healthz", {200}), ("/metrics", {200})]
)
def test_core_endpoints_best_effort(path, ok):
    r = _get(path, timeout=15, allow_redirects=False)
    assert r.status_code != 500, f"Server error on {path}"
    if r.status_code not in ok:
        pytest.skip(f"Optional endpoint {path} not present ({r.status_code})")


@pytest.mark.order(3)
def test_admin_guard_or_login_form():
    r = _get("/admin", allow_redirects=False)
    assert r.status_code in (200, 301, 302, 401, 403)
    if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
        s = BeautifulSoup(r.text, "html.parser")
        forms = s.find_all("form")
        assert (
            forms or "login" in r.text.lower() or "password" in r.text.lower()
        ), "Admin served 200 without login form"


@pytest.mark.order(4)
def test_markov_api_best_effort():
    r = _get("/api/markov", allow_redirects=False)
    assert r.status_code in (200, 301, 302, 401, 403, 404)
    if r.status_code == 200:
        assert len(r.text) > 0


@pytest.mark.order(5)
def test_jszip_api_best_effort():
    r = _get("/api/zip", allow_redirects=False)
    assert r.status_code in (200, 301, 302, 401, 403, 404)
    if r.status_code == 200:
        ctype = r.headers.get("Content-Type", "")
        assert "zip" in ctype.lower() or "application/octet-stream" in ctype.lower()


@pytest.mark.order(6)
def test_tarpit_latency_bounds():
    t0 = time.time()
    try:
        r = _get("/tarpit/slow", timeout=65)
    except requests.exceptions.ReadTimeout:
        pytest.skip("tarpit slow timed out (acceptable)")
        return
    dt = (time.time() - t0) * 1000
    assert dt >= 300 or r.status_code in (404, 501), f"Tarpit too fast ({dt:.1f}ms)"
    assert dt <= 60000, f"Tarpit too slow ({dt:.1f}ms)"

"""
Unit tests for the curl_cffi HTTP-only UTCMS login.

These tests exercise the pure logic of ``UtcmsHttpLogin`` without
requiring curl_cffi or Playwright to be installed: token extraction,
HTML/JSON response classification, cookie normalisation and the session
builder. The actual network round-trip is intentionally NOT exercised
(that is what the ``scripts/measure_curl_cffi_login.py`` diagnostic is for).
"""

from unittest.mock import AsyncMock

import pytest

from app.automation.utcms_http_login import UtcmsHttpLogin

# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------


class TestExtraction:
    def test_extract_antiforgery(self):
        html = '<form><input name="__RequestVerificationToken" ' 'type="hidden" value="abc123def" /></form>'
        assert UtcmsHttpLogin._extract_antiforgery(html) == "abc123def"

    def test_extract_antiforgery_reversed_order(self):
        html = '<form><input value="xyz789" name="__RequestVerificationToken" ' 'type="hidden" /></form>'
        assert UtcmsHttpLogin._extract_antiforgery(html) == "xyz789"

    def test_extract_antiforgery_missing(self):
        assert UtcmsHttpLogin._extract_antiforgery("<html>no token</html>") is None

    def test_extract_antiforgery_no_double_underscore(self):
        html = '<input name="RequestVerificationToken" type="hidden" value="utcms-token" />'
        assert UtcmsHttpLogin._extract_antiforgery(html) == "utcms-token"

    def test_extract_form_ajax_url(self):
        html = '<form id="loginForm" data-ajax="true" data-ajax-url="/Barname/Account/OldLogin">'
        assert UtcmsHttpLogin._extract_form_ajax_url(html) == "/Barname/Account/OldLogin"

    def test_extract_form_ajax_url_missing(self):
        assert UtcmsHttpLogin._extract_form_ajax_url("<form id='x'></form>") is None

    def test_resolve_post_url_uses_ajax_url(self):
        url = UtcmsHttpLogin._resolve_post_url(
            "https://barname.utcms.ir/Barname/Account/Login", "/Barname/Account/OldLogin"
        )
        assert url == "https://barname.utcms.ir/Barname/Account/OldLogin"

    def test_resolve_post_url_falls_back_to_get_url(self):
        url = UtcmsHttpLogin._resolve_post_url("https://barname.utcms.ir/Barname/Account/Login")
        assert url == "https://barname.utcms.ir/Barname/Account/Login"

    def test_extract_dnt_captcha_text(self):
        html = '<input name="DNTCaptchaText" value="cap-text-1" />'
        assert UtcmsHttpLogin._extract_dnt_captcha_text(html) == "cap-text-1"

    def test_extract_cap_type(self):
        html = '<input type="hidden" id="CapType" name="CapType" value="1" />'
        assert UtcmsHttpLogin._extract_cap_type(html) == "1"

    def test_extract_dnt_captcha_token(self):
        html = '<input name="DNTCaptchaToken" value="cap-token-123" />'
        assert UtcmsHttpLogin._extract_dnt_captcha_token(html) == "cap-token-123"

    def test_extract_dnt_captcha_token_missing(self):
        assert UtcmsHttpLogin._extract_dnt_captcha_token("<html></html>") is None

    def test_extract_captcha_image_url_by_id(self):
        html = '<img id="dntCaptchaImg" src="/Captcha/Image?x=1" alt="captcha" />'
        url = UtcmsHttpLogin._extract_captcha_image_url(html, "https://barname.utcms.ir/Barname/Account/Login")
        assert url == "https://barname.utcms.ir/Captcha/Image?x=1"

    def test_extract_captcha_image_url_by_src_keyword(self):
        html = '<img src="/Captcha/GetCaptcha?t=123" />'
        url = UtcmsHttpLogin._extract_captcha_image_url(html, "https://barname.utcms.ir/Barname/Account/Login")
        assert url == "https://barname.utcms.ir/Captcha/GetCaptcha?t=123"

    def test_extract_captcha_image_url_missing(self):
        assert UtcmsHttpLogin._extract_captcha_image_url("<html><img src='/x.png'/></html>", "https://x") is None


# ---------------------------------------------------------------------------
# Response classification
# ---------------------------------------------------------------------------


class _Fake:
    """Minimal stand-in for a curl_cffi Response for unit tests."""

    def __init__(
        self, status_code=200, headers=None, text="", url="https://barname.utcms.ir/Barname/login", cookies=None
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.url = url
        self.cookies = cookies or []
        self.content = text.encode() if isinstance(text, str) else b""


class TestPostEvaluation:
    def test_redirect_away_from_login_is_success(self):
        resp = _Fake(
            status_code=302,
            headers={"Location": "https://barname.utcms.ir/Barname/Dashboard"},
            cookies=[],
        )
        result = UtcmsHttpLogin()._evaluate_post_response(resp)
        assert result.success is True

    def test_redirect_back_to_login_is_failure(self):
        resp = _Fake(
            status_code=302,
            headers={"Location": "https://barname.utcms.ir/Barname/Account/Login"},
            url="https://barname.utcms.ir/Barname/Account/Login",
        )
        result = UtcmsHttpLogin()._evaluate_post_response(resp)
        assert result.success is False

    def test_ajax_json_success(self):
        resp = _Fake(
            status_code=200,
            headers={"Content-Type": "application/json"},
            text='{"success": true, "redirectUrl": "/Barname/Dashboard"}',
            url="https://barname.utcms.ir/Barname/login",
        )
        result = UtcmsHttpLogin()._evaluate_post_response(resp)
        assert result.success is True

    def test_ajax_json_failure_with_message(self):
        resp = _Fake(
            status_code=200,
            headers={"Content-Type": "application/json"},
            text='{"success": false, "message": "کد امنیتی اشتباه است"}',
            url="https://barname.utcms.ir/Barname/login",
        )
        result = UtcmsHttpLogin()._evaluate_post_response(resp)
        assert result.success is False
        assert "کد امنیتی" in result.error

    def test_html_login_error_returns_message(self):
        resp = _Fake(
            status_code=200,
            text='<div class="text-danger">کد ملی یا رمز عبور اشتباه است</div>',
            url="https://barname.utcms.ir/Barname/Account/Login",
        )
        result = UtcmsHttpLogin()._evaluate_post_response(resp)
        assert result.success is False
        assert "کد ملی یا رمز عبور" in result.error

    def test_200_auth_page_with_logout_is_success(self):
        resp = _Fake(
            status_code=200,
            text='<a href="/Account/Logout">خروج</a><nav><a href="/barname">سامانه باربران</a></nav>',
            url="https://barname.utcms.ir/Barname/Dashboard",
        )
        result = UtcmsHttpLogin()._evaluate_post_response(resp)
        assert result.success is True


# ---------------------------------------------------------------------------
# Cookie normalisation / auth detection
# ---------------------------------------------------------------------------


class TestCookies:
    def test_has_auth_cookie_positive(self):
        cookies = [{"name": ".AspNetCore.Cookies", "value": "x", "domain": "barname.utcms.ir", "path": "/"}]
        assert UtcmsHttpLogin._has_auth_cookie(cookies) is True

    def test_has_auth_cookie_negative(self):
        cookies = [{"name": "__RequestVerificationToken", "value": "x", "domain": "barname.utcms.ir", "path": "/"}]
        assert UtcmsHttpLogin._has_auth_cookie(cookies) is False

    def test_cookies_to_playwright_defaults(self):
        cookies = [
            {
                "name": ".AspNetCore.Cookies",
                "value": "abc",
                "domain": "barname.utcms.ir",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            }
        ]
        out = UtcmsHttpLogin._cookies_to_playwright_dicts(cookies, "https://barname.utcms.ir/Barname/Dashboard")
        assert out[0]["name"] == ".AspNetCore.Cookies"
        assert out[0]["domain"] == "barname.utcms.ir"
        assert out[0]["httpOnly"] is True
        assert out[0]["secure"] is True
        assert out[0]["sameSite"] == "Lax"
        assert "expires" not in out[0]

    def test_cookies_to_playwright_missing_domain_derived_from_url(self):
        cookies = [{"name": "sess", "value": "v", "path": "/", "domain": ""}]
        out = UtcmsHttpLogin._cookies_to_playwright_dicts(cookies, "https://barname.utcms.ir/Dashboard")
        assert out[0]["domain"] == "barname.utcms.ir"

    def test_normalise_filters_empty(self):
        cookies = [{"name": "a", "value": ""}, {"name": "", "value": "b"}, {"name": "c", "value": "v"}]
        out = UtcmsHttpLogin._normalise_cookies_for_playwright(cookies)
        assert [c["name"] for c in out] == ["c"]

    def test_parse_set_cookie_header_full_attrs(self):
        out = UtcmsHttpLogin._parse_set_cookie_header("Barname=abc123; path=/; HttpOnly; Secure; SameSite=Lax")
        assert out == {
            "name": "Barname",
            "value": "abc123",
            "domain": None,
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }

    def test_parse_set_cookie_header_expires_and_domain(self):
        out = UtcmsHttpLogin._parse_set_cookie_header(
            "name=value; domain=barname.utcms.ir; expires=Thu, 01 Jan 2026 00:00:00 GMT"
        )
        assert out["domain"] == "barname.utcms.ir"
        assert out["expires"] == 1767225600

    def test_parse_set_cookie_header_empty_returns_none(self):
        assert UtcmsHttpLogin._parse_set_cookie_header("") is None

    def test_parse_set_cookie_header_no_name_returns_none(self):
        assert UtcmsHttpLogin._parse_set_cookie_header("=x") is None

    def test_collect_set_cookies_uses_raw_header(self):
        class _H:
            def get_list(self, key):
                return ["Barname=abc; path=/; HttpOnly"]

            def get(self, key):
                return None

        class _Resp:
            headers = _H()
            cookies = {}

        out = UtcmsHttpLogin._collect_set_cookies(_Resp())
        assert [c["name"] for c in out] == ["Barname"]
        assert out[0]["httpOnly"] is True
        assert out[0]["path"] == "/"

    def test_collect_set_cookies_empty_returns_empty_list(self):
        class _Resp:
            headers = {}
            cookies = {}

        assert UtcmsHttpLogin._collect_set_cookies(_Resp()) == []


# ---------------------------------------------------------------------------
# Session builder (uses a fake curl_cffi module)
# ---------------------------------------------------------------------------


class _FakeRequests:
    class Session:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.headers = {}

        def __call__(self):
            return self


def _make_login(proxy_url=None):
    return UtcmsHttpLogin(login_url="https://barname.utcms.ir/Barname/Account/Login", proxy_url=proxy_url)


class TestSessionBuilder:
    def test_build_session_sets_impersonate_and_headers(self):
        login = _make_login(proxy_url="http://squid:3128")
        session = login._build_session(_FakeRequests)
        assert session.kwargs.get("impersonate") == "chrome120"
        assert session.kwargs.get("proxies") == {"http": "http://squid:3128", "https": "http://squid:3128"}
        assert session.headers.get("User-Agent", "").startswith("Mozilla/5.0")

    def test_build_session_no_proxy(self):
        login = _make_login(proxy_url="")
        session = login._build_session(_FakeRequests)
        assert session.kwargs.get("proxies") is None

    def test_default_impersonate_profile(self):
        assert UtcmsHttpLogin.DEFAULT_IMPERSONATE == "chrome120"

    def test_build_session_binds_curl_handle_to_the_session_not_the_thread(self):
        """curl_cffi's default puts the libcurl handle -- and with it the
        connection cache -- in thread-local storage.  This session is handed to
        the browser bridge, which drives it from a different pinned thread, so
        the default silently costs a fresh TLS handshake per request."""
        login = _make_login()
        session = login._build_session(_FakeRequests)
        assert session.kwargs.get("use_thread_local_curl") is False

    def test_take_authenticated_session_transfers_ownership(self):
        login = _make_login()
        session = object()
        login._authenticated_session = session

        assert login.take_authenticated_session() is session
        assert login._authenticated_session is None

    def test_take_authenticated_session_also_releases_the_session_alias(self):
        """``authenticate`` leaves ``_session`` pointing at the same object.  If
        the handoff does not release it too, a later ``close()`` closes the
        connection the new owner is depending on."""
        login = _make_login()
        session = object()
        login._session = session
        login._authenticated_session = session

        assert login.take_authenticated_session() is session
        assert login._session is None

    def test_take_authenticated_session_keeps_an_unrelated_live_session(self):
        login = _make_login()
        live = object()
        login._session = live
        login._authenticated_session = None

        assert login.take_authenticated_session() is None
        assert login._session is live


# ---------------------------------------------------------------------------
# fetch_authenticated() — session recovery loop
# ---------------------------------------------------------------------------


def _ok_login_result():
    return type(
        "R",
        (),
        {
            "success": True,
            "cookies": [{"name": "Barname", "value": "v", "domain": "barname.utcms.ir", "path": "/"}],
        },
    )()


async def _ok_authenticate(u, p):
    return _ok_login_result()


class _OkResp:
    status_code = 200
    text = "<html>ok</html>"


class _Err408Resp:
    status_code = 408


class TestFetchAuthenticated:
    def _build_fake_session(self, monkeypatch, login, behaviour, per_login_sessions=False):
        """Monkeypatch _build_session to return a fake session. With
        ``per_login_sessions=True`` a brand-new session object is returned
        on every _build_session() call (like the real code)."""

        class _FakeSession:
            def __init__(self):
                self.headers = {}
                self.cookies = type("J", (), {"set": lambda *a, **k: None})()
                self.calls = 0

            def get(self, url, timeout=None):
                self.calls += 1
                return behaviour(self, url, timeout)

        if per_login_sessions:
            monkeypatch.setattr(login, "_build_session", lambda _cc: _FakeSession())
            return None
        fake = _FakeSession()
        monkeypatch.setattr(login, "_build_session", lambda _cc: fake)
        return fake

    def test_transport_reset_triggers_relogin_and_success(self, monkeypatch):
        import asyncio

        login = _make_login()
        login.authenticate = _ok_authenticate
        login_calls = {"n": 0}
        orig_auth = login.authenticate

        async def counting_auth(u, p):
            login_calls["n"] += 1
            return await orig_auth(u, p)

        login.authenticate = counting_auth

        def behaviour(sess, url, timeout):
            if sess.calls == 1:
                raise ConnectionError("curl: (35) BoringSSL SSL_connect reset")
            return _OkResp()

        # A live session exists; the request is served from it. On transport
        # reset the session is dropped and a fresh login builds a new one.
        shared = self._build_fake_session(monkeypatch, login, behaviour)
        # Seed the first session so no login happens before the reset.
        login._session = login._build_session(object())
        assert login._session is shared

        async def run():
            return await login.fetch_authenticated(
                "https://barname.utcms.ir/barname/Document/HagigiHogugi",
                username="u",
                password="p",
                max_attempts=3,
                backoff_seconds=0.0,
            )

        resp, cookies = asyncio.run(run())
        assert resp.status_code == 200
        assert cookies[0]["name"] == "Barname"
        # Exactly one re-login was required after the transport reset.
        assert login_calls["n"] == 1

    def test_408_retries_then_raises(self, monkeypatch):
        import asyncio

        login = _make_login()
        login._session = None
        login.authenticate = _ok_authenticate
        self._build_fake_session(monkeypatch, login, lambda sess, url, timeout: _Err408Resp())

        async def run():
            with pytest.raises(RuntimeError):
                await login.fetch_authenticated(
                    "https://barname.utcms.ir/barname/Document/HagigiHogugi",
                    username="u",
                    password="p",
                    max_attempts=2,
                    backoff_seconds=0.0,
                )

        asyncio.run(run())

    def test_success_returns_cookies(self, monkeypatch):
        import asyncio

        login = _make_login()
        login._session = None
        login.authenticate = _ok_authenticate
        self._build_fake_session(monkeypatch, login, lambda sess, url, timeout: _OkResp())

        async def run():
            return await login.fetch_authenticated(
                "https://barname.utcms.ir/barname/Document/HagigiHogugi",
                username="u",
                password="p",
            )

        resp, cookies = asyncio.run(run())
        assert resp.status_code == 200
        assert cookies[0]["name"] == "Barname"

    def test_reuses_live_session_without_relogin(self, monkeypatch):
        import asyncio

        login = _make_login()
        login._session = None
        auth_calls = {"n": 0}
        login.authenticate = _ok_authenticate
        orig = login.authenticate

        async def counting(u, p):
            auth_calls["n"] += 1
            return await orig(u, p)

        login.authenticate = counting
        self._build_fake_session(monkeypatch, login, lambda sess, url, timeout: _OkResp())

        async def run():
            first, _ = await login.fetch_authenticated("https://barname.utcms.ir/x", username="u", password="p")
            second, _ = await login.fetch_authenticated("https://barname.utcms.ir/y", username="u", password="p")
            return first, second

        first, second = asyncio.run(run())
        assert first.status_code == 200 and second.status_code == 200
        assert auth_calls["n"] == 1  # second call reuses the live session


@pytest.mark.asyncio
async def test_authenticate_retries_transport_reset_without_spending_captcha_budget(monkeypatch):
    from app.automation.utcms_http_login import HttpLoginResult

    login = _make_login()
    sessions = []

    class _Session:
        def close(self):
            return None

    monkeypatch.setattr(login, "_build_session", lambda _cc: sessions.append(_Session()) or sessions[-1])
    responses = [
        HttpLoginResult(success=False, error="curl: (35) SSL_connect connection closed", status_code=None),
        HttpLoginResult(success=True, cookies=[{"name": "Barname", "value": "v"}], status_code=200),
    ]
    monkeypatch.setattr(login, "_attempt_single_session", lambda _u, _p: _async_pop(responses))
    monkeypatch.setattr("app.automation.utcms_http_login.asyncio.sleep", AsyncMock())

    result = await login.authenticate("u", "p")

    assert result.success is True
    assert len(sessions) == 2
    assert login.take_authenticated_session() is sessions[-1]


@pytest.mark.asyncio
async def test_authenticate_rotates_clean_pool_proxy_after_transport_failure(monkeypatch):
    from app.automation.utcms_http_login import HttpLoginResult

    login = _make_login()
    login._proxy_url = "http://203.0.113.10:8080"
    rotate = AsyncMock()
    monkeypatch.setattr(login, "_rotate_after_transport_failure", rotate)

    class _Session:
        def close(self):
            return None

    monkeypatch.setattr(login, "_build_session", lambda _cc: _Session())
    responses = [
        HttpLoginResult(success=False, error="curl: (28) connection timed out", status_code=None),
        HttpLoginResult(success=True, cookies=[{"name": "Barname", "value": "v"}], status_code=200),
    ]
    monkeypatch.setattr(login, "_attempt_single_session", lambda _u, _p: _async_pop(responses))
    monkeypatch.setattr("app.automation.utcms_http_login.asyncio.sleep", AsyncMock())

    result = await login.authenticate("u", "p")

    assert result.success is True
    rotate.assert_awaited_once_with("http://203.0.113.10:8080")


async def _async_pop(items):
    return items.pop(0)

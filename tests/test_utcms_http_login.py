"""
Unit tests for the curl_cffi HTTP-only UTCMS login.

These tests exercise the pure logic of ``UtcmsHttpLogin`` without
requiring curl_cffi or Playwright to be installed: token extraction,
HTML/JSON response classification, cookie normalisation and the session
builder. The actual network round-trip is intentionally NOT exercised
(that is what the ``scripts/measure_curl_cffi_login.py`` diagnostic is for).
"""


from app.automation.utcms_http_login import UtcmsHttpLogin

# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------


class TestExtraction:
    def test_extract_antiforgery(self):
        html = (
            '<form><input name="__RequestVerificationToken" '
            'type="hidden" value="abc123def" /></form>'
        )
        assert UtcmsHttpLogin._extract_antiforgery(html) == "abc123def"

    def test_extract_antiforgery_reversed_order(self):
        html = (
            '<form><input value="xyz789" name="__RequestVerificationToken" '
            'type="hidden" /></form>'
        )
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

    def __init__(self, status_code=200, headers=None, text="", url="https://barname.utcms.ir/Barname/login", cookies=None):
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
        out = UtcmsHttpLogin._parse_set_cookie_header(
            "Barname=abc123; path=/; HttpOnly; Secure; SameSite=Lax"
        )
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

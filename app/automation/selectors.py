"""
ثابت‌های انتخابگر برای اتوماسیون
"""

class LocationSelectors:
    """الگوهای انتخابگر مکان برای استفاده در LocationSelector"""

    PROVINCE_TEMPLATES = [
        'select[name="{prefix}Province"]',
        'select[name="{prefix}State"]',
        'select[id="{prefix}Province"]',
        'select[name="ddState{prefix}"]',
        'select[id="ddState{prefix}"]',
        '[id="{prefix_lower}_province"]',
        '[name*="province" i][name*="{prefix_lower}" i]',
        '[name*="state" i][name*="{prefix_lower}" i]',
        'select[name*="Ostan"]',
        'select[name*="استان"]'
    ]

    CITY_TEMPLATES = [
        'select[name="{prefix}City"]',
        'select[id="{prefix}City"]',
        'select[name="ddCity{prefix}"]',
        'select[id="ddCity{prefix}"]',
        '[id="{prefix_lower}_city"]',
        '[name*="city" i][name*="{prefix_lower}" i]',
        'select[name*="Shahr"]',
        'select[name*="شهر"]'
    ]

    _DISTRICT_ID = "{prefix_lower}_district"
    DISTRICT_TEMPLATES = [
        'select[name="{prefix}District"]',
        'select[id="{prefix}District"]',
        f"#{_DISTRICT_ID}",
        'select[name*="Mantaghe"]',
        'select[name*="منطقه"]'
    ]

    ADDRESS_TEMPLATES = [
        'textarea[name="{prefix}Address"]',
        'textarea[id="{prefix}Address"]',
        'input[name="{prefix}Address"]',
        'textarea[name="txtAddress{prefix}"]',
        'textarea[id="txtAddress{prefix}"]',
        'input[name="{prefix}PostalCode"]',
        'input[id="{prefix}PostalCode"]',
        '[name*="address" i][name*="{prefix_lower}" i]',
        '[name*="آدرس"]'
    ]

    INPUT_TEMPLATES = [
        'input[name="{prefix}Location"]',
        'input[name="{prefix}Address"]',
        'input[name="AddressSearch{prefix}"]',
        'select[name="AddressSearch{prefix}"]',
        'input[name="txtAddress{prefix}"]',
        'textarea[name="txtAddress{prefix}"]',
        '[id="AddressSearch"]',
        '[id="AddressSearch2"]',
        '[id="txtAddressSource"]',
        '[id="txtAddressDest"]',
        'input[placeholder*="{prefix}" i]',
        '[name*="location" i][name*="{prefix_lower}" i]',
        '.location-search',
        '[class*="location-search"]',
        'input[placeholder*="جستجو"]',
        'input[placeholder*="search"]'
    ]

    SUGGESTION_SELECTORS = [
        '.autocomplete-suggestion:first-child',
        '.pac-item:first-child',
        '[class*="suggestion"]:first-child',
        'li:first-child'
    ]

    MAP_SEARCH_TEMPLATES = [
        '#MapCity',
        '#MapCity2',
        '#AddressSearch',
        '#AddressSearch2',
        'input[name=\"{prefix}Search\"]',
        'select[name="MapCity{prefix}"]',
        'select[id="MapCity{prefix}"]',
        'input[name="AddressSearch{prefix}"]',
        'select[name="AddressSearch{prefix}"]',
        'input[placeholder*="{prefix}" i]',
        '.map-search input',
        '[class*="map-search"] input',
        '[id="map-search"]',
        '[id="MapCity"]',
        '[id="MapCity2"]',
        '[id="AddressSearch"]',
        '[id="AddressSearch2"]',
        'input[placeholder*="جستجو در نقشه"]',
        'input[placeholder*="Search map"]'
    ]


class AuthSelectors:
    """انتخابگرهای مربوط به احراز هویت"""

    LOGIN_PATH_CANDIDATES = (
        "/Barname/Account/Login",
        "/Account/Login",
        "/Barname/Login",
        "/Login",
    )
    USERNAME_SELECTORS = (
        "input[name='NationalCode']",
        "input[id='NationalCode']",
        "input[name*='national' i][type='text']",
        "input[name='Username']",
        "input[name='username']",
        "input[name='UserName']",
        "input[id='Username']",
        "input[id='username']",
        "input[type='text'][name*='user' i]",
        "input[autocomplete='username']",
    )
    PASSWORD_SELECTORS = (
        "input[name='Password']",
        "input[name='password']",
        "input[id='Password']",
        "input[id='password']",
        "input[type='password']",
    )
    CAPTCHA_SELECTORS = (
        "input[name='CapToken']",
        "input[id='CapToken']",
        "input[name='DNTCaptchaInputText']",
        "input[id='DNTCaptchaInputText']",
        "input[name*='captcha' i][type='text']",
        "input[name*='Captcha' i][type='text']",
        "input[name*='SecurityCode' i]",
        "input[id*='captcha' i][type='text']",
    )
    CAPTCHA_IMAGE_SELECTORS = (
        "img[id*='captcha' i]",
        "img[src*='captcha' i]",
        ".captcha img",
        "img.captcha",
        ".dntCaptcha img",
        "#dntCaptchaImg",
        "img[id*='dnt' i][id*='captcha' i]",
    )
    CAPTCHA_REFRESH_SELECTORS = (
        "button[id*='captcha' i][id*='refresh' i]",
        "button[class*='captcha' i][class*='refresh' i]",
        "a[id*='captcha' i][id*='refresh' i]",
        "a[class*='captcha' i][class*='refresh' i]",
        "button[onclick*='captcha' i][onclick*='refresh' i]",
        "a[onclick*='captcha' i][onclick*='refresh' i]",
        "#btnRefreshCaptcha",
        "#refreshCaptcha",
        ".captcha-refresh",
        "#dntCaptchaRefreshButton",
        "a[id*='dnt' i][id*='refresh' i]",
        "button.refresh-captcha",
    )
    SUBMIT_SELECTORS = (
        "button[id='inter']",
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('ورود')",
        "button:has-text('Login')",
        "button:has-text('Sign in')",
    )
    LOGOUT_SELECTORS = (
        "text=خروج",
        "a:has-text('خروج')",
        "a[href*='logout' i]:has-text('خروج')",
        "button:has-text('خروج')",
    )
    AUTHENTICATED_PAGE_MARKERS = (
        "text=اطلاعیه ها",
        "text=سوالات متداول",
        "text=تغییر کلمه عبور",
        "text=بارنامه حقیقی / حقوقی",
        "text=تاریخچه اسناد حمل",
        "text=حمل بارنامه",
        "text=مشاهده سهمیه سوخت",
    )
    WAYBILL_FORM_MARKERS = (
        "input[name='txtSenderFirstName']",
        "input[name='txtReceiverFirstName']",
        "select[name='ddStateSource']",
        "select[name='ddStateDest']",
        "button#btnGoLVL2",
        "input[name='SenderName']",
        "input[name='ReceiverName']",
        "textarea[name='SenderAddress']",
        "textarea[name='ReceiverAddress']",
        "input[name='SenderPhone']",
        "input[name='ReceiverPhone']",
    )
    LOGIN_ERROR_SELECTORS = (
        ".validation-summary-errors li",
        ".validation-summary-errors",
        ".field-validation-error",
        ".alert-danger",
        ".text-danger",
        ".toast-message",
        ".toast-body",
        ".swal2-html-container",
    )
